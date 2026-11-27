# Hermes: 해외 AI·Tech·Bio 인플루언서 한국어 피드

> 서비스 컨셉 v1 · 2026-11-27 · 이름은 가칭 (Hermes = 해석·번역을 뜻하는 hermeneutics의 어원)
> 이 문서는 컨셉까지만 다룬다. 구현과 세부 설계는 Claude Code에서 Mnemo 때처럼 **질문 → 추가 문서**로 하나씩 정한다.

---

## 1. 한 줄 정의

해외 AI·Tech·Bio 주요 인물의 SNS·블로그·영상을 **RSSHub로 모으고**, **콘텐츠 유형에 맞게 한국어로 번역하거나 요약한 뒤**, **Mnemo처럼 카드를 스와이프하며** 훑어보고 골라 담는 개인용 웹앱. iPhone에서는 홈 화면 앱(PWA)으로 쓴다.

## 2. 왜 만드나

- 기존 리더는 둘 중 하나가 빠진다. Flipboard, Surf, Reeder는 X를 못 넣고, Folo는 한국어 번역이 안 되며, Inoreader도 X 연동이 끊겼다. 해외 SNS를 한 화면에서 한국어로 읽을 수 있는 서비스가 없다.
- 지금까지 써 본 것 중 가장 손이 간 건 Mnemo의 카드 트리아지(한 장씩 보고 보관 또는 버림)였다. 이 방식을 해외 인플루언서 피드에 그대로 적용한다.

## 3. 확정된 방향

| 항목 | 결정 |
|---|---|
| 서버 | 이미 구축된 AWS 서버 |
| 화면 | Mnemo와 거의 같은 구성(카드 스와이프, 보관/버림, 보관함). 콘텐츠 유형별 뷰만 다르게 |
| 수집 | RSSHub 기반. 원본 RSS가 있는 소스(블로그, Substack, YouTube)는 직접 구독 |
| 형태 | 웹앱(PWA) → iOS Safari "홈 화면에 추가" |
| 진행 | 컨셉은 이 문서, 구현은 Claude Code |

## 4. 핵심 흐름

```
config/sources.yaml (구독 목록)
   ↓
수집 ─ RSSHub: X, Threads 등 RSS가 없는 소스
     └ 원본 RSS: 블로그, Substack, YouTube 채널
   ↓
정규화 → 중복 제거 → 유형 분류 (짧은 SNS / 긴 글 / 영상)
   ↓
유형별 AI 처리 (전문 번역 또는 요약+번역)
   ↓
SQLite 저장 (저장소는 하나)
   ↓
웹앱: 카드 스와이프 → 보관/버림 (+ 한 줄 코멘트) → 보관함
```

## 5. 콘텐츠 유형별 처리와 화면 (이 서비스의 핵심)

### 5.1 짧은 SNS

- **대상:** X, Threads, Bluesky 게시물 중 짧은 글 (경계는 예를 들어 원문 500자 이하. Claude Code에서 확정)
- **처리:** 요약하지 않고 **전문을 그대로 번역**한다. 링크, 멘션, 해시태그, 코드는 손대지 않는다.
- **카드:** 작성자(아바타, 이름, 소속 한 줄), 시간 / 번역 본문 / 첨부 이미지 / [원문 보기] 토글
- **2단계:** 같은 작성자의 연속 게시물(스레드)을 한 카드로 묶는다.

### 5.2 긴 글

- **대상:** 블로그, 뉴스레터, X 장문 글, 긴 스레드
- **처리:** 한국어 제목, 3줄 요약, soWhat(왜 중요한가), 태그를 만든다. **전문 번역도 함께 저장**한다.
- **카드:** Mnemo 카드와 같은 구성 (제목, 요약, soWhat, 태그)
- **상세:** [요약] [전문 번역] [원문] 탭. 전문 번역은 문단 단위로 원문과 나란히 볼 수 있게 한다.

### 5.3 영상 (YouTube)

- **처리:** 스크립트로 한 줄 요약과 타임스탬프 구간 요약(5~8개)을 만든다.
- **카드:** 썸네일, 길이, 채널 / 한 줄 요약 / 주요 구간 3개
- **상세:** 임베드 플레이어, 구간 목록(누르면 그 시점부터 재생), 스크립트 번역
- **주의:** AWS에서는 스크립트 수집이 막힐 가능성이 높다 (8장 2번).

