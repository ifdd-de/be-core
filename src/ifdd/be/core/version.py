"""The version of this package, read from its installed metadata.

There is one place that names the version: ``pyproject.toml``. Everything
else (``ifdd.be.core.__version__``, the default of ``IFDD_BE_VERSION``, the
OpenAPI description) reads it from the metadata of the installed
distribution, so a wheel can never report a version it was not built as.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

DISTRIBUTION = "ifdd-be-core"


def package_version() -> str:
    """Return the version of the installed ``ifdd-be-core`` distribution.

    Returns:
        The version string from the package metadata, or ``"0+unknown"``
        when the package is imported without being installed (for example
        from a plain source checkout on ``PYTHONPATH``).
    """
    try:
        return version(DISTRIBUTION)
    except PackageNotFoundError:
        return "0+unknown"


__version__ = package_version()
