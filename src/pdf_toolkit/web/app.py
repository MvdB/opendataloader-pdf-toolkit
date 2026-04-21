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
from ..enrich.pipeline import EnrichmentOptions
from ..enrich.pipeline import enrich as enrich_document
from .auth import require_auth
from .jobs import JobStatus, create_registry, now_utc

WEB_DIR = Path(__file__).parent
OUTPUT_DIR = Path(os.environ.get("OUTPUT_DIR", "/data/out"))
INPUT_DIR = Path(os.environ.get("INPUT_DIR", "/data/in"))
DEFAULT_PROFILE = os.environ.get("PROFILE", "rag")
DEFAULT_SANITIZE = os.environ.get("SANITIZE", "true").lower() == "true"
HYBRID_URL = os.environ.get("HYBRID_URL") or None
HYBRID_FULL = os.environ.get("HYBRID_FULL", "false").lower() == "true"

registry = create_registry()


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="pdf-toolkit", lifespan=lifespan)
templates = Jinja2Templates(directory=WEB_DIR / "templates")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, _: None = Depends(require_auth)) -> HTMLResponse:
    # Starlette 1.0 requires request as the first positional arg of TemplateResponse.
    return templates.TemplateResponse(
        request,
        "index.html",
        {"profile": DEFAULT_PROFILE},
    )


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/jobs")
async def create_job(
    profile: str = Form(DEFAULT_PROFILE),
    ocr: bool = Form(False),
    enrich: bool = Form(False),
    enrich_summarize: bool = Form(False),
    enrich_recaption: bool = Form(False),
    enrich_embed: bool = Form(False),
    enrich_markdown: bool = Form(False),
    files: list[UploadFile] = File(...),
    _: None = Depends(require_auth),
) -> dict[str, str]:
    if not files:
        raise HTTPException(400, "no files uploaded")
    job = await _new_job(
        profile=profile, ocr=ocr,
        enrich=enrich, enrich_summarize=enrich_summarize,
        enrich_recaption=enrich_recaption, enrich_embed=enrich_embed,
        enrich_markdown=enrich_markdown,
    )
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
    asyncio.create_task(_run_job(job.id))
    return {"job_id": job.id}


@app.post("/jobs/ingest-folder")
async def ingest_folder(
    profile: str = Form(DEFAULT_PROFILE),
    ocr: bool = Form(False),
    enrich: bool = Form(False),
    enrich_summarize: bool = Form(False),
    enrich_recaption: bool = Form(False),
    enrich_embed: bool = Form(False),
    enrich_markdown: bool = Form(False),
    _: None = Depends(require_auth),
) -> dict:
    """Process every PDF already present under INPUT_DIR — no upload required.

    Handy for batch ingestion when a host folder is mounted into the container.
    Files are read in place; the job's output_dir still goes under OUTPUT_DIR/<job>.
    """
    if not INPUT_DIR.exists():
        raise HTTPException(404, f"INPUT_DIR {INPUT_DIR} does not exist")
    pdfs = sorted(p for p in INPUT_DIR.glob("*.pdf") if p.is_file())
    if not pdfs:
        raise HTTPException(404, f"no PDFs found directly under {INPUT_DIR}")
    job = await _new_job(
        profile=profile, ocr=ocr,
        enrich=enrich, enrich_summarize=enrich_summarize,
        enrich_recaption=enrich_recaption, enrich_embed=enrich_embed,
        enrich_markdown=enrich_markdown,
    )
    job_out = OUTPUT_DIR / job.id / "out"
    job_out.mkdir(parents=True, exist_ok=True)
    await registry.update(
        job.id,
        input_paths=[str(p) for p in pdfs],
        output_dir=str(job_out),
    )
    asyncio.create_task(_run_job(job.id))
    return {"job_id": job.id, "files": [p.name for p in pdfs]}


async def _new_job(**fields: object):  # pragma: no cover — trivial wrapper
    return await registry.create(**fields)


async def _run_job(job_id: str) -> None:
    job = await registry.get(job_id)
    if job is None:
        return
    await registry.update(job_id, status=JobStatus.running)
    convert_opts = ConvertOptions(
        profile=job.profile,  # type: ignore[arg-type] — runtime-validated by the library
        ocr=job.ocr,
        sanitize=DEFAULT_SANITIZE,
        hybrid_url=HYBRID_URL,
        hybrid_full=HYBRID_FULL,
    )
    try:
        await asyncio.to_thread(
            convert,
            [Path(p) for p in job.input_paths],
            Path(job.output_dir),
            convert_opts,
        )
    except Exception as exc:  # surface any extraction failure to the job record
        await registry.update(job_id, status=JobStatus.failed, error=f"extract: {exc!r}", finished_at=now_utc())
        return

    if job.enrich:
        enrich_opts = EnrichmentOptions(
            summarize=job.enrich_summarize,
            recaption=job.enrich_recaption,
            embed=job.enrich_embed,
            write_markdown=job.enrich_markdown,
        )
        try:
            for json_file in sorted(Path(job.output_dir).glob("*.json")):
                # Skip our own previous sidecars if we ever re-run
                if json_file.name.endswith("_enriched.json"):
                    continue
                await asyncio.to_thread(enrich_document, json_file, enrich_opts)
        except Exception as exc:
            # Extraction succeeded; surface enrichment failure without destroying the raw output.
            await registry.update(
                job_id,
                status=JobStatus.failed,
                error=f"enrich: {exc!r} (extraction output is still available)",
                finished_at=now_utc(),
            )
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
