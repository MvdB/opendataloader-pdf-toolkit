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
tests/test_convert.py       unit tests over build_kwargs (no Java required).
main.py                     tiny launcher — `python main.py --help` dispatches into pdf_toolkit.cli.
```

## Key design invariants

- **One core, many clients.** `convert.convert()` is the single source of truth. The CLI and the FastAPI layer are thin clients over it — do NOT duplicate extraction logic into the web layer.
- **Hybrid lifecycle is "A-then-optional-B".** Default (A): our CLI or the Docker entrypoint spawns `opendataloader-pdf-hybrid` when OCR is requested. Override (B): set `HYBRID_URL` / `--hybrid-url` to point at an externally managed backend (sidecar container, separate host). There is only one hybrid client.
- **`sanitize=True` by default everywhere.** Prompt-injection filtering is a governance default, not an ergonomic one. Only disable via explicit `--no-sanitize` / `SANITIZE=false`.
- **No LLM enrichment in this repo yet.** Hybrid mode's picture descriptions use SmolVLM-256M bundled inside the backend — opendataloader does not expose a pluggable external LLM hook. A future, separate service may post-process opendataloader output through an OpenAI-compatible endpoint (enterprise gateway in prod; vLLM + Gemma 4 E2B/E4B for personal use). Don't add LLM code here without discussion.
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

## Conventions

- `from __future__ import annotations` in every module. Type hints everywhere.
- `dataclass` for option/config objects; no free-floating config dicts in public APIs.
- Comments are scarce — names should read themselves. Only annotate non-obvious *why*.
- No README.md yet (the enterprise deployment docs belong in a separate doc site when the time comes).
