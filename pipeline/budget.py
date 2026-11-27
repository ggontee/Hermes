"""하루 상한 (dev-spec 6장). 날짜는 서울 시간 기준."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from zoneinfo import ZoneInfo

LIMIT_KEYS = {"ai_items": "ai_items_per_day", "videos": "videos_per_day", "analyses": "analyses_per_day"}
DEFAULTS = {"ai_items": 60, "videos": 10, "analyses": 5}


def today(settings: dict) -> str:
    return datetime.now(ZoneInfo(settings.get("timezone", "Asia/Seoul"))).date().isoformat()


def limit(settings: dict, kind: str) -> int:
    return int(settings.get("budget", {}).get(LIMIT_KEYS[kind], DEFAULTS[kind]))


def used(conn: sqlite3.Connection, settings: dict, kind: str) -> int:
    row = conn.execute("SELECT count FROM usage WHERE date = ? AND kind = ?", (today(settings), kind)).fetchone()
    return row[0] if row else 0


def remaining(conn: sqlite3.Connection, settings: dict, kind: str) -> int:
    return max(0, limit(settings, kind) - used(conn, settings, kind))


def record(conn: sqlite3.Connection, settings: dict, kind: str, *, count: int = 1,
           tokens_in: int = 0, tokens_out: int = 0, cost_usd: float = 0.0) -> None:
    conn.execute(
        "INSERT INTO usage(date, kind, count, tokens_in, tokens_out, cost_usd) VALUES (?,?,?,?,?,?) "
        "ON CONFLICT(date, kind) DO UPDATE SET count = count + excluded.count, "
        "tokens_in = tokens_in + excluded.tokens_in, tokens_out = tokens_out + excluded.tokens_out, "
        "cost_usd = cost_usd + excluded.cost_usd",
        (today(settings), kind, count, tokens_in, tokens_out, cost_usd))
