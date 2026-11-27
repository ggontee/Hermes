# Hermes 개발 스펙 v0.1 (초안)

> 2026-11-27 · 근거: `261127_Hermes_서비스컨셉_v1.md`, 결정 기록 `decisions.md`(8개 질문)
> 이 문서는 "무엇을, 어떤 구조로" 만들지 정한다. 카드 화면 세부는 `views.md`, 프롬프트와 JSON 스키마는 `prompts.md`, 서버 구성과 운영은 `deploy-aws.md`에서 따로 정한다.

---

## 1. 범위

### 1단계 (MVP)

| 포함 | 제외 (2단계 이후) |
|---|---|
| 블로그, 뉴스레터(Substack 등), 기관 블로그 RSS | X (RSSHub 경로는 준비만, 부계정 연결 후 켬) |
| Bluesky (RSSHub 또는 공식 RSS) | Threads |
| YouTube: Gemini 받아쓰기 → 한 줄 요약, 구간 요약, 스크립트 번역 | 스레드 묶기 |
| 세 가지 카드: 짧은 SNS / 긴 글 / 영상 | 스와이프 반응 기반 정렬 가중치 |
| 스와이프 보관·버림, 한 줄 코멘트, 보관함, 태그 | 주간 테마 정리, 푸시 알림 |
| 보관 카드의 [심화 분석] → Tana 저장 | Obsidian 연동 |
| PWA (iOS 홈 화면 추가), Tailscale 안에서만 접속 | |
| AWS EC2 배포, `deploy.sh`, 진단 스크립트 | |

## 2. 시스템 구성

```
[EC2 t4g.small · Ubuntu · 서울 · 인바운드 없음, Tailscale만]
 ├─ rsshub + redis (Docker Compose)   127.0.0.1:1200, ACCESS_KEY
 ├─ hermes-pipeline (Python)          systemd timer: 06:00 / 14:00 / 22:00 KST
 │    collect → normalize → dedupe → classify → AI 처리 → SQLite
 ├─ hermes-web (Next.js production)   127.0.0.1:3000 ← tailscale serve (HTTPS)
 └─ data/hermes.db                    SQLite, WAL 모드, 저장소는 이것 하나

[iPhone] Tailscale 켬 → https://<기기이름>.<tailnet>.ts.net → 홈 화면에 추가
```

원칙 (Mnemo에서 배운 것)
- 저장소는 `hermes.db` 하나. 파이프라인이 직접 쓰고, 웹앱은 읽고 상태만 바꾼다. JSON 파일 사본을 두지 않는다.
- 프로세스 관리자는 systemd 하나. Docker 컨테이너도 systemd 유닛이 `docker compose`로 띄운다. PM2, cron을 섞지 않는다.
- 웹앱은 처음부터 `next build` + `next start`.
- 스케줄러는 systemd timer 하나.
- 메모리 2GB에 swap 2GB를 잡는다. RSSHub(약 300~500MB), Next.js(약 200~300MB), 파이프라인 실행 중 Python(약 200MB) 기준.

## 3. 저장소 구조 (`ggontee/Hermes`)

```
config/
  sources.yaml        구독 목록 (인물 → 소스 여러 개)
  glossary.yaml       번역 용어집 (원어 유지 목록, 고정 번역어)
  settings.yaml       주기, 상한, 모델명 기본값 (비밀값 제외)
pipeline/             Python 3.12
  collectors/         rss.py, rsshub.py, youtube.py
  normalize.py        공통 Item 형태로 변환
  dedupe.py
  classify.py         short / long / video
  processors/         short.py(번역), long.py(요약+번역), video.py(Gemini)
  analysis.py         심화 분석 + Tana 쓰기 (웹앱이 요청)
  db.py               스키마, 마이그레이션
  budget.py           하루 건수·토큰 상한
  run.py              진입점
web/                  Next.js(App Router) + TS + Tailwind + Framer Motion
  (Mnemo에서 옮김: SwipeCard, CardStack, CommentModal, KeptList, TagCloud, Navigation, db.ts 패턴)
infra/                CDK (TypeScript): VPC 또는 기본 VPC, EC2 t4g.small, 보안 그룹(인바운드 0), IAM(SSM, Secrets Manager 읽기)
deploy/
  docker-compose.rsshub.yml
  systemd/            hermes-web.service, hermes-pipeline.service/.timer, hermes-rsshub.service
scripts/
  deploy.sh           git pull → 빌드 → systemctl restart (한 줄)
  diagnose.sh         서비스 상태, 마지막 실행, 상한 소진, 디스크·메모리
docs/
  dev-spec.md  views.md  prompts.md  deploy-aws.md
```

