from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.config import get_settings
from app.services.storage import LOCAL_PREFIX, StorageService


@pytest.fixture(autouse=True)
def clear_settings_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    defaults = {
        "APP_NAME": "Family Storybook API",
        "APP_ENV": "test",
        "PUBLIC_BASE_URL": "http://testserver",
        "API_KEY": "test-api-key",
        "REQUIRE_API_KEY": "false",
        "USE_MOCK_AI": "true",
        "OPENAI_API_KEY": "",
        "OPENAI_VISION_MODEL": "gpt-4.1-mini",
        "OPENAI_STORY_MODEL": "gpt-4.1",
        "OPENAI_MAX_RETRIES": "2",
        "AWS_REGION": "us-east-1",
        "S3_BUCKET": "storybook-private-bucket",
        "S3_PREFIX": "storybook",
        "DOWNLOAD_URL_EXPIRES_SECONDS": "900",
        "SES_SENDER_EMAIL": "",
        "SES_ADMIN_EMAIL": "",
        "EMAIL_DELIVERY_ENABLED": "false",
        "MAX_IMAGES_PER_JOB": "40",
        "MAX_SINGLE_IMAGE_BYTES": "10000000",
        "MAX_TOTAL_IMAGE_BYTES": "50000000",
        "MAX_REQUEST_BYTES": "55000000",
        "JOB_STORE_PATH": str(tmp_path / "jobs.sqlite3"),
        "WORK_DIR": str(tmp_path / "work"),
        "LOCAL_OUTBOX_DIR": str(tmp_path / "outbox"),
        "PDF_PAGE_SIZE": "8.5in 8.5in",
        "PDF_MARGIN": "0.5in",
    }
    for key, value in defaults.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_upload_pdf_bytes_calls_put_object(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client = MagicMock()
    monkeypatch.setattr("app.services.storage.boto3.client", lambda *args, **kwargs: mock_client)

    service = StorageService()
    s3_key = service.upload_pdf_bytes("job-123", b"fake-pdf")

    assert s3_key == "storybook/job-123/storybook.pdf"
    mock_client.put_object.assert_called_once_with(
        Bucket="storybook-private-bucket",
        Key="storybook/job-123/storybook.pdf",
        Body=b"fake-pdf",
        ContentType="application/pdf",
        Metadata={"job_id": "job-123", "app_name": "Family Storybook API"},
    )


def test_generate_download_url_uses_presigned_get(monkeypatch: pytest.MonkeyPatch) -> None:
    mock_client = MagicMock()
    mock_client.generate_presigned_url.return_value = "https://signed.example.com/file.pdf"
    monkeypatch.setattr("app.services.storage.boto3.client", lambda *args, **kwargs: mock_client)

    service = StorageService()
    url = service.generate_download_url("storybook/job-123/storybook.pdf")

    assert url == "https://signed.example.com/file.pdf"
    mock_client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "storybook-private-bucket", "Key": "storybook/job-123/storybook.pdf"},
        ExpiresIn=900,
    )


def test_local_fallback_without_aws(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("S3_BUCKET", "")
    monkeypatch.setenv("WORK_DIR", str(tmp_path / "work"))
    get_settings.cache_clear()

    service = StorageService()
    key = service.upload_pdf_bytes("job-local", b"pdf-bytes")

    assert key.startswith(LOCAL_PREFIX)
    path = Path(key.removeprefix(LOCAL_PREFIX))
    assert path.exists()
    assert path.read_bytes() == b"pdf-bytes"


def test_local_fallback_download_url_returns_local_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("S3_BUCKET", "")
    monkeypatch.setenv("WORK_DIR", str(tmp_path / "work"))
    get_settings.cache_clear()

    service = StorageService()
    local_key = service.upload_pdf_bytes("job-local-2", b"pdf-bytes")
    assert service.generate_download_url(local_key) == local_key
