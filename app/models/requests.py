from __future__ import annotations

from typing import Literal
from uuid import uuid4

from pydantic import BaseModel, EmailStr, Field, field_validator


class CharacterInput(BaseModel):
    name: str = Field(min_length=1)
    role: str = Field(min_length=1)
    age: int | None = Field(default=None, ge=0)
    pronouns: str | None = None
    traits: list[str] = Field(default_factory=list)


class BookOptions(BaseModel):
    title_hint: str | None = None
    theme: str = Field(min_length=1)
    reading_age: str = Field(default="5-7")
    parent_review: bool = Field(default=False)
    dedication: str | None = None


class MediaInput(BaseModel):
    id: str = Field(min_length=1)
    original_filename: str | None = None
    original_media_type: Literal["photo", "video_frame"]
    mime_type: Literal["image/jpeg", "image/png"]
    width: int | None = Field(default=None, gt=0)
    height: int | None = Field(default=None, gt=0)
    captured_at: str | None = None
    data_base64: str = Field(min_length=1)

    @field_validator("data_base64")
    @classmethod
    def require_raw_base64(cls, value: str) -> str:
        if value.startswith("data:"):
            raise ValueError("Send raw base64 only, without a data: URI prefix.")
        return value


class StorybookRequest(BaseModel):
    request_id: str = Field(default_factory=lambda: str(uuid4()))
    parent_email: EmailStr
    book_options: BookOptions
    characters: list[CharacterInput] = Field(min_length=1)
    core_values: list[str] = Field(min_length=1)
    media: list[MediaInput] = Field(min_length=1)


class StorybookAcceptedResponse(BaseModel):
    job_id: str = Field(min_length=1)
    status: Literal["processing"]
    message: str = Field(min_length=1)
    status_url: str = Field(min_length=1)


class JobStatusResponse(BaseModel):
    job_id: str = Field(min_length=1)
    status: Literal["queued", "processing", "succeeded", "failed"]
    created_at: str = Field(min_length=1)
    updated_at: str = Field(min_length=1)
    pdf_url: str | None = None
    error_message: str | None = None