Mnemo에서 가져오지 않는 것: `cards.json`/`articles.json`, launchd plist, `youtube-transcript-api` 수집기, 테마·위키 컴파일(3단계에서 다시 봄).

## 4. 데이터 모델 (SQLite)

```sql
people   (id, name, field AI|Tech|Bio, affiliation, avatar_url)
sources  (id, person_id, type rss|bluesky|youtube|x, url_or_handle, enabled, last_fetched_at, last_error)
items    (id, source_id, person_id, external_id, url, published_at,
          kind short|long|video, lang, title_orig, body_orig, media_json,
          content_hash, canonical_url, group_id, fetched_at,
          UNIQUE(source_id, external_id))
cards    (id, item_id UNIQUE, kind,
          title_ko, summary_ko_json, so_what, tags_json,       -- 긴 글·영상
          translation_ko, translation_pairs_json,              -- 전문 번역 (문단 단위 원문 대응)
          video_oneliner, video_sections_json, transcript_ko,  -- 영상
          model, tokens_in, tokens_out, cost_usd,
          status pending|kept|discarded, user_comment, decided_at, created_at)
analyses (id, card_id, status queued|running|done|failed, content_md,
          tana_node_id, cost_usd, created_at, finished_at)
runs     (id, started_at, finished_at, fetched, new_items, processed, skipped_by_cap, errors_json)
usage    (date, provider, items, tokens_in, tokens_out, cost_usd)   -- 상한 계산용
```

## 5. 파이프라인

1. **수집:** `sources.yaml`의 enabled 소스만. 원본 RSS가 있으면 원본, 없으면 RSSHub. 소스별로 실패해도 나머지는 계속한다(`sources.last_error`에 기록).
2. **정규화:** 공통 Item으로 바꾼다. HTML은 본문 텍스트와 이미지 목록으로 나눈다.
3. **중복 제거와 묶기 (같은 사람의 여러 채널):**
   - **완전 중복:** `(source_id, external_id)`, 정규화한 URL, `content_hash`로 거른다. 같은 글이 블로그와 Substack에 동시에 오면 하나만 남긴다.
   - **링크 묶기:** SNS 글이 같은 사람의 블로그 글이나 영상 링크를 담고 있으면(예: Bluesky의 "새 글 올렸어요" + 링크) 새 카드를 만들지 않고, 원래 카드에 "작성자 한마디"로 붙인다. 원래 글이 아직 안 들어왔으면 SNS 글을 잠시 보류했다가 다음 회차에 다시 본다.
   - **같은 내용 다른 형식:** 같은 사람, 72시간 안, 제목이 거의 같으면(예: Dwarkesh 팟캐스트의 Substack 글과 YouTube 영상) 한 카드로 묶는다. 영상이 있으면 영상 카드를 기준으로 하고 글은 [다른 형식] 링크로 둔다.
   - 묶인 항목은 AI 처리를 한 번만 하므로 하루 상한도 한 건만 쓴다. `items.group_id`로 묶음을 기록한다.
4. **분류 (결정 7):**
   - YouTube → `video`
   - 블로그, 뉴스레터 → 길이와 상관없이 `long`
   - SNS(Bluesky, 나중에 X·Threads): 원문 **500자 이하 `short`**, 초과는 `long`
5. **AI 처리:** 최신 글부터, 하루 상한 안에서만. 넘친 글은 `pending_ai`로 남아 다음 회차에 처리한다.
6. **저장:** 한 트랜잭션에 `items` + `cards` + `usage`.

### 유형별 처리

| 유형 | 모델 (환경변수) | 출력 |
|---|---|---|
| short | `HERMES_MODEL_SHORT` (기본 Claude Haiku) | `translation_ko`. 링크, 멘션, 해시태그, 코드는 그대로 |
| long | `HERMES_MODEL_LONG` (기본 Claude Sonnet) | `title_ko`, `summary_ko[3]`, `so_what`, `tags[]`, `translation_ko`(문단 대응) |
| video | Gemini (`HERMES_MODEL_VIDEO`, 기본 `gemini-3.5-flash-lite`) 받아쓰기 → `HERMES_MODEL_LONG` 요약 | `video_oneliner`, `video_sections[5~8]{t, title, summary}`, `transcript_ko` |

