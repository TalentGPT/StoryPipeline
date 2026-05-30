"""Tests for the story generation retry loop, critic, and validation."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from app.models.requests import (
    BookOptions,
    CharacterInput,
    MediaInput,
    StorybookRequest,
)
from app.models.story import (
    CANONICAL_CORE_VALUES,
    ImageDescription,
    ImageDescriptionSet,
    StoryBook,
)
from app.services.story_generation import (
    CriticVerdict,
    StoryGenerationError,
    generate_storybook_with_retries,
)
from app.services.story_validation import validate_storybook


def _make_request(n_media: int = 2) -> StorybookRequest:
    return StorybookRequest(
        request_id="test-req-001",
        parent_email="parent@example.com",
        book_options=BookOptions(
            title_hint="A Test Adventure",
            theme="ocean adventure",
            reading_age="5-7",
            dedication="For the testers",
        ),
        characters=[
            CharacterInput(name="Roman", role="big brother hero", traits=["brave"]),
            CharacterInput(name="Beckham", role="little explorer", traits=["joyful"]),
        ],
        core_values=["courage", "kindness"],
        media=[
            MediaInput(
                id=f"img-{i:03d}",
                original_media_type="photo",
                mime_type="image/jpeg",
                data_base64="ZmFrZQ==",
            )
            for i in range(1, n_media + 1)
        ],
    )


def _make_description_set(n: int = 2) -> ImageDescriptionSet:
    return ImageDescriptionSet(
        descriptions=[
            ImageDescription(
                image_id=f"img-{i:03d}",
                setting=f"Scene {i}",
                subjects=[f"Subject {i}"],
                actions=f"Action {i}",
                mood="happy",
            )
            for i in range(1, n + 1)
        ]
    )


def _make_valid_storybook_dict(n_pages: int = 2, *, dedication: str = "For testers") -> dict:
    return {
        "title": "A Test Adventure",
        "subtitle": "A tale of ocean adventure",
        "dedication": dedication,
        "theme": "ocean adventure",
        "reading_age": "5-7",
        "characters": [
            {
                "name": "Roman",
                "story_role": "big brother hero",
                "magical_description": "A brave big brother hero",
            },
            {
                "name": "Beckham",
                "story_role": "little explorer",
                "magical_description": "A joyful little explorer",
            },
        ],
        "moral_summary": "A story about courage and kindness.",
        "pages": [
            {
                "page_number": i + 1,
                "source_image_id": f"img-{i + 1:03d}",
                "real_memory_anchor": f"The photo shows Scene {i + 1}.",
                "fantasy_transformation": f"Scene {i + 1} transforms into magic.",
                "value_focus": ["courage"] if i % 2 == 0 else ["kindness"],
                "text": [
                    f"Sentence one for page {i + 1}.",
                    f"Sentence two for page {i + 1}.",
                ],
                "illustration_note": f"Illustration for page {i + 1}.",
            }
            for i in range(n_pages)
        ],
        "closing_note": "The end!",
    }


def _make_critic_pass_response() -> str:
    return json.dumps({"passes": True, "issues": [], "revision_instructions": ""})


def _make_critic_fail_response(revision: str = "Fix the issues.") -> str:
    return json.dumps(
        {
            "passes": False,
            "issues": [
                {"severity": "major", "field": "pages[1].text", "message": "Too complex for age 5-7."},
            ],
            "revision_instructions": revision,
        }
    )


def _mock_openai_response(content: str) -> MagicMock:
    mock_message = MagicMock()
    mock_message.content = content
    mock_choice = MagicMock()
    mock_choice.message = mock_message
    mock_response = MagicMock()
    mock_response.choices = [mock_choice]
    return mock_response


class TestCriticVerdict:
    def test_parse_passing_verdict(self):
        v = CriticVerdict.from_json(_make_critic_pass_response())
        assert v.passes is True
        assert v.major_count == 0
        assert v.minor_count == 0
        assert "pass" in v.summary()

    def test_parse_failing_verdict(self):
        v = CriticVerdict.from_json(_make_critic_fail_response())
        assert v.passes is False
        assert v.major_count == 1
        assert "fail" in v.summary()
        assert v.revision_instructions == "Fix the issues."

    def test_invalid_json_raises(self):
        with pytest.raises(json.JSONDecodeError):
            CriticVerdict.from_json("not json")


class TestStoryValidation:
    def test_valid_story_passes(self):
        story = StoryBook.model_validate(_make_valid_storybook_dict())
        desc_set = _make_description_set()
        result = validate_storybook(story, desc_set)
        assert result.passes

    def test_page_count_mismatch_is_major(self):
        story = StoryBook.model_validate(_make_valid_storybook_dict(n_pages=1))
        desc_set = _make_description_set(n=2)
        result = validate_storybook(story, desc_set)
        assert not result.passes
        assert any("page" in i.message.lower() for i in result.issues)

    def test_unknown_image_id_is_major(self):
        d = _make_valid_storybook_dict()
        d["pages"][0]["source_image_id"] = "img-999"
        story = StoryBook.model_validate(d)
        result = validate_storybook(story, _make_description_set())
        assert not result.passes
        assert any("img-999" in i.message for i in result.issues)

    def test_non_canonical_value_is_major(self):
        d = _make_valid_storybook_dict()
        d["pages"][0]["value_focus"] = ["leadership"]
        story = StoryBook.model_validate(d)
        result = validate_storybook(story, _make_description_set())
        assert not result.passes
        assert any("canonical" in i.message.lower() for i in result.issues)

    def test_missing_dedication_is_minor(self):
        d = _make_valid_storybook_dict(dedication=None)
        d["dedication"] = None
        story = StoryBook.model_validate(d)
        result = validate_storybook(story, _make_description_set())
        assert result.passes
        assert any(i.field == "dedication" for i in result.issues)


class TestPromptContract:
    def test_prompt_contains_master_sections(self):
        from app.prompts.story_prompt import build_story_prompt

        prompt = build_story_prompt(
            _make_request(),
            _make_description_set().descriptions,
            json.dumps(StoryBook.model_json_schema(), indent=2),
        )

        lower = prompt.lower()
        assert "<role>" in prompt
        assert "<private_planning_instruction>" in prompt
        assert "hero’s journey" in prompt or "hero's journey" in lower
        assert "few_shot_transformations" in prompt
        assert "output only the final json object" in lower


class TestMockMode:
    @patch("app.services.story_generation.get_settings")
    def test_mock_returns_valid_story(self, mock_settings):
        from app.config import Settings

        mock_settings.return_value = Settings(USE_MOCK_AI=True)
        story = generate_storybook_with_retries(_make_request(), _make_description_set(), job_id="test-mock")

        assert isinstance(story, StoryBook)
        assert len(story.pages) == 2
        assert story.reading_age == "5-7"
        assert story.characters[0].story_role == "big brother hero"
        assert set(v for page in story.pages for v in page.value_focus).issubset(set(CANONICAL_CORE_VALUES))

    @patch("app.services.story_generation.get_settings")
    def test_mock_is_deterministic(self, mock_settings):
        from app.config import Settings

        mock_settings.return_value = Settings(USE_MOCK_AI=True)
        request = _make_request()
        desc_set = _make_description_set()
        story1 = generate_storybook_with_retries(request, desc_set, job_id="t1")
        story2 = generate_storybook_with_retries(request, desc_set, job_id="t2")
        assert story1.model_dump() == story2.model_dump()


class TestRetryLoop:
    @patch("app.services.story_generation.get_settings")
    def test_critic_pass_returns_story_first_attempt(self, mock_settings):
        from app.config import Settings

        mock_settings.return_value = Settings(USE_MOCK_AI=False, OPENAI_API_KEY="sk-test", OPENAI_MAX_RETRIES=3)
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _mock_openai_response(json.dumps(_make_valid_storybook_dict())),
            _mock_openai_response(_make_critic_pass_response()),
        ]
        story = generate_storybook_with_retries(_make_request(), _make_description_set(), client=mock_client, job_id="test-pass")
        assert isinstance(story, StoryBook)
        assert mock_client.chat.completions.create.call_count == 2

    @patch("app.services.story_generation.get_settings")
    def test_validation_failure_triggers_retry(self, mock_settings):
        from app.config import Settings

        mock_settings.return_value = Settings(USE_MOCK_AI=False, OPENAI_API_KEY="sk-test", OPENAI_MAX_RETRIES=3)
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _mock_openai_response(json.dumps({"title": "Incomplete"})),
            _mock_openai_response(json.dumps(_make_valid_storybook_dict())),
            _mock_openai_response(_make_critic_pass_response()),
        ]
        story = generate_storybook_with_retries(_make_request(), _make_description_set(), client=mock_client, job_id="test-retry")
        assert isinstance(story, StoryBook)
        assert mock_client.chat.completions.create.call_count == 3

    @patch("app.services.story_generation.get_settings")
    def test_critic_major_issue_triggers_revision(self, mock_settings):
        from app.config import Settings

        mock_settings.return_value = Settings(USE_MOCK_AI=False, OPENAI_API_KEY="sk-test", OPENAI_MAX_RETRIES=3)
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _mock_openai_response(json.dumps(_make_valid_storybook_dict())),
            _mock_openai_response(_make_critic_fail_response("Simplify page 1 language.")),
            _mock_openai_response(json.dumps(_make_valid_storybook_dict())),
            _mock_openai_response(_make_critic_pass_response()),
        ]
        story = generate_storybook_with_retries(_make_request(), _make_description_set(), client=mock_client, job_id="test-revision")
        assert isinstance(story, StoryBook)
        assert mock_client.chat.completions.create.call_count == 4

    @patch("app.services.story_generation.get_settings")
    def test_max_retries_exhausted_raises(self, mock_settings):
        from app.config import Settings

        mock_settings.return_value = Settings(USE_MOCK_AI=False, OPENAI_API_KEY="sk-test", OPENAI_MAX_RETRIES=2)
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = _mock_openai_response("not valid json at all")
        with pytest.raises(StoryGenerationError, match="failed after 2 attempts"):
            generate_storybook_with_retries(_make_request(), _make_description_set(), client=mock_client, job_id="test-exhaust")

    @patch("app.services.story_generation.get_settings")
    def test_structural_validation_failure_triggers_retry(self, mock_settings):
        from app.config import Settings

        mock_settings.return_value = Settings(USE_MOCK_AI=False, OPENAI_API_KEY="sk-test", OPENAI_MAX_RETRIES=3)
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _mock_openai_response(json.dumps(_make_valid_storybook_dict(n_pages=1))),
            _mock_openai_response(json.dumps(_make_valid_storybook_dict(n_pages=2))),
            _mock_openai_response(_make_critic_pass_response()),
        ]
        story = generate_storybook_with_retries(_make_request(), _make_description_set(), client=mock_client, job_id="test-struct")
        assert isinstance(story, StoryBook)
        assert len(story.pages) == 2

    @patch("app.services.story_generation.get_settings")
    def test_critic_failure_accepts_structurally_valid_story(self, mock_settings):
        from app.config import Settings
        from openai import OpenAIError

        mock_settings.return_value = Settings(USE_MOCK_AI=False, OPENAI_API_KEY="sk-test", OPENAI_MAX_RETRIES=3)
        mock_client = MagicMock()
        mock_client.chat.completions.create.side_effect = [
            _mock_openai_response(json.dumps(_make_valid_storybook_dict())),
            OpenAIError("rate limit"),
        ]
        story = generate_storybook_with_retries(_make_request(), _make_description_set(), client=mock_client, job_id="test-critic-fail")
        assert isinstance(story, StoryBook)

    @patch("app.services.story_generation.get_settings")
    def test_no_api_key_raises_runtime_error(self, mock_settings):
        from app.config import Settings

        mock_settings.return_value = Settings(USE_MOCK_AI=False, OPENAI_API_KEY="", OPENAI_MAX_RETRIES=2)
        with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
            generate_storybook_with_retries(_make_request(), _make_description_set(), job_id="test-no-key")


class TestCriticPrompt:
    def test_build_critic_prompt_structure(self):
        from app.prompts.critic_prompt import build_critic_prompt

        messages = build_critic_prompt(
            '{"title": "Test"}',
            image_count=3,
            core_values=["courage", "kindness"],
            character_names=["Roman", "Beckham"],
        )
        assert len(messages) == 2
        assert messages[0]["role"] == "system"
        assert messages[1]["role"] == "user"
        assert "3" in messages[1]["content"]
        assert "courage" in messages[1]["content"]
        assert "Roman" in messages[1]["content"]

    def test_system_prompt_covers_rubric(self):
        from app.prompts.critic_prompt import CRITIC_SYSTEM_PROMPT

        lower = CRITIC_SYSTEM_PROMPT.lower()
        assert "hero's journey" in lower or "story arc" in lower
        assert "banned" in lower
        assert "5-7" in lower or "5–7" in lower
        assert "major" in lower
        assert "minor" in lower
        assert "passes" in lower
