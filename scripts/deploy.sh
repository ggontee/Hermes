#!/bin/bash
# Mac에서 한 줄 배포: ./scripts/deploy.sh
# main이 깨끗하고 origin과 같을 때만 서버(Tailscale SSH)에 갱신을 시킨다. 자동 커밋은 하지 않는다.
set -euo pipefail
HOST="${HERMES_SSH:-ubuntu@hermes}"
cd "$(dirname "$0")/.."

branch="$(git rev-parse --abbrev-ref HEAD)"
[ "$branch" = "main" ] || { echo "main 브랜치에서 실행하세요 (지금: $branch)"; exit 1; }
[ -z "$(git status --porcelain)" ] || { echo "커밋하지 않은 변경이 있습니다"; exit 1; }
git fetch -q origin main
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || { echo "로컬 main과 origin/main이 다릅니다. push 또는 pull 하세요"; exit 1; }

echo "→ $HOST 에 $(git rev-parse --short HEAD) 배포"
ssh "$HOST" "sudo /opt/hermes/deploy/server-update.sh ${1:-}"
