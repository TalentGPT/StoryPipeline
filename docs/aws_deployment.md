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

## ECS Express Mode (Alternative)

ECS Express Mode is a newer AWS managed-container option that removes much of the traditional ECS/Fargate configuration overhead. Consider it when:

- You want a managed container experience without EC2 administration.
- You may add background workers or multi-service architectures later.
- You prefer staying within the ECS ecosystem for future scaling.

It is a reasonable upgrade path from EC2 Docker once operational needs grow.
