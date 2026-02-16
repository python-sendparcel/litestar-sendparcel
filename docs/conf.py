"""Sphinx configuration for litestar-sendparcel."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

project = "litestar-sendparcel"
copyright = "2026, Dominik Kozaczko"
author = "Dominik Kozaczko"

extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.viewcode",
    "sphinx.ext.intersphinx",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "plans"]

html_theme = "furo"

myst_enable_extensions = [
    "colon_fence",
    "deflist",
]

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "litestar": ("https://docs.litestar.dev/2/", None),
}

autodoc_member_order = "bysource"
autodoc_typehints = "description"
