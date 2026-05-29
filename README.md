# Family Storybook V1

A private family photo-to-children's-storybook product built with Python and FastAPI.

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

## Quick Start — Docker (Recommended)

The fastest way to run locally or deploy:

```bash
cp .env.example .env          # fill in your values
docker compose up --build      # builds image & starts on port 8000
```

Verify it's running:

```bash
curl http://localhost:8000/healthz
# → {"status":"ok"}
```

Stop with `docker compose down`. Data persists in the `./data` volume mount.

## Local Development (Without Docker)

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

WeasyPrint requires system libraries (libpango, libcairo, etc.). See the [Dockerfile](Dockerfile) for the full list, or the [WeasyPrint docs](https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation).

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

## Deployment

### Default V1: EC2 + Docker

EC2 running Docker Compose is the default v1 deployment — simple, debuggable, and handles WeasyPrint system dependencies without friction.

```bash
docker compose up --build -d
```

See `docs/aws_deployment.md` for full EC2 setup, IAM policy, S3, SES, and HTTPS guidance.

### App Runner (Optional)

An `apprunner.yaml` is included only for already-eligible App Runner accounts. It is **not** the default recommendation. See `docs/aws_deployment.md` for caveats.

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

```bash
python -m compileall app
uvicorn app.main:app --reload
```

Then open:
- `http://localhost:8000/healthz`

## Roadmap

| Phase | Focus | Status |
|-------|-------|--------|
| **V1** | Photos → PDF → email (private family use) | ✅ Complete |
| **V1.1** | Retry, idempotency, structured logs, cleanup | Planned |
| **V1.2** | Parent review & approval before final render | Planned |
| **V2** | Better book design — layouts, fonts, cover, themes | Planned |
| **V2.1** | Print-on-demand research (manual export only, no publishing automation) | Planned |
| **V3** | Productization — multi-user, billing, landing page | Planned |
| **Ongoing** | AI quality — prompt versioning, eval suite, cost optimization | Continuous |

See [`docs/roadmap.md`](docs/roadmap.md) for detailed checklists.
