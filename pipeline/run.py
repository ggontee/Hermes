"""파이프라인 한 회차: 수집 → 정규화 → 중복 제거·묶기 → 분류 → AI 처리 → 저장.

    python -m pipeline.run              # 전체 회차 (systemd timer가 부름)
    python -m pipeline.run --no-ai      # 수집·저장만
    python -m pipeline.run --check-sources   # 모든 소스를 열어 보고 표로 출력 (저장 안 함)

로그에는 건수와 상태만 남긴다. 원문·번역 본문은 남기지 않는다.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone

import httpx

from . import db, processors
from .collectors import FetchError, collect, fetch_feed, parse_entries
from .config import Person, load_people, load_settings
from .store import now_iso, resolve_held, store_item, sync_config

log = logging.getLogger("hermes")


def _since(conn, source_id: int) -> datetime | None:
    row = conn.execute("SELECT MAX(published_at) FROM items WHERE source_id = ?", (source_id,)).fetchone()
    return datetime.fromisoformat(row[0]) if row and row[0] else None


def run_once(*, ai: bool = True, conn=None, settings=None, people: list[Person] | None = None,
             client: httpx.Client | None = None) -> dict:
    settings = settings or load_settings()
    people = people if people is not None else load_people(settings=settings)
    conn = conn or db.connect(db.db_path(settings))
    source_ids = sync_config(conn, people)

    run_id = conn.execute("INSERT INTO runs(started_at) VALUES (?)", (now_iso(),)).lastrowid
    conn.commit()
    stats = {"fetched_sources": 0, "new_items": 0, "merged_items": 0, "held": 0,
             "processed": 0, "deferred_by_cap": 0, "failed": 0}
    errors: list[dict] = []

    c = settings.get("collect", {})
    own_client = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=c.get("timeout_seconds", 20),
                                    headers={"User-Agent": c.get("user_agent", "HermesFeedReader/0.1")})
    try:
        for person in people:
            for source in person.sources:
                if not source.enabled:
                    continue
                sid = source_ids[source.key]
                fetched_at = now_iso()
                try:
                    items = collect(source, since=_since(conn, sid), settings=settings, client=client)
                except FetchError as e:
                    errors.append({"source": source.key, "error": str(e)})
                    conn.execute("UPDATE sources SET last_fetched_at = ?, last_error = ? WHERE id = ?",
                                 (fetched_at, str(e), sid))
                    conn.commit()
                    log.warning("수집 실패 %s: %s", source.key, e)
                    continue
                stats["fetched_sources"] += 1
                for item in items:
                    outcome = store_item(conn, item, source_id=sid, person=person, settings=settings)
                    if outcome == "new":
                        stats["new_items"] += 1
                    elif outcome in ("merged", "dup"):
                        stats["merged_items"] += 1
                    elif outcome == "held":
                        stats["held"] += 1
                conn.execute("UPDATE sources SET last_fetched_at = ?, last_success_at = ?, last_error = NULL, "
                             "last_item_count = ? WHERE id = ?", (fetched_at, fetched_at, len(items), sid))
                conn.commit()
    finally:
        if own_client:
            client.close()

    held = resolve_held(conn, settings)
    stats["merged_items"] += held["merged"]

    if ai:
        result = processors.process_pending(conn, settings)
        stats["processed"] = result["processed"]
        stats["deferred_by_cap"] = result["deferred"]
        stats["failed"] = result["failed"]

    conn.execute(
        "UPDATE runs SET finished_at = ?, fetched_sources = ?, new_items = ?, merged_items = ?, "
        "processed = ?, deferred_by_cap = ?, errors_json = ? WHERE id = ?",
        (now_iso(), stats["fetched_sources"], stats["new_items"], stats["merged_items"],
         stats["processed"], stats["deferred_by_cap"], json.dumps(errors, ensure_ascii=False), run_id))
    conn.commit()
    stats["errors"] = len(errors)
    return stats


def check_sources(settings=None, people=None) -> int:
    """모든 소스를 열어 HTTP 결과, 항목 수, 최신 글 날짜를 출력한다. 실패 수를 돌려준다."""
    settings = settings or load_settings()
    people = people if people is not None else load_people(settings=settings)
    c = settings.get("collect", {})
    failures = 0
    with httpx.Client(follow_redirects=True, timeout=c.get("timeout_seconds", 20),
                      headers={"User-Agent": c.get("user_agent", "HermesFeedReader/0.1")}) as client:
        for person in people:
            for s in person.sources:
                if not s.enabled:
                    reason = "주소 없음(TODO)" if not s.url else "꺼짐"
                    print(f"-  {s.key:<60} {reason}")
                    continue
                try:
                    items = parse_entries(s, fetch_feed(s.url, timeout=20, user_agent="", client=client))
                    latest = max((i.published_at for i in items), default=None)
                    when = latest.astimezone(timezone.utc).strftime("%Y-%m-%d") if latest else "-"
                    print(f"OK {s.key:<60} {len(items):>3}건  최신 {when}")
                except FetchError as e:
                    failures += 1
                    print(f"!! {s.key:<60} {e}")
    return failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline.run")
    ap.add_argument("--no-ai", action="store_true", help="수집·저장만 하고 AI 처리는 건너뛴다")
    ap.add_argument("--check-sources", action="store_true", help="소스를 열어 보기만 한다")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    if args.check_sources:
        return 1 if check_sources() else 0
    stats = run_once(ai=not args.no_ai)
    log.info("회차 끝: %s", json.dumps(stats, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
