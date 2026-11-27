"""유형별 AI 처리 (dev-spec 5장, docs/prompts.md).

이 PR에서는 인터페이스만 둔다. 번역·요약·영상 처리는 다음 PR에서 채운다.
그때까지 수집한 항목은 status='pending_ai'로 남아 다음 회차에 처리된다.
"""
from __future__ import annotations

import logging
import sqlite3

log = logging.getLogger(__name__)


def process_pending(conn: sqlite3.Connection, settings: dict) -> dict[str, int]:
    """처리 대기 항목을 상한 안에서 처리한다. {'processed': n, 'deferred': m, 'failed': k}."""
    pending = conn.execute("SELECT COUNT(*) FROM items WHERE status = 'pending_ai'").fetchone()[0]
    log.info("AI 처리 미구현: 대기 %d건은 다음 회차로", pending)
    return {"processed": 0, "deferred": pending, "failed": 0}
