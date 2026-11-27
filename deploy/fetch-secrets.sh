#!/bin/bash
# Secrets Manager hermes/* → /etc/hermes/env (root 600). 부팅 때와 비밀값을 바꾼 뒤 돈다.
set -euo pipefail
AWS=/snap/bin/aws
export AWS_DEFAULT_REGION="${AWS_DEFAULT_REGION:-ap-northeast-2}"
get() { "$AWS" secretsmanager get-secret-value --secret-id "$1" --query SecretString --output text 2>/dev/null || true; }

tmp="$(mktemp)"
chmod 600 "$tmp"
{
  echo "NODE_ENV=production"
  echo "HERMES_DB_PATH=/var/lib/hermes/hermes.db"
  echo "TZ=Asia/Seoul"
  for pair in anthropic-api-key:ANTHROPIC_API_KEY gemini-api-key:GEMINI_API_KEY tana-token:TANA_TOKEN x-auth-token:X_AUTH_TOKEN; do
    v="$(get "hermes/${pair%%:*}")"
    [ -n "$v" ] && printf '%s=%s\n' "${pair##*:}" "$v"
  done
} > "$tmp"
install -m 600 -o root -g root "$tmp" /etc/hermes/env
rm -f "$tmp"
# 값은 남기지 않고 어떤 키가 채워졌는지만 남긴다
echo "hermes env: $(cut -d= -f1 /etc/hermes/env | tr '\n' ' ')"
