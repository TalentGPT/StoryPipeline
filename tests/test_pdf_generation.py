"""Tests for the PDF generation service.

Verifies HTML rendering and PDF output for the StoryBook model without
requiring any external services or secrets.
"""

from __future__ import annotations

import pytest

from app.config import Settings
from app.models.story import StoryBook, StoryCharacter, StoryPage
from app.services.pdf import render_html, render_pdf


# ── Fixtures ────────────────────────────────────────────────────────────


def _make_settings(**overrides) -> Settings:
    """Build a Settings instance suitable for testing (no env/secrets)."""
    defaults = {
        "APP_ENV": "test",
        "REQUIRE_API_KEY": False,
        "API_KEY": "",
        "USE_MOCK_AI": True,
        "OPENAI_API_KEY": "",
        "S3_BUCKET": "",
    }
    defaults.update(overrides)
    return Settings(**defaults)


def _make_story(*, num_pages: int = 3, dedication: str | None = "For the family") -> StoryBook:
    """Build a minimal but valid StoryBook for testing."""
    characters = [
        StoryCharacter(
            name="Luna",
            story_role="brave explorer",
            magical_description="A curious girl with starlight in her eyes.",
        ),
        StoryCharacter(
            name="Bear",
            story_role="loyal companion",
            magical_description="A gentle bear made of morning mist.",
        ),
    ]

    pages = [
        StoryPage(
            page_number=i + 1,
            source_image_id=f"img_{i + 1}",
            real_memory_anchor=f"A warm afternoon in the park (photo {i + 1}).",
            fantasy_transformation=f"The park became an enchanted meadow full of flowers.",
            value_focus=["courage", "kindness"],
            text=[
                f"Luna and Bear walked through the sparkling meadow on page {i + 1}.",
                "The flowers hummed a gentle tune as they passed.",
                "Together they smiled, knowing the adventure had just begun.",
            ],
            illustration_note=f"Meadow scene with glowing flowers, page {i + 1}.",
        )
        for i in range(num_pages)
    ]

    return StoryBook(
        title="The Enchanted Meadow",
        subtitle="A Story of Courage and Friendship",
        dedication=dedication,
        theme="nature adventure",
        reading_age="5-7",
        characters=characters,
        moral_summary="True courage is found in kindness.",
        pages=pages,
        closing_note="Made with love for our family.",
    )


@pytest.fixture
def story() -> StoryBook:
    return _make_story()


@pytest.fixture
def settings() -> Settings:
    return _make_settings()


# ── HTML rendering tests ────────────────────────────────────────────────


class TestRenderHtml:
    def test_returns_string(self, story: StoryBook, settings: Settings) -> None:
        html = render_html(story, settings=settings)
        assert isinstance(html, str)
        assert len(html) > 0

    def test_contains_title(self, story: StoryBook, settings: Settings) -> None:
        html = render_html(story, settings=settings)
        assert "The Enchanted Meadow" in html

    def test_contains_subtitle(self, story: StoryBook, settings: Settings) -> None:
        html = render_html(story, settings=settings)
        assert "A Story of Courage and Friendship" in html

    def test_contains_dedication(self, story: StoryBook, settings: Settings) -> None:
        html = render_html(story, settings=settings)
        assert "For the family" in html

    def test_no_dedication_when_none(self, settings: Settings) -> None:
        story = _make_story(dedication=None)
        html = render_html(story, settings=settings)
        # The dedication block should not be rendered
        assert "dedication" not in html.lower() or 'class="dedication"' not in html

    def test_contains_characters(self, story: StoryBook, settings: Settings) -> None:
        html = render_html(story, settings=settings)
        assert "Luna" in html
        assert "Bear" in html
        assert "brave explorer" in html
        assert "starlight in her eyes" in html

    def test_contains_story_pages(self, story: StoryBook, settings: Settings) -> None:
        html = render_html(story, settings=settings)
        for page in story.pages:
            for paragraph in page.text:
                assert paragraph in html
            assert page.illustration_note in html

    def test_contains_closing(self, story: StoryBook, settings: Settings) -> None:
        html = render_html(story, settings=settings)
        assert "The End" in html
        assert "True courage is found in kindness." in html
        assert "Made with love for our family." in html

    def test_page_size_in_style(self, settings: Settings) -> None:
        story = _make_story()
        html = render_html(story, settings=settings)
        assert settings.pdf_page_size in html
        assert settings.pdf_margin in html

    def test_valid_html_structure(self, story: StoryBook, settings: Settings) -> None:
        html = render_html(story, settings=settings)
        assert html.strip().startswith("<!doctype html>") or html.strip().startswith("<!DOCTYPE html>")
        assert "</html>" in html

    def test_multiple_page_counts(self, settings: Settings) -> None:
        for n in (1, 5, 10):
            story = _make_story(num_pages=n)
            html = render_html(story, settings=settings)
            assert f"page {n}" in html.lower()


# ── PDF rendering tests ────────────────────────────────────────────────


class TestRenderPdf:
    def test_returns_bytes(self, story: StoryBook, settings: Settings) -> None:
        pdf = render_pdf(story, settings=settings)
        assert isinstance(pdf, bytes)
        assert len(pdf) > 0

    def test_pdf_magic_bytes(self, story: StoryBook, settings: Settings) -> None:
        pdf = render_pdf(story, settings=settings)
        assert pdf[:5] == b"%PDF-", "Output must start with PDF magic bytes"

    def test_pdf_contains_eof(self, story: StoryBook, settings: Settings) -> None:
        pdf = render_pdf(story, settings=settings)
        assert b"%%EOF" in pdf, "PDF must contain %%EOF marker"

    def test_single_page_story(self, settings: Settings) -> None:
        story = _make_story(num_pages=1)
        pdf = render_pdf(story, settings=settings)
        assert pdf[:5] == b"%PDF-"

    def test_large_story(self, settings: Settings) -> None:
        story = _make_story(num_pages=20)
        pdf = render_pdf(story, settings=settings)
        assert pdf[:5] == b"%PDF-"
        # More pages should produce a larger PDF
        small_pdf = render_pdf(_make_story(num_pages=1), settings=settings)
        assert len(pdf) > len(small_pdf)

    def test_custom_page_size(self) -> None:
        settings = _make_settings(PDF_PAGE_SIZE="letter", PDF_MARGIN="1in")
        story = _make_story(num_pages=2)
        pdf = render_pdf(story, settings=settings)
        assert pdf[:5] == b"%PDF-"
