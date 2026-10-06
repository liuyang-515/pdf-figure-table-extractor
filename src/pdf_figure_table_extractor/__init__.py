"""High-resolution PDF figure and table extraction."""

from importlib.metadata import version

from .extractor import Asset, extract_assets

__version__ = version("pdf-figure-table-extractor")

__all__ = ["Asset", "__version__", "extract_assets"]
