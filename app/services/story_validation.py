"""Structural validation for StoryBook objects beyond Pydantic schema checks.

These validators catch semantic issues that Pydantic model_validators cannot
express (e.g. cross-referencing page image IDs against the input set).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.models.story import BANNED_SCARY_WORDS, CANONICAL_CORE_VALUES, _contains_whole_word

if TYPE_CHECKING:
    from app.models.story import ImageDescriptionSet, StoryBook


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    """A single validation finding."""

    severity: str  # "minor" | "major"
    field: str
    message: str


@dataclass(slots=True)
class ValidationResult:
    """Aggregated validation outcome."""

    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def passes(self) -> bool:
        return not any(i.severity == "major" for i in self.issues)

    def summary(self) -> str:
        if not self.issues:
            return "ok"
        majors = sum(1 for i in self.issues if i.severity == "major")
        minors = sum(1 for i in self.issues if i.severity == "minor")
        return f"{majors} major, {minors} minor"


def validate_storybook(
    story: StoryBook,
    image_description_set: ImageDescriptionSet,
) -> ValidationResult:
    """Run all structural validations and return a ``ValidationResult``.

    This is a fast, deterministic check — no LLM calls.  It covers things the
    Pydantic schema doesn't enforce:

    * Page count matches image count
    * Every ``source_image_id`` references a known image
    * No duplicate ``source_image_id`` values
    * ``reading_age`` is exactly ``"5-7"``
    * Pages are sequentially numbered
    * Each page has 2–3 sentences
    * Banned-word sweep (secondary defence after Pydantic validator)
    """
    result = ValidationResult()
    expected_ids = {d.image_id for d in image_description_set.descriptions}
    expected_count = len(image_description_set.descriptions)

    # ── page count ──────────────────────────────────────────────────
    if len(story.pages) != expected_count:
        result.issues.append(ValidationIssue(
            severity="major",
            field="pages",
            message=(
                f"Expected {expected_count} pages (one per image), "
                f"got {len(story.pages)}."
            ),
        ))

    # ── reading_age ─────────────────────────────────────────────────
    if story.reading_age != "5-7":
        result.issues.append(ValidationIssue(
            severity="major",
            field="reading_age",
            message=f"reading_age must be '5-7', got '{story.reading_age}'.",
        ))

    # ── per-page checks ────────────────────────────────────────────
    seen_image_ids: set[str] = set()
    for page in story.pages:
        prefix = f"pages[{page.page_number}]"

        # source_image_id references a real image
        if page.source_image_id not in expected_ids:
            result.issues.append(ValidationIssue(
                severity="major",
                field=f"{prefix}.source_image_id",
                message=(
                    f"source_image_id '{page.source_image_id}' does not match "
                    f"any input image. Valid IDs: {sorted(expected_ids)}"
                ),
            ))

        # no duplicate image references
        if page.source_image_id in seen_image_ids:
            result.issues.append(ValidationIssue(
                severity="major",
                field=f"{prefix}.source_image_id",
                message=f"Duplicate source_image_id '{page.source_image_id}'.",
            ))
        seen_image_ids.add(page.source_image_id)

        if not (2 <= len(page.text) <= 3):
            result.issues.append(ValidationIssue(
                severity="major",
                field=f"{prefix}.text",
                message=(
                    f"Expected 2–3 sentences, got {len(page.text)}."
                ),
            ))

        if not page.value_focus:
            result.issues.append(ValidationIssue(
                severity="major",
                field=f"{prefix}.value_focus",
                message="At least one canonical core value is required.",
            ))
        else:
            for idx, value in enumerate(page.value_focus):
                if value not in CANONICAL_CORE_VALUES:
                    result.issues.append(ValidationIssue(
                        severity="major",
                        field=f"{prefix}.value_focus[{idx}]",
                        message=(
                            f"Value '{value}' is not canonical. Allowed: {list(CANONICAL_CORE_VALUES)}"
                        ),
                    ))

        for field_name, content in {
            "real_memory_anchor": page.real_memory_anchor,
            "fantasy_transformation": page.fantasy_transformation,
            "illustration_note": page.illustration_note,
        }.items():
            lower = content.lower()
            for word in BANNED_SCARY_WORDS:
                if _contains_whole_word(lower, word):
                    result.issues.append(ValidationIssue(
                        severity="major",
                        field=f"{prefix}.{field_name}",
                        message=f"Banned word '{word}' found.",
                    ))

        for idx, sentence in enumerate(page.text):
            lower = sentence.lower()
            for word in BANNED_SCARY_WORDS:
                if _contains_whole_word(lower, word):
                    result.issues.append(ValidationIssue(
                        severity="major",
                        field=f"{prefix}.text[{idx}]",
                        message=f"Banned word '{word}' found.",
                    ))

    # ── sequential page numbering ──────────────────────────────────
    actual_nums = [p.page_number for p in story.pages]
    expected_nums = list(range(1, len(story.pages) + 1))
    if actual_nums != expected_nums:
        result.issues.append(ValidationIssue(
            severity="major",
            field="pages",
            message=(
                f"Page numbers must be sequential 1..{len(story.pages)}. "
                f"Got: {actual_nums}"
            ),
        ))

    # ── missing fields (minor) ─────────────────────────────────────
    if not story.dedication:
        result.issues.append(ValidationIssue(
            severity="minor",
            field="dedication",
            message="Dedication is empty (optional but recommended).",
        ))

    return result


__all__ = ["ValidationIssue", "ValidationResult", "validate_storybook"]
