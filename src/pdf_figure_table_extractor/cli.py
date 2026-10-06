from __future__ import annotations

import argparse
from pathlib import Path

from loguru import logger

from .extractor import extract_assets
from .logging import configure_logging


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract figures and tables from a PDF as tightly cropped PNG files."
    )
    parser.add_argument("pdf", type=Path, help="Input PDF file")
    parser.add_argument("output", type=Path, help="Output directory")
    parser.add_argument("--dpi", type=int, default=400, help="Output resolution (default: 400)")
    parser.add_argument(
        "--exclude-figure-captions",
        action="store_true",
        help="Export figure bodies only. By default, complete figure captions are included.",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    configure_logging()
    assets = extract_assets(
        args.pdf,
        args.output,
        dpi=args.dpi,
        include_figure_captions=not args.exclude_figure_captions,
    )
    figures = sum(asset.kind == "figure" for asset in assets)
    tables = sum(asset.kind == "table" for asset in assets)
    logger.info(
        "Extracted {} assets ({} figures, {} tables) into {}",
        len(assets),
        figures,
        tables,
        args.output.resolve(),
    )


if __name__ == "__main__":
    main()
