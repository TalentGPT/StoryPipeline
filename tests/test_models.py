from pydantic import ValidationError

from app.models.requests import (
    BookOptions,
    CharacterInput,
    JobStatusResponse,
    MediaInput,
    StorybookAcceptedResponse,
    StorybookRequest,
)


def test_minimal_storybook_request_is_valid() -> None:
    payload = StorybookRequest(
        parent_email="parent@example.com",
        book_options=BookOptions(theme="ocean adventure"),
        characters=[CharacterInput(name="Roman", role="hero", traits=["curious", "brave"])],
        core_values=["courage", "kindness"],
        media=[
            MediaInput(
                id="img-1",
                original_media_type="photo",
                mime_type="image/jpeg",
                data_base64="ZmFrZS1iYXNlNjQ=",
            )
        ],
    )

    assert payload.parent_email == "parent@example.com"
    assert payload.book_options.reading_age == "5-7"
    assert payload.media[0].mime_type == "image/jpeg"
    assert payload.request_id


def test_bad_mime_type_is_rejected() -> None:
    try:
        MediaInput(
            id="img-2",
            original_media_type="photo",
            mime_type="image/gif",
            data_base64="ZmFrZS1iYXNlNjQ=",
        )
    except ValidationError as exc:
        assert "image/jpeg" in str(exc)
        return
    raise AssertionError("Expected ValidationError for unsupported mime type")


def test_data_uri_prefix_is_rejected() -> None:
    try:
        MediaInput(
            id="img-3",
            original_media_type="video_frame",
            mime_type="image/jpeg",
            data_base64="data:image/jpeg;base64,ZmFrZQ==",
        )
    except ValidationError as exc:
        assert "raw base64" in str(exc)
        return
    raise AssertionError("Expected ValidationError for data URI prefix")


def test_accepted_response_model_is_valid() -> None:
    response = StorybookAcceptedResponse(
        job_id="job-123",
        status="processing",
        message="Your storybook is being created.",
        status_url="https://example.com/v1/storybooks/job-123",
    )
    assert response.status == "processing"


def test_job_status_response_model_is_valid() -> None:
    response = JobStatusResponse(
        job_id="job-123",
        status="queued",
        created_at="2026-05-29T20:00:00Z",
        updated_at="2026-05-29T20:00:00Z",
    )
    assert response.status == "queued"
