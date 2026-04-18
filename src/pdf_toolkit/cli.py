from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .convert import ConvertOptions, convert
from .hybrid import hybrid_backend


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="pdf-toolkit",
        description="Layout-aware PDF extraction via opendataloader-pdf.",
    )
    p.add_argument("input", nargs="+", help="PDF file(s) or folder(s) to process")
    p.add_argument("-o", "--output", required=True, help="Output directory")
    p.add_argument(
        "-p",
        "--profile",
        choices=["rag", "structured", "review", "all"],
        default="rag",
        help="Output profile (default: rag)",
    )
    p.add_argument("--ocr", action="store_true", help="Enable OCR via hybrid backend")
    p.add_argument(
        "--hybrid-full",
        action="store_true",
        help="Enable picture descriptions / formula extraction (hybrid_mode=full)",
    )
    p.add_argument(
        "--hybrid-url",
        help="Use an existing hybrid backend instead of spawning one locally",
    )
    p.add_argument("--ocr-lang", default="en", help="OCR languages, comma-separated")
    p.add_argument(
        "--no-sanitize",
        action="store_true",
        help="Disable prompt-injection filtering (default: enabled)",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    inputs = [Path(p) for p in args.input]
    output = Path(args.output)
    output.mkdir(parents=True, exist_ok=True)
    opts = ConvertOptions(
        profile=args.profile,
        ocr=args.ocr,
        hybrid_full=args.hybrid_full,
        hybrid_url=args.hybrid_url,
        sanitize=not args.no_sanitize,
    )

    if args.ocr and not args.hybrid_url:
        with hybrid_backend(ocr_lang=args.ocr_lang, enrich_pictures=args.hybrid_full) as url:
            opts.hybrid_url = url
            convert(inputs, output, opts)
    else:
        convert(inputs, output, opts)
    return 0


if __name__ == "__main__":
    sys.exit(main())
