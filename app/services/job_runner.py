"""Background job runner for storybook processing.

Orchestrates: image load → vision → story generation (with critic retry loop)
→ PDF → S3 upload → email delivery.
"""

from __future__ import annotations

import time

from app.config import get_settings
from app.logging_config import get_logger
from app.models.requests import StorybookRequest
from app.services.image_utils import load_decoded_images
from app.services.job_store import JobStore
from app.services.pdf import render_pdf
from app.services.storage import StorageService
from app.services.story_generation import (
    StoryGenerationError,
    generate_storybook_with_retries,
)
from app.services.vision import describe_images

LOGGER = get_logger(__name__)

# ── Concise error messages (never leak internals to API consumers) ──────────
_MAX_ERROR_LEN = 256


def _concise_error(exc: Exception) -> str:
    """Return a short, safe error string suitable for storing/returning to callers."""
    msg = f"{type(exc).__name__}: {exc}"
    if len(msg) > _MAX_ERROR_LEN:
        msg = msg[: _MAX_ERROR_LEN] + "…"
    return msg


def process_storybook_job(job_id: str) -> None:
    """Background job entry point for single-instance processing.

    Pipeline steps:
        1. Load job & request
        2. Load decoded images from work directory
        3. Vision analysis  →  ImageDescriptionSet
        4. Story generation with critic retry loop
        5. PDF rendering
        6. S3 upload + email delivery
    """
    settings = get_settings()
    job_store = JobStore(settings.job_store_path)
    t0 = time.monotonic()

    LOGGER.info(
        "job lifecycle",
        extra={"job_id": job_id, "event": "job_started", "status": "processing"},
    )

    job = job_store.get_job(job_id)
    if job is None:
        LOGGER.error(
            "job lifecycle",
            extra={"job_id": job_id, "event": "job_not_found", "status": "error"},
        )
        raise ValueError(f"Unknown job_id: {job_id}")

    request: StorybookRequest | None = None
    try:
        job_store.update_job_status(job_id, "processing")

        # ── Parse the request ───────────────────────────────────────
        request = StorybookRequest.model_validate(job.request_json)

        # ── Load persisted images from work directory ──────────────
        decoded_images = load_decoded_images(settings.work_dir, job_id)
        LOGGER.info(
            "job lifecycle",
            extra={
                "job_id": job_id,
                "event": "images_loaded",
                "image_count": len(decoded_images),
            },
        )

        # ── Vision step — describe each image ─────────────────────
        image_description_set = describe_images(request, decoded_images)
        LOGGER.info(
            "job lifecycle",
            extra={
                "job_id": job_id,
                "event": "vision_complete",
                "description_count": len(image_description_set.descriptions),
            },
        )

        # ── Story generation with retries ──────────────────────────
        story = generate_storybook_with_retries(
            request,
            image_description_set,
            job_id=job_id,
        )
        story_json = story.model_dump()

        # ── PDF rendering ─────────────────────────────────────────
        pdf_bytes = render_pdf(story, settings=settings)
        LOGGER.info(
            "job lifecycle",
            extra={
                "job_id": job_id,
                "event": "pdf_rendered",
                "status": "ok",
            },
        )

        # ── Upload / persist ──────────────────────────────────────
        storage = StorageService()
        pdf_s3_key = storage.upload_pdf_bytes(job_id, pdf_bytes)
        pdf_url = storage.generate_download_url(pdf_s3_key)

        # ── Mark success ───────────────────────────────────────────
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        job_store.mark_succeeded(
            job_id,
            story_json=story_json,
            pdf_s3_key=pdf_s3_key,
            pdf_url=pdf_url,
        )
        LOGGER.info(
            "job lifecycle",
            extra={
                "job_id": job_id,
                "event": "job_succeeded",
                "status": "succeeded",
                "duration_ms": elapsed_ms,
            },
        )

        _send_success_email(request, job_id, pdf_url=pdf_url)

    except StoryGenerationError as exc:
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        error_msg = _concise_error(exc)
        job_store.mark_failed(job_id, error_msg)
        LOGGER.error(
            "job lifecycle",
            extra={
                "job_id": job_id,
                "event": "job_failed",
                "status": "failed",
                "duration_ms": elapsed_ms,
            },
            exc_info=True,
        )
        _send_failure_email(request, job_id, error_msg)

    except Exception as exc:  # noqa: BLE001
        elapsed_ms = int((time.monotonic() - t0) * 1000)
        error_msg = _concise_error(exc)
        job_store.mark_failed(job_id, error_msg)
        LOGGER.exception(
            "job lifecycle",
            extra={
                "job_id": job_id,
                "event": "job_failed",
                "status": "failed",
                "duration_ms": elapsed_ms,
            },
        )
        _send_failure_email(request, job_id, error_msg)


def _send_success_email(
    request: StorybookRequest, job_id: str, *, pdf_url: str | None
) -> None:
    """Best-effort success email — never let delivery errors kill the job."""
    try:
        from app.services.email import EmailService

        email_svc = EmailService()
        email_svc.send_success_email(
            recipient=request.parent_email,
            job_id=job_id,
            pdf_url=pdf_url,
            book_title=request.book_options.title_hint,
        )
    except Exception:  # noqa: BLE001
        LOGGER.exception("success email delivery failed", extra={"job_id": job_id})


def _send_failure_email(
    request: StorybookRequest | None, job_id: str, error_message: str
) -> None:
    """Best-effort failure email + admin alert."""
    try:
        from app.services.email import EmailService

        email_svc = EmailService()
        if request is not None:
            email_svc.send_failure_email(
                recipient=request.parent_email,
                job_id=job_id,
                error_message=error_message,
            )
        email_svc.send_admin_failure_alert(
            job_id=job_id,
            error_message=error_message,
        )
    except Exception:  # noqa: BLE001
        LOGGER.exception("failure email delivery failed", extra={"job_id": job_id})


__all__ = ["process_storybook_job"]
