from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from logging.config import dictConfig
from typing import Any

SENSITIVE_MARKERS = (
    "base64",
    "api_key",
    "authorization",
    "openai_api_key",
    "ses_sender_email",
    "ses_admin_email",
)


class JsonFormatter(logging.Formatter):
    """Very small JSON formatter using only the standard library."""

    def format(self, record: logging.LogRecord) -> str:
        message = self._sanitize_message(record.getMessage())
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }

        job_id = getattr(record, "job_id", None)
        if job_id:
            payload["job_id"] = str(job_id)

        return json.dumps(payload, ensure_ascii=True)

    def _sanitize_message(self, message: str) -> str:
        lowered = message.lower()
        if any(marker in lowered for marker in SENSITIVE_MARKERS):
            return "[redacted-sensitive-log-message]"
        return message



def configure_logging() -> None:
    dictConfig(
        {
            "version": 1,
            "disable_existing_loggers": False,
            "formatters": {
                "json": {
                    "()": "app.logging_config.JsonFormatter",
                }
            },
            "handlers": {
                "console": {
                    "class": "logging.StreamHandler",
                    "formatter": "json",
                }
            },
            "root": {"handlers": ["console"], "level": "INFO"},
        }
    )



def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
