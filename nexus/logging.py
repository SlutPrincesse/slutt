"""Logging utilities for Nexus."""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from typing import Optional


def setup_logging(
    level: str = "info",
    log_file: str = "./config/nexus.log",
    fmt: str = "text",
) -> logging.Logger:
    """Set up Nexus logging with rotating file + stderr."""
    logger = logging.getLogger("nexus")
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
        if fmt == "text"
        else '{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","message":"%(message)s"}'
    )

    if log_file:
        log_path = os.path.expanduser(log_file)
        os.makedirs(os.path.dirname(log_path) or ".", exist_ok=True)
        fh = RotatingFileHandler(
            log_path, maxBytes=100_000, backupCount=3, encoding="utf-8"
        )
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    sh = logging.StreamHandler(sys.stderr)
    sh.setFormatter(formatter)
    logger.addHandler(sh)

    return logger
