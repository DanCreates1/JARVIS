"""Privacy-conscious application logging defaults."""

from __future__ import annotations

import logging


def configure_logging(level: str = "INFO") -> None:
    """Configure metadata-only console logging.

    JARVIS deliberately does not install transcript or prompt log handlers. Individual
    modules should log operation metadata, never message content or environment dumps.
    """
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
