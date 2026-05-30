# Security & Privacy

## Core Principles

- Treat family photos, generated stories, and PDFs as **private data** at every stage.
- Keep all secrets in environment variables — never commit them.
- Prefer visible failures over silent data loss.
- Log operational context; never log secrets or raw family media.

---

## API Key Authentication

- V1 uses a shared `API_KEY` validated on protected endpoints via the `X-Storybook-Api-Key` header.
- **Constant-time comparison** using `hmac.compare_digest` prevents timing side-channel attacks.
- Missing or incorrect keys receive a `401 Unauthorized` response with no detail that distinguishes "missing" from "wrong."
- If `API_KEY` is empty on the server and `REQUIRE_API_KEY=true`, all requests are rejected (fail-closed).
- The provided API key is **never logged** — the logging sanitizer redacts any message containing `api_key` or `authorization`.
- Set `REQUIRE_API_KEY=true` in production (the default).
- Transmit the key only over HTTPS.
- Rotate the key if it is ever exposed.

## Payload Size Limits

The app enforces multiple size limits to prevent abuse and resource exhaustion:

| Setting | Default | Purpose |
|---------|---------|---------|
| `MAX_REQUEST_BYTES` | 55 MB | Total HTTP request body (middleware guard) |
| `MAX_SINGLE_IMAGE_BYTES` | 10 MB | Any individual decoded image |
| `MAX_TOTAL_IMAGE_BYTES` | 50 MB | Sum of all decoded images in a job |
| `MAX_IMAGES_PER_JOB` | 40 | Number of media items per request |

Requests exceeding these limits receive `413 Request Entity Too Large`. Invalid or corrupt images receive `400 Bad Request`.

## Image Handling & EXIF Stripping

- **Only JPEG and PNG** are accepted. The Pydantic model enforces `mime_type` at the schema level (`image/jpeg` or `image/png`), and the image decoder performs a second check on the actual Pillow format. A GIF or WebP disguised with a JPEG `mime_type` is rejected with a `400` error.
- Every accepted image is **decoded and re-encoded to JPEG** (quality 90), which:
  - Strips all EXIF metadata (GPS coordinates, camera info, timestamps).
  - Normalizes orientation via `ImageOps.exif_transpose`.
  - Ensures a consistent output format regardless of input.
- Corrupt or unreadable images are rejected with `400 Bad Request`.
- Raw base64 image data is **stripped from the stored job record** (`request_json`) after validation. Only metadata (id, mime_type, dimensions, etc.) is persisted.
- Work images in `data/work/` are temporary and should be cleaned up after PDF generation.

## Private S3 Storage

- **Block all public access** on the S3 bucket (all four public-access-block settings enabled).
- Enable **server-side encryption** (SSE-S3 or SSE-KMS).
- Scope IAM permissions to the specific bucket and prefix (`s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`).
- Never add bucket policies that grant public read.

## Presigned URL Expiry

- PDF download links use **presigned S3 URLs** with a configurable TTL (`DOWNLOAD_URL_EXPIRES_SECONDS`, default 3600 seconds / 1 hour).
- After expiry, the URL stops working — the object remains private.
- Choose the shortest practical expiry for your use case.

## Logging & Redaction

The structured JSON logger enforces the following rules:

- **Sensitive markers** — any log message containing `base64`, `api_key`, `authorization`, `openai_api_key`, `ses_sender_email`, `ses_admin_email`, `presigned`, `data_base64`, or `image_bytes` is replaced with `[redacted-sensitive-log-message]`.
- **URL redaction** — full HTTP(S) URLs in non-redacted messages are truncated to `scheme://host/…`, preventing accidental leakage of presigned tokens or paths.
- **Structured extras** — logs include `job_id`, `status`, `event`, and `duration_ms` fields when available, providing operational context without sensitive content.
- **No raw media in logs** — base64 payloads, decoded image bytes, API keys, and full presigned URLs must never appear in log output.

## Family Photo Privacy

This product processes **real family photos of children**. Handle them accordingly:

- No analytics, telemetry, or third-party tracking on uploaded media.
- AI vision API calls use OpenAI — review OpenAI's data usage policy and opt out of training if required.
- Generated stories and PDFs are for the requesting family only; do not share or aggregate across users.
- Access to the API endpoint should be restricted to known clients (the iOS Shortcut) via API key and network controls.

## Manual Review Expectations

- A parent should review every generated storybook before sharing it with children.
- AI-generated content can be unpredictable — review story text and image descriptions for appropriateness.
- The system sends the PDF to the parent's email for review, not directly to any child-facing surface.

---

## Hardening Checklist (v0.1)

| Control | Status |
|---------|--------|
| Constant-time API key comparison (`hmac.compare_digest`) | ✅ Done |
| Reject missing/wrong key with 401 | ✅ Done |
| Never log the provided API key | ✅ Done |
| Request/image size limits with 400/413 | ✅ Done |
| Accept only JPEG/PNG (schema + actual format check) | ✅ Done |
| Decode & re-encode to JPEG, stripping EXIF | ✅ Done |
| Reject corrupt images | ✅ Done |
| Strip base64 from persisted job record | ✅ Done |
| No logging of base64/image bytes/API keys/presigned URLs | ✅ Done |
| Include job_id and status safely in logs | ✅ Done |

## Recommended Follow-Ups

- Add request signing or HMAC if the endpoint is ever exposed beyond the family network.
- Implement content retention and cleanup jobs for `data/work/` and `data/outbox/`.
- Consider VPN or IP allowlisting for additional endpoint protection.
- Rate limiting per API key / IP.
- Audit trail for job access (who retrieved which PDF).
