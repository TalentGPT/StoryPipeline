from __future__ import annotations

from pathlib import Path

import boto3

from app.config import get_settings
from app.logging_config import get_logger

LOGGER = get_logger(__name__)
LOCAL_PREFIX = "local://"


class StorageService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def upload_pdf_bytes(self, job_id: str, pdf_bytes: bytes) -> str:
        if self.settings.app_env == "local" and not self.settings.s3_bucket:
            output_dir = Path(self.settings.work_dir) / job_id
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / "storybook.pdf"
            output_path.write_bytes(pdf_bytes)
            return f"{LOCAL_PREFIX}{output_path.as_posix()}"

        s3_key = self._make_s3_key(job_id)
        client = boto3.client("s3", region_name=self.settings.aws_region)
        client.put_object(
            Bucket=self.settings.s3_bucket,
            Key=s3_key,
            Body=pdf_bytes,
            ContentType="application/pdf",
            Metadata={
                "job_id": job_id,
                "app_name": self.settings.app_name,
            },
        )
        LOGGER.info("storybook pdf uploaded", extra={"job_id": job_id})
        return s3_key

    def generate_download_url(self, s3_key: str) -> str:
        if s3_key.startswith(LOCAL_PREFIX):
            return s3_key

        client = boto3.client("s3", region_name=self.settings.aws_region)
        url = client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.settings.s3_bucket, "Key": s3_key},
            ExpiresIn=self.settings.download_url_expires_seconds,
        )
        LOGGER.info("storybook download url generated", extra={"job_id": "n/a"})
        return url

    def _make_s3_key(self, job_id: str) -> str:
        prefix = self.settings.s3_prefix.strip("/")
        return f"{prefix}/{job_id}/storybook.pdf"


__all__ = ["StorageService", "LOCAL_PREFIX"]
