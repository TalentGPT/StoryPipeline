# iOS Shortcut Build Guide

## Goal

Build an iPhone Share Sheet Shortcut that accepts family trip photos or videos, converts them into a V1-safe image payload, and sends one JSON POST request to FastAPI.

## V1 Rules

- V1 server accepts **images only**.
- Photos should be resized and converted to JPEG.
- Videos should be turned into **one JPEG thumbnail/frame** if possible.
- If a thumbnail cannot be extracted, skip the video and show a visible note.
- Send **raw base64 only**, not `data:image/jpeg;base64,...`.

## Shortcut Action Flow

1. **Enable Show in Share Sheet**
   - Configure the Shortcut to appear in the Share Sheet.

2. **Accept Images and Media**
   - Accept images and media from the Share Sheet.

3. **Ask for Parent Email**
   - Prompt the parent for email if it is not hardcoded.

4. **Ask for Theme**
   - Use `Choose from Menu` or `Ask for Input`.
   - Suggested options:
     - space mission
     - ocean adventure
     - animal kingdom
     - forest quest
     - castle quest

5. **Set Core Values List**
   - Create a fixed list such as:
     - courage
     - kindness
     - gratitude
     - teamwork

6. **Repeat Through Shortcut Input**
   - Loop through each selected photo/video.

7. **For Each Photo**
   - Resize so the long edge is **1280 px**.
   - Convert to **JPEG**.
   - Use quality around **65–75%**.
   - Base64 encode the JPEG.
   - Add a dictionary object to the `media` list.

8. **For Each Video**
   - Try to extract one thumbnail/frame.
   - Convert that frame to JPEG.
   - Base64 encode it.
   - Set `original_media_type` to `video_frame`.
   - If the Shortcut cannot produce a frame, skip the video and notify the user.

9. **Build Dictionary Payload**
   - Create the final JSON dictionary using the contract in `docs/shortcut_payload_contract.md`.

10. **Get Contents of URL**
   - Method: `POST`
   - URL: `https://your-api-host/v1/storybooks`
   - Headers:
     - `Content-Type: application/json`
     - `X-Storybook-Api-Key: <API_KEY>`
   - Body: JSON

11. **Show Returned Message**
   - Display the returned `message` or `status`.

## Troubleshooting

### 401 Unauthorized
- API key is missing or incorrect.
- Confirm the `X-Storybook-Api-Key` header matches the backend.

### 413 Payload Too Large
- Too many images.
- Images not compressed enough.
- Long edge too large.
- Reduce to around **6–12 images**, keep **1280px long edge**, JPEG **65–75%**.

### Timeout
- Backend should immediately return `processing`.
- If the Shortcut still times out, reduce payload size and number of media items.

### Invalid JSON
- Make sure the Shortcut sends a real JSON body, not form data.
- Ensure `data_base64` contains **raw base64 only**.

## Payload Size Guidance

Because base64 inflates payload size, V1 should stay conservative:
- target 6–12 images
- 1280px long edge
- JPEG quality 65–75%
- keep total request under `MAX_REQUEST_BYTES`
