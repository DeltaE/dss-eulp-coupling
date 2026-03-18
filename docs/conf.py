# -- Project information -----------------------------------------------------
project = "DSS-DMDU"
author = "Luis Victor Gallardo"
copyright = "2025, Luis Víctor Gallardo (Delta-E+, SEE, SFU)"
html_title = "DSS-DMDU – Distribution System DMDU Tool"

# -- General configuration ---------------------------------------------------
extensions = [
    "myst_parser",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinx.ext.autosectionlabel",
    "sphinx.ext.intersphinx",
    "sphinx.ext.todo",
    "sphinx.ext.mathjax",
    "sphinx.ext.viewcode",
    "sphinx_copybutton",
    "sphinx_design",
    "sphinxcontrib.mermaid",
    "sphinx_autodoc_typehints",
]

# Allow Markdown with MyST
source_suffix = {
    ".rst": "restructuredtext",
    ".md": "markdown",
}
myst_enable_extensions = [
    "colon_fence",
    "deflist",
    "fieldlist",
    "substitution",
    "attrs_block",
    "attrs_inline",
    "tasklist",
]
myst_heading_anchors = 3

# Avoid import errors on RTD when autodoc tries to import heavy/Windows-only deps
autodoc_mock_imports = [
    "win32com",
    "comtypes",
    "OpenDSSDirect",
    "opendssdirect",
    "opendss",
    "pandas",
    "pyarrow",
    "numpy",
    "scipy",
    "matplotlib",
    "sklearn",
]

templates_path = ["_templates"]
exclude_patterns = ["_build", "Thumbs.db", ".DS_Store"]

# -- Options for HTML output -------------------------------------------------
html_theme = "furo"
html_static_path = ["_static"]

# Optional: link to your GitHub repo in the theme (Furo supports extra nav items via HTML templates)
html_title = "DSS XLRM"
