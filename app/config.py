from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = Field(default="Family Storybook API", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    public_base_url: str = Field(default="http://localhost:8000", alias="PUBLIC_BASE_URL")
    api_key: str = Field(default="", alias="API_KEY")
    require_api_key: bool = Field(default=True, alias="REQUIRE_API_KEY")
    use_mock_ai: bool = Field(default=False, alias="USE_MOCK_AI")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_vision_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_VISION_MODEL")
    openai_story_model: str = Field(default="gpt-4.1", alias="OPENAI_STORY_MODEL")
    openai_max_retries: int = Field(default=2, alias="OPENAI_MAX_RETRIES")
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")
    s3_bucket: str = Field(default="", alias="S3_BUCKET")
    s3_prefix: str = Field(default="storybook", alias="S3_PREFIX")
    download_url_expires_seconds: int = Field(default=3600, alias="DOWNLOAD_URL_EXPIRES_SECONDS")
    ses_sender_email: str = Field(default="", alias="SES_SENDER_EMAIL")
    ses_admin_email: str = Field(default="", alias="SES_ADMIN_EMAIL")
    email_delivery_enabled: bool = Field(default=False, alias="EMAIL_DELIVERY_ENABLED")
    max_image_count: int = Field(default=40, alias="MAX_IMAGES_PER_JOB")
    max_single_image_bytes: int = Field(default=10_000_000, alias="MAX_SINGLE_IMAGE_BYTES")
    max_total_image_bytes: int = Field(default=50_000_000, alias="MAX_TOTAL_IMAGE_BYTES")
    max_request_bytes: int = Field(default=55_000_000, alias="MAX_REQUEST_BYTES")
    job_store_path: Path = Field(default=Path("data/jobs.sqlite3"), alias="JOB_STORE_PATH")
    work_dir: Path = Field(default=Path("data/work"), alias="WORK_DIR")
    local_outbox_dir: Path = Field(default=Path("data/outbox"), alias="LOCAL_OUTBOX_DIR")
    pdf_page_size: str = Field(default="8.5in 8.5in", alias="PDF_PAGE_SIZE")
    pdf_margin: str = Field(default="0.5in", alias="PDF_MARGIN")


@lru_cache
def get_settings() -> Settings:
    return Settings()
