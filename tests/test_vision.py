"""Tests for the vision description service and supporting models/prompts."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from app.models.requests import CharacterInput, BookOptions, StorybookRequest, MediaInput
from app.models.story import ImageDescription, ImageDescriptionSet
from app.prompts.vision_prompt import (
    VISION_SYSTEM_PROMPT,
    build_user_content,
    format_character_context,
)
from app.services.image_utils import DecodedImage
from app.services.vision import describe_images


# ── fixtures ────────────────────────────────────────────────────────────

def _make_decoded_image(image_id: str, size: int = 64) -> DecodedImage:
    """Tiny synthetic JPEG-like bytes — content doesn't matter for unit tests."""
    return DecodedImage(
        image_id=image_id,
        mime_type="image/jpeg",
        data=b"\xff\xd8\xff" + b"\x00" * size,
        width=100,
        height=100,
    )


def _make_request(n_media: int = 2) -> StorybookRequest:
    return StorybookRequest(
        request_id="test-req-001",
        parent_email="parent@example.com",
        book_options=BookOptions(
            title_hint="A Test Adventure",
            theme="ocean adventure",
            reading_age="5-7",
        ),
        characters=[
            CharacterInput(name="Roman", role="big brother hero", pronouns="he/him", traits=["brave"]),
            CharacterInput(name="Beckham", role="little explorer", pronouns="he/him", traits=["joyful"]),
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


# ── Model validation tests ─────────────────────────────────────────────

class TestImageDescriptionModel:
    def test_valid_description(self):
        desc = ImageDescription(
            image_id="img-001",
            setting="A sandy beach",
            subjects=["A child building a sandcastle"],
            actions="Building and digging",
            notable_objects=["sandcastle", "red bucket"],
            mood="playful",
            colors_and_light="Golden sunset light",
        )
        assert desc.image_id == "img-001"
        assert len(desc.subjects) == 1
        assert len(desc.notable_objects) == 2

    def test_minimal_description(self):
        """Only required fields — notable_objects and colors_and_light have defaults."""
        desc = ImageDescription(
            image_id="img-002",
            setting="Indoors",
            subjects=["An adult sitting at a table"],
            actions="Reading a book",
            mood="calm",
        )
        assert desc.notable_objects == []
        assert desc.colors_and_light == ""

    def test_empty_subjects_rejected(self):
        with pytest.raises(Exception):
            ImageDescription(
                image_id="img-003",
                setting="Park",
                subjects=[],
                actions="Walking",
                mood="happy",
            )


class TestImageDescriptionSetModel:
    def test_valid_set(self):
        desc_set = ImageDescriptionSet(
            descriptions=[
                ImageDescription(
                    image_id=f"img-{i}",
                    setting="Scene",
                    subjects=["Someone"],
                    actions="Doing something",
                    mood="neutral",
                )
                for i in range(3)
            ]
        )
        assert len(desc_set.descriptions) == 3

    def test_empty_descriptions_rejected(self):
        with pytest.raises(Exception):
            ImageDescriptionSet(descriptions=[])

    def test_roundtrip_json(self):
        desc_set = ImageDescriptionSet(
            descriptions=[
                ImageDescription(
                    image_id="img-001",
                    setting="Beach",
                    subjects=["A child in a red shirt"],
                    actions="Running",
                    notable_objects=["seashell"],
                    mood="excited",
                    colors_and_light="Bright afternoon sun",
                ),
            ]
        )
        raw = desc_set.model_dump_json()
        restored = ImageDescriptionSet.model_validate_json(raw)
        assert restored == desc_set


# ── Prompt helper tests ─────────────────────────────────────────────────

class TestPromptHelpers:
    def test_format_character_context(self):
        chars = [
            {"name": "Roman", "role": "hero", "pronouns": "he/him", "traits": ["brave", "curious"]},
            {"name": "Beckham", "role": "sidekick", "pronouns": None, "traits": []},
        ]
        result = format_character_context(chars)
        assert "Roman" in result
        assert "Beckham" in result
        assert "brave" in result

    def test_build_user_content_structure(self):
        content = build_user_content(
            ["img-001", "img-002"],
            ["data:image/jpeg;base64,abc", "data:image/jpeg;base64,def"],
            character_context="- Roman (hero)",
        )
        # Should contain: character text + (text + image_url) per image + final instruction
        types = [c["type"] for c in content]
        assert types.count("image_url") == 2
        # At least one text block per image plus character context + trailing instruction
        assert types.count("text") >= 4

    def test_build_user_content_no_character_context(self):
        content = build_user_content(
            ["img-001"],
            ["data:image/jpeg;base64,abc"],
        )
        # No character context block
        texts = [c for c in content if c["type"] == "text"]
        assert not any("Character context" in t["text"] for t in texts)

    def test_system_prompt_mentions_json(self):
        assert "JSON" in VISION_SYSTEM_PROMPT or "json" in VISION_SYSTEM_PROMPT

    def test_system_prompt_privacy_rules(self):
        lower = VISION_SYSTEM_PROMPT.lower()
        assert "do not infer" in lower or "never estimate" in lower
        assert "license plate" in lower or "private information" in lower


# ── Mock mode tests ─────────────────────────────────────────────────────

class TestVisionMockMode:
    @patch.dict(os.environ, {"USE_MOCK_AI": "true"}, clear=False)
    def test_mock_returns_one_per_image(self):
        from app.config import Settings

        with patch("app.services.vision.get_settings") as mock_settings:
            s = Settings(USE_MOCK_AI=True)
            mock_settings.return_value = s

            request = _make_request(n_media=3)
            images = [_make_decoded_image(f"img-{i:03d}") for i in range(1, 4)]

            result = describe_images(request, images)

        assert isinstance(result, ImageDescriptionSet)
        assert len(result.descriptions) == 3
        for i, desc in enumerate(result.descriptions, start=1):
            assert desc.image_id == f"img-{i:03d}"

    @patch.dict(os.environ, {"USE_MOCK_AI": "true"}, clear=False)
    def test_mock_descriptions_are_valid_pydantic(self):
        from app.config import Settings

        with patch("app.services.vision.get_settings") as mock_settings:
            s = Settings(USE_MOCK_AI=True)
            mock_settings.return_value = s

            request = _make_request(n_media=1)
            images = [_make_decoded_image("img-001")]
            result = describe_images(request, images)

        # Re-validate through Pydantic
        validated = ImageDescriptionSet.model_validate(result.model_dump())
        assert validated == result


# ── OpenAI client mock tests ───────────────────────────────────────────

class TestVisionOpenAIPath:
    def _make_mock_client(self, response_json: dict) -> MagicMock:
        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = json.dumps(response_json)
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response
        return mock_client

    def test_openai_path_parses_valid_response(self):
        from app.config import Settings

        valid_response = {
            "descriptions": [
                {
                    "image_id": "img-001",
                    "setting": "A cruise ship deck",
                    "subjects": ["A young child waving"],
                    "actions": "Waving at the camera",
                    "notable_objects": ["a large anchor"],
                    "mood": "excited",
                    "colors_and_light": "Clear blue sky",
                },
                {
                    "image_id": "img-002",
                    "setting": "A tropical beach",
                    "subjects": ["Two children playing in sand"],
                    "actions": "Building a sandcastle together",
                    "notable_objects": ["palm tree", "seashell"],
                    "mood": "joyful",
                    "colors_and_light": "Warm golden hour light",
                },
            ]
        }

        mock_client = self._make_mock_client(valid_response)

        with patch("app.services.vision.get_settings") as mock_settings:
            s = Settings(
                USE_MOCK_AI=False,
                OPENAI_API_KEY="sk-test",
                OPENAI_VISION_MODEL="gpt-4.1-mini",
            )
            mock_settings.return_value = s

            request = _make_request(n_media=2)
            images = [_make_decoded_image("img-001"), _make_decoded_image("img-002")]

            result = describe_images(request, images, client=mock_client)

        assert isinstance(result, ImageDescriptionSet)
        assert len(result.descriptions) == 2
        assert result.descriptions[0].image_id == "img-001"
        assert result.descriptions[1].setting == "A tropical beach"

        # Verify the API was called with json_object response format
        call_kwargs = mock_client.chat.completions.create.call_args.kwargs
        assert call_kwargs["response_format"] == {"type": "json_object"}

    def test_openai_path_rejects_invalid_json(self):
        from app.config import Settings

        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = "not valid json {{"
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        with patch("app.services.vision.get_settings") as mock_settings:
            s = Settings(USE_MOCK_AI=False, OPENAI_API_KEY="sk-test")
            mock_settings.return_value = s

            request = _make_request(n_media=1)
            images = [_make_decoded_image("img-001")]

            with pytest.raises(RuntimeError, match="invalid JSON"):
                describe_images(request, images, client=mock_client)

    def test_openai_path_rejects_schema_mismatch(self):
        from app.config import Settings

        bad_response = {"descriptions": [{"image_id": "img-001"}]}  # missing required fields
        mock_client = self._make_mock_client(bad_response)

        with patch("app.services.vision.get_settings") as mock_settings:
            s = Settings(USE_MOCK_AI=False, OPENAI_API_KEY="sk-test")
            mock_settings.return_value = s

            request = _make_request(n_media=1)
            images = [_make_decoded_image("img-001")]

            with pytest.raises(RuntimeError, match="schema validation"):
                describe_images(request, images, client=mock_client)

    def test_openai_path_handles_empty_response(self):
        from app.config import Settings

        mock_client = MagicMock()
        mock_message = MagicMock()
        mock_message.content = ""
        mock_choice = MagicMock()
        mock_choice.message = mock_message
        mock_response = MagicMock()
        mock_response.choices = [mock_choice]
        mock_client.chat.completions.create.return_value = mock_response

        with patch("app.services.vision.get_settings") as mock_settings:
            s = Settings(USE_MOCK_AI=False, OPENAI_API_KEY="sk-test")
            mock_settings.return_value = s

            request = _make_request(n_media=1)
            images = [_make_decoded_image("img-001")]

            with pytest.raises(RuntimeError, match="empty response"):
                describe_images(request, images, client=mock_client)

    def test_openai_path_no_api_key_raises(self):
        from app.config import Settings

        with patch("app.services.vision.get_settings") as mock_settings:
            s = Settings(USE_MOCK_AI=False, OPENAI_API_KEY="")
            mock_settings.return_value = s

            request = _make_request(n_media=1)
            images = [_make_decoded_image("img-001")]

            with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
                describe_images(request, images)
