from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .chunker import Chunk
from .client import LLMClient


def add_embeddings(chunks: list[Chunk], client: LLMClient, batch_size: int = 64) -> None:
    # Skip empty-text chunks — embedding "" is degenerate and pollutes retrieval.
    targets = [c for c in chunks if c.text.strip()]
    for start in range(0, len(targets), batch_size):
        batch = targets[start:start + batch_size]
        if not batch:
            continue
        vectors = client.embed([c.text for c in batch])
        for chunk, vec in zip(batch, vectors):
            chunk.embedding = vec


SUMMARY_SYSTEM = (
    "You write a one-sentence summary and a short keyword list for a chunk of a document "
    "that will be retrieved by semantic search. "
    "Both the summary and the keywords must be SPECIFIC and DISCRIMINATIVE: prefer named "
    "entities, distinctive concepts, and concrete technical terms that appear in this "
    "chunk. AVOID generic filler words like \"book\", \"section\", \"framework\", "
    "\"accessibility\", \"overview\", \"introduction\", or any word that would describe "
    "most chunks equally well. Use the heading path for context but do not just restate it. "
    "If the chunk is a table of contents, copyright page, or other boilerplate, say so "
    "plainly in the summary instead of paraphrasing it.\n\n"
    'Respond ONLY with a JSON object of the form {"summary": str, "keywords": [str, ...]}. '
    "Keywords: 3-6 short noun phrases drawn from the chunk's distinctive terms. "
    "No preamble, no markdown, no code fences."
)


def add_summaries(chunks: list[Chunk], client: LLMClient) -> None:
    for chunk in chunks:
        # Skip empty-text chunks — asking the LLM to summarize nothing produces
        # confident hallucinations (observed on cover-page / figure-only chunks).
        if not chunk.text.strip():
            continue
        prompt = (
            f"Heading path: {' > '.join(chunk.heading_path) or '(root)'}\n\n"
            f"Chunk:\n{chunk.text}"
        )
        try:
            raw = client.complete(prompt, system=SUMMARY_SYSTEM, json_mode=True)
            parsed = json.loads(raw)
        except Exception:
            continue
        summary = (parsed.get("summary") or "").strip() if isinstance(parsed, dict) else ""
        chunk.summary = summary or None
        kw = parsed.get("keywords") if isinstance(parsed, dict) else None
        if isinstance(kw, list):
            chunk.keywords = [k for k in kw if isinstance(k, str)] or None


TAXONOMY_SYSTEM = (
    "You classify a document chunk against a controlled vocabulary. "
    "You receive a taxonomy (facet -> allowed values) and a chunk. "
    "Respond ONLY with a JSON object keyed by facet name, whose values are single strings or short arrays "
    "chosen from the allowed values. Omit facets for which no value applies. No preamble, no code fences."
)


def add_taxonomy_tags(
    chunks: list[Chunk],
    client: LLMClient,
    taxonomy: dict[str, list[str]],
) -> None:
    tax_str = json.dumps(taxonomy, indent=2, ensure_ascii=False)
    for chunk in chunks:
        if not chunk.text.strip():
            continue
        prompt = (
            f"Taxonomy:\n{tax_str}\n\n"
            f"Heading path: {' > '.join(chunk.heading_path) or '(root)'}\n\n"
            f"Chunk:\n{chunk.text}"
        )
        try:
            raw = client.complete(prompt, system=TAXONOMY_SYSTEM, json_mode=True)
            parsed = json.loads(raw)
        except Exception:
            continue
        if not isinstance(parsed, dict):
            continue
        cleaned = {k: v for k, v in parsed.items() if k in taxonomy}
        if cleaned:
            chunk.tags = cleaned


def recaption_figures(chunks: list[Chunk], client: LLMClient, image_root: Path) -> None:
    for chunk in chunks:
        for fig in chunk.figures:
            img_path = (image_root / fig.source).resolve()
            if not img_path.is_file():
                continue
            try:
                hint = f"This figure appears in section: {' > '.join(chunk.heading_path)}." if chunk.heading_path else None
                fig.caption = client.describe_image(img_path, hint=hint)
            except Exception:
                continue
