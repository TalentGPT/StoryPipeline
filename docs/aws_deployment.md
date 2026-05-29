# AWS Deployment Guide

## Recommended V1 Default: EC2 + Docker

For a private family-use v1, the default deployment path should be a small EC2 instance running Docker Compose.

Why this is the default:
- simple to understand
- easy to debug
- good fit for WeasyPrint system dependencies
- low operational complexity for a single private workload

## EC2 Docker Steps

1. Launch a small Ubuntu EC2 instance.
2. Install Docker and Docker Compose plugin.
3. Clone the repository.
4. Copy `.env.example` to `.env` and fill in real values.
5. Run `docker compose up --build -d`.
6. Put Nginx or Caddy in front if you need TLS termination on the box.
7. Store generated files under the mounted `./data` volume or push outputs to S3.

## App Runner

App Runner can be included for already-eligible accounts, but it is optional.

Notes:
- App Runner can be attractive for simple container deployment.
- WeasyPrint system packages and local filesystem assumptions should be tested carefully.
- For new customers or greenfield setups, EC2 Docker or ECS Express Mode may be more predictable.

## ECS Express Mode

ECS Express Mode is a modern managed alternative when you want less EC2 administration.

Why consider it:
- better long-term managed posture
- container-native
- easier evolution if background workers are added later

## Storage

- S3 should hold finished PDFs and durable artifacts.
- Local mounted `data/` can be used for temporary work files and local outbox behavior.

## Email

- Use SES for success/failure emails.
- Start in sandbox or verified-sender mode if needed.
