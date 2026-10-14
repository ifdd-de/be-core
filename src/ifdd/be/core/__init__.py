"""ifdd.be.core - shared runtime for IFDD JSON-LD micro services."""

from .app import create_app
from .config import CoreSettings, configure, get_settings
from .version import __version__

__all__ = [
    "create_app",
    "CoreSettings",
    "configure",
    "get_settings",
    "__version__",
]
