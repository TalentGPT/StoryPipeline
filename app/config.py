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

    app_env: str = Field(default="development", alias="APP_ENV")
    api_key: str = Field(default="", alias="API_KEY")
    require_api_key: bool = Field(default=True, alias="REQUIRE_API_KEY")
    use_mock_ai: bool = Field(default=False, alias="USE_MOCK_AI")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    openai_vision_model: str = Field(default="gpt-4.1-mini", alias="OPENAI_VISION_MODEL")
    openai_story_model: str = Field(default="gpt-4.1", alias="OPENAI_STORY_MODEL")
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")
    s3_bucket: str = Field(default="", alias="S3_BUCKET")
    s3_prefix: str = Field(default="storybook", alias="S3_PREFIX")
    ses_sender_email: str = Field(default="", alias="SES_SENDER_EMAIL")
    ses_admin_email: str = Field(default="", alias="SES_ADMIN_EMAIL")
    email_delivery_enabled: bool = Field(default=False, alias="EMAIL_DELIVERY_ENABLED")
    max_images_per_job: int = Field(default=40, alias="MAX_IMAGES_PER_JOB")
    max_image_bytes: int = Field(default=10_000_000, alias="MAX_IMAGE_BYTES")
    image_max_width: int = Field(default=1600, alias="IMAGE_MAX_WIDTH")
    image_max_height: int = Field(default=1600, alias="IMAGE_MAX_HEIGHT")
    jpg_quality: int = Field(default=82, alias="JPG_QUALITY")
    job_store_path: Path = Field(default=Path("data/jobs.sqlite3"), alias="JOB_STORE_PATH")
    work_dir: Path = Field(default=Path("data/work"), alias="WORK_DIR")
    local_outbox_dir: Path = Field(default=Path("data/outbox"), alias="LOCAL_OUTBOX_DIR")
    pdf_page_size: str = Field(default="8.5in 8.5in", alias="PDF_PAGE_SIZE")
    pdf_margin: str = Field(default="0.5in", alias="PDF_MARGIN")
    pdf_base_url: str = Field(default="http://localhost:8000", alias="PDF_BASE_URL")


@lru_cache
def get_settings() -> Settings:
    return Settings()
