"""Pydantic models for vision descriptions and story generation output."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


# ── Vision models (existing) ───────────────────────────────────────────

class ImageDescription(BaseModel):
    """Vision-generated description of a single family photo."""

    image_id: str = Field(
        min_length=1,
        description="Matches the media.id from the ingest request.",
    )
    setting: str = Field(
        min_length=1,
        description="Brief description of the location or environment visible in the photo.",
    )
    subjects: list[str] = Field(
        min_length=1,
        description=(
            "People visible in the photo described by appearance only "
            "(e.g. 'a child in a red shirt'). Use parent-provided names "
            "only when the request context explicitly maps them."
        ),
    )
    actions: str = Field(
        min_length=1,
        description="What the subjects appear to be doing.",
    )
    notable_objects: list[str] = Field(
        default_factory=list,
        description=(
            "Interesting objects, animals, or landmarks that could become "
            "fantasy elements in a children's story."
        ),
    )
    mood: str = Field(
        min_length=1,
        description="Overall emotional tone of the scene (e.g. 'joyful', 'peaceful').",
    )
    colors_and_light: str = Field(
        default="",
        description="Dominant colours and lighting conditions visible in the photo.",
    )


class ImageDescriptionSet(BaseModel):
    """Ordered set of image descriptions returned by the vision service."""

    descriptions: list[ImageDescription] = Field(
        min_length=1,
        description="One description per input image, in the same order.",
    )


# ── Story generation models ────────────────────────────────────────────

CANONICAL_CORE_VALUES: tuple[str, ...] = (
    "courage",
    "kindness",
    "integrity",
    "humility",
    "hard work",
    "protection of others",
    "teamwork",
    "gratitude",
    "perseverance",
)

# Words that must never appear in story text (child safety).
BANNED_SCARY_WORDS: frozenset[str] = frozenset({
    "blood", "kill", "die", "dead", "death", "murder", "weapon",
    "gun", "knife", "sword", "demon", "devil", "hell", "damn",
    "terror", "horror", "nightmare", "scream", "monster",
    "zombie", "ghost", "skeleton", "corpse", "poison", "strangle",
    "stab", "shoot", "bomb", "war", "torture", "evil",
})


class StoryCharacter(BaseModel):
    """A character appearing in the storybook."""

    name: str = Field(min_length=1, description="Character's name.")
    story_role: str = Field(min_length=1, description="Role in the story.")
    magical_description: str = Field(min_length=1, description="Short magical framing of the character.")


class StoryPage(BaseModel):
    """A single page of the storybook."""

    page_number: int = Field(ge=1, description="1-indexed page number.")
    source_image_id: str = Field(
        min_length=1,
        description="The image id this page was inspired by.",
    )
    real_memory_anchor: str = Field(
        min_length=1,
        description="Short sentence grounding the page in what the photo actually shows.",
    )
    fantasy_transformation: str = Field(
        min_length=1,
        description="How the real scene is reimagined in the fantasy world.",
    )
    value_focus: list[str] = Field(
        min_length=1,
        description="One or more canonical core values highlighted on this page.",
    )
    text: list[str] = Field(
        min_length=2,
        max_length=3,
        description="2–3 sentences of story text for this page.",
    )
    illustration_note: str = Field(
        min_length=1,
        description="Brief direction for the illustrator.",
    )

    @model_validator(mode="after")
    def _ban_scary_words(self) -> StoryPage:
        """Reject any page whose text contains banned scary words."""
        fields_to_check = [self.real_memory_anchor, self.fantasy_transformation, self.illustration_note, *self.text]
        for field_text in fields_to_check:
            lower = field_text.lower()
            for word in BANNED_SCARY_WORDS:
                if _contains_whole_word(lower, word):
                    raise ValueError(
                        f"Page {self.page_number} text contains banned word '{word}'. "
                        "Story content must be safe for ages 5–7."
                    )
        return self


class StoryBook(BaseModel):
    """Complete storybook output from the story generation model."""

    title: str = Field(min_length=1, description="Book title.")
    subtitle: str = Field(min_length=1, description="Book subtitle.")
    dedication: str | None = Field(
        default=None,
        description="Optional dedication line (e.g. 'For Roman and Beckham').",
    )
    theme: str = Field(min_length=1, description="Overall story theme.")
    reading_age: Literal["5-7"] = Field(
        default="5-7",
        description="Target reading age bracket.",
    )
    characters: list[StoryCharacter] = Field(
        min_length=1,
        description="Characters appearing in the story.",
    )
    moral_summary: str = Field(
        min_length=1,
        description="One-sentence moral or takeaway of the story.",
    )
    pages: list[StoryPage] = Field(
        min_length=1,
        description="Ordered story pages (one per source image).",
    )
    closing_note: str = Field(
        min_length=1,
        description="A warm closing note for parents/family.",
    )

    @model_validator(mode="after")
    def _validate_sequential_pages(self) -> StoryBook:
        """Ensure page numbers are sequential starting from 1."""
        expected = list(range(1, len(self.pages) + 1))
        actual = [p.page_number for p in self.pages]
        if actual != expected:
            raise ValueError(
                f"Pages must be sequentially numbered 1..{len(self.pages)}. "
                f"Got: {actual}"
            )
        return self


# ── helpers ─────────────────────────────────────────────────────────────

def _contains_whole_word(text: str, word: str) -> bool:
    """Check if *word* appears as a whole word in *text*."""
    import re
    return bool(re.search(rf"\b{re.escape(word)}\b", text))
