# Shortcut Payload Contract

## Purpose

The iPhone Share Sheet Shortcut sends a single JSON POST request to the FastAPI ingest endpoint. The API should acknowledge quickly with a processing status so the Shortcut avoids timing out.

## V1 Payload Shape

```json
{
  "request_id": "uuid-generated-on-device",
  "submitted_at": "2026-05-29T18:00:00Z",
  "parent_email": "parent@example.com",
  "child_age_range": "5-7",
  "trip_title": "Disney Cruise Adventure",
  "memory_notes": "Optional context from parent",
  "media": [
    {
      "filename": "IMG_1234.jpg",
      "content_type": "image/jpeg",
      "base64_data": "...",
      "width": 1536,
      "height": 1024,
      "source_kind": "photo"
    }
  ]
}
```

## Contract Notes

- The Shortcut should compress/resize assets before upload.
- Videos should be handled conservatively in V1 and may be reduced to thumbnails plus metadata.
- The API should respond immediately with a job receipt, for example:

```json
{
  "status": "processing",
  "request_id": "uuid-generated-on-device"
}
```

- Authentication can begin with a simple API key header in V1.
- Keep the payload single-shot and private for family use.
