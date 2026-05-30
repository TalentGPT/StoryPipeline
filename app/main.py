from __future__ import annotations

from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.dependencies import validate_api_key
from app.logging_config import configure_logging, get_logger
from app.models.requests import JobStatusResponse, StorybookAcceptedResponse, StorybookRequest
from app.services.image_utils import DecodedImage, InvalidImageError, decode_media_item, save_decoded_images
from app.services.job_runner import process_storybook_job
from app.services.job_store import JobStore

APP_VERSION = "0.1.0"
LOGGER = get_logger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    LOGGER.info("app lifecycle", extra={"event": "app_started", "status": "ok"})
    yield
    LOGGER.info("app lifecycle", extra={"event": "app_shutdown", "status": "ok"})


v1_router = APIRouter(prefix="/v1")


def get_job_store(settings: Settings = Depends(get_settings)) -> JobStore:
    return JobStore(settings.job_store_path)


@v1_router.get("/protected/ping", dependencies=[Depends(validate_api_key)])
def protected_ping() -> dict[str, str]:
    return {"status": "authorized"}


@v1_router.post("/storybooks", dependencies=[Depends(validate_api_key)], response_model=StorybookAcceptedResponse)
def create_storybook(
    payload: StorybookRequest,
    background_tasks: BackgroundTasks,
    settings: Settings = Depends(get_settings),
    job_store: JobStore = Depends(get_job_store),
) -> StorybookAcceptedResponse:
    if len(payload.media) > settings.max_image_count:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Too many images in request.")

    total_bytes = 0
    decoded_images: list[DecodedImage] = []
    for media in payload.media:
        try:
            decoded = decode_media_item(media)
        except InvalidImageError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

        item_size = len(decoded.data)
        if item_size > settings.max_single_image_bytes:
            raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Single image exceeds size limit.")
        total_bytes += item_size
        decoded_images.append(decoded)

    if total_bytes > settings.max_total_image_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Total image payload exceeds size limit.")

    job_id = str(uuid4())

    # Persist validated/decoded images to the work directory so the
    # background runner can load them for vision analysis.
    save_decoded_images(decoded_images, settings.work_dir, job_id)

    request_json = payload.model_dump(mode="json")
    # Strip raw base64 image data before persisting to the job store.
    # The background runner loads decoded images from the work directory.
    for media_item in request_json.get("media", []):
        media_item["data_base64"] = "[stripped]"
    job_store.create_job(job_id=job_id, status="queued", request_json=request_json)
    background_tasks.add_task(process_storybook_job, job_id)
    LOGGER.info(
        "storybook job accepted",
        extra={"job_id": job_id, "status": "queued", "image_count": len(payload.media)},
    )

    return StorybookAcceptedResponse(
        job_id=job_id,
        status="processing",
        message="Your storybook request is processing.",
        status_url=f"/v1/jobs/{job_id}",
    )


@v1_router.get("/jobs/{job_id}", dependencies=[Depends(validate_api_key)], response_model=JobStatusResponse)
def get_job_status(
    job_id: str,
    settings: Settings = Depends(get_settings),
    job_store: JobStore = Depends(get_job_store),
) -> JobStatusResponse:
    job = job_store.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")

    # Regenerate a fresh presigned URL when we have an S3 key
    pdf_url = job.pdf_url
    if job.status == "succeeded" and job.pdf_s3_key:
        from app.services.storage import StorageService

        pdf_url = StorageService().generate_download_url(job.pdf_s3_key)

    return JobStatusResponse(
        job_id=job.job_id,
        status=job.status,
        created_at=job.created_at.isoformat(),
        updated_at=job.updated_at.isoformat(),
        pdf_url=pdf_url,
        error_message=job.error_message,
    )


async def request_size_guard(request: Request, call_next):
    settings = get_settings()
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > settings.max_request_bytes:
                return JSONResponse(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    content={"detail": "Request body too large."},
                )
        except ValueError:
            pass
    return await call_next(request)


app = FastAPI(title=get_settings().app_name, version=APP_VERSION, lifespan=lifespan)
app.middleware("http")(request_size_guard)
app.include_router(v1_router)


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/version")
def version(settings: Settings = Depends(get_settings)) -> dict[str, str]:
    return {
        "app_name": settings.app_name,
        "environment": settings.app_env,
        "version": APP_VERSION,
    }


@app.exception_handler(HTTPException)
async def http_exception_handler(_: Request, exc: HTTPException) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
