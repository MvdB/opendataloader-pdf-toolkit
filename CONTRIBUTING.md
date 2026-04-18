# Contributing

Thanks for considering a contribution.

## Dev setup

```bash
python -m venv .venv
.venv/Scripts/activate         # Linux/macOS: source .venv/bin/activate
pip install -e ".[ocr,dev]"
```

Java ≥ 11 must be on `PATH` to actually run `convert`. Unit tests do not need Java.

## Tests

```bash
pytest
```

The shipped tests cover the profile → opendataloader kwargs mapping. If you touch the FastAPI layer or the hybrid subprocess lifecycle, add tests that exercise those seams — prefer FastAPI's `TestClient` for the web routes and mock `opendataloader_pdf.convert` for code paths that would otherwise invoke the Java backend.

Integration tests against a real PDF are welcome, but do not commit the PDF itself: `samples/*.pdf` is `.gitignore`d to avoid inadvertently publishing copyrighted material. Link to the asset from the PR description or host it alongside the PR checks.

## Code conventions

- `from __future__ import annotations` in every module; type hints everywhere.
- Dataclasses (not free-floating dicts) for public option/config objects.
- **One core `convert()` — CLI and web are thin clients over it.** Do not duplicate extraction logic into the web or Docker layers.
- `sanitize=True` is a governance default, not an ergonomic one. Do not silently flip it.
- Comments are scarce. Only annotate non-obvious *why* (hidden constraints, subtle invariants, workarounds).

See [CLAUDE.md](CLAUDE.md) for the architecture and the design invariants that guide review.

## PR flow

1. Fork and branch from `main`.
2. Focused commits with messages that explain *why* rather than repeating the diff.
3. Open a PR; keep the description short but include reasoning for non-obvious choices.
4. Ensure `pytest` is green.
