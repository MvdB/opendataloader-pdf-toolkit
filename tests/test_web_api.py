from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def web_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """TestClient with isolated INPUT/OUTPUT dirs and a no-op convert + enrich."""
    in_dir = tmp_path / "in"
    out_dir = tmp_path / "out"
    in_dir.mkdir()
    out_dir.mkdir()

    # Set env before importing so the module-level constants pick it up.
    monkeypatch.setenv("INPUT_DIR", str(in_dir))
    monkeypatch.setenv("OUTPUT_DIR", str(out_dir))

    # Reload-safe: reimport with the new env, using importlib.
    import importlib
    import pdf_toolkit.web.app as app_module
    importlib.reload(app_module)

    # Replace the Java-backed convert and the LLM-backed enrich so tests never
    # reach out to external runtimes. We track calls for assertions.
    call_log: dict[str, list] = {"convert": [], "enrich": []}

    def fake_convert(inputs, output, opts):
        call_log["convert"].append((list(inputs), Path(output), opts))
        Path(output).mkdir(parents=True, exist_ok=True)
        # Simulate opendataloader's primary output — downstream enrichment keys on this.
        (Path(output) / "fake.json").write_text('{"kids": []}', encoding="utf-8")

    def fake_enrich(json_path, opts, config=None):
        call_log["enrich"].append((Path(json_path), opts))
        return Path(json_path)

    monkeypatch.setattr(app_module, "convert", fake_convert)
    monkeypatch.setattr(app_module, "enrich_document", fake_enrich)

    client = TestClient(app_module.app)
    client.input_dir = in_dir  # type: ignore[attr-defined]
    client.output_dir = out_dir  # type: ignore[attr-defined]
    client.call_log = call_log  # type: ignore[attr-defined]
    return client


def test_health(web_client: TestClient) -> None:
    r = web_client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_index_renders_enrichment_controls(web_client: TestClient) -> None:
    r = web_client.get("/")
    assert r.status_code == 200
    body = r.text
    for needle in [
        "enrich-toggle",
        "enrich_summarize",
        "enrich_recaption",
        "enrich_embed",
        "enrich_markdown",
        "Process INPUT_DIR",
    ]:
        assert needle in body, f"missing in rendered index: {needle}"


def test_ingest_folder_404_when_empty(web_client: TestClient) -> None:
    r = web_client.post("/jobs/ingest-folder", data={"profile": "rag"})
    assert r.status_code == 404
    assert "no PDFs" in r.json()["detail"]


def test_ingest_folder_schedules_job_for_every_pdf(web_client: TestClient) -> None:
    (web_client.input_dir / "a.pdf").write_bytes(b"%PDF-1.4 a")  # type: ignore[attr-defined]
    (web_client.input_dir / "b.pdf").write_bytes(b"%PDF-1.4 b")  # type: ignore[attr-defined]
    (web_client.input_dir / "ignored.txt").write_bytes(b"not a pdf")  # type: ignore[attr-defined]

    r = web_client.post(
        "/jobs/ingest-folder",
        data={"profile": "structured", "enrich": "true", "enrich_summarize": "true"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["files"] == ["a.pdf", "b.pdf"]
    job_id = body["job_id"]

    # The background task may or may not have run yet; verify the job record at least exists.
    job = web_client.get(f"/jobs/{job_id}").json()
    assert job["id"] == job_id
    assert job["profile"] == "structured"
    assert job["enrich"] is True
    assert job["enrich_summarize"] is True
    # input_paths were set to the source files under INPUT_DIR.
    assert len(job["input_paths"]) == 2


def test_upload_endpoint_still_works(web_client: TestClient) -> None:
    r = web_client.post(
        "/jobs",
        data={"profile": "rag"},
        files=[("files", ("sample.pdf", b"%PDF-1.4 sample", "application/pdf"))],
    )
    assert r.status_code == 200, r.text
    assert "job_id" in r.json()
