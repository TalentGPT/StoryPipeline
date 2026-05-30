from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(slots=True)
class JobRecord:
    job_id: str
    status: str
    request_json: dict[str, Any]
    story_json: dict[str, Any] | None
    pdf_s3_key: str | None
    pdf_url: str | None
    error_message: str | None
    created_at: datetime
    updated_at: datetime
