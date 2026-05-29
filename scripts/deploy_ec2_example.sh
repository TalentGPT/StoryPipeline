#!/usr/bin/env bash
# =============================================================================
# deploy_ec2_example.sh — Example EC2 bootstrap for StoryPipeline
#
# This script is a REFERENCE, not a push-button installer.
# Read each section, adapt to your environment, then run manually or paste
# into EC2 user-data.
#
# Default deployment: EC2 + Docker Compose (single instance, single container).
# No Terraform, no CDK, no multi-service orchestration.
#
# Prerequisites:
#   - Ubuntu 22.04 or 24.04 AMI
#   - t3.small or larger (WeasyPrint needs ~1 GB RAM)
#   - IAM instance profile with S3 + SES permissions (see docs/aws_deployment.md)
#   - Security group: allow TCP 443 (or 8000 for testing)
#   - 20 GB gp3 storage minimum
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# 1. System packages + Docker
# ---------------------------------------------------------------------------
sudo apt-get update -y
sudo apt-get install -y docker.io docker-compose-v2 git curl

# Let the current user run docker without sudo
sudo usermod -aG docker "$USER"

# NOTE: You need to log out and back in (or use `newgrp docker`) for the
# group change to take effect. In user-data this happens automatically on
# next login.

# ---------------------------------------------------------------------------
# 2. Clone the repo
# ---------------------------------------------------------------------------
# Replace with your actual repo URL (HTTPS or SSH).
# If private, set up a deploy key or use a GitHub PAT.
REPO_URL="https://github.com/YOUR_USER/StoryPipeline.git"
APP_DIR="/home/ubuntu/StoryPipeline"

if [ ! -d "$APP_DIR" ]; then
  git clone "$REPO_URL" "$APP_DIR"
fi
cd "$APP_DIR"

# ---------------------------------------------------------------------------
# 3. Create .env
# ---------------------------------------------------------------------------
# Copy the example and fill in real values.
# NEVER commit .env to version control.
if [ ! -f .env ]; then
  cp .env.example .env
  echo ">>> .env created from .env.example — edit it now before starting <<<"
  echo ">>> At minimum set: API_KEY, OPENAI_API_KEY, S3_BUCKET, SES_SENDER_EMAIL <<<"
  # Uncomment the next line to pause here (useful in interactive sessions):
  # exit 0
fi

# ---------------------------------------------------------------------------
# 4. Build and start
# ---------------------------------------------------------------------------
docker compose up --build -d

# ---------------------------------------------------------------------------
# 5. Verify
# ---------------------------------------------------------------------------
echo "Waiting for container to start..."
sleep 5
curl -sf http://localhost:8000/healthz && echo " ✓ healthy" || echo " ✗ healthz failed"

# ---------------------------------------------------------------------------
# 6. HTTPS (optional — recommended for production)
# ---------------------------------------------------------------------------
# Option A: Caddy (simplest — automatic Let's Encrypt)
#
#   sudo apt-get install -y caddy
#   cat <<EOF | sudo tee /etc/caddy/Caddyfile
#   yourdomain.example.com {
#       reverse_proxy localhost:8000
#   }
#   EOF
#   sudo systemctl restart caddy
#
# Option B: ALB + ACM
#   - Create an ALB in the same VPC, target group pointing to this instance:8000
#   - Attach an ACM certificate for your domain
#   - Point DNS to the ALB
#
# Either way, lock down the security group so port 8000 is only accessible
# from localhost or the ALB, not the public internet.

# ---------------------------------------------------------------------------
# 7. Updates
# ---------------------------------------------------------------------------
# To deploy a new version:
#
#   cd /home/ubuntu/StoryPipeline
#   git pull
#   docker compose up --build -d
#
# Docker Compose will rebuild only if files changed. The healthcheck in
# docker-compose.yml will restart the container if it becomes unhealthy.

# ---------------------------------------------------------------------------
# 8. Logs
# ---------------------------------------------------------------------------
# View live logs:
#   docker compose logs -f
#
# View last 100 lines:
#   docker compose logs --tail 100
