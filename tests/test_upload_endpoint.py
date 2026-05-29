from __future__ import annotations

import io
import json
import logging

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.logging_config import JsonFormatter
from app.main import app


@pytest.fixture(autouse=True)
def clear_settings_cache(monkeypatch: pytest.MonkeyPatch):
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
        "S3_BUCKET": "",
        "S3_PREFIX": "storybook",
        "DOWNLOAD_URL_EXPIRES_SECONDS": "3600",
        "SES_SENDER_EMAIL": "",
        "SES_ADMIN_EMAIL": "",
        "EMAIL_DELIVERY_ENABLED": "false",
        "MAX_IMAGES_PER_JOB": "40",
        "MAX_SINGLE_IMAGE_BYTES": "10000000",
        "MAX_TOTAL_IMAGE_BYTES": "50000000",
        "MAX_REQUEST_BYTES": "55000000",
        "JOB_STORE_PATH": "data/jobs.sqlite3",
        "WORK_DIR": "data/work",
        "LOCAL_OUTBOX_DIR": "data/outbox",
        "PDF_PAGE_SIZE": "8.5in 8.5in",
        "PDF_MARGIN": "0.5in",
    }
    for key, value in defaults.items():
        monkeypatch.setenv(key, value)
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version(client: TestClient) -> None:
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {
        "app_name": "Family Storybook API",
        "environment": "test",
        "version": "0.1.0",
    }


def test_api_key_allows_when_disabled(client: TestClient) -> None:
    response = client.get("/v1/protected/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "authorized"}


def test_api_key_rejection_when_enabled_missing_header(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REQUIRE_API_KEY", "true")
    monkeypatch.setenv("API_KEY", "expected-key")
    get_settings.cache_clear()

    response = client.get("/v1/protected/ping")
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing API key."}


def test_api_key_accepts_valid_header_when_enabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REQUIRE_API_KEY", "true")
    monkeypatch.setenv("API_KEY", "expected-key")
    get_settings.cache_clear()

    response = client.get(
        "/v1/protected/ping",
        headers={"X-Storybook-Api-Key": "expected-key"},
    )
    assert response.status_code == 200
    assert response.json() == {"status": "authorized"}


def test_content_length_guard_returns_413(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAX_REQUEST_BYTES", "5")
    get_settings.cache_clear()

    response = client.post(
        "/v1/protected/ping",
        content=b"{}",
        headers={"content-length": "6"},
    )
    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large."}


def test_json_formatter_redacts_sensitive_message() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="received base64 image data with API_KEY and parent@example.com",
        args=(),
        exc_info=None,
    )
    payload = json.loads(formatter.format(record))
    assert payload["message"] == "[redacted-sensitive-log-message]"
    assert "base64" not in payload["message"]


def test_json_formatter_includes_job_id() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="storybook",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="job started",
        args=(),
        exc_info=None,
    )
    record.job_id = "job-123"
    payload = json.loads(formatter.format(record))
    assert payload["job_id"] == "job-123"
    assert payload["message"] == "job started"
