# Hermes 배포·운영·진단 v0.1 (초안)

> 2026-11-27 · 대상: AWS 계정 `ggontee`(Octopus와 같은 계정), 서울 `ap-northeast-2`. Octopus 스택과 별도 CDK 스택 `Hermes`.
> 로그인은 Octopus와 같은 SSO 프로필(`AWS_PROFILE=octopus`)을 쓴다. 다른 프로필을 만들지는 첫 배포 때 오너가 정한다.

## 1. 인프라 (CDK, `infra/`)

| 리소스 | 설정 |
|---|---|
| VPC | 새 VPC 1개, 퍼블릭 서브넷 1개(AZ 1개), NAT 없음. Octopus VPC와 섞지 않는다 |
| EC2 | `t4g.small`(ARM, 2 vCPU, 2GB), Ubuntu 24.04 LTS arm64, gp3 30GB(암호화) |
| 보안 그룹 | **인바운드 0개.** 아웃바운드 443, 80(apt), 41641/udp(Tailscale 직접 연결) |
| 퍼블릭 IP | IPv4 1개(아웃바운드용. Elastic IP는 쓰지 않음) |
| IAM 역할 | `AmazonSSMManagedInstanceCore`(비상 접속), Secrets Manager `hermes/*` 읽기, CloudWatch 에이전트 |
| 비밀 | Secrets Manager `hermes/anthropic-api-key`, `hermes/gemini-api-key`, `hermes/rsshub-access-key`, `hermes/tana-token`, (2단계) `hermes/x-auth-token` |
| 백업 | DLM 스냅샷 하루 1번, 7일 보관 |
| 예산 | 기존 `octopus-monthly`($50)에 포함. 비용 할당 태그 `project=hermes` |
| UserData | 첫 부팅 스크립트: swap 2GB, Docker, Node 22, Python 3.12, Tailscale 설치(인증 키는 Secrets Manager `hermes/tailscale-authkey`, 1회용) |

예상 월 비용(서울, 확인 필요): EC2 t4g.small 약 $12~13, EBS 30GB 약 $2.5, 퍼블릭 IPv4 약 $3.6, 스냅샷 소액. 합계 약 $18~20. AI API 비용은 별도.

명령:
```bash
cd infra
AWS_PROFILE=octopus npx cdk diff Hermes
AWS_PROFILE=octopus npx cdk deploy Hermes
```
첫 `cdk deploy`는 오너 승인 뒤 한다.

## 2. 서버 구성

```
/opt/hermes/                 git clone (main)
  .venv/                     파이프라인 Python
  web/.next/                 next build 결과
/var/lib/hermes/hermes.db    SQLite (WAL). repo 밖에 둔다
/etc/hermes/env              비밀값 (권한 600, 부팅 때 Secrets Manager에서 채움)
```

### systemd 유닛 (프로세스 관리자는 이것 하나)

| 유닛 | 하는 일 |
|---|---|
| `hermes-secrets.service` | 부팅 때 Secrets Manager → `/etc/hermes/env` (oneshot) |
| `hermes-rsshub.service` | `docker compose -f deploy/docker-compose.rsshub.yml up` (rsshub + redis, `127.0.0.1:1200`) |
| `hermes-web.service` | `next start -H 127.0.0.1 -p 3000` |
| `hermes-pipeline.service` | `python -m pipeline.run` (oneshot) |
| `hermes-pipeline.timer` | `OnCalendar=*-*-* 06,14,22:00:00 Asia/Seoul`, `Persistent=true` |
| `hermes-analysis.service` | 심화 분석 대기열 워커 (상시, 대기열이 비면 쉼) |

### Tailscale

```bash
sudo tailscale up --ssh --hostname=hermes
sudo tailscale serve --bg --https=443 http://127.0.0.1:3000
```
- iPhone: Tailscale 켜고 `https://hermes.<tailnet>.ts.net` → 공유 → 홈 화면에 추가.
- SSH는 Tailscale SSH로만. 22번 포트는 열지 않는다. Tailscale이 끊기면 SSM Session Manager로 들어간다.

