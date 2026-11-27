#!/bin/bash
# 서버 설치·갱신. root로 실행한다. 여러 번 돌려도 같다.
set -euo pipefail
APP=/opt/hermes
cd "$APP"
as_hermes() { sudo -u hermes -H "$@"; }

# Python
[ -d .venv ] || as_hermes python3.12 -m venv .venv
as_hermes .venv/bin/pip install -q --upgrade pip
as_hermes .venv/bin/pip install -q -r pipeline/requirements.txt

# 비밀값과 DB
systemctl daemon-reload
install -m 644 deploy/systemd/*.service deploy/systemd/*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now hermes-secrets.service
set -a; . /etc/hermes/env; set +a
as_hermes env HERMES_DB_PATH="$HERMES_DB_PATH" .venv/bin/python -m pipeline.db migrate

# 웹앱 (t4g.small에서 1~3분)
as_hermes bash -c "cd web && npm ci --no-audit --no-fund && NODE_OPTIONS=--max-old-space-size=1024 npm run build"

# 서비스
ln -sf "$APP/deploy/diagnose.sh" /usr/local/bin/hermes-diagnose
systemctl enable --now hermes-rsshub.service hermes-web.service hermes-analysis.service hermes-backup.timer
systemctl restart hermes-web.service hermes-analysis.service

if ! systemctl is-enabled -q hermes-pipeline.timer; then
  echo "수집 타이머는 꺼져 있다. 확인 후: sudo systemctl start hermes-pipeline && sudo systemctl enable --now hermes-pipeline.timer"
fi
