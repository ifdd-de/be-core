# Sphinx configuration for checking docs/en and docs/de of this repository
# (tests/check_docs.py). The documentation is built for real in a separate
# Sphinx project that copies both directories; it needs the same extensions.
project = "ifdd-be-core (check)"
extensions = [
    "myst_parser",
    "sphinxcontrib.mermaid",
    "sphinx.ext.autodoc",
    "sphinx.ext.napoleon",
    "sphinxcontrib.openapi",
]
exclude_patterns = ["_build"]

# References to other parts of the full documentation (the backend instance
# ifdd-be-*, the instance chapter ifdd-instances-*) cannot resolve here;
# check_docs.py checks the references within this repository.
suppress_warnings = ["ref.ref"]
