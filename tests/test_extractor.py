import json
from pathlib import Path

import pymupdf

from pdf_figure_table_extractor import extract_assets


def create_test_pdf(path: Path) -> None:
    document = pymupdf.open()

    figure_page = document.new_page(width=612, height=792)
    figure_page.draw_rect(pymupdf.Rect(60, 100, 280, 260), width=1)
    figure_page.draw_line((80, 220), (140, 150), width=2)
    figure_page.draw_line((140, 150), (240, 205), width=2)
    figure_page.insert_text((90, 125), "Synthetic Architecture", fontsize=12)
    figure_page.insert_textbox(
        pymupdf.Rect(60, 275, 285, 310),
        "Figure 1: Synthetic architecture used to verify complete caption extraction.",
        fontsize=9,
    )

    ruled_table_page = document.new_page(width=612, height=792)
    ruled_table_page.insert_textbox(
        pymupdf.Rect(60, 80, 285, 115),
        "Table 1: Synthetic ruled table with two columns and complete title.",
        fontsize=9,
    )
    for y in (130, 155, 180, 205):
        ruled_table_page.draw_line((60, y), (280, y), width=1)
    for x in (60, 170, 280):
        ruled_table_page.draw_line((x, 130), (x, 205), width=1)
    ruled_table_page.insert_text((80, 148), "Method", fontsize=9)
    ruled_table_page.insert_text((195, 148), "Score", fontsize=9)
    ruled_table_page.insert_text((80, 173), "Baseline", fontsize=9)
    ruled_table_page.insert_text((205, 173), "0.75", fontsize=9)
    ruled_table_page.insert_text((80, 198), "Ours", fontsize=9)
    ruled_table_page.insert_text((205, 198), "0.91", fontsize=9)

    unruled_table_page = document.new_page(width=612, height=792)
    unruled_table_page.insert_text((80, 120), "Model        Accuracy", fontsize=9)
    unruled_table_page.insert_text((80, 142), "Small        82.0", fontsize=9)
    unruled_table_page.insert_text((80, 164), "Large        91.5", fontsize=9)
    unruled_table_page.insert_textbox(
        pymupdf.Rect(60, 185, 285, 220),
        "Table 2: Synthetic unruled table whose title appears below the data.",
        fontsize=9,
    )

    document.save(path)
    document.close()


def test_extracts_figures_and_tables(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    output_dir = tmp_path / "assets"
    create_test_pdf(pdf_path)

    assets = extract_assets(pdf_path, output_dir, dpi=144)

    assert [asset.kind for asset in assets] == ["figure", "table", "table"]
    assert all((output_dir / asset.file).is_file() for asset in assets)
    manifest = json.loads((output_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["asset_count"] == 3
    assert len(list(output_dir.glob("*.png"))) == 3

    figure = pymupdf.Pixmap(output_dir / assets[0].file)
    assert figure.width > 400
    assert figure.height > 300


def test_rerun_preserves_unrelated_files(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    output_dir = tmp_path / "assets"
    create_test_pdf(pdf_path)
    extract_assets(pdf_path, output_dir, dpi=144)
    unrelated = output_dir / "notes.txt"
    unrelated.write_text("keep", encoding="utf-8")

    extract_assets(pdf_path, output_dir, dpi=144)

    assert unrelated.read_text(encoding="utf-8") == "keep"


def test_extracts_consecutive_tables_with_captions_below(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    output_dir = tmp_path / "assets"
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)

    for number, top in ((1, 100), (2, 300)):
        page.insert_text((80, top), "Model        Accuracy", fontsize=9)
        page.insert_text((80, top + 22), "Small        82.0", fontsize=9)
        page.insert_text((80, top + 44), "Large        91.5", fontsize=9)
        page.insert_textbox(
            pymupdf.Rect(60, top + 65, 285, top + 100),
            f"Table {number}: Table with its caption below the data.",
            fontsize=9,
        )

    document.save(pdf_path)
    document.close()

    assets = extract_assets(pdf_path, output_dir, dpi=144)

    assert [(asset.kind, asset.label) for asset in assets] == [
        ("table", "1"),
        ("table", "2"),
    ]


def test_ignores_prose_starting_with_a_figure_reference(tmp_path: Path) -> None:
    pdf_path = tmp_path / "paper.pdf"
    output_dir = tmp_path / "assets"
    document = pymupdf.open()
    page = document.new_page(width=612, height=792)
    page.insert_textbox(
        pymupdf.Rect(60, 100, 550, 150),
        "Figure 18. Our method generates progressively finer identifiers for each item.",
        fontsize=11,
    )
    document.save(pdf_path)
    document.close()

    assets = extract_assets(pdf_path, output_dir, dpi=144)

    assert assets == []
