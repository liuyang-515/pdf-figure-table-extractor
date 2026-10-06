from __future__ import annotations

import argparse
import json
import re
import time
from collections import Counter
from pathlib import Path

import pymupdf

from pdf_figure_table_extractor import extract_assets

CAPTION_CANDIDATE_RE = re.compile(
    r"^\s*(?:fig(?:ure)?\.?|table)\s+[A-Z]?\d+(?:[.:-]\d+)*\s*(?:[|:.\-\u2013\u2014])",
    re.IGNORECASE,
)


def _caption_candidate_count(document: pymupdf.Document) -> int:
    count = 0
    for page in document:
        for line in page.get_text("text").splitlines():
            count += bool(CAPTION_CANDIDATE_RE.match(line))
    return count


def _contact_sheet(image_paths: list[Path], output_path: Path) -> None:
    if not image_paths:
        return

    sheet = pymupdf.open()
    page_width, page_height = 842, 595
    columns, rows = 4, 3
    margin, gap, label_height = 18, 10, 18
    cell_width = (page_width - 2 * margin - (columns - 1) * gap) / columns
    cell_height = (page_height - 2 * margin - (rows - 1) * gap) / rows

    for start in range(0, len(image_paths), columns * rows):
        page = sheet.new_page(width=page_width, height=page_height)
        for offset, image_path in enumerate(image_paths[start : start + columns * rows]):
            row, column = divmod(offset, columns)
            x0 = margin + column * (cell_width + gap)
            y0 = margin + row * (cell_height + gap)
            image_rect = pymupdf.Rect(x0, y0 + label_height, x0 + cell_width, y0 + cell_height)
            page.insert_text(
                (x0, y0 + 12),
                image_path.name[:38],
                fontsize=7,
            )
            page.insert_image(image_rect, filename=image_path, keep_proportion=True)

    sheet.save(output_path, garbage=4, deflate=True)
    sheet.close()


def evaluate_pdf(pdf_path: Path, output_root: Path, dpi: int) -> dict:
    output_dir = output_root / pdf_path.parent.name
    started = time.perf_counter()
    assets = extract_assets(pdf_path, output_dir, dpi=dpi)
    elapsed = time.perf_counter() - started

    document = pymupdf.open(pdf_path)
    pages = len(document)
    caption_candidates = _caption_candidate_count(document)
    document.close()

    labels = [(asset.kind, asset.label.lower()) for asset in assets]
    duplicate_labels = [
        f"{kind} {label}" for (kind, label), count in Counter(labels).items() if count > 1
    ]
    suspicious_crops = []
    for asset in assets:
        pixmap = pymupdf.Pixmap(output_dir / asset.file)
        aspect = pixmap.width / pixmap.height
        if pixmap.width < 120 or pixmap.height < 60 or aspect < 0.15 or aspect > 8:
            suspicious_crops.append(
                {
                    "file": asset.file,
                    "size": [pixmap.width, pixmap.height],
                    "aspect": round(aspect, 2),
                }
            )

    image_paths = [output_dir / asset.file for asset in assets]
    _contact_sheet(image_paths, output_dir / "contact-sheet.pdf")
    return {
        "pdf": str(pdf_path.resolve()),
        "pages": pages,
        "seconds": round(elapsed, 2),
        "figures": sum(asset.kind == "figure" for asset in assets),
        "tables": sum(asset.kind == "table" for asset in assets),
        "assets": len(assets),
        "caption_candidates": caption_candidates,
        "candidate_difference": caption_candidates - len(assets),
        "duplicate_labels": duplicate_labels,
        "suspicious_crops": suspicious_crops,
        "output": str(output_dir.resolve()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate extraction on a corpus of PDFs.")
    parser.add_argument("pdfs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path, default=Path("evaluation-output"))
    parser.add_argument("--dpi", type=int, default=144)
    args = parser.parse_args()

    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    for pdf_path in args.pdfs:
        print(f"Evaluating {pdf_path}", flush=True)
        try:
            result = evaluate_pdf(pdf_path, args.output, args.dpi)
        except Exception as error:
            result = {"pdf": str(pdf_path.resolve()), "error": repr(error)}
        results.append(result)
        print(json.dumps(result, ensure_ascii=False), flush=True)

    report_path = args.output / "evaluation.json"
    report_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Report: {report_path.resolve()}")


if __name__ == "__main__":
    main()