- AI 응답은 JSON으로 고정하고 스키마 검증에 실패하면 한 번 다시 묻는다. 그래도 실패하면 해당 글만 `failed`로 둔다.
- 용어집(`glossary.yaml`)은 프롬프트에 넣는다. 고유명사, 모델명, 회사명은 원어 유지.
- 긴 글 전문 번역이 길면 문단 묶음으로 나눠 번역한다. 세부는 `prompts.md`.

## 6. 갱신 주기와 비용 상한 (결정 6)

| 설정 | 기본값 |
|---|---|
| 실행 시각 | 06:00, 14:00, 22:00 KST (systemd timer, `Persistent=true`) |
| 하루 AI 처리 건수 | 60건 |
| 하루 토큰 상한 | Claude 입력·출력 각각 설정값 (`prompts.md`에서 글당 예상치를 정한 뒤 확정) |
| 하루 Gemini 상한 | 영상 10개 |
| 심화 분석 | 하루 5건, 1건당 비용 상한 설정값 |

상한에 닿으면 그 회차는 수집과 저장만 하고 AI 처리를 건너뛴다. 진단 스크립트와 웹앱 상단에 "오늘 상한 도달"을 보여 준다.

## 7. 웹앱

Mnemo 구성을 그대로 따르고, 카드 안쪽만 유형별로 다르게 그린다 (세부는 `views.md`).

- **피드:** 카드 스택. 오른쪽 스와이프 = 보관, 왼쪽 = 버림. 보관 뒤 한 줄 코멘트(선택).
- **카드 상단:** 유형 배지(SNS / 글 / 영상), 분야, 인물, 시간.
- **필터:** 분야(AI / Tech / Bio / 전체), 유형, 인물.
- **상세:** 긴 글은 [요약] [전문 번역] [원문] 탭, 영상은 임베드 플레이어와 구간 목록(누르면 그 시점 재생).
- **보관함:** 보관 카드 목록, 태그, 코멘트 수정, [심화 분석] 버튼.
- **PWA:** `manifest.webmanifest`, 아이콘, 오프라인 셸(최근 카드 캐시). 푸시 알림은 3단계.

## 8. 보관과 심화 분석 → Tana (결정 8)

- 카드 수준은 Hermes 보관함에만 있다(Mnemo와 같음).
- 보관함에서 [심화 분석]을 누르면 `analyses`에 요청이 쌓이고, 파이프라인 워커가 처리한다(웹 요청 안에서 길게 돌리지 않는다).
- 분석은 **Hermes가 직접** 한다. 원문, 번역, 사용자 코멘트를 넣고 Claude가 Markdown 문서를 쓴다. Octopus나 Discord를 거치지 않는다.
- 결과는 Hermes 상세 화면에 보이고, **Tana에 노드로 저장**한다. 저장 뒤 `tana_node_id`를 남겨 두 번 쓰지 않는다.
- Tana 연결은 Tana 원격 MCP(`https://app.tana.inc/mcp`, OAuth). 토큰은 EC2의 비밀값 파일(또는 AWS Secrets Manager)에 두고 갱신 토큰으로 자동 갱신한다. Octopus의 `gateway/src/tana.ts` 방식을 참고한다.
- **Tana 태그: 기존 `#Research`** (2026-11-27 결정). 2026-11-10 기준 노드 12개, 필드 Topic, 작성일, 관련 리서치, 신뢰도(Octopus `docs/tana-schema.md`). 필드 채우는 규칙과 저장 위치(Library)는 첫 구현 때 실제 스키마를 읽고 확정한다.

## 9. 보안과 비밀값

- 보안 그룹 인바운드 0개. SSH도 Tailscale SSH(또는 SSM Session Manager)로만.
- RSSHub, Next.js는 `127.0.0.1`에만 바인딩. 외부 노출은 `tailscale serve`뿐.
- 비밀값: `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, `RSSHUB_ACCESS_KEY`, Tana 토큰, (2단계) X `auth_token`. repo에 넣지 않는다. `/etc/hermes/env`(권한 600) 또는 Secrets Manager.
- repo는 private로 둔다(번역 전문은 repo에 없지만 구독 목록·설정이 있다).

## 10. 추가 결정 (2026-11-27)

| 항목 | 결정 |
|---|---|
| Tana 저장 태그 | 기존 `#Research` |
| Anthropic API 키 | Hermes용 키를 따로 발급 (Octopus 키와 분리) |
| EC2 생성 | CDK (repo의 `infra/`, Octopus처럼). 같은 계정 `ggontee`, 서울, Octopus 스택과 별도 스택 |
| 구독 목록 | `config/sources.yaml` 초안 → 오너 검토 |
