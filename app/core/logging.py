import json
import logging
from typing import Any

LOGGER_NAME = "ai_compute_router"


def get_logger() -> logging.Logger:
    logger = logging.getLogger(LOGGER_NAME)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


def log_event(event: str, **fields: Any) -> None:
    payload = {"event": event, **fields}
    get_logger().info(json.dumps(payload, sort_keys=True))
