"""Email delivery service for storybook pipeline.

Supports two backends:
- **SES**: sends via Amazon SES when ``EMAIL_DELIVERY_ENABLED=true`` and
  ``SES_SENDER_EMAIL`` is configured.
- **Local outbox**: writes ``.json`` message files to ``LOCAL_OUTBOX_DIR``
  when SES is disabled.  Useful for development, testing, and CI.

Both success (PDF ready) and failure (job error) flows are provided.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.config import Settings, get_settings
from app.logging_config import get_logger

LOGGER = get_logger(__name__)


class EmailDeliveryError(Exception):
    """Raised when an email cannot be sent or written to the outbox."""


class EmailService:
    """Thin wrapper around SES / local-outbox email delivery."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()

    # ── public API ──────────────────────────────────────────────

    def send_success_email(
        self,
        *,
        recipient: str,
        job_id: str,
        pdf_url: str | None = None,
        book_title: str | None = None,
    ) -> str:
        """Send a "your storybook is ready" email.

        Returns a message-id string (SES MessageId or local filename).
        """
        subject = "Your storybook is ready! 📖"
        if book_title:
            subject = f"Your storybook: {book_title} is ready! 📖"

        body_lines = [
            "Great news — your Family Storybook has been created!",
            "",
        ]
        if pdf_url:
            body_lines.append(f"Download your PDF here:\n{pdf_url}")
            body_lines.append("")
            body_lines.append(
                "(This link expires in "
                f"{self.settings.download_url_expires_seconds // 3600} hour(s).)"
            )
        else:
            body_lines.append(
                "Your PDF is ready.  Check your status page for the download link."
            )
        body_lines += ["", f"Job ID: {job_id}", "", "— Family Storybook Pipeline"]
        body_text = "\n".join(body_lines)

        return self._deliver(
            recipient=recipient,
            subject=subject,
            body_text=body_text,
            job_id=job_id,
            email_type="success",
        )

    def send_failure_email(
        self,
        *,
        recipient: str,
        job_id: str,
        error_message: str | None = None,
    ) -> str:
        """Send a "something went wrong" email.

        Returns a message-id string (SES MessageId or local filename).
        """
        subject = "Storybook generation failed 😞"
        body_lines = [
            "We're sorry — something went wrong while creating your storybook.",
            "",
        ]
        if error_message:
            body_lines.append(f"Details: {error_message}")
            body_lines.append("")
        body_lines += [
            "You can try submitting again, or reply to this email for help.",
            "",
            f"Job ID: {job_id}",
            "",
            "— Family Storybook Pipeline",
        ]
        body_text = "\n".join(body_lines)

        return self._deliver(
            recipient=recipient,
            subject=subject,
            body_text=body_text,
            job_id=job_id,
            email_type="failure",
        )

    def send_admin_failure_alert(
        self,
        *,
        job_id: str,
        error_message: str | None = None,
    ) -> str | None:
        """Notify the admin email about a job failure (if configured)."""
        admin = self.settings.ses_admin_email
        if not admin:
            LOGGER.debug("no admin email configured; skipping alert")
            return None

        subject = f"[StoryPipeline] Job {job_id} failed"
        body_lines = [
            f"Job {job_id} failed.",
            "",
            f"Error: {error_message or 'unknown'}",
            "",
            "— StoryPipeline Automation",
        ]
        body_text = "\n".join(body_lines)

        return self._deliver(
            recipient=admin,
            subject=subject,
            body_text=body_text,
            job_id=job_id,
            email_type="admin_failure",
        )

    # ── internals ───────────────────────────────────────────────

    def _deliver(
        self,
        *,
        recipient: str,
        subject: str,
        body_text: str,
        job_id: str,
        email_type: str,
    ) -> str:
        """Route to SES or local outbox based on settings."""
        if self.settings.email_delivery_enabled and self.settings.ses_sender_email:
            return self._send_ses(
                recipient=recipient,
                subject=subject,
                body_text=body_text,
                job_id=job_id,
            )
        return self._write_local(
            recipient=recipient,
            subject=subject,
            body_text=body_text,
            job_id=job_id,
            email_type=email_type,
        )

    def _send_ses(
        self,
        *,
        recipient: str,
        subject: str,
        body_text: str,
        job_id: str,
    ) -> str:
        sender = self.settings.ses_sender_email
        try:
            client = boto3.client("ses", region_name=self.settings.aws_region)
            response = client.send_email(
                Source=sender,
                Destination={"ToAddresses": [recipient]},
                Message={
                    "Subject": {"Data": subject, "Charset": "UTF-8"},
                    "Body": {
                        "Text": {"Data": body_text, "Charset": "UTF-8"},
                    },
                },
                Tags=[
                    {"Name": "job_id", "Value": job_id},
                    {"Name": "app", "Value": "storypipeline"},
                ],
            )
            message_id: str = response["MessageId"]
            LOGGER.info(
                "email sent via SES",
                extra={"job_id": job_id, "ses_message_id": message_id},
            )
            return message_id
        except (BotoCoreError, ClientError) as exc:
            LOGGER.error(
                "SES send failed",
                extra={"job_id": job_id, "error": str(exc)},
            )
            raise EmailDeliveryError(f"SES send failed: {exc}") from exc

    def _write_local(
        self,
        *,
        recipient: str,
        subject: str,
        body_text: str,
        job_id: str,
        email_type: str,
    ) -> str:
        outbox = Path(self.settings.local_outbox_dir)
        outbox.mkdir(parents=True, exist_ok=True)

        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"{job_id}_{email_type}_{ts}.json"
        envelope: dict[str, Any] = {
            "to": recipient,
            "from": self.settings.ses_sender_email or "noreply@localhost",
            "subject": subject,
            "body_text": body_text,
            "job_id": job_id,
            "email_type": email_type,
            "timestamp": ts,
        }

        filepath = outbox / filename
        filepath.write_text(json.dumps(envelope, indent=2), encoding="utf-8")
        LOGGER.info(
            "email written to local outbox",
            extra={"job_id": job_id, "path": str(filepath)},
        )
        return filename


__all__ = ["EmailService", "EmailDeliveryError"]
