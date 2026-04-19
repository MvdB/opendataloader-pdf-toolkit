from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .chunker import chunk_document
from .client import LLMClient, LLMConfig
from .enrichers import add_embeddings, add_summaries, add_taxonomy_tags, recaption_figures


@dataclass
class EnrichmentOptions:
    embed: bool = False
    summarize: bool = False
    recaption: bool = False
    taxonomy: dict[str, list[str]] | None = None
    target_chunk_chars: int = 1500
    limit: int | None = None

    def requires_llm(self) -> bool:
        return self.embed or self.summarize or self.recaption or bool(self.taxonomy)


def enrich(
    json_path: str | Path,
    options: EnrichmentOptions,
    config: LLMConfig | None = None,
) -> Path:
    """Chunk + enrich an opendataloader JSON; write a sidecar, return its path."""
    src = Path(json_path)
    chunks = chunk_document(src, target_chars=options.target_chunk_chars)
    if options.limit is not None:
        chunks = chunks[: options.limit]

    client: LLMClient | None = None
    if options.requires_llm():
        client = LLMClient(config or LLMConfig.from_env())

    # Re-caption first so summaries (which only see chunk.text) aren't blind to figures
    # that would benefit from a richer description — but since captions aren't folded
    # into chunk.text today, order only matters if you later change that policy.
    if options.recaption and client is not None:
        recaption_figures(chunks, client, image_root=src.parent)
    if options.embed and client is not None:
        add_embeddings(chunks, client)
    if options.summarize and client is not None:
        add_summaries(chunks, client)
    if options.taxonomy and client is not None:
        add_taxonomy_tags(chunks, client, options.taxonomy)

    out_path = src.with_name(src.stem + "_enriched.json")
    payload: dict[str, Any] = {
        "source": src.name,
        "chunk_count": len(chunks),
        "chunks": [c.to_dict() for c in chunks],
    }
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_path
