"""Tests for app.services.email – EmailService."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config import Settings
from app.services.email import EmailDeliveryError, EmailService


# ── helpers ─────────────────────────────────────────────────────

def _local_settings(tmp_path: Path, **overrides) -> Settings:
    """Return a Settings instance that writes to a local outbox."""
    # Use alias (uppercase) keys so pydantic-settings picks them up.
    defaults = dict(
        APP_ENV="development",
        EMAIL_DELIVERY_ENABLED=False,
        SES_SENDER_EMAIL="test@example.com",
        SES_ADMIN_EMAIL="admin@example.com",
        LOCAL_OUTBOX_DIR=str(tmp_path / "outbox"),
        S3_BUCKET="",
    )
    defaults.update(overrides)
    return Settings(**defaults)


def _ses_settings(tmp_path: Path, **overrides) -> Settings:
    """Return a Settings instance that would route through SES."""
    defaults = dict(
        APP_ENV="production",
        EMAIL_DELIVERY_ENABLED=True,
        SES_SENDER_EMAIL="noreply@example.com",
        SES_ADMIN_EMAIL="admin@example.com",
        LOCAL_OUTBOX_DIR=str(tmp_path / "outbox"),
        S3_BUCKET="my-bucket",
        AWS_REGION="us-east-1",
    )
    defaults.update(overrides)
    return Settings(**defaults)


# ── local outbox tests ──────────────────────────────────────────

class TestLocalOutbox:
    def test_success_email_writes_json(self, tmp_path: Path):
        svc = EmailService(settings=_local_settings(tmp_path))
        filename = svc.send_success_email(
            recipient="parent@example.com",
            job_id="job-001",
            pdf_url="https://example.com/dl/storybook.pdf",
            book_title="Lila's Adventure",
        )

        outbox = tmp_path / "outbox"
        assert outbox.exists()
        filepath = outbox / filename
        assert filepath.exists()

        envelope = json.loads(filepath.read_text())
        assert envelope["to"] == "parent@example.com"
        assert envelope["email_type"] == "success"
        assert "job-001" in envelope["body_text"]
        assert "Lila's Adventure" in envelope["subject"]
        assert "https://example.com/dl/storybook.pdf" in envelope["body_text"]

    def test_failure_email_writes_json(self, tmp_path: Path):
        svc = EmailService(settings=_local_settings(tmp_path))
        filename = svc.send_failure_email(
            recipient="parent@example.com",
            job_id="job-002",
            error_message="Vision step timed out",
        )

        filepath = (tmp_path / "outbox") / filename
        envelope = json.loads(filepath.read_text())
        assert envelope["email_type"] == "failure"
        assert "Vision step timed out" in envelope["body_text"]
        assert envelope["job_id"] == "job-002"

    def test_admin_failure_alert_writes_json(self, tmp_path: Path):
        svc = EmailService(settings=_local_settings(tmp_path))
        filename = svc.send_admin_failure_alert(
            job_id="job-003",
            error_message="OOM",
        )

        assert filename is not None
        filepath = (tmp_path / "outbox") / filename
        envelope = json.loads(filepath.read_text())
        assert envelope["to"] == "admin@example.com"
        assert envelope["email_type"] == "admin_failure"

    def test_admin_alert_skipped_when_no_admin_email(self, tmp_path: Path):
        svc = EmailService(
            settings=_local_settings(tmp_path, SES_ADMIN_EMAIL="")
        )
        result = svc.send_admin_failure_alert(job_id="job-004")
        assert result is None

    def test_success_email_without_pdf_url(self, tmp_path: Path):
        svc = EmailService(settings=_local_settings(tmp_path))
        filename = svc.send_success_email(
            recipient="parent@example.com",
            job_id="job-005",
        )
        filepath = (tmp_path / "outbox") / filename
        envelope = json.loads(filepath.read_text())
        assert "status page" in envelope["body_text"]

    def test_outbox_dir_created_automatically(self, tmp_path: Path):
        deep_outbox = tmp_path / "a" / "b" / "outbox"
        svc = EmailService(
            settings=_local_settings(tmp_path, LOCAL_OUTBOX_DIR=str(deep_outbox))
        )
        svc.send_success_email(
            recipient="p@example.com", job_id="job-006"
        )
        assert deep_outbox.exists()
        assert len(list(deep_outbox.iterdir())) == 1


# ── SES backend tests ──────────────────────────────────────────

class TestSESBackend:
    @patch("app.services.email.boto3")
    def test_success_email_calls_ses(self, mock_boto3, tmp_path: Path):
        mock_client = MagicMock()
        mock_client.send_email.return_value = {"MessageId": "ses-msg-001"}
        mock_boto3.client.return_value = mock_client

        svc = EmailService(settings=_ses_settings(tmp_path))
        msg_id = svc.send_success_email(
            recipient="parent@example.com",
            job_id="job-010",
            pdf_url="https://cdn.example.com/storybook.pdf",
        )

        assert msg_id == "ses-msg-001"
        mock_boto3.client.assert_called_once_with("ses", region_name="us-east-1")
        call_kwargs = mock_client.send_email.call_args[1]
        assert call_kwargs["Source"] == "noreply@example.com"
        assert call_kwargs["Destination"]["ToAddresses"] == ["parent@example.com"]
        assert "storybook.pdf" in call_kwargs["Message"]["Body"]["Text"]["Data"]

    @patch("app.services.email.boto3")
    def test_failure_email_calls_ses(self, mock_boto3, tmp_path: Path):
        mock_client = MagicMock()
        mock_client.send_email.return_value = {"MessageId": "ses-msg-002"}
        mock_boto3.client.return_value = mock_client

        svc = EmailService(settings=_ses_settings(tmp_path))
        msg_id = svc.send_failure_email(
            recipient="parent@example.com",
            job_id="job-011",
            error_message="crash",
        )
        assert msg_id == "ses-msg-002"

    @patch("app.services.email.boto3")
    def test_ses_error_raises_email_delivery_error(self, mock_boto3, tmp_path: Path):
        from botocore.exceptions import ClientError

        mock_client = MagicMock()
        mock_client.send_email.side_effect = ClientError(
            {"Error": {"Code": "MessageRejected", "Message": "bad"}},
            "SendEmail",
        )
        mock_boto3.client.return_value = mock_client

        svc = EmailService(settings=_ses_settings(tmp_path))
        with pytest.raises(EmailDeliveryError, match="SES send failed"):
            svc.send_success_email(
                recipient="parent@example.com",
                job_id="job-012",
            )


# ── routing logic tests ────────────────────────────────────────

class TestRouting:
    def test_falls_back_to_local_when_disabled(self, tmp_path: Path):
        """Even with ses_sender_email set, disabled flag → local outbox."""
        svc = EmailService(settings=_local_settings(tmp_path))
        filename = svc.send_success_email(
            recipient="p@example.com", job_id="job-020"
        )
        assert filename.endswith(".json")
        assert (tmp_path / "outbox" / filename).exists()

    def test_falls_back_to_local_when_no_sender(self, tmp_path: Path):
        """email_delivery_enabled but no sender → local outbox."""
        svc = EmailService(
            settings=_local_settings(
                tmp_path, EMAIL_DELIVERY_ENABLED=True, SES_SENDER_EMAIL=""
            )
        )
        filename = svc.send_success_email(
            recipient="p@example.com", job_id="job-021"
        )
        assert filename.endswith(".json")
