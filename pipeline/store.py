"""새 항목 저장과 중복 제거·묶기 (dev-spec 5장 3번).

한 사람이 여러 채널에 올린 같은 내용을 카드 하나로 만든다.

1. 완전 중복: 같은 소스의 같은 ID → 무시. 다른 소스라도 정규화 URL이나 본문 해시가
   같으면 role='dup'으로 기록만 하고 카드는 만들지 않는다.
2. 링크 묶기: SNS 글이 같은 사람의 블로그 글·영상 링크를 담고 있으면 그 카드의
   '작성자 한마디'(role='note')가 된다. 원글이 아직 없고 링크가 그 사람의 사이트를
   가리키면 status='held'로 두었다가 다음 회차에 다시 본다.
3. 같은 내용 다른 형식: 같은 사람, 72시간 안, 제목이 비슷하면 한 묶음.
   영상이 있으면 영상이 기준(primary), 글은 role='alt'.
"""
from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from urllib.parse import urlsplit

from .classify import classify
from .config import Person, Source
from .normalize import Item, canonical_url


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def sync_config(conn: sqlite3.Connection, people: list[Person]) -> dict[str, int]:
    """sources.yaml 내용을 people·sources 테이블에 맞춘다. {source.key: source_id}."""
    ids: dict[str, int] = {}
    with conn:
        conn.execute("UPDATE sources SET enabled = 0")
        for p in people:
            conn.execute(
                "INSERT INTO people(name, field, affiliation) VALUES (?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET field = excluded.field, affiliation = excluded.affiliation",
                (p.name, p.field, p.affiliation))
            pid = conn.execute("SELECT id FROM people WHERE name = ?", (p.name,)).fetchone()[0]
            for s in p.sources:
                conn.execute(
                    "INSERT INTO sources(key, person_id, type, url, enabled) VALUES (?, ?, ?, ?, ?) "
                    "ON CONFLICT(key) DO UPDATE SET person_id = excluded.person_id, type = excluded.type, "
                    "url = excluded.url, enabled = excluded.enabled",
                    (s.key, pid, s.type, s.url, int(s.enabled)))
                ids[s.key] = conn.execute("SELECT id FROM sources WHERE key = ?", (s.key,)).fetchone()[0]
    return ids


def person_hosts(person: Person) -> set[str]:
    """그 사람의 '원글'이 사는 호스트 (블로그·뉴스레터·YouTube)."""
    hosts: set[str] = set()
    for s in person.sources:
        if s.type == "youtube":
            hosts.update({"youtube.com", "youtu.be"})
        elif s.type == "rss" and s.url:
            hosts.add(urlsplit(canonical_url(s.url)).netloc)
    return hosts


def _norm_title(t: str) -> str:
    t = re.sub(r"\s*[|·–—-]\s*(podcast|episode|ep\.?\s*\d+).*$", "", t, flags=re.I)
    return re.sub(r"[^0-9a-z가-힣]+", " ", t.lower()).strip()


