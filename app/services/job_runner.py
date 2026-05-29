"""Background job runner for storybook processing.

Orchestrates: vision → story generation (with critic retry loop) → PDF → delivery.
Currently wired for mock-mode and ready for full pipeline integration once
vision produces an ``ImageDescriptionSet``.
"""

from __future__ import annotations

import time
import traceback

from app.config import get_settings
from app.logging_config import get_logger
from app.models.requests import StorybookRequest
from app.services.job_store import JobStore
from app.services.pdf import render_pdf
from app.services.storage import StorageService
from app.services.story_generation import (
    StoryGenerationError,
    generate_storybook_with_retries,
)

LOGGER = get_logger(__name__)

# ── Concise error messages (never leak internals to API consumers) ──────────
_MAX_ERROR_LEN = 256


def _concise_error(exc: Exception) -> str:
    """Return a short, safe error string suitable for storing/returning to callers."""
    msg = f"{type(exc).__name__}: {exc}"
    if len(msg) > _MAX_ERROR_LEN:
        msg = msg[:_MAX_ERROR_LEN] + "…"
    return msg


def process_storybook_job(job_id: str) -> None:
    """Background job entry point for single-instance processing.

    Pipeline steps (wired incrementally):
        1. Load job & request
        2. Vision analysis  →  ImageDescriptionSet   (TODO: wire real vision)
        3. Story generation with critic retry loop
        4. PDF rendering                              (TODO)
        5. S3 upload + email delivery                  (TODO)
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

    try:
        job_store.update_job_status(job_id, "processing")

        # ── Parse the request ───────────────────────────────────────
        request = StorybookRequest.model_validate(job.request_json)

        # ── Vision step (placeholder) ──────────────────────────────
        image_description_set = _build_placeholder_descriptions(request)

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
            extra={"job_id": job_id, "event": "pdf_rendered", "size_bytes": len(pdf_bytes)},
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
        _send_failure_email(job_id, error_msg)

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
        _send_failure_email(job_id, error_msg)


def _send_failure_email(job_id: str, error_msg: str) -> None:
    """Best-effort failure notification via SES when configured."""
    settings = get_settings()
    if not settings.email_delivery_enabled:
        return
    if not settings.ses_sender_email or not settings.ses_admin_email:
        LOGGER.warning(
            "job lifecycle",
            extra={
                "job_id": job_id,
                "event": "failure_email_skipped",
                "status": "warning",
            },
        )
        return

    try:
        import boto3  # late import to keep module importable without boto3 in tests

        client = boto3.client("ses", region_name=settings.aws_region)
        client.send_email(
            Source=settings.ses_sender_email,
            Destination={"ToAddresses": [settings.ses_admin_email]},
            Message={
                "Subject": {"Data": f"StoryPipeline job {job_id} failed"},
                "Body": {
                    "Text": {
                        "Data": (
                            f"Job {job_id} failed.\n\n"
                            f"Error: {error_msg}\n\n"
                            "Check application logs for the full stack trace."
                        ),
                    },
                },
            },
        )
        LOGGER.info(
            "job lifecycle",
            extra={"job_id": job_id, "event": "failure_email_sent", "status": "ok"},
        )
    except Exception:  # noqa: BLE001
        LOGGER.exception(
            "job lifecycle",
            extra={
                "job_id": job_id,
                "event": "failure_email_error",
                "status": "error",
            },
        )


def _send_success_email(
    request: StorybookRequest, job_id: str, *, pdf_url: str | None
) -> None:
    """Best-effort success email — never let delivery errors kill the job."""
    try:
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
    request: StorybookRequest, job_id: str, error_message: str
) -> None:
    """Best-effort failure email + admin alert."""
    try:
        email_svc = EmailService()
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


def _build_placeholder_descriptions(request: StorybookRequest):
    """Build a minimal ``ImageDescriptionSet`` from the request media list.

    This is a temporary bridge until the vision service is wired into
    the job runner.  It produces descriptions just complete enough for
    ``generate_storybook_with_retries`` to work in mock mode.
    """
    from app.models.story import ImageDescription, ImageDescriptionSet

    descriptions = [
        ImageDescription(
            image_id=m.id,
            setting="a family scene",
            subjects=["family members"],
            actions="spending time together",
            mood="joyful",
        )
        for m in request.media
    ]
    return ImageDescriptionSet(descriptions=descriptions)


__all__ = ["process_storybook_job"]
