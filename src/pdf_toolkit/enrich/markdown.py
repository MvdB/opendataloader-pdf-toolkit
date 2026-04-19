from __future__ import annotations

from typing import Any


def render_markdown(enriched: dict[str, Any]) -> str:
    """Render an enriched document (dict as produced by enrich.pipeline) as reviewable Markdown.

    Each chunk becomes a section with a metadata callout (summary/keywords/tags/pages),
    the chunk body verbatim, and any attached figures with their VLM captions.
    """
    lines: list[str] = [
        f"# Enriched: {enriched.get('source', 'document')}",
        "",
        f"*{enriched.get('chunk_count', len(enriched.get('chunks', [])))} chunk(s)*",
        "",
    ]
    for chunk in enriched.get("chunks", []):
        heading = " › ".join(chunk.get("heading_path") or []) or "(no heading)"
        lines.append(f"## {heading}")
        lines.append("")
        lines.extend(_metadata_callout(chunk))
        text = (chunk.get("text") or "").strip()
        if text:
            lines.append(text)
            lines.append("")
        for fig in chunk.get("figures") or []:
            lines.extend(_figure_block(fig))
    return "\n".join(lines).rstrip() + "\n"


def _metadata_callout(chunk: dict[str, Any]) -> list[str]:
    parts: list[str] = [f"**Chunk:** `{chunk.get('id', '?')}`"]
    p0, p1 = chunk.get("page_start"), chunk.get("page_end")
    if p0 is not None:
        parts.append(f"**Page:** {p0}" if p0 == p1 else f"**Pages:** {p0}–{p1}")
    if chunk.get("summary"):
        parts.append(f"**Summary:** {chunk['summary']}")
    kw = chunk.get("keywords")
    if kw:
        parts.append("**Keywords:** " + ", ".join(kw))
    tags = chunk.get("tags")
    if tags:
        parts.append("**Tags:** " + ", ".join(f"{k}={_fmt_tag(v)}" for k, v in tags.items()))
    # Markdown blockquote with in-callout line breaks via trailing two-space newlines.
    return ["> " + "  \n> ".join(parts), ""]


def _fmt_tag(val: Any) -> str:
    if isinstance(val, list):
        return "/".join(str(x) for x in val)
    return str(val)


def _figure_block(fig: dict[str, Any]) -> list[str]:
    src = fig.get("source", "")
    out = [f"![figure]({src})"]
    if fig.get("caption"):
        out.append(f"> **Caption:** {fig['caption']}")
    out.append("")
    return out