### 메모리 예산 (2GB + swap 2GB)

| 프로세스 | 예상 | 제한 |
|---|---|---|
| RSSHub | 300~500MB | Docker `mem_limit: 600m` |
| Redis | 30~50MB | `maxmemory 64mb` |
| Next.js | 200~300MB | `MemoryMax=500M` |
| 파이프라인 (실행 중) | 150~300MB | `MemoryMax=600M` |
| 분석 워커 | 100MB | `MemoryMax=300M` |

## 3. 배포 (`scripts/deploy.sh`, 한 줄)

```bash
./scripts/deploy.sh          # Mac에서 실행
```
흐름:
1. 로컬 변경이 커밋·푸시돼 있는지 확인 (안 돼 있으면 멈춤. Mnemo처럼 자동 커밋하지 않는다)
2. `ssh hermes` (Tailscale SSH) → `cd /opt/hermes && git pull --ff-only`
3. 바뀐 게 있으면: `pip install -r pipeline/requirements.txt`, `npm ci && npm run build`
4. DB 마이그레이션 (`python -m pipeline.db migrate`)
5. `systemctl restart hermes-web hermes-analysis` (파이프라인은 다음 회차에 새 코드로 돈다)
6. `curl -fsS http://127.0.0.1:3000/api/health` 확인, 실패하면 직전 커밋으로 되돌리고 다시 빌드

빌드는 t4g.small에서 1~3분, 그동안 웹앱이 잠시 끊긴다.

## 4. 진단 (`scripts/diagnose.sh`)

서버에서 `hermes-diagnose` 로 실행. 결과 예:
```
[서비스]   rsshub ✓  web ✓  analysis ✓  timer ✓ (다음 22:00)
[마지막 회차] 14:00  새 글 23 · AI 처리 18 · 상한으로 미룸 0 · 오류 1
[오늘 사용]  42/60건 · 영상 3/10 · 분석 1/5 · 추정 $0.84
[소스 오류]  Andrew Ng/The Batch: HTTP 404 (마지막 성공: 없음)
[자원]      메모리 1.3/1.9GB · swap 120MB · 디스크 6.2/29GB · DB 48MB
[RSSHub]    /healthz 200
```
- `hermes-diagnose --sources`: 모든 소스를 한 번씩 열어 HTTP 코드, 항목 수, 최신 글 날짜를 표로 보여 준다(`sources.yaml`의 `verified` 갱신용).
- 같은 정보를 웹앱 `/status` 화면에도 보여 준다.

## 5. 운영 규칙

- 스케줄러는 systemd timer 하나. cron을 쓰지 않는다.
- 로그: `journalctl -u hermes-*`. 본문(원문·번역)은 로그에 남기지 않고 건수·상태만 남긴다.
- DB 백업: 하루 1번 `sqlite3 .backup` → `/var/lib/hermes/backup/` 7개 보관 + EBS 스냅샷.
- 비밀값 교체: Secrets Manager 값 변경 → `systemctl restart hermes-secrets hermes-web hermes-analysis`.
- 업그레이드: Ubuntu 보안 업데이트는 `unattended-upgrades`. RSSHub 이미지는 태그를 고정하고 한 달에 한 번 올린다.

## 6. 첫 배포 순서

1. 오너: Anthropic Console에서 Hermes용 API 키 발급 → `hermes/anthropic-api-key`에 저장 (Octopus의 `scripts/put-secret.sh` 방식)
2. 오너: Tailscale 관리 화면에서 1회용 인증 키 발급 → `hermes/tailscale-authkey`
3. Gemini 키: Octopus 키를 함께 쓸지 새로 발급할지 오너가 정함 → `hermes/gemini-api-key`
4. `cdk deploy Hermes` (오너 승인 뒤)
5. Tailscale에 `hermes` 기기가 보이면 `tailscale serve` 설정, iPhone에서 접속 확인
6. `hermes-diagnose --sources`로 구독 목록 검증
7. 파이프라인 수동 1회 → 카드 확인 → 타이머 켬
