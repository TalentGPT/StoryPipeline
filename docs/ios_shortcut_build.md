# iOS Shortcut Build Guide

## Goal

Create an iPhone Share Sheet Shortcut that takes selected family trip photos or videos, compresses them, base64-encodes them, and POSTs one JSON request to the FastAPI backend.

## Recommended Shortcut Flow

1. Accept input from Share Sheet.
2. Filter to supported photos/videos.
3. Resize images to the configured max width/height.
4. Compress JPEG quality to the configured target.
5. Convert each asset to base64.
6. Build a JSON object matching `docs/shortcut_payload_contract.md`.
7. Send a `POST` request to the ingest endpoint with an API key header.
8. Show a success/failure notification to the parent.

## V1 Practical Notes

- Keep the request under conservative iOS Shortcut size limits.
- Prefer sending batches of images rather than full-length videos in V1.
- If large trips exceed payload limits, split into multiple submissions manually.
- The backend should respond immediately with `{"status":"processing"}`.

## Suggested Request Headers

- `Content-Type: application/json`
- `X-API-Key: <API_KEY>`

## Failure Handling

- If the Shortcut receives a non-200 response, show a visible failure message.
- Parent should retry with fewer images if the payload is too large.
