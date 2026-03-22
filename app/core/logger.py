from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def setup_logging(log_path: Path, debug: bool = False) -> None:
    """Configure root logger with a rotating file handler."""
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG if debug else logging.INFO)

    fh = RotatingFileHandler(
        log_path,
        maxBytes=5_000_000,
        backupCount=3,
        encoding='utf-8',
    )
    fh.setFormatter(
        logging.Formatter('%(asctime)s %(levelname)-8s %(name)s  %(message)s')
    )
    root.addHandler(fh)
