"""개발용 예시 데이터. 실제 수집 없이 웹앱 화면을 확인할 때 쓴다.

    python -m scripts.seed_dev data/dev.db
    HERMES_DB_PATH=$PWD/data/dev.db npm --prefix web run dev
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pipeline import db

NOW = datetime.now(timezone.utc)


def iso(hours_ago: float) -> str:
    return (NOW - timedelta(hours=hours_ago)).isoformat(timespec="seconds")


def main(path: str) -> None:
    p = Path(path)
    for f in (p, p.with_name(p.name + "-wal"), p.with_name(p.name + "-shm")):
        f.unlink(missing_ok=True)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = db.connect(p)
    people = [
        ("Simon Willison", "AI", "Datasette"),
        ("Andrej Karpathy", "AI", "Eureka Labs"),
        ("Dwarkesh Patel", "AI", "Dwarkesh Podcast"),
        ("Ben Thompson", "Tech", "Stratechery"),
        ("Eric Topol", "Bio", "Scripps Research"),
    ]
    for name, field, aff in people:
        conn.execute("INSERT INTO people(name, field, affiliation) VALUES (?, ?, ?)", (name, field, aff))
    srcs = [(1, "rss"), (1, "bluesky"), (2, "bluesky"), (3, "youtube"), (4, "rss"), (5, "bluesky")]
    for i, (pid, typ) in enumerate(srcs, 1):
        conn.execute("INSERT INTO sources(key, person_id, type, url, last_success_at) VALUES (?, ?, ?, ?, ?)",
                     (f"s{i}", pid, typ, f"https://example.com/feed{i}", iso(1)))
    conn.execute("UPDATE sources SET last_error = 'HTTP 503', last_success_at = ? WHERE id = 6", (iso(30),))

    def item(src, pid, ext, platform, kind, title, paragraphs, hours, url=None, role="primary", group=None):
        cur = conn.execute(
            """INSERT INTO items(source_id, person_id, external_id, url, canonical_url, published_at, platform, kind,
               title_orig, paragraphs_json, char_count, content_hash, role, group_id, status, fetched_at)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'done', ?)""",
            (src, pid, ext, url or f"https://example.com/{ext}", url or f"https://example.com/{ext}", iso(hours),
             platform, kind, title, json.dumps(paragraphs), sum(map(len, paragraphs)), ext, role, group, iso(0)))
        iid = cur.lastrowid
        conn.execute("UPDATE items SET group_id = COALESCE(group_id, ?) WHERE id = ?", (iid, iid))
        return iid

    def card(iid, kind, status="pending", **f):
        cols = ["item_id", "kind", "status", "created_at", *f]
        vals = [iid, kind, status, iso(0), *[json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v
                                               for v in f.values()]]
        cur = conn.execute(f"INSERT INTO cards({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", vals)
        return cur.lastrowid

    a = item(2, 1, "sk1", "sns", "short", "", ["Just shipped llm 0.30 with support for structured outputs: https://llm.datasette.io/en/stable/changelog.html"], 2)
    card(a, "short", translation_ko="구조화된 출력을 지원하는 llm 0.30을 방금 배포했습니다: https://llm.datasette.io/en/stable/changelog.html")

    b = item(1, 1, "blog1", "blog", "long", "Things I learned about prompt injection this year",
             ["Prompt injection remains unsolved.", "The best defence is still limiting what tools can do.",
              "Dual LLM patterns help but are awkward."], 5)
    item(2, 1, "sk2", "sns", "short", "", ["New post: what I learned about prompt injection this year"], 4.5,
         role="note", group=b)
    card(b, "long", title_ko="올해 프롬프트 인젝션에 대해 배운 것들",
         summary_ko_json=["프롬프트 인젝션은 여전히 해결되지 않았다.", "가장 좋은 방어는 도구가 할 수 있는 일을 제한하는 것이다.",
                          "이중 LLM 패턴은 도움이 되지만 쓰기 번거롭다."],
         so_what="에이전트에 도구를 붙일 때 권한 설계가 모델 성능보다 먼저다.", tags_json=["보안", "에이전트", "LLM"],
         translation_pairs_json=[{"id": "p1", "orig": "Prompt injection remains unsolved.", "ko": "프롬프트 인젝션은 여전히 해결되지 않았다."},
                                 {"id": "p2", "orig": "The best defence is still limiting what tools can do.", "ko": "가장 좋은 방어는 여전히 도구가 할 수 있는 일을 제한하는 것이다."},
                                 {"id": "p3", "orig": "Dual LLM patterns help but are awkward.", "ko": "이중 LLM 패턴은 도움이 되지만 쓰기 번거롭다."}])

    v = item(4, 3, "dQw4w9WgXcQ", "video", "video", "Interview: scaling, RL and the next five years", ["desc"], 20,
             url="https://www.youtube.com/watch?v=dQw4w9WgXcQ")
    card(v, "video", video_oneliner="강화학습 확장이 다음 5년의 병목을 어떻게 바꾸는지에 대한 대담",
         video_sections_json=[{"t": 0, "title": "도입", "summary": "게스트 소개"},
                              {"t": 192, "title": "RL 확장", "summary": "사전학습 다음의 확장 축"},
                              {"t": 1120, "title": "평가의 어려움", "summary": "벤치마크 포화 문제"},
                              {"t": 2465, "title": "5년 전망", "summary": "연구 자동화의 시점"}],
         video_top3_json=[1, 2, 3], tags_json=["RL", "스케일링"],
         transcript_ko=[{"t": 0, "orig": "Welcome back.", "ko": "다시 오신 것을 환영합니다."},
                        {"t": 192, "orig": "Let's talk about RL.", "ko": "강화학습 이야기를 해 봅시다."}])

    c = item(3, 2, "ak1", "sns", "short", "", ["The hottest new programming language is English."], 30)
    card(c, "short", translation_ko="가장 핫한 새 프로그래밍 언어는 영어입니다.")

    d = item(5, 4, "st1", "blog", "long", "Aggregators and AI", ["Paywalled intro paragraph."], 40)
    kept = card(d, "long", status="kept", title_ko="애그리게이터와 AI", summary_ko_json=["AI는 애그리게이터 이론을 다시 쓴다.",
                "분배 비용이 0에 가까워진다.", "통합 지점이 모델로 옮겨 간다."], so_what="플랫폼 전략을 다시 볼 때다.",
                tags_json=["전략", "플랫폼"], is_preview=1, user_comment="다음 기획 회의에서 공유", decided_at=iso(3).replace("T", " ")[:19],
                user_tags_json=["기획"])
    conn.execute("""INSERT INTO analyses(card_id, status, title, content_md, cost_usd, created_at, finished_at)
                    VALUES (?, 'done', '애그리게이터 이론과 생성형 AI', ?, 0.12, ?, ?)""",
                 (kept, "## 핵심\n\n- **분배**가 무료가 되면 차별점은 *수요 쪽*으로 옮겨 간다.\n- 모델이 새 통합 지점이 된다.\n\n## 시사점\n\n1. 자체 데이터\n2. 사용자 관계",
                  iso(2), iso(2)))

    e = item(6, 5, "et1", "sns", "short", "", ["New trial: GLP-1 drugs reduce kidney disease progression by 24%."], 8)
    card(e, "short", status="kept", translation_ko="새 임상: GLP-1 계열 약물이 신장 질환 진행을 24% 줄였다.",
         decided_at=iso(6).replace("T", " ")[:19])

    conn.execute("""INSERT INTO runs(started_at, finished_at, fetched_sources, new_items, processed, deferred_by_cap, errors_json)
                    VALUES (?, ?, 6, 7, 6, 0, '[{"source":"s6","error":"HTTP 503"}]')""", (iso(1), iso(0.9)))
    from pipeline.budget import today
    for kind, n, cost in [("ai_items", 6, 0.21), ("videos", 1, 0.09), ("analyses", 1, 0.12)]:
        conn.execute("INSERT INTO usage(date, kind, count, cost_usd) VALUES (?, ?, ?, ?)", (today({}), kind, n, cost))
    conn.commit()
    print(f"seeded {p}")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "data/dev.db")
