#!/bin/bash
# EC2 첫 부팅 스크립트 (CDK UserData로 들어간다). root로 한 번 돈다.
# 로그: /var/log/hermes-bootstrap.log
set -euxo pipefail
exec > >(tee -a /var/log/hermes-bootstrap.log) 2>&1

REPO_URL="__REPO_URL__"
export AWS_DEFAULT_REGION="__AWS_REGION__"
export DEBIAN_FRONTEND=noninteractive

secret() { /snap/bin/aws secretsmanager get-secret-value --secret-id "$1" --query SecretString --output text 2>/dev/null || true; }

# 1. swap 2GB, 시간대
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
timedatectl set-timezone Asia/Seoul

# 2. 패키지: Docker, Python 3.12, Node 22, AWS CLI, Tailscale
apt-get update
apt-get install -y docker.io docker-compose-v2 python3.12-venv python3-pip sqlite3 git jq curl unattended-upgrades
systemctl enable --now docker
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
apt-get install -y nodejs
snap install aws-cli --classic
curl -fsSL https://tailscale.com/install.sh | sh

# 3. Tailscale: 1회용 인증 키로 붙고, 웹앱을 tailnet 안에서만 HTTPS로 연다
TS_KEY="$(secret hermes/tailscale-authkey)"
if [ -n "$TS_KEY" ]; then
  tailscale up --authkey "$TS_KEY" --ssh --hostname=hermes
  tailscale serve --bg --https=443 http://127.0.0.1:3000 || true
else
  echo "hermes/tailscale-authkey 없음: SSM으로 들어가 'tailscale up --ssh --hostname=hermes'를 직접 실행"
fi

# 4. 실행 사용자와 디렉터리
id hermes >/dev/null 2>&1 || useradd --system --create-home --home-dir /var/lib/hermes --shell /usr/sbin/nologin hermes
install -d -o hermes -g hermes -m 750 /var/lib/hermes /var/lib/hermes/backup
install -d -o hermes -g hermes /opt/hermes
install -d -m 755 /etc/hermes

# 5. 코드: 비공개 저장소라 배포 키(읽기 전용)로 받는다. SSH 22번은 막혀 있으니 ssh.github.com:443을 쓴다.
DEPLOY_KEY="$(secret hermes/github-deploy-key)"
if [ -n "$DEPLOY_KEY" ]; then
  install -d -o hermes -g hermes -m 700 /var/lib/hermes/.ssh
  printf '%s\n' "$DEPLOY_KEY" > /var/lib/hermes/.ssh/id_ed25519
  cat > /var/lib/hermes/.ssh/config <<'CFG'
Host github.com
  HostName ssh.github.com
  Port 443
  User git
  IdentityFile ~/.ssh/id_ed25519
  StrictHostKeyChecking accept-new
CFG
  chown -R hermes:hermes /var/lib/hermes/.ssh && chmod 600 /var/lib/hermes/.ssh/*
fi
if [ ! -d /opt/hermes/.git ]; then
  sudo -u hermes -H git clone "$REPO_URL" /opt/hermes
fi

# 6. 설치 (venv, npm build, DB 마이그레이션, systemd 유닛). 타이머는 첫 수동 실행을 확인한 뒤 켠다.
/opt/hermes/deploy/install.sh
echo "bootstrap 완료"
