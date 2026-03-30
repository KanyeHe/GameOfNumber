import logging
from typing import Optional


_LOGGER: Optional[logging.Logger] = None


def get_logger() -> logging.Logger:
    global _LOGGER
    if _LOGGER is not None:
        return _LOGGER
    logger = logging.getLogger("gameofnumber")
    logger.setLevel(logging.INFO)
    handler = logging.FileHandler("error.log", encoding="utf-8")
    formatter = logging.Formatter(
        "%(asctime)s %(levelname)s %(message)s", "%Y-%m-%d %H:%M:%S"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    _LOGGER = logger
    return logger
