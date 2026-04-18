# pdf-toolkit

Sample project wrapping [opendataloader-pdf](https://github.com/opendataloader-project/opendataloader-pdf) (Apache-2.0) for layout-aware PDF → structured-data extraction. Ships a Python library, a CLI, and a FastAPI web UI with an async job queue, plus a Docker image for both single-container and sidecar deployments.

The primary use case is producing RAG-ready Markdown and structured JSON (with bounding boxes and semantic block types) from PDFs — for personal projects or enterprise AI platforms.

## Features

- Four output **profiles** — `rag` (markdown + json), `structured` (json with native PDF tag tree), `review` (annotated PDF + json), `all`.
- **OCR** for scanned PDFs via `opendataloader-pdf-hybrid` (docling + easyocr). Managed as a subprocess by default, or pointed at a user-managed backend via `--hybrid-url`.
- **Prompt-injection filtering** (`sanitize=True`) enabled by default on every profile.
- **Async job API** — upload PDFs, poll for completion, download per-file outputs.
- **Dockerized** — single-container (hybrid managed internally) or `docker-compose` sidecar layout for enterprise deployments.

## Requirements

- Python ≥ 3.10 (developed on 3.14).
- Java ≥ 11 on `PATH` (`opendataloader-pdf` shells out to a Java CLI). [Temurin](https://adoptium.net/) works well.

## Quickstart

```bash
python -m venv .venv
.venv/Scripts/activate         # Linux/macOS: source .venv/bin/activate
pip install -e ".[ocr,dev]"

# CLI
pdf-toolkit path/to/file.pdf -o out --profile rag
pdf-toolkit scanned.pdf -o out --profile rag --ocr          # spawns hybrid backend locally

# Web UI at http://localhost:8080
uvicorn pdf_toolkit.web.app:app --reload --port 8080
```

Benchmarked on a 216-page, 31 MB born-digital book: 216 pages processed in ≈ 5 s on a 16-thread laptop, producing 508 KB of Markdown, 1.3 MB of JSON (1 841 semantically typed blocks), and 36 externalized images.

## Docker

Single container (entrypoint manages the hybrid backend when OCR is on):

```bash
docker build -f docker/Dockerfile -t pdf-toolkit:latest .
docker run --rm -p 8080:8080 \
  -v "$PWD/data/in:/data/in" -v "$PWD/data/out:/data/out" \
  -e ENABLE_OCR=true \
  pdf-toolkit:latest
```

Enterprise / sidecar (API and hybrid backend as separate services):

```bash
docker compose up --build
```

## Configuration

| Variable       | Default     | Meaning                                                                         |
|----------------|-------------|---------------------------------------------------------------------------------|
| `OUTPUT_DIR`   | `/data/out` | Where per-job output folders are written.                                       |
| `INPUT_DIR`    | `/data/in`  | Bound to a host folder in Docker; reserved for a future ingest-folder endpoint. |
| `PROFILE`      | `rag`       | Default profile for new jobs when the form omits one.                           |
| `SANITIZE`     | `true`      | Prompt-injection filtering default.                                             |
| `ENABLE_OCR`   | `false`     | If `true` and `HYBRID_URL` unset, entrypoint spawns the hybrid backend.         |
| `HYBRID_URL`   | *(unset)*   | External hybrid backend URL; skips internal subprocess when set.                |
| `HYBRID_FULL`  | `false`     | Enable picture-description / formula enrichment (`hybrid_mode=full`).           |
| `OCR_LANG`     | `en`        | Comma-separated OCR language codes.                                             |
| `HYBRID_PORT`  | `5002`      | Port for the internally spawned hybrid backend.                                 |
| `PORT`         | `8080`      | Web UI / API port.                                                              |
| `HOST`         | `0.0.0.0`   | Bind host for uvicorn.                                                          |

## Architecture

See [CLAUDE.md](CLAUDE.md) for module-by-module notes, key design invariants, and the rationale behind the hybrid-backend lifecycle split.

## Status and non-goals

- v0.1 scaffold. Single-user, in-process jobs (lost on restart). **No authentication by default** — put the service behind an authenticating reverse proxy (Keycloak / OIDC / your SSO) before exposing it to untrusted networks. An `auth.py` seam is reserved in the code for OIDC verification.
- **No external LLM calls.** Opendataloader's hybrid mode does picture descriptions locally with SmolVLM-256M. Any future enrichment service (summarization, re-captioning, embeddings) will live in a separate, opt-in module that talks to a provider-neutral OpenAI-compatible endpoint — it is explicitly not part of this repo today.

## Security

See [SECURITY.md](SECURITY.md) for the vulnerability-reporting process and a summary of built-in mitigations and known non-mitigations.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

Apache-2.0 — see [LICENSE](LICENSE). The bundled dependency `opendataloader-pdf` is also Apache-2.0.
