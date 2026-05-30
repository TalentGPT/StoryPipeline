"""Tests for end-to-end pipeline wiring: upload → image persistence → vision → story."""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from app.config import get_settings
from app.services.image_utils import (
    DecodedImage,
    decode_media_item,
    load_decoded_images,
    save_decoded_images,
)
from app.models.requests import MediaInput


# ── fixtures ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def _clear_settings(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
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
        "MAX_IMAGES_PER_JOB": "10",
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


def _make_tiny_jpeg() -> bytes:
    img = Image.new("RGB", (4, 4), color=(100, 150, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _make_decoded(image_id: str) -> DecodedImage:
    jpeg = _make_tiny_jpeg()
    return DecodedImage(
        image_id=image_id,
        mime_type="image/jpeg",
        data=jpeg,
        width=4,
        height=4,
    )


# ── Image persistence round-trip ────────────────────────────────────────


class TestImagePersistence:
    def test_save_and_load_roundtrip(self, tmp_path: Path):
        images = [_make_decoded("img-001"), _make_decoded("img-002")]
        save_decoded_images(images, tmp_path, "job-abc")

        loaded = load_decoded_images(tmp_path, "job-abc")
        assert len(loaded) == 2
        assert loaded[0].image_id == "img-001"
        assert loaded[1].image_id == "img-002"
        assert loaded[0].data == images[0].data
        assert loaded[1].data == images[1].data
        assert loaded[0].width == 4
        assert loaded[0].mime_type == "image/jpeg"

    def test_manifest_is_valid_json(self, tmp_path: Path):
        images = [_make_decoded("img-x")]
        save_decoded_images(images, tmp_path, "job-manifest")

        manifest_path = tmp_path / "job-manifest" / "manifest.json"
        assert manifest_path.exists()
        manifest = json.loads(manifest_path.read_text())
        assert len(manifest) == 1
        assert manifest[0]["image_id"] == "img-x"
        assert manifest[0]["filename"] == "img-x.jpg"

    def test_load_missing_manifest_raises(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError, match="manifest"):
            load_decoded_images(tmp_path, "nonexistent-job")

    def test_idempotent_save(self, tmp_path: Path):
        """Saving twice to the same job dir overwrites cleanly."""
        images_v1 = [_make_decoded("img-a")]
        images_v2 = [_make_decoded("img-a"), _make_decoded("img-b")]
        save_decoded_images(images_v1, tmp_path, "job-idem")
        save_decoded_images(images_v2, tmp_path, "job-idem")

        loaded = load_decoded_images(tmp_path, "job-idem")
        assert len(loaded) == 2


# ── Upload endpoint saves images to disk ────────────────────────────────


class TestUploadSavesImages:
    def test_upload_persists_images_to_work_dir(self):
        from fastapi.testclient import TestClient
        from app.main import app

        jpeg_b64 = base64.b64encode(_make_tiny_jpeg()).decode()
        payload = {
            "parent_email": "parent@example.com",
            "book_options": {"theme": "adventure"},
            "characters": [{"name": "Hero", "role": "protagonist"}],
            "core_values": ["courage"],
            "media": [
                {
                    "id": "img-upload-1",
                    "original_media_type": "photo",
                    "mime_type": "image/jpeg",
                    "data_base64": jpeg_b64,
                },
                {
                    "id": "img-upload-2",
                    "original_media_type": "photo",
                    "mime_type": "image/jpeg",
                    "data_base64": jpeg_b64,
                },
            ],
        }

        client = TestClient(app)
        response = client.post("/v1/storybooks", json=payload)
        assert response.status_code == 200
        job_id = response.json()["job_id"]

        settings = get_settings()
        loaded = load_decoded_images(settings.work_dir, job_id)
        assert len(loaded) == 2
        assert loaded[0].image_id == "img-upload-1"
        assert loaded[1].image_id == "img-upload-2"


# ── Job runner uses vision service ──────────────────────────────────────


class TestJobRunnerVisionIntegration:
    def test_runner_calls_vision_in_mock_mode(self):
        """In mock mode, the runner should load images, call describe_images
        (which returns mock descriptions), and complete successfully."""
        from app.services.job_runner import process_storybook_job
        from app.services.job_store import JobStore

        settings = get_settings()
        job_store = JobStore(settings.job_store_path)

        # Create a job with a valid request (base64 stripped as the endpoint does)
        request_json = {
            "parent_email": "parent@example.com",
            "book_options": {"theme": "ocean adventure"},
            "characters": [{"name": "Roman", "role": "hero", "traits": ["brave"]}],
            "core_values": ["courage"],
            "media": [
                {
                    "id": "img-run-1",
                    "original_media_type": "photo",
                    "mime_type": "image/jpeg",
                    "data_base64": "[stripped]",
                },
            ],
        }
        job_store.create_job("job-vision-1", "queued", request_json)

        # Save images to work dir (as the endpoint would)
        images = [_make_decoded("img-run-1")]
        save_decoded_images(images, settings.work_dir, "job-vision-1")

        # Run the job — should complete in mock mode
        process_storybook_job("job-vision-1")

        job = job_store.get_job("job-vision-1")
        assert job is not None
        assert job.status == "succeeded"
        assert job.story_json is not None
        assert job.story_json["title"]  # story was generated

    def test_runner_fails_gracefully_when_images_missing(self):
        """If images weren't saved to work_dir, the runner should mark failed."""
        from app.services.job_runner import process_storybook_job
        from app.services.job_store import JobStore

        settings = get_settings()
        job_store = JobStore(settings.job_store_path)

        request_json = {
            "parent_email": "parent@example.com",
            "book_options": {"theme": "adventure"},
            "characters": [{"name": "Test", "role": "hero"}],
            "core_values": ["courage"],
            "media": [
                {
                    "id": "img-miss-1",
                    "original_media_type": "photo",
                    "mime_type": "image/jpeg",
                    "data_base64": "[stripped]",
                },
            ],
        }
        job_store.create_job("job-no-images", "queued", request_json)

        # Don't save images — runner should fail gracefully
        process_storybook_job("job-no-images")

        job = job_store.get_job("job-no-images")
        assert job is not None
        assert job.status == "failed"
        assert "manifest" in (job.error_message or "").lower() or "FileNotFoundError" in (job.error_message or "")

    def test_runner_uses_vision_descriptions_in_story(self):
        """Verify the vision descriptions flow into story generation output."""
        from app.services.job_runner import process_storybook_job
        from app.services.job_store import JobStore

        settings = get_settings()
        job_store = JobStore(settings.job_store_path)

        request_json = {
            "parent_email": "parent@example.com",
            "book_options": {"theme": "ocean adventure"},
            "characters": [{"name": "Roman", "role": "hero"}],
            "core_values": ["courage", "kindness"],
            "media": [
                {"id": "img-v1", "original_media_type": "photo", "mime_type": "image/jpeg", "data_base64": "[stripped]"},
                {"id": "img-v2", "original_media_type": "photo", "mime_type": "image/jpeg", "data_base64": "[stripped]"},
            ],
        }
        job_store.create_job("job-vision-flow", "queued", request_json)

        images = [_make_decoded("img-v1"), _make_decoded("img-v2")]
        save_decoded_images(images, settings.work_dir, "job-vision-flow")

        process_storybook_job("job-vision-flow")

        job = job_store.get_job("job-vision-flow")
        assert job is not None
        assert job.status == "succeeded"
        # Story should have pages matching the image IDs
        pages = job.story_json["pages"]
        assert len(pages) == 2
        page_image_ids = {p["source_image_id"] for p in pages}
        assert page_image_ids == {"img-v1", "img-v2"}
