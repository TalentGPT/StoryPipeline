# AWS Deployment Guide

## Default V1 Path: EC2 + Docker

A small EC2 instance running Docker Compose is the recommended v1 deployment. It is the simplest option, easy to debug, and handles WeasyPrint system dependencies without surprises.

---

## Local Docker Run

```bash
cp .env.example .env        # fill in real values
docker compose up --build    # builds image & starts on port 8000
curl http://localhost:8000/healthz
```

Stop with `docker compose down`. Data persists in the `./data` volume mount.

---

## EC2 Docker Deployment

### 1. Launch instance

- **AMI:** Ubuntu 22.04 or 24.04, `t3.small` or larger.
- **Security group:** allow TCP 8000 (or 443 if fronting with TLS).
- **Storage:** 20 GB gp3 minimum.

### 2. Install Docker

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo usermod -aG docker $USER
# log out and back in for group change
```

### 3. Deploy

```bash
git clone <your-repo-url> StoryPipeline && cd StoryPipeline
cp .env.example .env
# edit .env — set API_KEY, OPENAI_API_KEY, S3_BUCKET, SES_SENDER_EMAIL, etc.
docker compose up --build -d
```

### 4. Verify

```bash
curl http://localhost:8000/healthz   # → {"status":"ok"}
curl http://localhost:8000/version   # → app info
```

---

## IAM Instance Profile Policy

Attach an IAM role to the EC2 instance instead of embedding credentials. Minimum policy:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "S3StorybookBucket",
      "Effect": "Allow",
      "Action": [
        "s3:PutObject",
        "s3:GetObject",
        "s3:DeleteObject"
      ],
      "Resource": "arn:aws:s3:::YOUR_BUCKET/storybook/*"
    },
    {
      "Sid": "SESSend",
      "Effect": "Allow",
      "Action": [
        "ses:SendEmail",
        "ses:SendRawEmail"
      ],
      "Resource": "*",
      "Condition": {
        "StringEquals": {
          "ses:FromAddress": "YOUR_VERIFIED_SENDER@example.com"
        }
      }
    }
  ]
}
```

Replace `YOUR_BUCKET` and the sender address. Scope `ses:SendEmail` further if you need tighter controls.

---

## S3 Bucket Configuration

### Create the bucket

1. Create an S3 bucket in the same region as the app.
2. Choose a private bucket name dedicated to storybook output.
3. Keep the bucket **private** and do not enable public website hosting.

### Required settings

- **Block all public access** — enable all four public-access-block settings.
- **Server-side encryption** — use SSE-S3 (AES-256) or SSE-KMS.
- **Versioning** — optional but recommended for durability.
- The app generates **presigned download URLs** with configurable expiry (`DOWNLOAD_URL_EXPIRES_SECONDS`, default 1 hour) so PDFs are never public.

---

## SES Email

- **Verify sender identity** — either a specific email or the entire domain in SES.
- **Sandbox mode:** New SES accounts start in sandbox; you can only send to verified recipients. Request production access when ready.
- `EMAIL_DELIVERY_ENABLED=false` by default — the app writes PDFs to local outbox until you're ready.

---

## HTTPS

Do **not** expose port 8000 directly in production. Options:

- **Caddy** (simplest) — automatic Let's Encrypt TLS, reverse proxy to `localhost:8000`.
- **ALB + ACM** — AWS-managed TLS via Application Load Balancer with a free ACM certificate.

---

## App Runner (Optional — Eligible Accounts Only)

> **Caveat:** App Runner is **not** the default recommendation. Use it only if you already have an eligible App Runner account and are comfortable with its constraints.

An `apprunner.yaml` is included for convenience. Key considerations:

- WeasyPrint requires system libraries — use the ECR image-based deployment (push your Docker image), not source-code mode.
- Local filesystem is ephemeral on App Runner; all artifacts must go to S3.
- Cold-start latency may be noticeable for infrequent use.

---

## Observability & Logging

The application emits **structured JSON logs to stdout**, compatible with CloudWatch Logs, Docker `json-file` driver, and any log aggregator.

Each log line is a JSON object with at minimum:

```json
{"timestamp": "…", "level": "INFO", "logger": "app.services.job_runner", "message": "job lifecycle"}
```

Job-related logs include additional structured fields:

| Field         | Description                              |
|---------------|------------------------------------------|
| `job_id`      | UUID of the storybook job                |
| `event`       | Lifecycle event name (e.g. `job_started`, `job_succeeded`, `job_failed`) |
| `status`      | Current status (`processing`, `succeeded`, `failed`, etc.) |
| `duration_ms` | Wall-clock milliseconds for the job run  |

### Security

- Messages containing sensitive markers (`base64`, `api_key`, `authorization`, etc.) are automatically redacted.
- Full URLs (e.g. presigned S3 links) are truncated to `scheme://host/…` in log output.
- Stack traces appear **only in logs** (`exc` field), never in API responses or stored `error_message`.
- Stored `error_message` values are truncated to 256 characters.

### Failure Notifications

When `EMAIL_DELIVERY_ENABLED=true` and both `SES_SENDER_EMAIL` and `SES_ADMIN_EMAIL` are set, the runner sends a failure notification email via SES for any job that fails. The email contains the job ID and a concise error message; full stack traces remain in logs only.

### CloudWatch Integration (Docker)

To stream logs to CloudWatch from Docker Compose, set the `awslogs` driver:

```yaml
services:
  app:
    logging:
      driver: awslogs
      options:
        awslogs-region: us-east-1
        awslogs-group: /storypipeline/app
        awslogs-stream-prefix: app
```

Then create the log group and add `logs:CreateLogStream` / `logs:PutLogEvents` to the IAM policy.

---

## ECS Express Mode (Managed Alternative)

ECS Express Mode is a newer AWS managed-container option that removes much of the traditional ECS/Fargate configuration overhead. Consider it when:

- You want a managed container experience without EC2 administration.
- You may add background workers or multi-service architectures later.
- You prefer staying within the ECS ecosystem for future scaling.

It is a reasonable upgrade path from EC2 Docker once operational needs grow.

### Quick start

1. Push your Docker image to ECR.
2. Create an ECS cluster with Express Mode enabled.
3. Define a task with the same env vars from `.env.example`.
4. Attach the IAM task role with the S3 + SES policy above.
5. Map port 8000 and front with an ALB for TLS.

> **No Terraform/CDK required.** The AWS Console or CLI is sufficient for a single-service deploy. Add IaC only when you have multiple environments or team members.

---

## Deploy Script

An example EC2 bootstrap script is provided at `scripts/deploy_ec2_example.sh`. It is **commented, not executable by default** — read it, adapt it, then run the commands manually or via user-data.
