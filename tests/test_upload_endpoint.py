from __future__ import annotations

import base64
import io
import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app.config import get_settings
from app.logging_config import JsonFormatter
from app.main import app
from app.services.job_runner import process_storybook_job
from app.services.job_store import JobStore


@pytest.fixture(autouse=True)
def clear_settings_cache(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    defaults = {
        "APP_NAME": "Family Storybook API",
        "APP_ENV": "local",
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
        "MAX_IMAGES_PER_JOB": "3",
        "MAX_SINGLE_IMAGE_BYTES": "500000",
        "MAX_TOTAL_IMAGE_BYTES": "1500000",
        "MAX_REQUEST_BYTES": "2000000",
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


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, raise_server_exceptions=False)


@pytest.fixture
def tiny_jpeg_base64() -> str:
    image = Image.new("RGB", (2, 2), color=(255, 0, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


@pytest.fixture
def tiny_png_base64() -> str:
    image = Image.new("RGB", (2, 2), color=(0, 255, 0))
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


@pytest.fixture
def valid_payload(tiny_jpeg_base64: str) -> dict[str, object]:
    return {
        "parent_email": "parent@example.com",
        "book_options": {"theme": "ocean adventure"},
        "characters": [{"name": "Roman", "role": "hero", "traits": ["brave"]}],
        "core_values": ["courage"],
        "media": [
            {
                "id": "img-1",
                "original_media_type": "photo",
                "mime_type": "image/jpeg",
                "data_base64": tiny_jpeg_base64,
            }
        ],
    }


# ---------------------------------------------------------------------------
# Basic health / version
# ---------------------------------------------------------------------------

def test_healthz(client: TestClient) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_version(client: TestClient) -> None:
    response = client.get("/version")
    assert response.status_code == 200
    assert response.json() == {
        "app_name": "Family Storybook API",
        "environment": "local",
        "version": "0.1.0",
    }


# ---------------------------------------------------------------------------
# API key authentication (constant-time via hmac.compare_digest)
# ---------------------------------------------------------------------------

def test_api_key_allows_when_disabled(client: TestClient) -> None:
    response = client.get("/v1/protected/ping")
    assert response.status_code == 200
    assert response.json() == {"status": "authorized"}


def test_api_key_rejection_when_enabled_missing_header(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQUIRE_API_KEY", "true")
    monkeypatch.setenv("API_KEY", "expected-key")
    get_settings.cache_clear()

    response = client.get("/v1/protected/ping")
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing API key."}


def test_api_key_rejects_wrong_key(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """Constant-time compare must still reject a wrong key."""
    monkeypatch.setenv("REQUIRE_API_KEY", "true")
    monkeypatch.setenv("API_KEY", "expected-key")
    get_settings.cache_clear()

    response = client.get("/v1/protected/ping", headers={"X-Storybook-Api-Key": "wrong-key"})
    assert response.status_code == 401
    assert response.json() == {"detail": "Invalid or missing API key."}


def test_api_key_accepts_valid_header_when_enabled(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("REQUIRE_API_KEY", "true")
    monkeypatch.setenv("API_KEY", "expected-key")
    get_settings.cache_clear()

    response = client.get("/v1/protected/ping", headers={"X-Storybook-Api-Key": "expected-key"})
    assert response.status_code == 200


def test_api_key_rejects_when_server_key_empty(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    """If the server has no API_KEY configured but require_api_key is true, reject all."""
    monkeypatch.setenv("REQUIRE_API_KEY", "true")
    monkeypatch.setenv("API_KEY", "")
    get_settings.cache_clear()

    response = client.get("/v1/protected/ping", headers={"X-Storybook-Api-Key": ""})
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Request size guard
# ---------------------------------------------------------------------------

def test_content_length_guard_returns_413(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_REQUEST_BYTES", "5")
    get_settings.cache_clear()

    response = client.post("/v1/protected/ping", content=b"{}", headers={"content-length": "6"})
    assert response.status_code == 413
    assert response.json() == {"detail": "Request body too large."}


# ---------------------------------------------------------------------------
# Upload / storybook creation
# ---------------------------------------------------------------------------

def test_valid_upload_returns_processing(client: TestClient, valid_payload: dict[str, object]) -> None:
    response = client.post("/v1/storybooks", json=valid_payload)
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "processing"
    assert body["job_id"]
    assert body["status_url"].startswith("/v1/jobs/")


def test_png_upload_accepted(client: TestClient, valid_payload: dict[str, object], tiny_png_base64: str) -> None:
    """PNG images should be accepted and re-encoded to JPEG."""
    valid_payload["media"][0]["mime_type"] = "image/png"
    valid_payload["media"][0]["data_base64"] = tiny_png_base64
    response = client.post("/v1/storybooks", json=valid_payload)
    assert response.status_code == 200


def test_get_status_returns_job(client: TestClient, valid_payload: dict[str, object]) -> None:
    create = client.post("/v1/storybooks", json=valid_payload)
    job_id = create.json()["job_id"]

    response = client.get(f"/v1/jobs/{job_id}")
    assert response.status_code == 200
    assert response.json()["job_id"] == job_id
    # Background task may fail in test env (no S3/AI) — any terminal state is fine.
    assert response.json()["status"] in {"queued", "processing", "succeeded", "failed"}


def test_missing_api_key_returns_401_when_enabled(
    client: TestClient, valid_payload: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("REQUIRE_API_KEY", "true")
    monkeypatch.setenv("API_KEY", "expected-key")
    get_settings.cache_clear()

    response = client.post("/v1/storybooks", json=valid_payload)
    assert response.status_code == 401


# ---------------------------------------------------------------------------
# Image count / size limits (413)
# ---------------------------------------------------------------------------

def test_too_many_images_returns_413(client: TestClient, valid_payload: dict[str, object], tiny_jpeg_base64: str) -> None:
    valid_payload["media"] = [
        {
            "id": f"img-{i}",
            "original_media_type": "photo",
            "mime_type": "image/jpeg",
            "data_base64": tiny_jpeg_base64,
        }
        for i in range(1, 5)
    ]
    response = client.post("/v1/storybooks", json=valid_payload)
    assert response.status_code == 413


def test_oversized_single_image_returns_413(
    client: TestClient, valid_payload: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("MAX_SINGLE_IMAGE_BYTES", "10")
    get_settings.cache_clear()
    response = client.post("/v1/storybooks", json=valid_payload)
    assert response.status_code == 413


# ---------------------------------------------------------------------------
# Image validation (400) — format, corruption, base64
# ---------------------------------------------------------------------------

def test_bad_base64_returns_400(client: TestClient, valid_payload: dict[str, object]) -> None:
    valid_payload["media"][0]["data_base64"] = "not-valid-base64***"
    response = client.post("/v1/storybooks", json=valid_payload)
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid base64 image payload."}


def test_unsupported_mime_type_returns_422(client: TestClient, valid_payload: dict[str, object]) -> None:
    """The Pydantic model restricts mime_type to image/jpeg|image/png, so
    sending an unsupported type should be rejected at validation time (422)."""
    valid_payload["media"][0]["mime_type"] = "image/webp"
    response = client.post("/v1/storybooks", json=valid_payload)
    assert response.status_code == 422


def test_corrupt_image_returns_400(client: TestClient, valid_payload: dict[str, object]) -> None:
    """Valid base64 but not a real image."""
    valid_payload["media"][0]["data_base64"] = base64.b64encode(b"this is not an image").decode()
    response = client.post("/v1/storybooks", json=valid_payload)
    assert response.status_code == 400
    assert "Corrupt" in response.json()["detail"] or "unsupported" in response.json()["detail"]


def test_gif_disguised_as_jpeg_rejected(client: TestClient, valid_payload: dict[str, object]) -> None:
    """A GIF image with a declared JPEG mime_type should be rejected at the
    actual-format check (defense in depth)."""
    gif_img = Image.new("RGB", (2, 2), color=(0, 0, 255))
    buf = io.BytesIO()
    gif_img.save(buf, format="GIF")
    gif_b64 = base64.b64encode(buf.getvalue()).decode()

    valid_payload["media"][0]["data_base64"] = gif_b64
    valid_payload["media"][0]["mime_type"] = "image/jpeg"
    response = client.post("/v1/storybooks", json=valid_payload)
    assert response.status_code == 400
    assert "GIF" in response.json()["detail"]


# ---------------------------------------------------------------------------
# Job store — base64 not persisted
# ---------------------------------------------------------------------------

def test_base64_stripped_from_stored_job(client: TestClient, valid_payload: dict[str, object]) -> None:
    """After creating a storybook job, the stored request_json must not
    contain raw base64 image data — only the '[stripped]' placeholder."""
    response = client.post("/v1/storybooks", json=valid_payload)
    job_id = response.json()["job_id"]

    store = JobStore(get_settings().job_store_path)
    job = store.get_job(job_id)
    assert job is not None
    for media_item in job.request_json.get("media", []):
        assert media_item.get("data_base64") == "[stripped]"


def test_job_row_created_in_sqlite(client: TestClient, valid_payload: dict[str, object]) -> None:
    response = client.post("/v1/storybooks", json=valid_payload)
    job_id = response.json()["job_id"]
    store = JobStore(get_settings().job_store_path)
    job = store.get_job(job_id)
    assert job is not None
    assert job.job_id == job_id
    assert job.request_json["parent_email"] == "parent@example.com"
    # Background task may fail in test env (no S3/AI) — any terminal state is fine.
    assert job.status in {"queued", "processing", "succeeded", "failed"}


# ---------------------------------------------------------------------------
# Job status
# ---------------------------------------------------------------------------

def test_unknown_job_returns_404(client: TestClient) -> None:
    response = client.get("/v1/jobs/does-not-exist")
    assert response.status_code == 404


def test_background_runner_marks_failed_for_unknown_job() -> None:
    with pytest.raises(ValueError):
        process_storybook_job("missing-job-id")


def test_background_runner_can_mark_job_failed(monkeypatch: pytest.MonkeyPatch, valid_payload: dict[str, object]) -> None:
    store = JobStore(get_settings().job_store_path)
    job = store.create_job("job-fail-1", "queued", valid_payload)
    assert job.status == "queued"

    original_update = JobStore.update_job_status

    def boom(self, job_id: str, status: str):
        original_update(self, job_id, status)
        raise RuntimeError("forced failure")

    monkeypatch.setattr(JobStore, "update_job_status", boom)
    process_storybook_job("job-fail-1")
    failed_job = JobStore(get_settings().job_store_path).get_job("job-fail-1")
    assert failed_job is not None
    assert failed_job.status == "failed"
    assert "forced failure" in (failed_job.error_message or "")


# ---------------------------------------------------------------------------
# Logging — redaction & structured fields
# ---------------------------------------------------------------------------

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


def test_json_formatter_redacts_presigned_url_marker() -> None:
    """Messages mentioning 'presigned' should be fully redacted."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="generated presigned url https://s3.amazonaws.com/bucket/key?token=secret",
        args=(),
        exc_info=None,
    )
    payload = json.loads(formatter.format(record))
    assert payload["message"] == "[redacted-sensitive-log-message]"


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


def test_json_formatter_includes_status() -> None:
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="storybook",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="job status changed",
        args=(),
        exc_info=None,
    )
    record.job_id = "job-456"
    record.status = "succeeded"
    payload = json.loads(formatter.format(record))
    assert payload["job_id"] == "job-456"
    assert payload["status"] == "succeeded"


def test_json_formatter_redacts_image_bytes_marker() -> None:
    """Messages containing 'image_bytes' should be redacted."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="wrote 1234 image_bytes to disk",
        args=(),
        exc_info=None,
    )
    payload = json.loads(formatter.format(record))
    assert payload["message"] == "[redacted-sensitive-log-message]"


def test_json_formatter_includes_event_and_duration() -> None:
    """Formatter propagates event and duration_ms extras."""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="runner",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="job lifecycle",
        args=(),
        exc_info=None,
    )
    record.job_id = "job-789"
    record.event = "job_succeeded"
    record.status = "succeeded"
    record.duration_ms = 4321
    payload = json.loads(formatter.format(record))
    assert payload["event"] == "job_succeeded"
    assert payload["duration_ms"] == 4321


def test_json_formatter_redacts_full_urls() -> None:
    """Presigned URLs in messages are truncated to scheme://host/…"""
    formatter = JsonFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="download at https://bucket.s3.amazonaws.com/storybook/abc/out.pdf?X-Amz-Signature=secret",
        args=(),
        exc_info=None,
    )
    payload = json.loads(formatter.format(record))
    assert "secret" not in payload["message"]
    assert "https://bucket.s3.amazonaws.com/\u2026" in payload["message"]


def test_json_formatter_includes_exc_info() -> None:
    """Exception info is serialized in the 'exc' field."""
    import sys
    formatter = JsonFormatter()
    try:
        raise RuntimeError("boom")
    except RuntimeError:
        exc_info = sys.exc_info()
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="something failed",
        args=(),
        exc_info=exc_info,
    )
    payload = json.loads(formatter.format(record))
    assert "exc" in payload
    assert any("RuntimeError" in line for line in payload["exc"])


def test_runner_stores_concise_error(monkeypatch: pytest.MonkeyPatch, valid_payload: dict[str, object]) -> None:
    """Runner stores concise error_message without stack traces."""
    store = JobStore(get_settings().job_store_path)
    store.create_job("job-concise-1", "queued", valid_payload)

    original_update = JobStore.update_job_status

    def boom(self, job_id: str, status: str):
        original_update(self, job_id, status)
        raise RuntimeError("something specific went wrong")

    monkeypatch.setattr(JobStore, "update_job_status", boom)
    process_storybook_job("job-concise-1")
    job = JobStore(get_settings().job_store_path).get_job("job-concise-1")
    assert job is not None
    assert job.status == "failed"
    assert "RuntimeError" in job.error_message
    assert "something specific went wrong" in job.error_message
    assert "Traceback" not in (job.error_message or "")


def test_get_job_returns_error_message_for_failed_job(
    client: TestClient, valid_payload: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    """GET /v1/jobs/{id} returns error_message for failed jobs."""
    store = JobStore(get_settings().job_store_path)
    store.create_job("job-api-fail", "queued", valid_payload)

    original_update = JobStore.update_job_status

    def boom(self, job_id: str, status: str):
        original_update(self, job_id, status)
        raise RuntimeError("api visible error")

    monkeypatch.setattr(JobStore, "update_job_status", boom)
    process_storybook_job("job-api-fail")

    response = client.get("/v1/jobs/job-api-fail")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "failed"
    assert body["error_message"] is not None
    assert "api visible error" in body["error_message"]
    assert "job_id" in body
    assert "created_at" in body
    assert "updated_at" in body
