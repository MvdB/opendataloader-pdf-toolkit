from __future__ import annotations

import asyncio
import os
import shutil
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import Depends, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.templating import Jinja2Templates

from ..convert import ConvertOptions, convert
from .auth import require_auth
from .jobs import JobRegistry, JobStatus, now_utc

WEB_DIR = Path(__file__).parent
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/data/out"))
INPUT_DIR = Path(os.environ.get("INPUT_DIR", "/data/in"))
DEFAULT_PROFILE = os.environ.get("PROFILE", "rag")
DEFAULT_SANITIZE = os.environ.get("SANITIZE", "true").lower() == "true"
HYBRID_URL = os.environ.get("HYBRID_URL") or None
HYBRID_FULL = os.environ.get("HYBRID_FULL", "false").lower() == "true"

registry = JobRegistry()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="pdf-toolkit", lifespan=lifespan)
templates = Jinja2Templates(directory=WEB_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, _: None = Depends(require_auth)) -> HTMLResponse:
    return templates.TemplateResponse(
        "index.html",
        {"request": request, "profile": DEFAULT_PROFILE},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/jobs")
async def create_job(
    profile: str = Form(DEFAULT_PROFILE),
    ocr: bool = Form(False),
    files: list[UploadFile] = File(...),
    _: None = Depends(require_auth),
) -> dict[str, str]:
    if not files:
        raise HTTPException(400, "no files uploaded")
    job = await registry.create(profile=profile, ocr=ocr)
    job_in = OUTPUT_DIR / job.id / "in"
    job_out = OUTPUT_DIR / job.id / "out"
    job_in.mkdir(parents=True, exist_ok=True)
    job_out.mkdir(parents=True, exist_ok=True)
    for upload in files:
        name = Path(upload.filename or "upload.pdf").name
        with (job_in / name).open("wb") as fh:
            shutil.copyfileobj(upload.file, fh)
    await registry.update(
        job.id,
        input_paths=[str(p) for p in sorted(job_in.iterdir())],
        output_dir=str(job_out),
    )
    asyncio.create_task(_run_job(job.id, profile, ocr))
    return {"job_id": job.id}


async def _run_job(job_id: str, profile: str, ocr: bool) -> None:
    job = await registry.get(job_id)
    if job is None:
        return
    await registry.update(job_id, status=JobStatus.running)
    opts = ConvertOptions(
        profile=profile,  # type: ignore[arg-type] — runtime-validated by the library
        ocr=ocr,
        sanitize=DEFAULT_SANITIZE,
        hybrid_url=HYBRID_URL,
        hybrid_full=HYBRID_FULL,
    )
    try:
        await asyncio.to_thread(
            convert,
            [Path(p) for p in job.input_paths],
            Path(job.output_dir),
            opts,
        )
    except Exception as exc:  # surface any backend failure to the job record
        await registry.update(job_id, status=JobStatus.failed, error=repr(exc), finished_at=now_utc())
        return
    await registry.update(job_id, status=JobStatus.succeeded, finished_at=now_utc())


@app.get("/jobs")
async def list_jobs(_: None = Depends(require_auth)) -> list[dict]:
    return [j.to_dict() for j in await registry.all()]


@app.get("/jobs/{job_id}")
async def get_job(job_id: str, _: None = Depends(require_auth)) -> dict:
    job = await registry.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job.to_dict()


@app.get("/jobs/{job_id}/files")
async def list_files(job_id: str, _: None = Depends(require_auth)) -> list[str]:
    job = await registry.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    out = Path(job.output_dir)
    if not out.exists():
        return []
    return sorted(
        str(p.relative_to(out)).replace("\\", "/")
        for p in out.rglob("*")
        if p.is_file()
    )


@app.get("/jobs/{job_id}/files/{name:path}")
async def download_file(job_id: str, name: str, _: None = Depends(require_auth)) -> FileResponse:
    job = await registry.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    root = Path(job.output_dir).resolve()
    candidate = (root / name).resolve()
    try:
        candidate.relative_to(root)
    except ValueError:
        raise HTTPException(400, "invalid path")
    if not candidate.is_file():
        raise HTTPException(404, "file not found")
    return FileResponse(candidate)
