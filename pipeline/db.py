"""SQLite 스키마와 연결. 저장소는 hermes.db 하나 (WAL).

웹앱(web/)도 같은 파일을 읽고 cards.status 등만 바꾼다. 스키마를 바꿀 때는
MIGRATIONS에 새 단계를 덧붙이고 기존 단계는 고치지 않는다.

실행: python -m pipeline.db migrate
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from .config import REPO_ROOT, load_settings

MIGRATIONS: list[str] = [
    # 1: 첫 스키마
    """
    CREATE TABLE people (
        id INTEGER PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        field TEXT NOT NULL,
        affiliation TEXT,
        avatar_url TEXT
    );
    CREATE TABLE sources (
        id INTEGER PRIMARY KEY,
        key TEXT NOT NULL UNIQUE,
        person_id INTEGER NOT NULL REFERENCES people(id),
        type TEXT NOT NULL,
        url TEXT NOT NULL,
        enabled INTEGER NOT NULL DEFAULT 1,
        last_fetched_at TEXT,
        last_success_at TEXT,
        last_error TEXT,
        last_item_count INTEGER
    );
    CREATE TABLE items (
        id INTEGER PRIMARY KEY,
        source_id INTEGER NOT NULL REFERENCES sources(id),
        person_id INTEGER NOT NULL REFERENCES people(id),
        external_id TEXT NOT NULL,
        url TEXT NOT NULL,
        canonical_url TEXT NOT NULL,
        published_at TEXT NOT NULL,
        platform TEXT NOT NULL,              -- blog | sns | video
        kind TEXT NOT NULL,                  -- short | long | video
        title_orig TEXT NOT NULL DEFAULT '',
        paragraphs_json TEXT NOT NULL,       -- 원문 문단 배열
        media_json TEXT NOT NULL DEFAULT '[]',
        links_json TEXT NOT NULL DEFAULT '[]',
        char_count INTEGER NOT NULL,
        content_hash TEXT NOT NULL,
        group_id INTEGER,                    -- 묶음의 기준(primary) item id
        role TEXT NOT NULL DEFAULT 'primary',-- primary | note(작성자 한마디) | alt(다른 형식)
        status TEXT NOT NULL DEFAULT 'pending_ai',
                                             -- held | pending_ai | done | failed | merged
        hold_runs INTEGER NOT NULL DEFAULT 0,
        fail_reason TEXT,
        fetched_at TEXT NOT NULL,
        UNIQUE (source_id, external_id)
    );
    CREATE INDEX items_canonical ON items(canonical_url);
    CREATE INDEX items_hash ON items(content_hash);
    CREATE INDEX items_person_time ON items(person_id, published_at);
    CREATE INDEX items_status ON items(status);

    CREATE TABLE cards (
        id INTEGER PRIMARY KEY,
        item_id INTEGER NOT NULL UNIQUE REFERENCES items(id),
        kind TEXT NOT NULL,
        title_ko TEXT,
        summary_ko_json TEXT,
        so_what TEXT,
        tags_json TEXT NOT NULL DEFAULT '[]',
        translation_ko TEXT,
        translation_pairs_json TEXT,
        quote_translation_ko TEXT,
        is_preview INTEGER NOT NULL DEFAULT 0,
        video_oneliner TEXT,
        video_sections_json TEXT,
        video_top3_json TEXT,
        transcript_ko TEXT,
        from_description INTEGER NOT NULL DEFAULT 0,
        model TEXT,
        tokens_in INTEGER NOT NULL DEFAULT 0,
        tokens_out INTEGER NOT NULL DEFAULT 0,
        cost_usd REAL NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'pending',   -- pending | kept | discarded
        user_comment TEXT,
        user_tags_json TEXT NOT NULL DEFAULT '[]',
        decided_at TEXT,
        created_at TEXT NOT NULL
    );
    CREATE INDEX cards_status ON cards(status, created_at);

    CREATE TABLE analyses (
        id INTEGER PRIMARY KEY,
        card_id INTEGER NOT NULL REFERENCES cards(id),
        question TEXT,
        status TEXT NOT NULL DEFAULT 'queued',    -- queued | running | done | failed
        title TEXT,
        content_md TEXT,
        tana_node_id TEXT,
        error TEXT,
        cost_usd REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        finished_at TEXT
    );

    CREATE TABLE runs (
        id INTEGER PRIMARY KEY,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        fetched_sources INTEGER NOT NULL DEFAULT 0,
        new_items INTEGER NOT NULL DEFAULT 0,
        merged_items INTEGER NOT NULL DEFAULT 0,
        processed INTEGER NOT NULL DEFAULT 0,
        deferred_by_cap INTEGER NOT NULL DEFAULT 0,
        errors_json TEXT NOT NULL DEFAULT '[]'
    );

    CREATE TABLE usage (
        date TEXT NOT NULL,           -- 서울 시간 기준 YYYY-MM-DD
        kind TEXT NOT NULL,           -- ai_items | videos | analyses
        count INTEGER NOT NULL DEFAULT 0,
        tokens_in INTEGER NOT NULL DEFAULT 0,
        tokens_out INTEGER NOT NULL DEFAULT 0,
        cost_usd REAL NOT NULL DEFAULT 0,
        PRIMARY KEY (date, kind)
    );
    """,
]


def db_path(settings: dict | None = None) -> Path:
    settings = settings or load_settings()
    p = Path(settings.get("db_path", "data/hermes.db"))
    return p if p.is_absolute() else REPO_ROOT / p


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(path) if path else db_path()
    if str(path) != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    migrate(conn)
    return conn


def migrate(conn: sqlite3.Connection) -> int:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    for i, sql in enumerate(MIGRATIONS[version:], start=version + 1):
        with conn:
            conn.executescript(sql)
            conn.execute(f"PRAGMA user_version = {i}")
    return conn.execute("PRAGMA user_version").fetchone()[0]


if __name__ == "__main__":
    if sys.argv[1:] == ["migrate"]:
        c = connect()
        print(f"schema version {c.execute('PRAGMA user_version').fetchone()[0]} at {db_path()}")
    else:
        print("usage: python -m pipeline.db migrate")
        sys.exit(2)
