from contextlib import asynccontextmanager

from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.config import Settings, get_settings
from app.dependencies import validate_api_key
from app.logging_config import configure_logging

APP_VERSION = "0.1.0"


@asynccontextmanager
async def lifespan(_: FastAPI):
    configure_logging()
    yield


v1_router = APIRouter(prefix="/v1")


@v1_router.get("/protected/ping", dependencies=[Depends(validate_api_key)])
def protected_ping() -> dict[str, str]:
    return {"status": "authorized"}


async def request_size_guard(request: Request, call_next):
    settings = get_settings()
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            if int(content_length) > settings.max_request_bytes:
                raise HTTPException(
                    status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    detail="Request body too large.",
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
