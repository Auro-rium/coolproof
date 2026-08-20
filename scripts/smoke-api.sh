#!/usr/bin/env bash
set -euo pipefail

base_url="${COOLPROOF_API_URL:-http://127.0.0.1:8000}"
base_url="${base_url%/}"

check_health() {
  local endpoint="$1"
  local response
  response="$(curl --fail --silent --show-error --max-time 15 "${base_url}${endpoint}")"
  python -c 'import json, sys; body=json.load(sys.stdin); assert body.get("status") in {"ok", "healthy"}, body' <<<"${response}"
}

check_health "/health/live"
check_health "/health/ready"
printf 'API smoke check passed: %s\n' "$base_url"
