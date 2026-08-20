#!/bin/bash
set -euo pipefail
exec > >(tee -a /var/log/coolproof-bootstrap.log | logger -t coolproof-bootstrap -s 2>/dev/console) 2>&1
dnf update -y
dnf install -y docker git jq amazon-ssm-agent openssl
systemctl enable --now docker
systemctl enable --now amazon-ssm-agent
usermod -aG docker ec2-user
install -d -o ec2-user -g ec2-user /opt/coolproof
cd /opt/coolproof
if [ ! -d .git ]; then
  git clone --depth 1 --branch codex/coolproof-v1 https://github.com/Auro-rium/coolproof.git .
else
  git fetch origin codex/coolproof-v1
  git reset --hard origin/codex/coolproof-v1
fi
runtime_json="$(aws secretsmanager get-secret-value --region us-east-2 --secret-id '${runtime_secret_arn}' --query SecretString --output text)"
fortyguard_key="$(aws secretsmanager get-secret-value --region us-east-2 --secret-id '${fortyguard_secret_arn}' --query SecretString --output text)"
backboard_key="$(aws secretsmanager get-secret-value --region us-east-2 --secret-id '${backboard_secret_arn}' --query SecretString --output text)"
nvidia_key="$(aws secretsmanager get-secret-value --region us-east-2 --secret-id '${nvidia_secret_arn}' --query SecretString --output text)"
imds_token="$(curl -fsS -X PUT -H 'X-aws-ec2-metadata-token-ttl-seconds: 21600' http://169.254.169.254/latest/api/token)"
public_ip="$(curl -fsS -H "X-aws-ec2-metadata-token: $imds_token" http://169.254.169.254/latest/meta-data/public-ipv4)"
api_domain="$${public_ip}.sslip.io"
umask 077
printf '%s\n' "$runtime_json" | jq --arg fg "$fortyguard_key" --arg bb "$backboard_key" --arg nim "$nvidia_key" --arg domain "$api_domain" '.COOLPROOF_FORTYGUARD_API_KEY=$fg | .COOLPROOF_BACKBOARD_API_KEY=$bb | .COOLPROOF_NIM_API_KEY=$nim | .CADDY_EMAIL="" | .COOLPROOF_API_DOMAIN=$domain' > .env
install -d -m 755 deploy/secrets
openssl rand -hex 24 > deploy/secrets/grafana_admin_password
# Grafana reads this through the Compose secret mount. Keep it readable only
# by root; the file contains a live credential generated during provisioning.
chmod 600 deploy/secrets/grafana_admin_password
chown -R ec2-user:ec2-user /opt/coolproof
docker compose pull otel-collector caddy prometheus grafana
docker compose build api
# Apply the idempotent Alembic schema revision before publishing the API. This
# also enables pgvector on RDS and is safe to rerun during instance replacement.
docker compose run --rm api alembic upgrade head
docker compose up -d
docker compose ps
