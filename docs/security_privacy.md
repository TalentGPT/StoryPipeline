# Security & Privacy

## Core Principles

- Treat family photos, generated stories, and PDFs as **private data** at every stage.
- Keep all secrets in environment variables — never commit them.
- Prefer visible failures over silent data loss.
- Log operational context; never log secrets or raw family media.

---

## Private S3 Storage

- **Block all public access** on the S3 bucket (all four public-access-block settings enabled).
- Enable **server-side encryption** (SSE-S3 or SSE-KMS).
- Scope IAM permissions to the specific bucket and prefix (`s3:PutObject`, `s3:GetObject`, `s3:DeleteObject`).
- Never add bucket policies that grant public read.

## Presigned URL Expiry

- PDF download links use **presigned S3 URLs** with a configurable TTL (`DOWNLOAD_URL_EXPIRES_SECONDS`, default 3600 seconds / 1 hour).
- After expiry, the URL stops working — the object remains private.
- Choose the shortest practical expiry for your use case.

## Image Handling & Deletion

- Work images are written to `data/work/` during processing and should be cleaned up after the PDF is generated and uploaded.
- Raw base64 image data is decoded in memory and never written to durable storage beyond the temporary work directory.
- Implement a periodic cleanup job (cron or app-level) to remove stale work files older than a configurable retention window.

## No Logging of Base64 / Media

- **Never log request bodies** that contain base64-encoded images or video data.
- Structured logging should capture: job ID, image count, total size, timestamps, and error messages — not media content.
- Failure notification emails should include metadata only (job ID, error type), not raw user content.

## API Key Authentication

- V1 uses a shared `API_KEY` validated on protected endpoints.
- Set `REQUIRE_API_KEY=true` in production (the default).
- Transmit the key only over HTTPS.
- Rotate the key if it is ever exposed.

## Payload Size Limits

The app enforces multiple size limits to prevent abuse and resource exhaustion:

| Setting | Default | Purpose |
|---------|---------|---------|
| `MAX_REQUEST_BYTES` | 55 MB | Total HTTP request body |
| `MAX_SINGLE_IMAGE_BYTES` | 10 MB | Any individual image |
| `MAX_TOTAL_IMAGE_BYTES` | 50 MB | Sum of all images in a job |
| `MAX_IMAGES_PER_JOB` | 40 | Number of images per request |

Requests exceeding these limits receive a `413` response.

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

## Recommended Follow-Ups

- Add request signing or HMAC if the endpoint is ever exposed beyond the family network.
- Implement content retention and cleanup jobs for `data/work/` and `data/outbox/`.
- Add audit-friendly structured logging with correlation IDs.
- Consider VPN or IP allowlisting for additional endpoint protection.
