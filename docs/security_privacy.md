# Security and Privacy Notes

## Core Principles

- Keep all secrets in environment variables.
- Treat family photos, videos, generated stories, and PDFs as private data.
- Prefer visible failures over silent data loss.
- Log operational failures without leaking secrets or raw family media.

## V1 Security Posture

- API access should be protected with an API key in V1.
- AWS credentials should be provided through IAM roles or environment variables.
- S3 bucket access should be least-privilege.
- SES sender should be controlled and verified.
- Generated PDFs should not be made public by default.

## Privacy Expectations

- This product is for private family use first.
- Do not retain raw media longer than necessary once durable artifacts are created.
- Avoid logging request bodies that contain base64 media.
- Failure emails should contain metadata only, not raw user content.

## Recommended Follow-Ups

- Add request signing or stronger auth if the Shortcut endpoint is ever exposed more broadly.
- Add server-side payload size enforcement.
- Add content retention and cleanup jobs for `data/work`.
- Add audit-friendly structured logging.
