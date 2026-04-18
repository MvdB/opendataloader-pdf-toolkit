# Security

## Reporting a vulnerability

Please report security issues via a **private GitHub security advisory** on this repository rather than opening a public issue. Reports will be acknowledged within a few working days.

Include, if possible: a minimal reproduction, the affected version (`pdf-toolkit` and the bundled `opendataloader-pdf`), and your assessment of exploitability.

## Built-in mitigations

- **Prompt-injection filtering** is on by default (`sanitize=True`) in every profile and in every CLI / web invocation. Disable only with `--no-sanitize` / `SANITIZE=false`, and only for trusted sources.
- **Local processing.** `opendataloader-pdf` parses documents on-device. The toolkit itself makes no outbound calls on a document's behalf. Any future LLM-enrichment layer will make remote calls explicit and opt-in.
- **Hybrid backend isolation.** The OCR / picture-description backend can run as a sidecar container (`docker-compose.yml`), isolating its process from the public-facing API.
- **Path-traversal protection** on the `GET /jobs/{id}/files/{path}` download route.

## Known risks and non-mitigations

- **No authentication by default.** The web UI binds to `0.0.0.0` and accepts uploads from anyone who can reach the port. Deploy behind an authenticating reverse proxy (Keycloak / OIDC / your SSO) before exposing to untrusted networks. The `auth.py` dependency seam in `src/pdf_toolkit/web/` is reserved for plugging in OIDC verification without touching route bodies.
- **Jobs are in-process** and retain uploaded PDFs plus extracted output on disk for the lifetime of the container. Treat `OUTPUT_DIR` as sensitive.
- **No input validation beyond content-type.** A malicious or malformed PDF can consume significant CPU and memory on the host running the Java backend.
- **Hybrid backend** pulls `docling` and `easyocr`, which download model weights to the runtime environment on first use. Audit the supply chain of those dependencies before enabling OCR in high-trust environments.

## Supported versions

v0.x sample project. Only the latest tagged release is supported.
