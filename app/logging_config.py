import logging
from logging.config import dictConfig


def configure_logging() -> None:
    """Configure basic console logging for local development."""

    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "default": {
                    "format": "%(asctime)s %(levelname)s [%(name)s] %(message)s",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "default",
                }
            },
            "root": {"handlers": ["console"], "level": "INFO"},
        }
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
