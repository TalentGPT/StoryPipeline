# Shortcut Payload Contract

## Endpoint

- **Method:** `POST`
- **Path:** `/v1/storybooks`
- **Header:** `X-Storybook-Api-Key`
- **Content-Type:** `application/json`

## V1 Contract Notes

- V1 server accepts **images only**.
- If the parent selects a video, the Shortcut should try to convert it into a single JPEG thumbnail/frame.
- If that is not possible, the Shortcut should skip the video and show a user-visible note.
- Send **raw base64 only** in `data_base64`, not a `data:image/jpeg;base64,...` prefix.
- Base64 increases payload size significantly.
- Recommended V1 target:
  - **6–12 compressed images**
  - **1280px long edge**
  - **JPEG quality around 65–75%**
  - **total request under `MAX_REQUEST_BYTES`**
- If JSON payloads become too large, the future alternative is **presigned direct S3 uploads**.

## Sample Request JSON

```json
{
  "request_id": "6d7cf484-6d0b-4d2f-b470-6c90fcae5c33",
  "parent_email": "parent@example.com",
  "book_options": {
    "title_hint": "Our Magic Cruise",
    "theme": "ocean adventure",
    "reading_age": "5-7",
    "parent_review": false,
    "dedication": "For Beckham and Roman"
  },
  "characters": [
    {
      "name": "Roman",
      "role": "big brother hero",
      "age": 4,
      "pronouns": "he/him",
      "traits": ["curious", "brave", "kind"]
    },
    {
      "name": "Beckham",
      "role": "little explorer",
      "age": 1,
      "pronouns": "he/him",
      "traits": ["joyful", "gentle"]
    }
  ],
  "core_values": [
    "courage",
    "kindness",
    "gratitude",
    "teamwork"
  ],
  "media": [
    {
      "id": "img-001",
      "original_filename": "IMG_1234.HEIC",
      "original_media_type": "photo",
      "mime_type": "image/jpeg",
      "width": 1280,
      "height": 960,
      "captured_at": "2026-05-29T16:20:00Z",
      "data_base64": "ZmFrZS1iYXNlNjQtZGF0YQ=="
    },
    {
      "id": "vid-thumb-001",
      "original_filename": "IMG_5678.MOV",
      "original_media_type": "video_frame",
      "mime_type": "image/jpeg",
      "width": 1280,
      "height": 720,
      "captured_at": "2026-05-29T16:24:00Z",
      "data_base64": "bW9yZS1mYWtlLWJhc2U2NA=="
    }
  ]
}
```

## Accepted Response JSON

```json
{
  "job_id": "job_01J123EXAMPLE",
  "status": "processing",
  "message": "Your storybook is being created.",
  "status_url": "https://example.com/v1/storybooks/job_01J123EXAMPLE"
}
```

## Future Alternative

If this JSON contract becomes too large or fragile in practice, the next step is:
- presigned direct S3 upload for media
- small metadata-only request to FastAPI referencing uploaded objects
