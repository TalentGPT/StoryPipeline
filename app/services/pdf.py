"""PDF generation service.

Renders a ``StoryBook`` model into a styled PDF using Jinja2 templates
and WeasyPrint.  Designed for private family-use storybooks (v1).
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from app.config import Settings, get_settings
from app.logging_config import get_logger
from app.models.story import StoryBook

LOGGER = get_logger(__name__)

TEMPLATE_DIR = Path(__file__).resolve().parent.parent / "templates"


def render_html(story: StoryBook, *, settings: Settings | None = None) -> str:
    """Render *story* to an HTML string using the book.html.j2 template."""
    settings = settings or get_settings()

    env = Environment(
        loader=FileSystemLoader(str(TEMPLATE_DIR)),
        autoescape=True,
    )
    template = env.get_template("book.html.j2")

    return template.render(
        title=story.title,
        subtitle=story.subtitle,
        dedication=story.dedication,
        theme=story.theme,
        reading_age=story.reading_age,
        characters=story.characters,
        moral_summary=story.moral_summary,
        pages=story.pages,
        closing_note=story.closing_note,
        page_size=settings.pdf_page_size,
        page_margin=settings.pdf_margin,
    )


def render_pdf(story: StoryBook, *, settings: Settings | None = None) -> bytes:
    """Render *story* to PDF bytes.

    Returns the raw PDF content suitable for writing to disk or uploading
    to S3.
    """
    from weasyprint import HTML  # lazy import – heavy C dependency

    settings = settings or get_settings()
    html_string = render_html(story, settings=settings)

    LOGGER.info("rendering pdf", extra={"title": story.title, "pages": len(story.pages)})

    pdf_bytes: bytes = HTML(
        string=html_string,
        base_url=str(TEMPLATE_DIR),
    ).write_pdf()

    LOGGER.info("pdf rendered", extra={"size_bytes": len(pdf_bytes)})
    return pdf_bytes


__all__ = ["render_html", "render_pdf"]
