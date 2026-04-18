from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

# Text-bearing blocks carry a 'content' string directly.
# Container blocks wrap other blocks in 'kids' (or 'rows'/'list items').
# Page-chrome types (header/footer) are typically repeated watermarks / running
# titles and we strip them by default — they pollute RAG chunks.
DEFAULT_STRIP_TYPES = {"header", "footer"}


@dataclass
class FigureRef:
    source: str
    page: int | None = None
    caption: str | None = None


@dataclass
class Chunk:
    id: str
    text: str
    heading_path: list[str]
    page_start: int | None
    page_end: int | None
    block_ids: list[int]
    block_types: list[str]
    figures: list[FigureRef] = field(default_factory=list)
    embedding: list[float] | None = None
    summary: str | None = None
    keywords: list[str] | None = None
    tags: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "id": self.id,
            "text": self.text,
            "heading_path": self.heading_path,
            "page_start": self.page_start,
            "page_end": self.page_end,
            "block_ids": self.block_ids,
            "block_types": self.block_types,
            "figures": [f.__dict__ for f in self.figures],
        }
        if self.embedding is not None:
            d["embedding"] = self.embedding
        if self.summary is not None:
            d["summary"] = self.summary
        if self.keywords is not None:
            d["keywords"] = self.keywords
        if self.tags is not None:
            d["tags"] = self.tags
        return d


def _walk(nodes: list[dict], strip_types: set[str]) -> Iterator[dict]:
    """Yield leaf blocks (or headings/images) in reading order."""
    for node in nodes:
        t = node.get("type")
        if t in strip_types:
            continue
        if t == "table":
            for row in node.get("rows", []) or []:
                for cell in row.get("cells", []) or []:
                    yield from _walk(cell.get("kids", []) or [], strip_types)
            continue
        if t == "list":
            for li in node.get("list items", []) or []:
                if "content" in li and li.get("content"):
                    yield li
                elif li.get("kids"):
                    yield from _walk(li["kids"], strip_types)
            continue
        kids = node.get("kids")
        if kids:
            yield from _walk(kids, strip_types)
            continue
        yield node


def chunk_document(
    json_path: str | Path,
    target_chars: int = 1500,
    strip_types: set[str] | None = None,
) -> list[Chunk]:
    """Chunk an opendataloader-pdf JSON document into RAG-ready chunks."""
    src = Path(json_path)
    doc = json.loads(src.read_text(encoding="utf-8"))
    strip = strip_types if strip_types is not None else DEFAULT_STRIP_TYPES

    chunks: list[Chunk] = []
    heading_stack: list[tuple[int, str]] = []
    text_parts: list[str] = []
    block_ids: list[int] = []
    block_types: list[str] = []
    pages: list[int] = []
    figures: list[FigureRef] = []

    def flush() -> None:
        if not text_parts and not figures:
            return
        text = "\n\n".join(text_parts).strip()
        if not text and not figures:
            _reset()
            return
        chunks.append(Chunk(
            id=f"chunk_{len(chunks):04d}",
            text=text,
            heading_path=[h for _, h in heading_stack],
            page_start=min(pages) if pages else None,
            page_end=max(pages) if pages else None,
            block_ids=list(block_ids),
            block_types=list(block_types),
            figures=list(figures),
        ))
        _reset()

    def _reset() -> None:
        text_parts.clear()
        block_ids.clear()
        block_types.clear()
        pages.clear()
        figures.clear()

    for block in _walk(doc.get("kids", []) or [], strip):
        t = block.get("type")
        page = block.get("page number")
        bid = block.get("id")

        if t == "heading":
            flush()
            content = (block.get("content") or "").strip()
            if not content:
                continue
            lvl = int(block.get("heading level") or 99)
            while heading_stack and heading_stack[-1][0] >= lvl:
                heading_stack.pop()
            heading_stack.append((lvl, content))
            continue

        if t == "image":
            source = block.get("source")
            if source:
                figures.append(FigureRef(source=source, page=page))
            block_types.append("image")
            if bid is not None:
                block_ids.append(bid)
            if page is not None:
                pages.append(page)
            continue

        content = (block.get("content") or "").strip()
        if not content:
            continue

        text_parts.append(content)
        block_types.append(t or "unknown")
        if bid is not None:
            block_ids.append(bid)
        if page is not None:
            pages.append(page)

        if sum(len(p) + 2 for p in text_parts) >= target_chars:
            flush()

    flush()
    return chunks
