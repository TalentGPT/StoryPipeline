# Roadmap

## V1 Scope

- iPhone Share Sheet Shortcut sends one JSON POST request.
- FastAPI accepts request and returns `processing` immediately.
- Backend processes asynchronously.
- Vision descriptions summarize family media.
- Story generation turns memories into a magical children’s adventure for ages 5–7.
- Pydantic validation + critic retry keep outputs structured.
- WeasyPrint renders a polished PDF storybook.
- Finished PDF uploads to S3 and sends by email.
- Failures are visible through logs and failure email where possible.

## Explicit V1 Non-Goals

- No public web app
- No microservices
- No KDP/browser automation
- No advanced user accounts
- No generalized consumer SaaS platform

## Suggested Next Steps After Scaffold

1. Define ingest request/response models.
2. Add API key auth dependency.
3. Implement async job storage and worker loop.
4. Add image preprocessing and media staging.
5. Add OpenAI vision description service.
6. Add story generation + validation + critic retry.
7. Add Jinja2 + WeasyPrint PDF pipeline.
8. Add S3 upload + SES delivery.
9. Add failure notifications and cleanup routines.
