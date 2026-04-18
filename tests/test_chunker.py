from __future__ import annotations

import json
from pathlib import Path

from pdf_toolkit.enrich.chunker import chunk_document


def _write_doc(tmp_path: Path, kids: list[dict]) -> Path:
    doc = {"file name": "t.pdf", "number of pages": 3, "kids": kids}
    p = tmp_path / "t.json"
    p.write_text(json.dumps(doc), encoding="utf-8")
    return p


def test_heading_boundary_creates_new_chunk(tmp_path: Path) -> None:
    p = _write_doc(tmp_path, [
        {"type": "heading", "id": 1, "heading level": 1, "page number": 1, "content": "Chapter 1"},
        {"type": "paragraph", "id": 2, "page number": 1, "content": "First paragraph of chapter 1."},
        {"type": "heading", "id": 3, "heading level": 1, "page number": 2, "content": "Chapter 2"},
        {"type": "paragraph", "id": 4, "page number": 2, "content": "First paragraph of chapter 2."},
    ])
    chunks = chunk_document(p)
    assert len(chunks) == 2
    assert chunks[0].heading_path == ["Chapter 1"]
    assert "First paragraph of chapter 1" in chunks[0].text
    assert chunks[1].heading_path == ["Chapter 2"]
    assert chunks[0].page_start == 1


def test_heading_stack_pops_same_or_lower_level(tmp_path: Path) -> None:
    p = _write_doc(tmp_path, [
        {"type": "heading", "id": 1, "heading level": 1, "page number": 1, "content": "Ch 1"},
        {"type": "heading", "id": 2, "heading level": 2, "page number": 1, "content": "Sec 1.1"},
        {"type": "paragraph", "id": 3, "page number": 1, "content": "Text A"},
        {"type": "heading", "id": 4, "heading level": 2, "page number": 2, "content": "Sec 1.2"},
        {"type": "paragraph", "id": 5, "page number": 2, "content": "Text B"},
    ])
    chunks = chunk_document(p)
    assert [c.heading_path for c in chunks] == [["Ch 1", "Sec 1.1"], ["Ch 1", "Sec 1.2"]]


def test_footer_and_header_stripped_by_default(tmp_path: Path) -> None:
    p = _write_doc(tmp_path, [
        {"type": "footer", "id": 1, "page number": 1, "kids": [
            {"type": "heading", "id": 2, "page number": 1, "heading level": 14, "content": "Watermark noise"}
        ]},
        {"type": "paragraph", "id": 3, "page number": 1, "content": "Real content"},
    ])
    chunks = chunk_document(p)
    assert len(chunks) == 1
    assert "Watermark" not in chunks[0].text
    assert "Real content" in chunks[0].text


def test_image_becomes_figure_ref(tmp_path: Path) -> None:
    p = _write_doc(tmp_path, [
        {"type": "heading", "id": 1, "heading level": 1, "page number": 1, "content": "Figures"},
        {"type": "paragraph", "id": 2, "page number": 1, "content": "Before fig."},
        {"type": "image", "id": 3, "page number": 1, "source": "test_images/img1.png"},
        {"type": "caption", "id": 4, "page number": 1, "content": "Figure 1. An example."},
    ])
    chunks = chunk_document(p)
    assert len(chunks) == 1
    assert len(chunks[0].figures) == 1
    assert chunks[0].figures[0].source == "test_images/img1.png"
    # Caption stays in the chunk text so retrieval can surface it alongside the figure
    assert "Figure 1" in chunks[0].text


def test_target_size_triggers_split(tmp_path: Path) -> None:
    kids = [
        {"type": "paragraph", "id": i, "page number": 1, "content": f"Paragraph {i}: " + "lorem " * 20}
        for i in range(10)
    ]
    p = _write_doc(tmp_path, kids)
    chunks = chunk_document(p, target_chars=200)
    assert len(chunks) > 1


def test_table_cells_are_linearized(tmp_path: Path) -> None:
    p = _write_doc(tmp_path, [
        {"type": "paragraph", "id": 1, "page number": 1, "content": "Before table."},
        {"type": "table", "id": 2, "page number": 1, "rows": [
            {"type": "table row", "row number": 1, "cells": [
                {"type": "table cell", "kids": [{"type": "paragraph", "id": 3, "content": "Cell A"}]},
                {"type": "table cell", "kids": [{"type": "paragraph", "id": 4, "content": "Cell B"}]},
            ]},
        ]},
    ])
    chunks = chunk_document(p)
    assert len(chunks) == 1
    assert "Cell A" in chunks[0].text and "Cell B" in chunks[0].text


def test_list_items_with_content_or_kids(tmp_path: Path) -> None:
    p = _write_doc(tmp_path, [
        {"type": "list", "id": 1, "page number": 1, "list items": [
            {"type": "list item", "id": 2, "page number": 1, "content": "Item one"},
            {"type": "list item", "id": 3, "page number": 1, "kids": [
                {"type": "paragraph", "id": 4, "page number": 1, "content": "Item two body"},
            ]},
        ]},
    ])
    chunks = chunk_document(p)
    assert len(chunks) == 1
    assert "Item one" in chunks[0].text
    assert "Item two body" in chunks[0].text
