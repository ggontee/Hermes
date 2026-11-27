#!/bin/bash
# 서버 진단: hermes-diagnose [--sources]
set -uo pipefail
DB="${HERMES_DB_PATH:-/var/lib/hermes/hermes.db}"
q() { sudo sqlite3 -readonly "$DB" "$1" 2>/dev/null; }
mark() { systemctl is-active -q "$1" && echo "✓" || echo "✗"; }

if [ "${1:-}" = "--sources" ]; then
  cd /opt/hermes && sudo -u hermes -H bash -c 'set -a; . /etc/hermes/env 2>/dev/null; set +a; .venv/bin/python -m pipeline.run --check-sources' 
  exit $?
fi

next="$(systemctl list-timers hermes-pipeline.timer --no-legend 2>/dev/null | awk '{print $2" "$3}')"
timer="$(systemctl is-enabled -q hermes-pipeline.timer && echo "✓ (다음 ${next:-?})" || echo "꺼짐")"
echo "[서비스]     rsshub $(mark hermes-rsshub)  web $(mark hermes-web)  timer $timer"

echo "[마지막 회차] $(q "SELECT strftime('%m-%d %H:%M', started_at, '+9 hours') || '  새 글 ' || new_items || ' · AI 처리 ' || processed || ' · 상한으로 미룸 ' || deferred_by_cap || ' · 오류 ' || json_array_length(errors_json) || CASE WHEN finished_at IS NULL THEN ' (진행 중/중단)' ELSE '' END FROM runs ORDER BY id DESC LIMIT 1")"

today="$(TZ=Asia/Seoul date +%F)"
echo "[오늘 사용]   $(q "SELECT group_concat(kind || ' ' || count, ' · ') || ' · 추정 \$' || printf('%.2f', sum(cost_usd)) FROM usage WHERE date = '$today'")"

errs="$(q "SELECT '  ' || p.name || '/' || s.type || ': ' || s.last_error || ' (마지막 성공: ' || COALESCE(s.last_success_at, '없음') || ')' FROM sources s JOIN people p ON p.id = s.person_id WHERE s.enabled = 1 AND s.last_error IS NOT NULL")"
echo "[소스 오류]   ${errs:+$'\n'}${errs:-없음}"

mem="$(free -m | awk '/Mem:/{printf "%.1f/%.1fGB", $3/1024, $2/1024} /Swap:/{printf " · swap %dMB", $3}')"
disk="$(df -h / | awk 'NR==2{print $3"/"$2}')"
dbsize="$(sudo du -h "$DB" 2>/dev/null | cut -f1)"
echo "[자원]       메모리 $mem · 디스크 $disk · DB ${dbsize:-?}"
echo "[RSSHub]     /healthz $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:1200/healthz)"
echo "[웹앱]       /api/health $(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:3000/api/health)"