### 5.4 공통

- 필터: 분야(AI / Tech / Bio / 전체), 유형, 인물별 보기
- 카드 상단에 유형 배지(SNS, 글, 영상)를 붙인다.
- 번역 원칙: 고유명사, 모델명, 회사명은 원어 그대로 둔다. 용어집(`config/glossary.yaml`)으로 관리한다.

## 6. Mnemo에서 가져올 것

**그대로 쓰는 것**
- 카드 스와이프: 오른쪽 보관, 왼쪽 버림, 스와이프 뒤 한 줄 코멘트
- 보관함, 태그, Obsidian 내보내기(선택)
- 스택: Next.js(App Router) + TypeScript + Tailwind + Framer Motion / Python 파이프라인 / Claude API / SQLite
- 배포를 한 줄로 끝내는 `deploy.sh`, 진단 스크립트

**Mnemo에서 배운 것 (반복하지 않기)**
- 저장소는 하나로 둔다. 파이프라인이 SQLite에 직접 쓴다 (`cards.json`과 `mnemo.db`가 어긋났던 문제 방지).
- 프로세스 관리자도 하나만 쓴다 (AWS에서는 systemd. PM2와 섞어 쓰지 않는다).
- 웹앱은 처음부터 production 모드(`next build` + `next start`)로 띄운다.
- 스케줄러도 하나만 쓴다 (systemd timer와 cron 중 하나).

## 7. 아키텍처 (AWS)

```
[AWS 인스턴스]  외부에 공개하지 않고 Tailscale 안에서만 접근
 ├─ rsshub (Docker) + redis   내부 포트만 사용, ACCESS_KEY 설정
 ├─ pipeline (Python)         1~2시간마다 실행
 │    fetch → classify → Claude API → SQLite
 ├─ webapp (Next.js, PWA)     :3000
 └─ data/hermes.db            SQLite (WAL 모드)

[iPhone] Safari → 홈 화면에 추가 → Tailscale로 접속
```

- **모델 배분 (초안):** 짧은 글 번역은 Claude Haiku, 긴 글과 영상 요약은 Claude Sonnet. 모델명은 환경변수로 뺀다.
- **AI 응답은 JSON으로 고정한다.** 예: `{title_ko, summary_ko[3], so_what, tags[], translation_ko}`
- **비용 상한:** 하루 처리 건수와 토큰 상한을 설정값으로 둔다.

## 8. 미리 알아둘 기술 리스크

1. **X 수집:** RSSHub의 X 경로는 로그인 쿠키(`auth_token`)가 있어야 동작하므로 부계정이 필수다. 비공식 방식이라 언제든 막힐 수 있다. 게다가 AWS는 데이터센터 IP라서 집에서 돌릴 때보다 차단되거나 계정이 제재받을 위험이 크다. 수집 주기는 길게 잡고, 구독 계정 수도 제한한다.
2. **YouTube 스크립트:** YouTube는 AWS 같은 클라우드 IP 대부분에서 스크립트 요청을 막는다. 그래서 Mnemo(집의 M2)에서 되던 수집이 AWS에서는 실패할 가능성이 높다. 대안은 세 가지다.
   - (a) Gemini API에 YouTube URL을 넘겨 요약하기
   - (b) 주거용 프록시 쓰기
   - (c) 스크립트 수집만 집 M2에서 하고 결과를 AWS로 보내기

   MVP는 제목과 설명만으로 요약해서 시작한다.
3. **서버 사양:** RSSHub, Redis, Next.js, 파이프라인을 한 대에서 돌린다. 메모리가 1GB 수준이면 빠듯하므로 사양을 확인하고, 필요하면 swap을 잡는다.
4. **개인용으로만 쓴다:** 번역 전문을 저장하므로 외부에 공개하지 않는다 (Tailscale 안에서만 접근).
5. **RSSHub 경로별 설정:** YouTube 등 일부 경로는 API 키가 필요하다. 원본 RSS가 있는 소스는 원본으로 받는 편이 단순하다.

