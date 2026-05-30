from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError

from app.models.requests import MediaInput


@dataclass(slots=True)
class DecodedImage:
    image_id: str
    mime_type: str
    data: bytes
    width: int
    height: int


class InvalidImageError(ValueError):
    pass



ALLOWED_MIME_TYPES = frozenset({"image/jpeg", "image/png"})

# Pillow format strings that map to our allowed MIME types.
_ALLOWED_PILLOW_FORMATS = frozenset({"JPEG", "PNG"})


def decode_media_item(media: MediaInput) -> DecodedImage:
    # Validate declared MIME type first.
    if media.mime_type not in ALLOWED_MIME_TYPES:
        raise InvalidImageError(
            f"Unsupported image type '{media.mime_type}'. Only JPEG and PNG are accepted."
        )

    raw_base64 = _strip_data_url_prefix(media.data_base64)

    try:
        decoded = base64.b64decode(raw_base64, validate=True)
    except Exception as exc:  # noqa: BLE001
        raise InvalidImageError("Invalid base64 image payload.") from exc

    try:
        original = Image.open(io.BytesIO(decoded))
        original.load()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise InvalidImageError("Corrupt or unsupported image data.") from exc

    # Verify the actual decoded image format matches an allowed type,
    # regardless of the declared mime_type (defense in depth).
    actual_format = (original.format or "").upper()
    if actual_format not in _ALLOWED_PILLOW_FORMATS:
        raise InvalidImageError(
            f"Image content is '{actual_format}', not JPEG or PNG. Rejected."
        )

    try:
        normalized = ImageOps.exif_transpose(original).convert("RGB")
    except (OSError, ValueError) as exc:
        raise InvalidImageError("Corrupt or unsupported image data.") from exc

    # Re-encode to JPEG to strip EXIF and normalize format.
    output = io.BytesIO()
    normalized.save(output, format="JPEG", quality=90)
    jpeg_bytes = output.getvalue()

    return DecodedImage(
        image_id=media.id,
        mime_type="image/jpeg",
        data=jpeg_bytes,
        width=normalized.width,
        height=normalized.height,
    )



def save_decoded_images(
    images: list[DecodedImage],
    work_dir: Path,
    job_id: str,
) -> Path:
    """Persist decoded images to ``work_dir/job_id/`` for background processing.

    Each image is saved as ``{image_id}.jpg`` alongside a ``manifest.json``
    that records metadata needed to reconstruct ``DecodedImage`` objects.

    Returns the job-specific directory path.
    """
    import json

    job_dir = work_dir / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    manifest: list[dict[str, object]] = []
    for img in images:
        fname = f"{img.image_id}.jpg"
        (job_dir / fname).write_bytes(img.data)
        manifest.append({
            "image_id": img.image_id,
            "mime_type": img.mime_type,
            "width": img.width,
            "height": img.height,
            "filename": fname,
        })

    (job_dir / "manifest.json").write_text(json.dumps(manifest))
    return job_dir


def load_decoded_images(work_dir: Path, job_id: str) -> list[DecodedImage]:
    """Load previously-saved decoded images from ``work_dir/job_id/``.

    Raises ``FileNotFoundError`` if the manifest or any image file is missing.
    """
    import json

    job_dir = work_dir / job_id
    manifest_path = job_dir / "manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Image manifest not found for job {job_id} at {manifest_path}"
        )

    manifest = json.loads(manifest_path.read_text())
    images: list[DecodedImage] = []
    for entry in manifest:
        img_path = job_dir / entry["filename"]
        images.append(
            DecodedImage(
                image_id=entry["image_id"],
                mime_type=entry["mime_type"],
                data=img_path.read_bytes(),
                width=entry["width"],
                height=entry["height"],
            )
        )
    return images


def _strip_data_url_prefix(value: str) -> str:
    if value.startswith("data:") and "," in value:
        return value.split(",", 1)[1]
    return value
