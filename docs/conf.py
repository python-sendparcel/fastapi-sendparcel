"""Sphinx configuration for fastapi-sendparcel."""

project = "fastapi-sendparcel"
author = "Dominik Kozaczko"
release = "0.1.0"

extensions = [
    "myst_parser",
    "autodoc2",
    "sphinx.ext.intersphinx",
]

autodoc2_packages = [
    {
        "path": "../src/fastapi_sendparcel",
        "module": "fastapi_sendparcel",
    },
]

myst_enable_extensions = [
    "colon_fence",
    "fieldlist",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "plans"]

html_theme = "furo"

intersphinx_mapping = {
    "python": ("https://docs.python.org/3", None),
    "fastapi": ("https://fastapi.tiangolo.com", None),
}

source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
