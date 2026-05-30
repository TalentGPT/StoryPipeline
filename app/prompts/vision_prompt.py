"""Prompt template for the family-photo vision description step."""

from __future__ import annotations

# ── system prompt ───────────────────────────────────────────────────────
VISION_SYSTEM_PROMPT = """\
You are a careful family-photo describer working for a children's storybook \
generator (ages 5–7).

## Your job

For **each** image you receive, produce a structured JSON description that a \
story-writing model will use later to craft a magical adventure.

## Rules

1. **Describe only what is visible.** Do not infer names, ages, identities, \
relationships, ethnicity, religion, or any sensitive personal traits.
2. **Names:** Use the character names from the request context *only* when the \
parent has explicitly mapped them. If no mapping exists, describe people by \
visible appearance (e.g. "a child wearing a blue hat").
3. **Age:** Never estimate or state a person's age. Use neutral descriptors \
like "young child", "toddler", or "adult" if relevant.
4. **Objects & animals:** Call out interesting objects, animals, vehicles, or \
landmarks that could become fantasy story elements (a talking dolphin, an \
enchanted ship, a magical seashell, etc.).
5. **Tone:** Warm, factual, and concise. Write as if you are jotting friendly \
notes for a storyteller, not narrating the final book.
6. **Privacy:** Never mention text on documents, license plates, addresses, \
phone numbers, or other private information visible in the photo.

## Output format

Return a single JSON object with key `"descriptions"` containing an array. \
Each element corresponds to one input image **in order** and must include:

```json
{
  "image_id": "<id from request>",
  "setting": "Brief description of the location or environment.",
  "subjects": ["Person described by appearance only", "…"],
  "actions": "What the subjects appear to be doing.",
  "notable_objects": ["object or animal that could become a story element"],
  "mood": "Overall emotional tone of the scene.",
  "colors_and_light": "Dominant colours and lighting conditions."
}
```

Return **only** the JSON object. No markdown fences, no commentary.\
"""


# ── helpers ─────────────────────────────────────────────────────────────

def build_user_content(
    image_ids: list[str],
    data_urls: list[str],
    *,
    character_context: str = "",
) -> list[dict]:
    """Build the multimodal user-message content array.

    Each image is sent as an ``image_url`` content block followed by a short
    text block carrying its ``image_id`` so the model can match them up.

    Parameters
    ----------
    image_ids:
        Ordered list of image identifiers (``media.id`` from the request).
    data_urls:
        Matching list of ``data:image/jpeg;base64,...`` strings.
    character_context:
        Optional pre-formatted character/name mapping string the model can
        reference when assigning names to visible subjects.
    """
    parts: list[dict] = []

    if character_context:
        parts.append({
            "type": "text",
            "text": (
                "Character context provided by the parent:\n"
                f"{character_context}\n\n"
                "Use these names only when you are confident a visible person "
                "matches the parent's description."
            ),
        })

    for idx, (img_id, url) in enumerate(zip(image_ids, data_urls), start=1):
        parts.append({
            "type": "text",
            "text": f"Image {idx} (id: {img_id}):",
        })
        parts.append({
            "type": "image_url",
            "image_url": {"url": url, "detail": "low"},
        })

    parts.append({
        "type": "text",
        "text": (
            "Describe every image above following the rules and JSON schema "
            "in your system instructions."
        ),
    })

    return parts


def format_character_context(characters: list[dict]) -> str:
    """Turn the request's character list into a compact string for the prompt.

    Parameters
    ----------
    characters:
        List of dicts with at least ``name`` and ``role`` keys, plus optional
        ``traits`` and ``pronouns``.
    """
    lines: list[str] = []
    for ch in characters:
        parts = [f"- {ch['name']} ({ch['role']})"]
        if ch.get("pronouns"):
            parts.append(f"pronouns {ch['pronouns']}")
        traits = ch.get("traits")
        if traits:
            parts.append(f"traits: {', '.join(traits)}")
        lines.append(", ".join(parts))
    return "\n".join(lines)
