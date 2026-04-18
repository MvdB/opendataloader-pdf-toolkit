# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Purpose

Sample project wrapping [`opendataloader-pdf`](https://github.com/opendataloader-project/opendataloader-pdf) (Apache-2.0) for layout-aware PDF → structured-data extraction. Targets both personal use and integration into Michael's enterprise AI platform.

## Stack

- **Python ≥ 3.10.** Dev venv at `.venv/` (currently 3.14.3). Docker image uses `python:3.13-slim-bookworm` (stable wheel availability) — both are fine because the package is a pure-Python wheel.
- **Java 11+** required at runtime. `opendataloader-pdf` shells out to a Java CLI. Docker installs `default-jre-headless`.
- **FastAPI + Uvicorn** for the web UI and async job API.
- **`opendataloader-pdf[hybrid]`** (via the `[ocr]` extra) for OCR / picture descriptions / formula extraction — pulls docling + easyocr + fastapi + uvicorn.
- Package layout: `src/pdf_toolkit/`, installable via `pyproject.toml` (hatchling).

## Architecture

```
src/pdf_toolkit/
  convert.py     core wrapper. Four profiles (rag / structured / review / all) → opendataloader kwargs.
  hybrid.py     context manager that spawns and tears down opendataloader-pdf-hybrid locally.
  cli.py         argparse entry point, installed as `pdf-toolkit`.
  web/
    app.py       FastAPI: GET / , POST /jobs (upload), GET /jobs, GET /jobs/{id}, GET /jobs/{id}/files[/path].
    jobs.py      in-process async Job/JobRegistry. Jobs DO NOT survive restart — swap for Redis/ARQ later.
    auth.py      empty Depends() seam for Keycloak/OIDC later. No-op today.
    templates/index.html   single self-contained page (vanilla JS, no framework, no build step).
docker/Dockerfile           multi-stage; runtime has JRE + tini + the venv. Spawns hybrid iff ENABLE_OCR=true and HYBRID_URL unset.
docker/entrypoint.sh        owns hybrid subprocess lifecycle, then exec uvicorn.
docker-compose.yml          enterprise / sidecar layout: separate `hybrid` and `api` services; api points at HYBRID_URL=http://hybrid:5002.
src/pdf_toolkit/enrich/   optional post-processing layer (chunker + LLM enrichers).
tests/test_convert.py       unit tests over build_kwargs (no Java required).
tests/test_chunker.py        unit tests for the chunker (no LLM / no Java required).
main.py                     tiny launcher — `python main.py --help` dispatches into pdf_toolkit.cli.
```

## Key design invariants

- **One core, many clients.** `convert.convert()` is the single source of truth. The CLI and the FastAPI layer are thin clients over it — do NOT duplicate extraction logic into the web layer.
- **Hybrid lifecycle is "A-then-optional-B".** Default (A): our CLI or the Docker entrypoint spawns `opendataloader-pdf-hybrid` when OCR is requested. Override (B): set `HYBRID_URL` / `--hybrid-url` to point at an externally managed backend (sidecar container, separate host). There is only one hybrid client.
- **`sanitize=True` by default everywhere.** Prompt-injection filtering is a governance default, not an ergonomic one. Only disable via explicit `--no-sanitize` / `SANITIZE=false`.
- **LLM enrichment lives in `src/pdf_toolkit/enrich/`, strictly as a separate pass.** Extraction (`convert.py`) does not touch an LLM. Enrichment reads the JSON opendataloader produced and writes a `*_enriched.json` sidecar with chunks + optional embeddings / summaries / VLM re-captions / taxonomy tags. See the "Enrichment layer" section below.
- **Jobs are in-process and lost on restart.** Acceptable for the sample. Before production use, replace `JobRegistry` with a durable backend (Redis + ARQ recommended) — the async interface doesn't need to change.

## Commands

Install (editable, with OCR and dev extras):

```bash
.venv/Scripts/python.exe -m pip install -e ".[ocr,dev]"
```

CLI:

```bash
.venv/Scripts/pdf-toolkit.exe path/to/file.pdf -o out --profile rag
.venv/Scripts/pdf-toolkit.exe scanned.pdf -o out --profile rag --ocr          # spawns hybrid locally
.venv/Scripts/pdf-toolkit.exe scanned.pdf -o out --ocr --hybrid-url http://hybrid:5002   # use external backend
```

Web UI (local dev):

```bash
.venv/Scripts/uvicorn.exe pdf_toolkit.web.app:app --reload --port 8080
```

Tests:

```bash
.venv/Scripts/pytest.exe
.venv/Scripts/pytest.exe tests/test_convert.py::test_rag_profile_defaults
```

Docker — single container (hybrid managed internally):

```bash
docker build -f docker/Dockerfile -t pdf-toolkit:latest .
docker run --rm -p 8080:8080 \
  -v "$PWD/data/in:/data/in" -v "$PWD/data/out:/data/out" \
  -e ENABLE_OCR=true \
  pdf-toolkit:latest
```

Docker — sidecar layout (enterprise):

```bash
docker compose up --build
```

## Enrichment layer

`src/pdf_toolkit/enrich/` post-processes opendataloader JSON into RAG-ready chunks with four opt-in capabilities — embeddings, summaries + keywords, figure re-captioning via VLM, and taxonomy tagging. Output is a `<basename>_enriched.json` sidecar next to the source JSON.

- `chunker.py` walks the opendataloader block tree, strips page chrome (header/footer) by default, flushes at heading boundaries, and accumulates text up to `target_chars`. Tables are linearized (cell-by-cell); lists respect `list items`; images become `FigureRef`s attached to the surrounding chunk. A chunk carries `heading_path`, `page_start/end`, `block_ids`, `block_types`, and mutable enrichment fields (`embedding`, `summary`, `keywords`, `tags`).
- `client.py` is a thin wrapper over the `openai` SDK pointed at any OpenAI-compatible endpoint via env vars — `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`, `EMBEDDING_MODEL`, `VLM_MODEL`. Enterprise: point at your gateway. Personal: `docker-compose.vllm.yml` brings up a vLLM sidecar (requires NVIDIA Container Toolkit; set `VLLM_MODEL` to a Gemma 4 E2B/E4B HF repo id or any other OpenAI-compat-servable model).
- `enrichers.py` has one function per capability; each is a no-op when its option flag is off. Enrichers only populate fields on `Chunk`; missing fields must remain legal for any downstream consumer.
- `pipeline.py` orchestrates: chunk → (re-caption → embed → summarize → tag) → write sidecar.
- `cli.py` is a separate entry point: `pdf-toolkit-enrich out/rag/test.json --all --taxonomy taxonomy.yml`.

### Enrichment invariants

- Never bake a provider default. The client reads the URL from env; never fall back to a public cloud endpoint silently.
- An empty chunk with figures but no text is legal output (typical at cover pages / figure-only regions). Consumers decide whether to index them.
- Install lives in the `[enrich]` extra so the base install stays lean for users who only want extraction.

## Conventions

- `from __future__ import annotations` in every module. Type hints everywhere.
- `dataclass` for option/config objects; no free-floating config dicts in public APIs.
- Comments are scarce — names should read themselves. Only annotate non-obvious *why*.
- No README.md yet (the enterprise deployment docs belong in a separate doc site when the time comes).
