from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .client import LLMConfig
from .pipeline import EnrichmentOptions, enrich


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pdf-toolkit-enrich",
        description="Post-process opendataloader-pdf JSON into RAG-ready chunks with optional LLM enrichment.",
    )
    p.add_argument("json_path", help="Path to a opendataloader-pdf JSON output file")
    p.add_argument("--embed", action="store_true", help="Generate embeddings per chunk")
    p.add_argument("--summarize", action="store_true", help="Generate per-chunk summary and keywords")
    p.add_argument("--recaption", action="store_true", help="Re-caption figures with a VLM")
    p.add_argument("--taxonomy", help="Path to a JSON or YAML taxonomy file for tagging")
    p.add_argument(
        "--all",
        action="store_true",
        help="Shortcut for --embed --summarize --recaption (taxonomy still requires --taxonomy)",
    )
    p.add_argument("--chunk-chars", type=int, default=1500, help="Target chunk size in characters")
    p.add_argument("--offset", type=int, default=0, help="Skip the first N chunks before applying --limit")
    p.add_argument("--limit", type=int, help="Only enrich N chunks (after --offset; useful for smoke tests)")
    p.add_argument(
        "--markdown",
        action="store_true",
        help="Also write a human-readable <basename>_enriched.md alongside the JSON sidecar",
    )

    g = p.add_argument_group("LLM overrides (otherwise env vars LLM_BASE_URL / LLM_API_KEY / LLM_MODEL / EMBEDDING_MODEL / VLM_MODEL)")
    g.add_argument("--base-url")
    g.add_argument("--api-key")
    g.add_argument("--model")
    g.add_argument("--embedding-model")
    g.add_argument("--vlm-model")
    return p


def _load_taxonomy(path: str) -> dict[str, list[str]]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix.lower() in {".yaml", ".yml"}:
        import yaml
        data = yaml.safe_load(text)
    else:
        data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("taxonomy file must be a mapping of facet -> list of values")
    for facet, values in data.items():
        if not isinstance(values, list) or not all(isinstance(x, str) for x in values):
            raise ValueError(f"taxonomy facet '{facet}' must be a list of strings")
    return data


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    opts = EnrichmentOptions(
        embed=args.embed or args.all,
        summarize=args.summarize or args.all,
        recaption=args.recaption or args.all,
        taxonomy=_load_taxonomy(args.taxonomy) if args.taxonomy else None,
        target_chunk_chars=args.chunk_chars,
        offset=args.offset,
        limit=args.limit,
        write_markdown=args.markdown,
    )
    config = LLMConfig.from_env()
    if args.base_url:
        config.base_url = args.base_url
    if args.api_key:
        config.api_key = args.api_key
    if args.model:
        config.chat_model = args.model
    if args.embedding_model:
        config.embedding_model = args.embedding_model
    if args.vlm_model:
        config.vlm_model = args.vlm_model

    out = enrich(args.json_path, opts, config=config)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
