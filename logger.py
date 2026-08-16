"""File and console logging for the jukebox service."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

DEFAULT_LOG_DIR = Path("/var/log/jukebox")
FALLBACK_LOG_DIR_NAME = "logs"
SCAN_LOG_NAME = "scan.log"
MAX_BYTES = 5 * 1024 * 1024
BACKUP_COUNT = 5

_logger: logging.Logger | None = None


def _resolve_log_dir(log_dir: Path | None) -> Path:
    if log_dir is not None:
        return log_dir

    env_dir = os.environ.get("JUKEBOX_LOG_DIR")
    if env_dir:
        return Path(env_dir)

    return DEFAULT_LOG_DIR


def setup_logging(log_dir: Path | None = None) -> logging.Logger:
    global _logger

    if _logger is not None:
        return _logger

    target_dir = _resolve_log_dir(log_dir)
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        target_dir = Path(__file__).resolve().parent / FALLBACK_LOG_DIR_NAME
        target_dir.mkdir(parents=True, exist_ok=True)

    logger = logging.getLogger("jukebox")
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()
    logger.propagate = False

    formatter = logging.Formatter(
        fmt="%(asctime)s %(levelname)s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    scan_log = target_dir / SCAN_LOG_NAME
    file_handler = RotatingFileHandler(
        scan_log,
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    logger.debug("Writing logs to %s", scan_log)
    _logger = logger
    return logger


def flush_logs() -> None:
    if _logger is None:
        return
    for handler in _logger.handlers:
        handler.flush()


def get_logger() -> logging.Logger:
    if _logger is None:
        return setup_logging()
    return _logger