## 9. 초기 구독 목록 (초안: 핸들과 주소는 첫 실행 때 검증)

### AI

| 인물 | X | 그 외 |
|---|---|---|
| Andrej Karpathy | @karpathy | YouTube, 블로그 |
| Simon Willison | @simonw | simonwillison.net |
| Ethan Mollick | @emollick | One Useful Thing (Substack) |
| swyx | @swyx | Latent Space (AINews 포함) |
| Nathan Lambert | @natolambert | Interconnects |
| Jim Fan | @DrJimFan | |
| Yann LeCun | @ylecun | |
| François Chollet | @fchollet | |
| Andrew Ng | @AndrewYNg | The Batch |
| Demis Hassabis | @demishassabis | |
| Dwarkesh Patel | @dwarkesh_sp | 팟캐스트 (YouTube) |
| Lilian Weng | @lilianweng | 블로그 |
| 기관 | | Anthropic, OpenAI, Google DeepMind 블로그 |

### Tech

| 인물 | X | 그 외 |
|---|---|---|
| Paul Graham | @paulg | 에세이 |
| Garry Tan | @garrytan | YouTube |
| Benedict Evans | @benedictevans | 뉴스레터 |
| Gergely Orosz | @GergelyOrosz | The Pragmatic Engineer |
| Ben Thompson | @benthompson | Stratechery (무료 글) |
| Lenny Rachitsky | @lennysan | 뉴스레터, 팟캐스트 |
| Patrick Collison | @patrickc | |

### Bio

| 인물 | X | 그 외 |
|---|---|---|
| Eric Topol | @EricTopol | Ground Truths (Substack) |
| Patrick Hsu | @pdhsu | |
| Elliot Hershberg | @ElliotHershberg | The Century of Biology |
| Derek Lowe | | In the Pipeline (블로그) |
| Sergey Ovchinnikov | @sokrypton | |

### `config/sources.yaml` 형태 (예시)

```yaml
- name: Andrej Karpathy
  field: AI
  sources:
    - { type: x, handle: karpathy }
    - { type: youtube, handle: "@AndrejKarpathy" }
    - { type: rss, url: "<블로그 피드 URL>" }
```

## 10. 단계별 범위

| 단계 | 범위 |
|---|---|
| **1단계 (MVP)** | 블로그, 뉴스레터, Bluesky, YouTube(제목·설명 기반) / 짧은 SNS·긴 글·영상 세 가지 카드 / 스와이프, 보관함 / PWA / AWS 배포 |
| **2단계** | X (RSSHub + 부계정) / 영상 스크립트 요약 / 스레드 묶기 |
| **3단계** | 스와이프 반응으로 정렬 가중치 조정 / 주간 테마 정리 (Mnemo 위키 컴파일처럼) / Obsidian 연동 / 새 글 푸시 알림 (iOS 홈 화면 웹앱) |

## 11. Claude Code에서 정할 것

### 착수 전 질문

1. AWS 서버: 인스턴스 사양과 OS는? Docker가 있는가? 이미 돌고 있는 서비스(OpenClaw 등)와 같은 서버를 쓸 것인가?
2. 접속: Tailscale로 갈지, 도메인과 인증을 붙일지
3. 코드: Mnemo repo를 복제해 새 repo로 시작할지, Mnemo에 모듈로 붙일지
4. X: 부계정이 준비되어 있는가? 몇 명까지 볼 것인가?
5. 영상: 8장 2번의 대안 중 무엇으로 할지
6. 갱신 주기와 하루 처리 상한 (비용)
7. 짧은 글과 긴 글을 나누는 기준
8. 보관한 카드는 어디로 보낼지 (Obsidian, 아니면 보관함에만)

### 만들 문서 (Mnemo_Dev_Spec.md처럼)

| 파일 | 내용 |
|---|---|
| `docs/dev-spec.md` | 전체 개발 스펙 |
| `config/sources.yaml` | 구독 목록 |
| `config/glossary.yaml` | 번역 용어집 |
| `docs/views.md` | 유형별 카드와 상세 화면 스펙 |
| `docs/prompts.md` | 번역·요약 프롬프트, JSON 스키마 |
| `docs/deploy-aws.md` | 배포, 운영, 진단 |
