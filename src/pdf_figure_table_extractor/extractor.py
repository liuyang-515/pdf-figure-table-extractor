from __future__ import annotations

import json
import re
import statistics
from dataclasses import asdict, dataclass
from pathlib import Path

import pymupdf
from loguru import logger

CAPTION_RE = re.compile(
    r"^\s*(?P<kind>fig(?:ure)?\.?|table)\s+"
    r"(?P<label>[A-Z]?\d+(?:[.:-]\d+)*)\s*(?:[|:.\-\u2013\u2014])\s*",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Caption:
    kind: str
    label: str
    text: str
    rect: pymupdf.Rect


@dataclass(frozen=True)
class Asset:
    kind: str
    label: str
    page: int
    caption: str
    bbox: tuple[float, float, float, float]
    file: str


def _line_text(line: dict) -> str:
    return "".join(span["text"] for span in line["spans"]).strip()


def _find_captions(page: pymupdf.Page) -> list[Caption]:
    captions: list[Caption] = []
    data = page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)
    for block in data["blocks"]:
        if "lines" not in block:
            continue
        lines = block["lines"]
        for index, line in enumerate(lines):
            text = _line_text(line)
            match = CAPTION_RE.match(text)
            if not match:
                continue

            rect = pymupdf.Rect(line["bbox"])
            full_text = text
            for continuation in lines[index + 1 :]:
                next_rect = pymupdf.Rect(continuation["bbox"])
                if next_rect.y0 - rect.y1 > 4 or abs(next_rect.x0 - rect.x0) > 12:
                    break
                full_text += " " + _line_text(continuation)
                rect |= next_rect

            raw_kind = match.group("kind").lower()
            kind = "table" if raw_kind == "table" else "figure"
            captions.append(Caption(kind, match.group("label"), full_text.strip(), rect))

    text_blocks = [block for block in data["blocks"] if "lines" in block]
    extended: list[Caption] = []
    for caption in captions:
        rect = pymupdf.Rect(caption.rect)
        text = caption.text
        for block in text_blocks:
            block_rect = pymupdf.Rect(block["bbox"])
            if (
                0 <= block_rect.y0 - rect.y1 <= 3
                and abs(block_rect.x0 - rect.x0) <= 3
                and block_rect.width >= rect.width * 0.75
            ):
                text += " " + " ".join(_line_text(line) for line in block["lines"])
                rect |= block_rect
        extended.append(Caption(caption.kind, caption.label, text, rect))
    return extended


def _column_rect(page_rect: pymupdf.Rect, caption: Caption) -> pymupdf.Rect:
    margin = max(24.0, page_rect.width * 0.045)
    midpoint = page_rect.x0 + page_rect.width / 2
    if caption.rect.width > page_rect.width * 0.46:
        return pymupdf.Rect(
            page_rect.x0 + margin,
            page_rect.y0 + margin,
            page_rect.x1 - margin,
            page_rect.y1 - margin,
        )
    if caption.rect.x1 <= midpoint + 12:
        return pymupdf.Rect(
            page_rect.x0 + margin,
            page_rect.y0 + margin,
            midpoint - 7,
            page_rect.y1 - margin,
        )
    return pymupdf.Rect(
        midpoint + 7,
        page_rect.y0 + margin,
        page_rect.x1 - margin,
        page_rect.y1 - margin,
    )


def _graphic_rects(page: pymupdf.Page) -> list[pymupdf.Rect]:
    rects = [pymupdf.Rect(item["rect"]) for item in page.get_drawings()]
    for image in page.get_images(full=True):
        rects.extend(page.get_image_rects(image[0]))
    page_rect = page.rect
    usable = []
    for rect in rects:
        if rect.width > page_rect.width * 2 or rect.height > page_rect.height * 2:
            continue
        if rect.width < 0.5:
            rect.x0 -= 0.25
            rect.x1 += 0.25
        if rect.height < 0.5:
            rect.y0 -= 0.25
            rect.y1 += 0.25
        rect &= page_rect
        in_header_or_footer = (
            rect.y1 <= page_rect.y0 + 70 or rect.y0 >= page_rect.y1 - 70
        )
        if (
            not rect.is_empty
            and max(rect.width, rect.height) > 1
            and not in_header_or_footer
        ):
            usable.append(rect)
    return usable


def _distance(a: pymupdf.Rect, b: pymupdf.Rect) -> tuple[float, float]:
    dx = max(a.x0 - b.x1, b.x0 - a.x1, 0)
    dy = max(a.y0 - b.y1, b.y0 - a.y1, 0)
    return dx, dy


