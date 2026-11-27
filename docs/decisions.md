# Hermes 결정 기록

컨셉 문서 11장 "착수 전 질문"에 대한 결정. repo가 생기면 `docs/dev-spec.md`로 옮긴다.

| # | 질문 | 결정 | 날짜 |
|---|---|---|---|
| 1 | AWS 서버 | 같은 계정(`ggontee`, 서울)에 **새 EC2 t4g.small(2GB, ARM)**. Octopus 스택과 분리. 월 약 $15 (AWS 예산 $50 안). 컨셉 구성(systemd, Docker RSSHub+redis, SQLite, Next.js) 그대로 | 2026-11-27 |
| 2 | 코드 저장소 | **새 repo**(예: `ggontee/hermes`, private). `ggontee/mnemo-app`에서 카드 스와이프 UI 등 필요한 코드만 옮긴다. Mnemo에 모듈로 붙이지 않는다 | 2026-11-27 |
| 3 | 접속 | **Tailscale 안에서만.** 서버 인바운드는 인터넷에 열지 않는다. iPhone은 Tailscale 앱을 켜고 접속, 별도 로그인 없음. PWA용 HTTPS는 Tailscale 인증서(`tailscale serve`)로 | 2026-11-27 |
| 7 | 짧은 글/긴 글 기준 | SNS(X, Threads, Bluesky) 원문 **500자 이하는 전문 번역**(짧은 SNS 카드), 500자 초과나 스레드는 긴 글(요약+전문 번역). 블로그, 뉴스레터는 길이와 상관없이 늘 긴 글 | 2026-11-27 |
| 6 | 갱신 주기와 상한 | **하루 3번, 8시간 간격(06:00, 14:00, 22:00 KST)**, systemd timer 하나. AI 처리는 **하루 60건** 상한(넘으면 다음 회차로), 토큰 상한도 설정값으로 둔다. Octopus market-signal(08·16시)와 겹치지 않게 했다 | 2026-11-27 |
| 5 | 영상 | **Gemini로 YouTube 받아쓰기 → 요약**(8장 2번 (a)안). MVP부터 한 줄 요약, 타임스탬프 구간 요약 5~8개, 스크립트 번역. Octopus의 Gemini 키와 방식(`gemini-3.5-flash-lite`, 8분 영상 약 $0.02)을 참고. Gemini 하루 상한도 둔다 | 2026-11-27 |
| 4 | X | **2단계로 미룬다.** MVP 소스는 블로그, 뉴스레터, Bluesky, YouTube. X는 부계정을 준비한 뒤 RSSHub로 붙인다(RSSHub 자체는 MVP부터 띄움) | 2026-11-27 |
| 8 | 보관 후 처리 | **두 층.** 카드 수준은 Mnemo처럼 Hermes 보관함(보관, 한 줄 코멘트, 태그). 추가 분석으로 문서가 되는 것은 보관 카드의 [심화 분석]으로 **Tana**에 저장. **Hermes가 직접** 분석하고 Tana에 쓴다(Octopus·Discord를 거치지 않음. Discord 사용이 적어 오너가 원인은 Octopus 쪽에서 따로 보기로 함) | 2026-11-27 |

## 참고 (Octopus 문서에서 확인)
- Octopus는 Fargate 작업 1개(0.25 vCPU, 0.5GB)와 Lambda, DynamoDB로 돌며 인바운드가 없다. Hermes를 올릴 자리가 아니다.
- AWS에서 YouTube 채널 RSS 정상, Gemini YouTube 받아쓰기 성공(8분 영상 약 $0.02). 8장 2번 (a)안 검증됨.
- AWS 출구 IP에서 일부 API는 403(업비트). X도 비슷한 위험.
