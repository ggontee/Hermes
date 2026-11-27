#!/bin/bash
# 서버에서 root로 실행: main을 받아 설치하고, 웹앱 상태 확인이 실패하면 직전 커밋으로 되돌린다.
set -euo pipefail
cd /opt/hermes
old="$(git rev-parse HEAD)"
sudo -u hermes -H git fetch -q origin main
sudo -u hermes -H git merge -q --ff-only origin/main
new="$(git rev-parse HEAD)"
if [ "$old" = "$new" ] && [ "${1:-}" != "--force" ]; then
  echo "바뀐 것 없음 ($new)"
  exit 0
fi
echo "갱신: ${old:0:7} → ${new:0:7}"

health() {
  for _ in $(seq 1 30); do
    curl -fsS http://127.0.0.1:3000/api/health >/dev/null 2>&1 && return 0
    sleep 2
  done
  return 1
}

if /opt/hermes/deploy/install.sh && health; then
  echo "배포 완료 ${new:0:7}"
else
  echo "상태 확인 실패: ${old:0:7}로 되돌린다" >&2
  sudo -u hermes -H git reset -q --hard "$old"
  /opt/hermes/deploy/install.sh && health && echo "되돌림 완료 ${old:0:7}" >&2
  exit 1
fi