def _cluster_rects(rects: list[pymupdf.Rect]) -> list[pymupdf.Rect]:
    clusters = [pymupdf.Rect(rect) for rect in rects]
    changed = True
    while changed:
        changed = False
        merged: list[pymupdf.Rect] = []
        while clusters:
            current = clusters.pop()
            index = 0
            while index < len(clusters):
                other = clusters[index]
                dx, dy = _distance(current, other)
                x_overlap = min(current.x1, other.x1) - max(current.x0, other.x0)
                if (dx <= 8 and dy <= 8) or (x_overlap > 0 and dy <= 36):
                    current |= clusters.pop(index)
                    changed = True
                    index = 0
                else:
                    index += 1
            merged.append(current)
        clusters = merged
    return clusters


def _next_caption_limit(captions: list[Caption], caption: Caption, default: float) -> float:
    candidates = [
        other.rect.y0
        for other in captions
        if other is not caption
        and other.rect.y0 > caption.rect.y1
        and min(other.rect.x1, caption.rect.x1) > max(other.rect.x0, caption.rect.x0)
    ]
    return min(candidates, default=default)


def _pick_graphics(
    page: pymupdf.Page,
    caption: Caption,
    captions: list[Caption],
) -> pymupdf.Rect | None:
    column = _column_rect(page.rect, caption)
    clusters = _cluster_rects(
        [rect & column for rect in _graphic_rects(page) if not (rect & column).is_empty]
    )
    candidates: list[tuple[float, pymupdf.Rect]] = []

    if caption.kind == "figure":
        figure_area = pymupdf.Rect(
            column.x0,
            max(column.y0, page.rect.y0 + 70),
            column.x1,
            caption.rect.y0,
        )
        for rect in clusters:
            rect &= figure_area
            gap = caption.rect.y0 - rect.y1
            if (
                not rect.is_empty
                and 0 <= gap <= 360
                and rect.width >= 35
                and rect.height >= 25
            ):
                candidates.append((gap, rect))
    else:
        limit = _next_caption_limit(captions, caption, column.y1)
        for rect in clusters:
            below_gap = rect.y0 - caption.rect.y1
            above_gap = caption.rect.y0 - rect.y1
            if -8 <= below_gap <= 90 and rect.y1 < limit and rect.width >= 35:
                candidates.append((max(below_gap, 0), rect))
            if -8 <= above_gap <= 90 and rect.y0 < caption.rect.y0 and rect.width >= 35:
                candidates.append((max(above_gap, 0), rect))

    if not candidates:
        return None
    candidates.sort(key=lambda item: (item[0], -item[1].get_area()))
    return candidates[0][1]


def _word_rects(page: pymupdf.Page) -> list[pymupdf.Rect]:
    return [pymupdf.Rect(word[:4]) for word in page.get_text("words")]


def _expand_to_content(
    page: pymupdf.Page,
    caption: Caption,
    graphics: pymupdf.Rect,
    include_figure_captions: bool,
) -> pymupdf.Rect:
    if caption.kind == "figure":
        crop = pymupdf.Rect(graphics)
        search = pymupdf.Rect(graphics.x0 - 8, graphics.y0 - 10, graphics.x1 + 8, graphics.y1 + 8)
        if include_figure_captions:
            crop |= caption.rect
            search |= caption.rect
        for word in _word_rects(page):
            if word.intersects(search):
                crop |= word
        crop.y0 = max(crop.y0, page.rect.y0 + 70)
    else:
        words = _word_rects(page)
        content = pymupdf.Rect(graphics)
        content_is_above = content.y0 < caption.rect.y0
        changed = True
        while changed:
            changed = False
            for word in words:
                if content_is_above and word.y1 > caption.rect.y0:
                    continue
                if not content_is_above and word.y0 < caption.rect.y1:
                    continue
                dx, dy = _distance(content, word)
                if dx <= 8 and dy <= 8 and not content.contains(word):
                    content |= word
                    changed = True
        crop = content | caption.rect
    crop += (-3, -3, 3, 3)
    return crop & page.rect


