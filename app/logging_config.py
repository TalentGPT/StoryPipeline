from __future__ import annotations

import json
import logging
import re
import traceback
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
    "presigned",
    "data_base64",
    "image_bytes",
)

# Matches http(s) URLs, replaces path/query with ellipsis to protect presigned URLs
_URL_RE = re.compile(r"https?://[^\s]+")


def _redact_url(match: re.Match) -> str:
    """Keep scheme+host but strip path/query to avoid leaking presigned tokens."""
    url = match.group(0)
    # Keep up to the third slash (scheme://host)
    parts = url.split("/", 3)
    if len(parts) > 3:
        return "/".join(parts[:3]) + "/…"
    return url


class JsonFormatter(logging.Formatter):
    """Structured JSON formatter for stdout logging."""

    def format(self, record: logging.LogRecord) -> str:
        message = self._sanitize_message(record.getMessage())
        payload: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": message,
        }

        # Structured extras
        for key in ("job_id", "event", "status", "duration_ms"):
            val = getattr(record, key, None)
            if val is not None:
                payload[key] = val

        # Include stack trace for exceptions (logs only, not API responses)
        if record.exc_info and record.exc_info[1] is not None:
            payload["exc"] = traceback.format_exception(*record.exc_info)

        return json.dumps(payload, default=str, ensure_ascii=True)

    def _sanitize_message(self, message: str) -> str:
        lowered = message.lower()
        if any(marker in lowered for marker in SENSITIVE_MARKERS):
            return "[redacted-sensitive-log-message]"
        # Redact full URLs to protect presigned tokens / paths
        message = _URL_RE.sub(_redact_url, message)
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
