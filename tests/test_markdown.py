from __future__ import annotations

from pdf_toolkit.enrich.markdown import render_markdown


def _doc(chunks: list[dict]) -> dict:
    return {"source": "test.pdf", "chunk_count": len(chunks), "chunks": chunks}


def test_header_and_count_emitted() -> None:
    md = render_markdown(_doc([]))
    assert md.startswith("# Enriched: test.pdf")
    assert "0 chunk(s)" in md


def test_heading_path_joined_with_separator() -> None:
    md = render_markdown(_doc([{
        "id": "chunk_0",
        "text": "body",
        "heading_path": ["Chapter 1", "Section A"],
        "page_start": 1,
        "page_end": 1,
        "figures": [],
    }]))
    assert "## Chapter 1 › Section A" in md


def test_single_page_vs_range_rendering() -> None:
    single = render_markdown(_doc([{
        "id": "c", "text": "x", "heading_path": [], "page_start": 5, "page_end": 5, "figures": [],
    }]))
    ranged = render_markdown(_doc([{
        "id": "c", "text": "x", "heading_path": [], "page_start": 5, "page_end": 9, "figures": [],
    }]))
    assert "**Page:** 5" in single
    assert "**Pages:** 5–9" in ranged


def test_metadata_callout_contains_summary_keywords_tags() -> None:
    md = render_markdown(_doc([{
        "id": "c_00", "text": "body text", "heading_path": ["H"], "page_start": 1, "page_end": 1,
        "summary": "one-line summary", "keywords": ["alpha", "beta"],
        "tags": {"topic": "AI", "audience": ["tech", "exec"]},
        "figures": [],
    }]))
    assert "**Chunk:** `c_00`" in md
    assert "**Summary:** one-line summary" in md
    assert "**Keywords:** alpha, beta" in md
    assert "topic=AI" in md
    assert "audience=tech/exec" in md


def test_figure_with_caption_rendered_as_image_and_blockquote() -> None:
    md = render_markdown(_doc([{
        "id": "c", "text": "", "heading_path": [], "page_start": 1, "page_end": 1,
        "figures": [{"source": "imgs/one.png", "page": 1, "caption": "A cover image."}],
    }]))
    assert "![figure](imgs/one.png)" in md
    assert "> **Caption:** A cover image." in md


def test_empty_text_chunk_with_figures_still_renders_figures() -> None:
    md = render_markdown(_doc([{
        "id": "c", "text": "", "heading_path": [], "page_start": 1, "page_end": 1,
        "figures": [{"source": "imgs/cover.png", "page": 1}],
    }]))
    assert "![figure](imgs/cover.png)" in md


def test_no_heading_fallback() -> None:
    md = render_markdown(_doc([{
        "id": "c", "text": "t", "heading_path": [], "page_start": 1, "page_end": 1, "figures": [],
    }]))
    assert "## (no heading)" in md
