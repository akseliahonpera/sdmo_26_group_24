"""Cloud-server-specific shared utilities."""

import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def get_logger(name: str) -> logging.Logger:
    """Return the module logger for the cloud service."""
    return logging.getLogger(name)
