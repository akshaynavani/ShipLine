"""Logging setup with stage-aware prefixes."""

from __future__ import annotations

import logging
import os
import sys

_FORMAT = "%(asctime)s %(levelname)-7s %(name)s: %(message)s"


def setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    if os.environ.get("SHIPLINE_LOG_LEVEL"):
        level = getattr(logging, os.environ["SHIPLINE_LOG_LEVEL"].upper(), level)
    logging.basicConfig(level=level, format=_FORMAT, datefmt="%H:%M:%S", stream=sys.stderr)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"shipline.{name}")


def banner(title: str) -> str:
    line = "=" * max(40, len(title) + 8)
    return f"\n{line}\n==  {title}\n{line}"
