"""심화 분석 워커. 웹앱이 analyses에 'queued'로 넣은 요청을 하나씩 처리한다.

    python -m pipeline.analysis            # 상시 (systemd hermes-analysis)
    python -m pipeline.analysis --once     # 대기열을 한 번 비우고 끝

흐름: queued → running → Claude로 리서치 노트 → done(본문 저장, 사용량 기록) → Tana #Research에 노드 생성
→ tana_node_id 저장. Tana 저장이 실패해도 분석은 done으로 두고, 다음 회차에 저장만 다시 시도한다.
"""
from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import time
from datetime import datetime
from zoneinfo import ZoneInfo

from . import budget, db
from .config import load_glossary, load_settings
from .llm import Claude, LLMError, NotConfigured, prompt

log = logging.getLogger("pipeline.analysis")

ANALYSIS_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "conclusion": {"type": "string"},
        "body_md": {"type": "string"},
        "topic": {"type": "string"},
        "confidence": {"type": "string", "enum": ["높음", "중간", "낮음"]},
    },
    "required": ["title", "conclusion", "body_md", "topic", "confidence"],
    "additionalProperties": False,
}

TANA_RETRY_DAYS = 7


def _j(s, fallback):
    try:
        return json.loads(s) if s else fallback
    except json.JSONDecodeError:
        return fallback


def card_row(conn: sqlite3.Connection, card_id: int) -> sqlite3.Row | None:
    return conn.execute(
        """SELECT c.*, i.url, i.published_at, i.title_orig, i.paragraphs_json, p.name AS person, p.affiliation
           FROM cards c JOIN items i ON i.id = c.item_id JOIN people p ON p.id = i.person_id WHERE c.id = ?""",
        (card_id,),
    ).fetchone()


def build_input(card: sqlite3.Row, question: str | None, max_chars: int) -> str:
    """카드 요약 + 원문(또는 번역/스크립트) + 사용자 코멘트·질문. 원문은 데이터로 감싼다."""
    tags = _j(card["tags_json"], []) + _j(card["user_tags_json"], [])
    summary = _j(card["summary_ko_json"], [])
    if card["kind"] == "video":
        lines = _j(card["transcript_ko"], [])
        body = "\n".join(f"[{ln.get('t') if ln.get('t') is not None else '-'}] {ln.get('orig') or ln.get('ko')}" for ln in lines)
        if not body:
            body = "\n\n".join(_j(card["paragraphs_json"], []))
        summary = [card["video_oneliner"] or ""] + [f"{s.get('title')}: {s.get('summary')}" for s in _j(card["video_sections_json"], [])]
    else:
        body = "\n\n".join(f"[p{i}] {p}" for i, p in enumerate(_j(card["paragraphs_json"], []), 1))
    if len(body) > max_chars:
        body = body[:max_chars] + "\n…(이하 생략)"
    aff = f" ({card['affiliation']})" if card["affiliation"] else ""
    parts = [
        "<item>",
        f"  <author>{card['person']}{aff}</author>",
        f"  <url>{card['url']}</url>",
        f"  <published>{card['published_at']}</published>",
        f"  <kind>{card['kind']}</kind>",
        f"  <title>{card['title_orig'] or ''}</title>",
        f"  <card_summary>{json.dumps([s for s in [card['title_ko'], *summary, card['so_what']] if s], ensure_ascii=False)}</card_summary>",
        f"  <tags>{', '.join(tags)}</tags>",
        f"  <body>\n{body}\n  </body>",
        "</item>",
    ]
    if card["kind"] == "short" and card["translation_ko"]:
        parts.append(f"<translation_ko>{card['translation_ko']}</translation_ko>")
    if card["user_comment"]:
        parts.append(f"<user_comment>{card['user_comment']}</user_comment>")
    if question:
        parts.append(f"<user_question>{question}</user_question>")
    return "\n".join(parts)


def claim_next(conn: sqlite3.Connection) -> sqlite3.Row | None:
    with conn:
        row = conn.execute("SELECT * FROM analyses WHERE status = 'queued' ORDER BY id LIMIT 1").fetchone()
        if not row:
            return None
        n = conn.execute("UPDATE analyses SET status = 'running' WHERE id = ? AND status = 'queued'", (row["id"],)).rowcount
    return row if n else claim_next(conn)