def title_similarity(a: str, b: str) -> float:
    a, b = _norm_title(a), _norm_title(b)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _insert(conn, item: Item, source_id: int, person_id: int, kind: str, *,
            role: str, status: str, group_id: int | None) -> int:
    cur = conn.execute(
        """INSERT INTO items(source_id, person_id, external_id, url, canonical_url, published_at,
               platform, kind, title_orig, paragraphs_json, media_json, links_json, char_count,
               content_hash, group_id, role, status, fetched_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (source_id, person_id, item.external_id, item.url, item.canonical_url,
         item.published_at.isoformat(timespec="seconds"), item.platform, kind, item.title,
         json.dumps(item.paragraphs, ensure_ascii=False), json.dumps(item.media),
         json.dumps(item.links), len(item.text), item.content_hash, group_id, role, status, now_iso()))
    new_id = cur.lastrowid
    if group_id is None:
        conn.execute("UPDATE items SET group_id = ? WHERE id = ?", (new_id, new_id))
    return new_id


def _find_link_target(conn, person_id: int, links: list[str]) -> int | None:
    """링크 중 같은 사람의 원글(SNS가 아닌 항목)이 있으면 그 묶음 id."""
    for link in links:
        row = conn.execute(
            "SELECT group_id FROM items WHERE person_id = ? AND canonical_url = ? AND platform != 'sns' "
            "AND role IN ('primary', 'alt') LIMIT 1",
            (person_id, canonical_url(link))).fetchone()
        if row:
            return row[0]
    return None


def store_item(conn: sqlite3.Connection, item: Item, *, source_id: int, person: Person,
               settings: dict) -> str:
    """항목 하나를 저장하고 결과를 돌려준다: dup | new | merged | held | known."""
    if conn.execute("SELECT 1 FROM items WHERE source_id = ? AND external_id = ?",
                    (source_id, item.external_id)).fetchone():
        return "known"
    person_id = conn.execute("SELECT person_id FROM sources WHERE id = ?", (source_id,)).fetchone()[0]
    cfg = settings.get("classify", {})
    dd = settings.get("dedupe", {})
    kind = classify(item.platform, item.text, cfg.get("short_max_chars", 500))

    with conn:
        # 1. 완전 중복
        dup = conn.execute(
            "SELECT group_id FROM items WHERE person_id = ? AND (canonical_url = ? OR "
            "(content_hash = ? AND char_count > 80)) LIMIT 1",
            (person_id, item.canonical_url, item.content_hash)).fetchone()
        if dup:
            _insert(conn, item, source_id, person_id, kind, role="dup", status="merged", group_id=dup[0])
            return "dup"

        # 2. 링크 묶기 (SNS만)
        if item.platform == "sns" and item.links:
            target = _find_link_target(conn, person_id, item.links)
            if target:
                _insert(conn, item, source_id, person_id, kind, role="note", status="merged", group_id=target)
                return "merged"
            own = person_hosts(person)
            if any(urlsplit(canonical_url(l)).netloc in own for l in item.links):
                _insert(conn, item, source_id, person_id, kind, role="primary", status="held", group_id=None)
                return "held"

        # 3. 같은 내용 다른 형식 (제목이 있는 블로그·영상)
        if item.platform != "sns" and item.title:
            window = timedelta(hours=dd.get("same_content_window_hours", 72))
            lo = (item.published_at - window).isoformat(timespec="seconds")
            hi = (item.published_at + window).isoformat(timespec="seconds")
            rows = conn.execute(
                "SELECT id, group_id, platform, title_orig, status FROM items WHERE person_id = ? "
                "AND role = 'primary' AND platform != ? AND platform != 'sns' "
                "AND published_at BETWEEN ? AND ?",
                (person_id, item.platform, lo, hi)).fetchall()
            threshold = dd.get("title_similarity", 0.8)
            for r in rows:
                if title_similarity(item.title, r["title_orig"]) < threshold:
                    continue
                if item.platform == "video" and r["status"] in ("pending_ai", "held"):
                    # 영상이 기준이 된다. 아직 처리 전인 글은 alt로 내린다.
                    new_id = _insert(conn, item, source_id, person_id, kind,
                                     role="primary", status="pending_ai", group_id=None)
                    old_group = r["group_id"]
                    conn.execute("UPDATE items SET role = 'alt', status = 'merged' "
                                 "WHERE group_id = ? AND role = 'primary'", (old_group,))
                    conn.execute("UPDATE items SET group_id = ? WHERE group_id = ?", (new_id, old_group))
                    return "merged"
                _insert(conn, item, source_id, person_id, kind, role="alt", status="merged",
                        group_id=r["group_id"])
                return "merged"

        _insert(conn, item, source_id, person_id, kind, role="primary", status="pending_ai", group_id=None)
        return "new"


def resolve_held(conn: sqlite3.Connection, settings: dict) -> dict[str, int]:
    """보류한 SNS 글을 다시 본다. 원글이 들어왔으면 묶고, 오래 기다렸으면 따로 카드로 만든다."""
    max_runs = settings.get("dedupe", {}).get("hold_max_runs", 2)
    out = {"merged": 0, "released": 0, "still_held": 0}
    rows = conn.execute("SELECT id, person_id, links_json, hold_runs FROM items WHERE status = 'held'").fetchall()
    with conn:
        for r in rows:
            target = _find_link_target(conn, r["person_id"], json.loads(r["links_json"]))
            if target:
                conn.execute("UPDATE items SET group_id = ?, role = 'note', status = 'merged' WHERE id = ?",
                             (target, r["id"]))
                out["merged"] += 1
            elif r["hold_runs"] + 1 >= max_runs:
                conn.execute("UPDATE items SET status = 'pending_ai', hold_runs = hold_runs + 1 WHERE id = ?",
                             (r["id"],))
                out["released"] += 1
            else:
                conn.execute("UPDATE items SET hold_runs = hold_runs + 1 WHERE id = ?", (r["id"],))
                out["still_held"] += 1
    return out
