from fastapi import Depends, Header, HTTPException, status

from app.config import Settings, get_settings

API_KEY_HEADER = "X-Storybook-Api-Key"


async def validate_api_key(
    x_storybook_api_key: str | None = Header(default=None, alias=API_KEY_HEADER),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.require_api_key:
        return

    if not x_storybook_api_key or x_storybook_api_key != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or missing API key.",
        )
