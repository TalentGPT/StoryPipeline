"""Story generation service — produces a StoryBook from image descriptions.

The public entry point ``generate_storybook_with_retries`` implements a
generate → validate → critic → revise retry loop, raising
``StoryGenerationError`` if all attempts are exhausted.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from pydantic import ValidationError
from openai import OpenAI, OpenAIError

from app.config import get_settings
from app.logging_config import get_logger
from app.models.story import StoryBook, StoryCharacter, StoryPage
from app.prompts.story_prompt import build_story_prompt
from app.prompts.critic_prompt import build_critic_prompt
from app.services.story_validation import validate_storybook

if TYPE_CHECKING:
    from app.models.requests import StorybookRequest
    from app.models.story import ImageDescriptionSet

LOGGER = get_logger(__name__)


# ── custom exception ────────────────────────────────────────────────────

class StoryGenerationError(Exception):
    """Raised when story generation fails after all retry attempts."""


# ── critic result model ─────────────────────────────────────────────────

class CriticVerdict:
    """Parsed critic response."""

    __slots__ = ("passes", "issues", "revision_instructions")

    def __init__(self, passes: bool, issues: list[dict], revision_instructions: str):
        self.passes = passes
        self.issues = issues
        self.revision_instructions = revision_instructions

    @classmethod
    def from_json(cls, raw: str) -> CriticVerdict:
        data = json.loads(raw)
        return cls(
            passes=bool(data.get("passes", False)),
            issues=data.get("issues", []),
            revision_instructions=data.get("revision_instructions", ""),
        )

    @property
    def major_count(self) -> int:
        return sum(1 for i in self.issues if i.get("severity") == "major")

    @property
    def minor_count(self) -> int:
        return sum(1 for i in self.issues if i.get("severity") == "minor")

    def summary(self) -> str:
        if self.passes:
            return f"pass ({self.minor_count} minor)"
        return f"fail ({self.major_count} major, {self.minor_count} minor)"


# ── public entry points ─────────────────────────────────────────────────

def generate_storybook_with_retries(
    request: StorybookRequest,
    image_description_set: ImageDescriptionSet,
    *,
    client: OpenAI | None = None,
    job_id: str = "",
) -> StoryBook:
    """Generate a ``StoryBook`` with a validate → critic → revise retry loop.

    Flow per attempt:
        1. Generate candidate JSON (LLM or mock)
        2. Parse with Pydantic
        3. Run ``validate_storybook`` (deterministic structural checks)
        4. Run LLM critic (skipped in mock mode)
        5. If critic fails with major issues → revise and retry

    Raises ``StoryGenerationError`` if all retries are exhausted.
    """
    settings = get_settings()
    max_retries = settings.openai_max_retries

    if settings.use_mock_ai:
        LOGGER.info("story generation mock mode", extra={"job_id": job_id})
        story = _mock_storybook(request, image_description_set)
        # Run structural validation even in mock mode for consistency
        vr = validate_storybook(story, image_description_set)
        LOGGER.info(
            "mock validation: %s", vr.summary(),
            extra={"job_id": job_id},
        )
        return story

    return _openai_generate_with_retries(
        request, image_description_set, settings, client,
        max_retries=max_retries, job_id=job_id,
    )


def generate_storybook(
    request: StorybookRequest,
    image_description_set: ImageDescriptionSet,
    *,
    client: OpenAI | None = None,
) -> StoryBook:
    """Legacy entry point — delegates to ``generate_storybook_with_retries``."""
    return generate_storybook_with_retries(
        request, image_description_set, client=client,
    )


# ── mock path ───────────────────────────────────────────────────────────

def _mock_storybook(
    request: StorybookRequest,
    image_description_set: ImageDescriptionSet,
) -> StoryBook:
    """Return a deterministic mock storybook with one page per image."""
    descriptions = image_description_set.descriptions

    characters = [
        StoryCharacter(
            name=ch.name,
            story_role=ch.role,
            magical_description=(
                f"A {', '.join(ch.traits[:2])} {ch.role}" if ch.traits else f"A {ch.role}"
            ),
        )
        for ch in request.characters
    ]

    pages = [
        StoryPage(
            page_number=i + 1,
            source_image_id=desc.image_id,
            real_memory_anchor=f"The photo shows {desc.setting.lower()}.",
            fantasy_transformation=(
                f"The {desc.setting.lower()} transforms into an enchanted realm."
            ),
            value_focus=[request.core_values[i % len(request.core_values)]],
            text=[
                f"Once upon a time, our heroes arrived at a magical {desc.setting.lower()}.",
                f"They felt {desc.mood} as they explored together.",
            ],
            illustration_note=(
                f"Wide shot of {desc.setting.lower()} with fantasy elements. "
                f"Mood: {desc.mood}."
            ),
        )
        for i, desc in enumerate(descriptions)
    ]

    return StoryBook(
        title=request.book_options.title_hint or "A Magical Adventure",
        subtitle=f"A tale of {request.book_options.theme}",
        dedication=request.book_options.dedication,
        theme=request.book_options.theme,
        reading_age="5-7",
        characters=characters,
        moral_summary=(
            f"A story about {', '.join(request.core_values[:3])}."
        ),
        pages=pages,
        closing_note="The end — and the adventure continues every day!",
    )


# ── OpenAI retry loop ──────────────────────────────────────────────────

def _openai_generate_with_retries(
    request: StorybookRequest,
    image_description_set: ImageDescriptionSet,
    settings,
    client: OpenAI | None,
    *,
    max_retries: int,
    job_id: str,
) -> StoryBook:
    """Core retry loop: generate → parse → validate → critic → revise."""

    if client is None:
        api_key = settings.openai_api_key
        if not api_key:
            raise RuntimeError("OPENAI_API_KEY is not configured.")
        client = OpenAI(
            api_key=api_key,
            max_retries=settings.openai_max_retries,
        )

    descriptions_dicts = [d.model_dump() for d in image_description_set.descriptions]
    schema_hint = json.dumps(StoryBook.model_json_schema(), indent=2)
    base_prompt = build_story_prompt(request, descriptions_dicts, schema_hint)

    revision_context: str | None = None
    last_error: str = ""

    for attempt in range(1, max_retries + 1):
        log_extra = {"job_id": job_id, "attempt": attempt, "max": max_retries}

        # ── 1. Generate candidate ───────────────────────────────────
        LOGGER.info("generating story candidate", extra=log_extra)
        try:
            raw_json = _call_story_model(
                client, settings, base_prompt,
                revision_context=revision_context,
            )
        except RuntimeError as exc:
            last_error = str(exc)
            LOGGER.warning("story API error: %s", last_error, extra=log_extra)
            revision_context = None  # reset for clean retry
            continue

        # ── 2. Pydantic parse ───────────────────────────────────────
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            last_error = f"Invalid JSON: {exc}"
            LOGGER.warning("JSON parse failure", extra=log_extra)
            revision_context = f"Your previous output was not valid JSON. Error: {exc}. Output ONLY valid JSON."
            continue

        try:
            story = StoryBook.model_validate(parsed)
        except (ValidationError, ValueError) as exc:
            last_error = f"Schema validation failed: {exc}"
            LOGGER.warning("Pydantic validation failure", extra=log_extra)
            revision_context = (
                f"Your previous output failed schema validation:\n{exc}\n\n"
                f"Fix these issues and output the corrected JSON."
            )
            continue

        # ── 3. Structural validation ────────────────────────────────
        vr = validate_storybook(story, image_description_set)
        LOGGER.info("structural validation: %s", vr.summary(), extra=log_extra)

        if not vr.passes:
            issues_text = "; ".join(
                f"[{i.severity}] {i.field}: {i.message}" for i in vr.issues
            )
            last_error = f"Structural validation failed: {issues_text}"
            revision_context = (
                f"Your story failed structural validation:\n{issues_text}\n\n"
                f"Fix all major issues and output the corrected JSON."
            )
            continue

        # ── 4. LLM critic ──────────────────────────────────────────
        LOGGER.info("running critic", extra=log_extra)
        try:
            verdict = _call_critic(
                client, settings, story, request, image_description_set,
            )
        except RuntimeError as exc:
            # Critic failure is not fatal — accept the story if structural
            # validation passed.
            LOGGER.warning(
                "critic call failed, accepting structurally valid story: %s",
                exc, extra=log_extra,
            )
            return story

        LOGGER.info("critic verdict: %s", verdict.summary(), extra=log_extra)

        if verdict.passes:
            return story

        # Critic found major issues → build revision context
        last_error = f"Critic rejected: {verdict.summary()}"
        revision_context = (
            f"A critic reviewed your story and found issues:\n"
            f"{verdict.revision_instructions}\n\n"
            f"Fix all major issues and output the corrected JSON."
        )
        # Loop continues with next attempt

    raise StoryGenerationError(
        f"Story generation failed after {max_retries} attempts. "
        f"Last error: {last_error}"
    )


# ── LLM call helpers ───────────────────────────────────────────────────

def _call_story_model(
    client: OpenAI,
    settings,
    base_prompt: str,
    *,
    revision_context: str | None = None,
) -> str:
    """Call the story generation model. Returns raw JSON string."""
    messages: list[dict[str, str]] = [
        {"role": "system", "content": base_prompt},
    ]

    if revision_context:
        messages.append({
            "role": "user",
            "content": revision_context,
        })
        messages.append({
            "role": "user",
            "content": "Write the corrected storybook now. Output ONLY the JSON object.",
        })
    else:
        messages.append({
            "role": "user",
            "content": "Write the storybook now. Output ONLY the JSON object.",
        })

    try:
        response = client.chat.completions.create(
            model=settings.openai_story_model,
            messages=messages,
            temperature=0.4,
            max_tokens=8192,
            response_format={"type": "json_object"},
        )
    except OpenAIError as exc:
        raise RuntimeError(f"OpenAI story API call failed: {exc}") from exc

    raw_text = response.choices[0].message.content
    if not raw_text:
        raise RuntimeError("OpenAI story model returned an empty response.")

    return raw_text


def _call_critic(
    client: OpenAI,
    settings,
    story: StoryBook,
    request: StorybookRequest,
    image_description_set: ImageDescriptionSet,
) -> CriticVerdict:
    """Call the critic model and return a parsed ``CriticVerdict``."""
    candidate_json = story.model_dump_json(indent=2)
    messages = build_critic_prompt(
        candidate_json,
        image_count=len(image_description_set.descriptions),
        core_values=request.core_values,
        character_names=[ch.name for ch in request.characters],
    )

    try:
        response = client.chat.completions.create(
            model=settings.openai_story_model,
            messages=messages,
            temperature=0.0,
            max_tokens=4096,
            response_format={"type": "json_object"},
        )
    except OpenAIError as exc:
        raise RuntimeError(f"Critic API call failed: {exc}") from exc

    raw = response.choices[0].message.content
    if not raw:
        raise RuntimeError("Critic returned an empty response.")

    try:
        return CriticVerdict.from_json(raw)
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise RuntimeError(f"Critic returned unparseable response: {exc}") from exc


__all__ = [
    "StoryGenerationError",
    "CriticVerdict",
    "generate_storybook",
    "generate_storybook_with_retries",
]