class Analyzer:
    def __init__(self, conn: sqlite3.Connection, settings: dict, claude: Claude | None = None, tana=None):
        self.conn = conn
        self.settings = settings
        self._claude = claude
        self._tana = tana
        self._tana_checked = tana is not None
        a = settings.get("analysis", {})
        self.model = settings.get("models", {}).get("analysis", "claude-sonnet-5-5")
        self.effort = a.get("effort", "medium")
        self.max_tokens = int(a.get("max_tokens", 8000))
        self.input_chars = int(a.get("input_chars", 100000))

    @property
    def claude(self) -> Claude:
        if self._claude is None:
            self._claude = Claude(self.settings, load_glossary())
        return self._claude

    @property
    def tana(self):
        """Tana가 설정돼 있지 않으면 None (분석은 Hermes 안에만 남는다)."""
        if not self._tana_checked:
            self._tana_checked = True
            t = self.settings.get("tana", {})
            if t.get("enabled", True) and t.get("parent_node_id"):
                from . import tana
                self._tana = tana.connect(self.settings)
        return self._tana

    def recover(self) -> None:
        """워커가 죽었을 때 running으로 남은 요청을 되돌린다."""
        with self.conn:
            self.conn.execute("UPDATE analyses SET status = 'queued' WHERE status = 'running'")

    def run_one(self, row: sqlite3.Row) -> str:
        card = card_row(self.conn, row["card_id"])
        if card is None:
            self._fail(row["id"], "카드가 없다")
            return "failed"
        content = build_input(card, row["question"], self.input_chars)
        try:
            out, usage = self.claude.json(model=self.model, instruction=prompt("analysis"), content=content,
                                          schema=ANALYSIS_SCHEMA, max_tokens=self.max_tokens, effort=self.effort)
        except NotConfigured:
            raise
        except LLMError as e:
            self._fail(row["id"], str(e))
            return "failed"
        except Exception as e:  # API 장애 등: 다시 대기열로
            log.warning("분석 %s 호출 실패 (%s), 대기열로 되돌린다", row["id"], type(e).__name__)
            with self.conn:
                self.conn.execute("UPDATE analyses SET status = 'queued' WHERE id = ?", (row["id"],))
            raise
        md = f"> **결론** {out['conclusion']}\n\n{out['body_md'].strip()}\n"
        with self.conn:
            self.conn.execute(
                """UPDATE analyses SET status = 'done', title = ?, content_md = ?, cost_usd = ?, error = NULL,
                   finished_at = datetime('now') WHERE id = ?""",
                (out["title"], md, usage.cost_usd, row["id"]),
            )
            budget.record(self.conn, self.settings, "analyses", tokens_in=usage.tokens_in,
                          tokens_out=usage.tokens_out, cost_usd=usage.cost_usd)
        log.info("분석 %s 완료 (model=%s, in=%s, out=%s)", row["id"], usage.model, usage.tokens_in, usage.tokens_out)
        self.save_to_tana(row["id"], card, row["question"], out)
        return "done"

    def save_to_tana(self, analysis_id: int, card: sqlite3.Row, question: str | None, out: dict) -> bool:
        if self.tana is None:
            return False
        from .tana import created_node_id, research_paste
        t = self.settings.get("tana", {})
        date = datetime.now(ZoneInfo(self.settings.get("timezone", "Asia/Seoul"))).date().isoformat()
        paste = research_paste(title=out["title"], topic=out["topic"], confidence=out["confidence"], date=date,
                               url=card["url"], conclusion=out["conclusion"], body_md=out["body_md"],
                               question=question, tana=t)
        try:
            node = created_node_id(self.tana.import_paste(t["parent_node_id"], paste))
        except Exception as e:
            log.warning("분석 %s Tana 저장 실패: %s", analysis_id, str(e)[:200])
            with self.conn:
                self.conn.execute("UPDATE analyses SET error = ? WHERE id = ?", (f"Tana 저장 실패: {str(e)[:200]}", analysis_id))
            return False
        with self.conn:
            self.conn.execute("UPDATE analyses SET tana_node_id = ?, error = NULL WHERE id = ?", (node or "unknown", analysis_id))
        log.info("분석 %s Tana 저장 (%s)", analysis_id, node or "ID 못 읽음")
        return True

    def retry_tana(self) -> int:
        """done인데 Tana에 못 쓴 것을 다시 쓴다. 본문은 저장된 Markdown이 아니라 다시 만들 수 없으니
        title·content_md로 단순 노드를 만든다."""
        if self.tana is None:
            return 0
        rows = self.conn.execute(
            f"""SELECT * FROM analyses WHERE status = 'done' AND tana_node_id IS NULL AND content_md IS NOT NULL
                AND finished_at >= datetime('now', '-{TANA_RETRY_DAYS} days')""").fetchall()
        n = 0
        for r in rows:
            card = card_row(self.conn, r["card_id"])
            if card is None:
                continue
            md = r["content_md"]
            first, _, rest = md.partition("\n\n")
            conclusion = first.replace("> **결론**", "").strip()
            out = {"title": r["title"] or "심화 분석", "topic": "", "confidence": "중간", "conclusion": conclusion, "body_md": rest}
            n += self.save_to_tana(r["id"], card, r["question"], out)
        return n

    def _fail(self, analysis_id: int, reason: str) -> None:
        with self.conn:
            self.conn.execute("UPDATE analyses SET status = 'failed', error = ?, finished_at = datetime('now') WHERE id = ?",
                              (reason[:300], analysis_id))
        log.warning("분석 %s 실패: %s", analysis_id, reason[:120])

    def drain(self) -> dict:
        counts = {"done": 0, "failed": 0}
        while (row := claim_next(self.conn)) is not None:
            counts[self.run_one(row)] += 1
        return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m pipeline.analysis")
    ap.add_argument("--once", action="store_true", help="대기열을 한 번 비우고 끝낸다")
    ap.add_argument("--interval", type=float, default=10.0, help="대기열 확인 간격(초)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    settings = load_settings()
    conn = db.connect(db.db_path(settings))
    worker = Analyzer(conn, settings)
    worker.recover()
    last_retry = 0.0
    while True:
        try:
            worker.drain()
            if time.time() - last_retry > 1800:
                last_retry = time.time()
                worker.retry_tana()
        except NotConfigured as e:
            log.error("설정 없음: %s", e)
            if args.once:
                return 2
            time.sleep(300)
        except Exception:
            log.exception("분석 워커 오류, 잠시 뒤 다시")
            if args.once:
                return 1
            time.sleep(60)
        if args.once:
            return 0
        time.sleep(args.interval)


if __name__ == "__main__":
    raise SystemExit(main())
