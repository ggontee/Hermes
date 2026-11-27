# Hermes

해외 AI·Tech·Bio 인플루언서의 블로그·뉴스레터·SNS·영상을 모아 한국어로 번역·요약하고, 카드를 스와이프하며 훑어보는 개인용 PWA.

- 컨셉: [docs/concept-v1.md](docs/concept-v1.md)
- 결정 기록: [docs/decisions.md](docs/decisions.md)
- 개발 스펙: [docs/dev-spec.md](docs/dev-spec.md)
- 구독 목록: [config/sources.yaml](config/sources.yaml)
- 화면: [docs/views.md](docs/views.md)
- 프롬프트: [docs/prompts.md](docs/prompts.md)
- 배포·운영: [docs/deploy-aws.md](docs/deploy-aws.md)
- 용어집: [config/glossary.yaml](config/glossary.yaml)

## 개발

```bash
python3.12 -m venv .venv && . .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q                       # 테스트 (네트워크 없이 돈다)
python -m pipeline.run --check-sources    # 구독 소스를 실제로 열어 보기
python -m pipeline.run --no-ai            # 수집·저장만 (data/hermes.db)
```

## 웹앱 (web/)

Next.js PWA. 파이프라인과 같은 `data/hermes.db`를 읽고, 카드 상태·코멘트·태그와 심화 분석 요청만 쓴다.

```bash
python -m scripts.seed_dev data/dev.db          # 예시 데이터
cd web && npm install
HERMES_DB_PATH=$PWD/../data/dev.db npm run dev   # http://127.0.0.1:3000
```

환경변수: `HERMES_DB_PATH`(기본 `../data/hermes.db`), `HERMES_LIMIT_AI_ITEMS`·`HERMES_LIMIT_VIDEOS`·`HERMES_LIMIT_ANALYSES`, `HERMES_TANA_NODE_URL`(Tana 노드 링크 앞부분).
