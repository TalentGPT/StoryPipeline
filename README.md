# Family Storybook V1

A private family photo-to-children’s-storybook product built with Python and FastAPI.

**Photos in → PDF out.**

V1 is intentionally simple:
- no web app
- no microservices
- no browser automation
- private family use first

## V1 Flow

1. Parent selects trip photos/videos on iPhone.
2. Share Sheet Shortcut compresses/resizes media, base64-encodes it, and sends one JSON POST request.
3. FastAPI immediately returns a `processing` response so the Shortcut does not time out.
4. Backend processes asynchronously.
5. Vision descriptions summarize the real memories.
6. Story generation turns the memories into a magical story for ages 5–7.
7. Pydantic validation and critic/self-check retries improve output quality.
8. WeasyPrint renders the storybook as a PDF.
9. PDF uploads to S3 and is delivered by email.

## Repository Structure

```text
app/
  main.py
  config.py
  logging_config.py
  models/
  prompts/
  services/
  templates/
docs/
scripts/
tests/
data/
```

## Local Development

### 1. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Create env file

```bash
cp .env.example .env
```

### 4. Start the API

```bash
uvicorn app.main:app --reload
```

### 5. Health check

```bash
curl http://localhost:8000/healthz
```

Expected response:

```json
{"status":"ok"}
```

## Payload Summary

The Shortcut will eventually POST one JSON payload containing:
- request metadata
- parent email
- optional trip context
- resized/compressed base64 image data
- optional reduced video metadata or derivatives

See:
- `docs/shortcut_payload_contract.md`
- `docs/ios_shortcut_build.md`

## Deployment Options

### Default V1 Recommendation: EC2 + Docker

This is the default recommendation because it is the simplest and easiest to debug for a private family workload with WeasyPrint dependencies.

```bash
docker compose up --build
```

### App Runner

Include `apprunner.yaml` only as an optional deployment path for already-eligible App Runner users. It is not the default recommendation for new customers.

### ECS Express Mode

ECS Express Mode is the modern managed alternative if you want a more managed AWS container experience without starting from App Runner.

## Core Environment Variables

See `.env.example` for the full list.

Important settings include:
- `APP_ENV`
- `API_KEY`
- `REQUIRE_API_KEY`
- `USE_MOCK_AI`
- `OPENAI_API_KEY`
- `OPENAI_VISION_MODEL`
- `OPENAI_STORY_MODEL`
- `AWS_REGION`
- `S3_BUCKET`
- `S3_PREFIX`
- `SES_SENDER_EMAIL`
- `SES_ADMIN_EMAIL`
- `EMAIL_DELIVERY_ENABLED`
- image size limits
- `JOB_STORE_PATH`
- `WORK_DIR`
- `LOCAL_OUTBOX_DIR`
- PDF settings

## Security Notes

- Keep all secrets in environment variables.
- Do not log raw base64 media.
- Prefer visible failures and failure email when possible.
- Keep generated PDFs private by default.

See `docs/security_privacy.md`.

## Testing / Validation

For this scaffold stage, validate:

```bash
python -m compileall app
uvicorn app.main:app --reload
```

Then open:
- `http://localhost:8000/healthz`

## Roadmap

See `docs/roadmap.md` for the phased implementation path after this scaffold.