def _fallback_crop(
    page: pymupdf.Page,
    caption: Caption,
    captions: list[Caption],
    include_figure_captions: bool,
) -> pymupdf.Rect | None:
    column = _column_rect(page.rect, caption)
    block_data: list[tuple[pymupdf.Rect, float]] = []
    for block in page.get_text("dict", flags=pymupdf.TEXTFLAGS_TEXT)["blocks"]:
        if "lines" not in block:
            continue
        rect = pymupdf.Rect(block["bbox"])
        sizes = [
            span["size"]
            for line in block["lines"]
            for span in line["spans"]
            if span["text"].strip()
        ]
        if (
            sizes
            and rect.intersects(column)
            and rect.y0 > page.rect.y0 + 65
            and rect.y1 < page.rect.y1 - 65
        ):
            block_data.append((rect, statistics.median(sizes)))
    blocks = [rect for rect, _ in block_data]
    if caption.kind == "figure":
        above = [rect for rect in blocks if rect.y1 < caption.rect.y0 - 2]
        if not above:
            return None
        nearest = max(above, key=lambda rect: rect.y1)
        top = max(column.y0, nearest.y0)
        crop = pymupdf.Rect(column.x0, top, column.x1, caption.rect.y0 - 2)
        if include_figure_captions:
            crop |= caption.rect
        if crop.height - caption.rect.height < 40:
            return None
        return crop

    bottom = _next_caption_limit(captions, caption, column.y1)
    above = sorted(
        (item for item in block_data if item[0].y1 < caption.rect.y0),
        key=lambda item: item[0].y1,
        reverse=True,
    )
    below = sorted(
        (item for item in block_data if caption.rect.y1 < item[0].y0 < bottom),
        key=lambda item: item[0].y0,
    )
    if not above and not below:
        return None

    above_gap = caption.rect.y0 - above[0][0].y1 if above else float("inf")
    below_gap = below[0][0].y0 - caption.rect.y1 if below else float("inf")
    above_size = above[0][1] if above else float("inf")
    below_size = below[0][1] if below else float("inf")
    wider_below = (
        above
        and below
        and below[0][0].width > above[0][0].width * 1.5
        and below_gap <= above_gap + 5
    )
    if not below:
        use_above = True
    elif not above:
        use_above = False
    else:
        use_above = (
            not wider_below
            and (
                above_size + 0.75 < below_size
                or abs(above_size - below_size) <= 0.75
                and above_gap < below_gap
            )
        )
    if use_above:
        crop = caption.rect | above[0][0]
        for rect, _ in above[1:]:
            if crop.y0 - rect.y1 > 18:
                break
            crop |= rect
    else:
        crop = caption.rect | below[0][0]
        for rect, _ in below[1:]:
            if rect.y0 - crop.y1 > 18:
                break
            crop |= rect
    return (crop + (-3, -3, 3, 3)) & page.rect


def _safe_label(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9.-]+", "-", label).strip("-").lower()


def _clear_previous_assets(output_dir: Path) -> None:
    manifest_path = output_dir / "manifest.json"
    if not manifest_path.is_file():
        return
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    for asset in manifest.get("assets", []):
        filename = asset.get("file", "")
        if filename and Path(filename).name == filename:
            (output_dir / filename).unlink(missing_ok=True)
    manifest_path.unlink()


def extract_assets(
    pdf_path: str | Path,
    output_dir: str | Path,
    *,
    dpi: int = 400,
    include_figure_captions: bool = True,
) -> list[Asset]:
    pdf_path = Path(pdf_path)
    output_dir = Path(output_dir)
    if not pdf_path.is_file() or pdf_path.suffix.lower() != ".pdf":
        raise ValueError(f"Input is not a PDF file: {pdf_path}")
    if dpi < 72:
        raise ValueError("DPI must be at least 72")

    output_dir.mkdir(parents=True, exist_ok=True)
    _clear_previous_assets(output_dir)

    document = pymupdf.open(pdf_path)
    assets: list[Asset] = []
    counters = {"figure": 0, "table": 0}
    scale = dpi / 72

    for page_index, page in enumerate(document):
        captions = _find_captions(page)
        logger.debug("Page {}: found {} captions", page_index + 1, len(captions))
        for caption in captions:
            graphics = _pick_graphics(page, caption, captions)
            crop = (
                _expand_to_content(page, caption, graphics, include_figure_captions)
                if graphics
                else _fallback_crop(page, caption, captions, include_figure_captions)
            )
            if crop is None or crop.width < 30 or crop.height < 15:
                logger.warning(
                    "Skipped {} {} on page {}: no content boundary found",
                    caption.kind,
                    caption.label,
                    page_index + 1,
                )
                continue

            counters[caption.kind] += 1
            filename = (
                f"{caption.kind}-{counters[caption.kind]:03d}-"
                f"{_safe_label(caption.label)}-page-{page_index + 1:03d}.png"
            )
            pixmap = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=crop, alpha=False)
            pixmap.save(output_dir / filename)
            assets.append(
                Asset(
                    kind=caption.kind,
                    label=caption.label,
                    page=page_index + 1,
                    caption=caption.text,
                    bbox=tuple(round(value, 2) for value in crop),
                    file=filename,
                )
            )

    document.close()
    manifest = {
        "source": str(pdf_path.resolve()),
        "dpi": dpi,
        "asset_count": len(assets),
        "assets": [asdict(asset) for asset in assets],
    }
    (output_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return assets
