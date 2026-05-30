"""Vision service — describes family photos for storybook generation."""

from __future__ import annotations

import base64
import json
import os
from typing import TYPE_CHECKING

from openai import OpenAI, OpenAIError

from app.config import get_settings
from app.logging_config import get_logger
from app.models.story import ImageDescription, ImageDescriptionSet
from app.prompts.vision_prompt import (
    VISION_SYSTEM_PROMPT,
    build_user_content,
    format_character_context,
)

if TYPE_CHECKING:
    from app.models.requests import StorybookRequest
    from app.services.image_utils import DecodedImage

LOGGER = get_logger(__name__)


# ── public entry point ──────────────────────────────────────────────────

def describe_images(
    request: StorybookRequest,
    decoded_images: list[DecodedImage],
    *,
    client: OpenAI | None = None,
) -> ImageDescriptionSet:
    """Return an ``ImageDescriptionSet`` with one description per image.

    Parameters
    ----------
    request:
        The full storybook request (used for character context).
    decoded_images:
        Pre-decoded JPEG images produced by ``image_utils.decode_media_item``.
    client:
        Optional pre-built OpenAI client (useful for testing).
    """
    settings = get_settings()

    if settings.use_mock_ai:
        LOGGER.info("vision mock mode — returning deterministic descriptions")
        return _mock_descriptions(decoded_images)

    return _openai_descriptions(request, decoded_images, settings, client)


# ── mock path ───────────────────────────────────────────────────────────

def _mock_descriptions(decoded_images: list[DecodedImage]) -> ImageDescriptionSet:
    """Return one deterministic description per image (test/dev only)."""
    descriptions = [
        ImageDescription(
            image_id=img.image_id,
            setting="A sunny outdoor scene",
            subjects=["A person smiling at the camera"],
            actions="Standing and smiling",
            notable_objects=["a colourful umbrella"],
            mood="joyful",
            colors_and_light="Bright daylight with warm tones",
        )
        for img in decoded_images
    ]
    return ImageDescriptionSet(descriptions=descriptions)


# ── OpenAI path ─────────────────────────────────────────────────────────

def _openai_descriptions(
    request: StorybookRequest,
    decoded_images: list[DecodedImage],
    settings,
    client: OpenAI | None,
) -> ImageDescriptionSet:
    """Call the OpenAI multimodal chat endpoint and parse the response."""

    if client is None:
        api_key = settings.openai_api_key
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        client = OpenAI(
            api_key=api_key,
            max_retries=settings.openai_max_retries,
        )

    # Build data URLs — never log these.
    image_ids: list[str] = []
    data_urls: list[str] = []
    for img in decoded_images:
        image_ids.append(img.image_id)
        b64 = base64.b64encode(img.data).decode("ascii")
        data_urls.append(f"data:{img.mime_type};base64,{b64}")

    character_context = format_character_context(
        [ch.model_dump() for ch in request.characters],
    )

    user_content = build_user_content(
        image_ids,
        data_urls,
        character_context=character_context,
    )

    LOGGER.info(
        "calling OpenAI vision model",
        extra={"model": settings.openai_vision_model, "image_count": len(decoded_images)},
    )

    try:
        response = client.chat.completions.create(
            model=settings.openai_vision_model,
            messages=[
                {"role": "system", "content": VISION_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            temperature=0.3,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
    except OpenAIError as exc:
        LOGGER.error("OpenAI vision API error: %s", exc)
        raise RuntimeError(f"OpenAI vision API call failed: {exc}") from exc

    raw_text = response.choices[0].message.content
    if not raw_text:
        raise RuntimeError("OpenAI vision returned an empty response.")

    LOGGER.info("OpenAI vision response received, parsing JSON")

    try:
        parsed = json.loads(raw_text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"OpenAI vision returned invalid JSON: {exc}") from exc

    # Validate through Pydantic
    try:
        result = ImageDescriptionSet.model_validate(parsed)
    except Exception as exc:
        raise RuntimeError(
            f"OpenAI vision output failed schema validation: {exc}"
        ) from exc

    # Sanity check: one description per image
    if len(result.descriptions) != len(decoded_images):
        LOGGER.warning(
            "vision description count mismatch: expected %d, got %d",
            len(decoded_images),
            len(result.descriptions),
        )

    return result


__all__ = ["describe_images"]
