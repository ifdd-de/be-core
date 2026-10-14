"""Loggers configured from the settings (level, format, optional rotating file)."""

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional

from .config import get_settings


def setup_logger(name: str, level: Optional[str] = None) -> logging.Logger:
    """Return a logger configured from the active settings.

    The logger is configured only once per name; repeated calls return the
    already configured instance.
    """
    logger = logging.getLogger(name)

    if logger.handlers:
        return logger

    settings = get_settings()
    log_level = getattr(logging, (level or settings.LOG_LEVEL).upper())
    logger.setLevel(log_level)
    formatter = logging.Formatter(settings.LOG_FORMAT)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(log_level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    if settings.LOG_TO_FILE:
        os.makedirs(os.path.dirname(settings.LOG_FILE_PATH), exist_ok=True)
        file_handler = RotatingFileHandler(
            settings.LOG_FILE_PATH, maxBytes=10485760, backupCount=5
        )
        file_handler.setLevel(log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger
