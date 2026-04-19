from __future__ import annotations

from pathlib import Path

import pytest

from pdf_toolkit.enrich.chunker import Chunk, FigureRef
from pdf_toolkit.enrich.enrichers import (
    add_embeddings,
    add_summaries,
    add_taxonomy_tags,
    recaption_figures,
)


class FakeClient:
    """Stand-in for LLMClient; records calls so tests can assert on them without hitting a real endpoint."""

    def __init__(self, *, complete_return: str = '{"summary": "s", "keywords": ["k"]}') -> None:
        self.complete_calls: list[str] = []
        self.embed_calls: list[list[str]] = []
        self.describe_calls: list[Path] = []
        self._complete_return = complete_return

    def complete(self, prompt: str, **_: object) -> str:
        self.complete_calls.append(prompt)
        return self._complete_return

    def embed(self, texts: list[str], **_: object) -> list[list[float]]:
        self.embed_calls.append(list(texts))
        return [[0.1, 0.2] for _ in texts]

    def describe_image(self, image_path: Path, **_: object) -> str:
        self.describe_calls.append(image_path)
        return "fake caption"


def _chunk(id_: str, text: str, figures: list[FigureRef] | None = None) -> Chunk:
    return Chunk(
        id=id_,
        text=text,
        heading_path=[],
        page_start=None,
        page_end=None,
        block_ids=[],
        block_types=[],
        figures=figures or [],
    )


def test_add_summaries_skips_empty_text_chunks() -> None:
    chunks = [_chunk("0", ""), _chunk("1", "real content")]
    client = FakeClient()
    add_summaries(chunks, client)
    assert len(client.complete_calls) == 1
    assert chunks[0].summary is None
    assert chunks[1].summary == "s"


def test_add_embeddings_skips_empty_text_chunks() -> None:
    chunks = [_chunk("0", ""), _chunk("1", "first"), _chunk("2", "second")]
    client = FakeClient()
    add_embeddings(chunks, client)
    # Single batch, only the two non-empty texts sent.
    assert client.embed_calls == [["first", "second"]]
    assert chunks[0].embedding is None
    assert chunks[1].embedding == [0.1, 0.2]
    assert chunks[2].embedding == [0.1, 0.2]


def test_add_taxonomy_tags_skips_empty_text_chunks() -> None:
    chunks = [_chunk("0", ""), _chunk("1", "content")]
    client = FakeClient(complete_return='{"topic": "AI"}')
    add_taxonomy_tags(chunks, client, {"topic": ["AI", "Ops"]})
    assert len(client.complete_calls) == 1
    assert chunks[0].tags is None
    assert chunks[1].tags == {"topic": "AI"}


def test_add_taxonomy_tags_drops_unknown_facets() -> None:
    client = FakeClient(complete_return='{"topic": "AI", "bogus": "value"}')
    chunks = [_chunk("0", "content")]
    add_taxonomy_tags(chunks, client, {"topic": ["AI"]})
    assert chunks[0].tags == {"topic": "AI"}


def test_recaption_figures_touches_only_chunks_with_existing_figure_file(tmp_path: Path) -> None:
    real = tmp_path / "figs" / "real.png"
    real.parent.mkdir()
    real.write_bytes(b"\x89PNG")  # not a valid PNG, just needs to exist for is_file()
    chunks = [
        _chunk("0", "", figures=[FigureRef(source="figs/real.png", page=1)]),
        _chunk("1", "no figures"),
        _chunk("2", "missing fig", figures=[FigureRef(source="figs/missing.png", page=2)]),
    ]
    client = FakeClient()
    recaption_figures(chunks, client, image_root=tmp_path)
    assert [p.name for p in client.describe_calls] == ["real.png"]
    assert chunks[0].figures[0].caption == "fake caption"
    assert chunks[2].figures[0].caption is None
