# PDF Figure and Table Extractor

Extract labeled figures and tables from PDF files into tightly cropped,
high-resolution PNG images. The extractor uses PDF-native captions, vector
paths, embedded images, and text positions; it does not require OCR or a
vision model for text-based PDFs.

## Features

- Extracts labeled `Figure`, `Fig.`, and `Table` regions.
- Handles figure captions below content and table titles above or below content.
- Supports vector figures, raster figures, ruled tables, and unruled tables.
- Includes complete captions by default.
- Produces a JSON manifest with page numbers, captions, crop boxes, and filenames.
- Re-running into the same directory removes only files recorded by the previous manifest.

## Installation

Install the command-line tool with `uv`:

```bash
uv tool install pdf-figure-table-extractor
```

Or add it to a project:

```bash
uv add pdf-figure-table-extractor
```

## Usage

```bash
pdf-figure-table-extractor paper.pdf extracted-assets
```

The default resolution is 400 DPI. For larger output:

```bash
pdf-figure-table-extractor paper.pdf extracted-assets --dpi 600
```

To omit figure captions while keeping table titles:

```bash
pdf-figure-table-extractor paper.pdf extracted-assets --exclude-figure-captions
```

The Python API is also available:

```python
from pdf_figure_table_extractor import extract_assets

assets = extract_assets("paper.pdf", "extracted-assets", dpi=400)
```

## Output

```text
extracted-assets/
├── figure-001-1-page-001.png
├── table-001-1-page-002.png
└── manifest.json
```

`manifest.json` records the source PDF, DPI, detected caption, page number,
crop box, and output filename for every asset.

## Scope and limitations

The extractor targets PDFs with machine-readable text and conventional labeled
captions. Scanned documents, rotated captions, unusual caption formats, and
figures spanning multiple pages may require OCR or manual correction. Always
visually inspect extracted assets before using them in publications or reports.

## Development

```bash
uv sync --all-groups
uv run ruff check .
uv run pytest
uv build
```

Before publishing, choose and add an appropriate `LICENSE`, update the version,
and add repository URLs to `pyproject.toml` after the GitHub repository exists.
See [PUBLISHING.md](PUBLISHING.md) for the Trusted Publishing setup and release checklist.
