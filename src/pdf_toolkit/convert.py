from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import opendataloader_pdf

Profile = Literal["rag", "structured", "review", "all"]

PROFILES: dict[Profile, dict[str, Any]] = {
    "rag": {
        "format": "markdown,json",
        "image_output": "external",
    },
    "structured": {
        "format": "json",
        "image_output": "embedded",
        "use_struct_tree": True,
    },
    "review": {
        "format": "pdf,json",
    },
    "all": {
        "format": "markdown,json,pdf,html,text",
        "image_output": "external",
        "use_struct_tree": True,
    },
}


@dataclass
class ConvertOptions:
    profile: Profile = "rag"
    sanitize: bool = True
    ocr: bool = False
    hybrid_full: bool = False
    hybrid_url: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


def build_kwargs(options: ConvertOptions) -> dict[str, Any]:
    kwargs: dict[str, Any] = {**PROFILES[options.profile], "sanitize": options.sanitize}
    if options.ocr or options.hybrid_url:
        kwargs["hybrid"] = "docling-fast"
        if options.hybrid_full:
            kwargs["hybrid_mode"] = "full"
        if options.hybrid_url:
            kwargs["hybrid_url"] = options.hybrid_url
    kwargs.update(options.extra)
    return kwargs


def convert(
    input_paths: list[str | Path],
    output_dir: str | Path,
    options: ConvertOptions | None = None,
) -> None:
    options = options or ConvertOptions()
    opendataloader_pdf.convert(
        input_path=[str(p) for p in input_paths],
        output_dir=str(output_dir),
        **build_kwargs(options),
    )
