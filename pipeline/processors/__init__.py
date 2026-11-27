"""유형별 AI 처리 (dev-spec 5장, docs/prompts.md).

process_pending: status='pending_ai'인 묶음 기준(primary) 항목을 최신순으로, 하루 상한 안에서
처리해 cards 행을 만든다. 실패한 항목은 status='failed'와 이유만 남기고 다음으로 넘어간다.
"""
from __future__ import annotations

import json
import logging
import re
import sqlite3

from .. import budget
from ..config import load_glossary
from ..llm import Claude, Gemini, LLMError, NotConfigured, Usage, prompt
from ..store import now_iso

log = logging.getLogger(__name__)

HANGUL = re.compile(r"[가-힣]")
TS_RE = re.compile(r"^\[(\d+):(\d{2})(?::(\d{2}))?\]")

# ── JSON 스키마 (docs/prompts.md) ──

def _obj(props: dict) -> dict:
    return {"type": "object", "properties": props, "required": list(props), "additionalProperties": False}


STR = {"type": "string"}
STRS = {"type": "array", "items": STR}
SHORT_SCHEMA = _obj({"translation_ko": STR, "quote_translation_ko": {"type": ["string", "null"]},
                     "lang_detected": STR})
LONG_SUMMARY_SCHEMA = _obj({"title_ko": STR, "summary_ko": STRS, "so_what": STR, "tags": STRS,
                            "is_preview": {"type": "boolean"}})
TRANSLATE_SCHEMA = _obj({"paragraphs": {"type": "array", "items": _obj({"id": STR, "ko": STR})}})
VIDEO_SCHEMA = _obj({
    "oneliner": STR,
    "sections": {"type": "array", "items": _obj({"t": {"type": "integer"}, "title": STR, "summary": STR})},
    "top3": {"type": "array", "items": {"type": "integer"}},
    "tags": STRS,
    "from_description": {"type": "boolean"},
})


# ── 입력 만들기 ──

def _item_xml(row: sqlite3.Row, paragraphs: list[str], *, numbered: bool = True, start: int = 1) -> str:
    body = "\n".join(f"[p{i}] {p}" if numbered else p for i, p in enumerate(paragraphs, start=start))
    return (f"<item>\n<author>{row['person_name']}"
            f"{' (' + row['affiliation'] + ')' if row['affiliation'] else ''}</author>\n"
            f"<source>{row['source_type']}</source>\n<published>{row['published_at']}</published>\n"
            f"<title>{row['title_orig']}</title>\n<body>\n{body}\n</body>\n</item>")


def is_korean(text: str) -> bool:
    letters = [c for c in text if c.isalpha()]
    return bool(letters) and sum(1 for c in letters if HANGUL.match(c)) / len(letters) > 0.3


def chunk_paragraphs(paragraphs: list[str], max_chars: int) -> list[tuple[int, list[str]]]:
    """[(시작 번호, 문단들)]. 한 문단이 max_chars보다 길면 그 문단만 한 묶음."""
    chunks, cur, size, start = [], [], 0, 1
    for i, p in enumerate(paragraphs, start=1):
        if cur and size + len(p) > max_chars:
            chunks.append((start, cur))
            cur, size, start = [], 0, i
        cur.append(p)
        size += len(p)
    if cur:
        chunks.append((start, cur))
    return chunks


def parse_timestamp(line: str) -> int | None:
    m = TS_RE.match(line.strip())
    if not m:
        return None
    a, b, c = m.groups()
    return int(a) * 3600 + int(b) * 60 + int(c) if c else int(a) * 60 + int(b)


# ── 처리기 ──

class Processor:
    def __init__(self, conn: sqlite3.Connection, settings: dict, claude: Claude | None = None,
                 gemini: Gemini | None = None):
        self.conn, self.settings = conn, settings
        self.models = settings.get("models", {})
        self.limits = settings.get("ai", {})
        self.claude = claude or Claude(settings, load_glossary())
        self._gemini = gemini
        self._gemini_checked = gemini is not None

    @property
    def gemini(self) -> Gemini | None:
        if not self._gemini_checked:
            self._gemini_checked = True
            try:
                self._gemini = Gemini(self.settings)
            except NotConfigured as e:
                log.info("영상 받아쓰기 꺼짐: %s", e)
        return self._gemini

    # 긴 문단 목록 번역 (긴 글 전문, 영상 스크립트 공통)
    def translate(self, row, paragraphs: list[str]) -> tuple[list[dict], Usage]:
        model = self.models.get("long", "claude-sonnet-5-5")
        max_chars = int(self.limits.get("translate_chunk_chars", 18000))
        pairs: list[dict] = []
        usage = Usage(model)
        for start, chunk in chunk_paragraphs(paragraphs, max_chars):
            context = ""
            if pairs:
                prev = "\n".join(p["ko"] for p in pairs[-2:])
                context = f"<앞 내용>\n{prev}\n</앞 내용>\n\n"
            data, u = self.claude.json(model=model, instruction=prompt("long_translate"),
                                       content=context + _item_xml(row, chunk, start=start),
                                       schema=TRANSLATE_SCHEMA, max_tokens=int(self.limits.get("translate_max_tokens", 16000)),
                                       effort=self.limits.get("translate_effort", "medium"))
            usage = usage.add(u)
            got = {p["id"].strip("[]"): p["ko"] for p in data["paragraphs"]}
            for i, orig in enumerate(chunk, start=start):
                pairs.append({"id": f"p{i}", "orig": orig, "ko": got.get(f"p{i}", "")})
        missing = [p["id"] for p in pairs if not p["ko"]]
        if missing:
            log.warning("번역에서 빠진 문단 %d개", len(missing))
        return pairs, usage

    def short(self, row, paragraphs) -> tuple[dict, Usage]:
        text = "\n\n".join(paragraphs)
        model = self.models.get("short", "claude-haiku-5-5")
        if is_korean(text):
            return {"translation_ko": text}, Usage(model)
        data, u = self.claude.json(model=model, instruction=prompt("short"),
                                   content=_item_xml(row, paragraphs, numbered=False), schema=SHORT_SCHEMA,
                                   max_tokens=4000, effort=self.limits.get("short_effort", "low"))
        return {"translation_ko": data["translation_ko"],
                "quote_translation_ko": data.get("quote_translation_ko")}, u

    def long(self, row, paragraphs) -> tuple[dict, Usage]:
        model = self.models.get("long", "claude-sonnet-5-5")
        max_chars = int(self.limits.get("summary_input_chars", 120000))
        clipped, total = [], 0
        for p in paragraphs:
            if total + len(p) > max_chars:
                break
            clipped.append(p)
            total += len(p)
        data, u = self.claude.json(model=model, instruction=prompt("long_summary"),
                                   content=_item_xml(row, clipped), schema=LONG_SUMMARY_SCHEMA,
                                   max_tokens=4000, effort=self.limits.get("summary_effort", "medium"))
        pairs, u2 = self.translate(row, paragraphs)
        return {"title_ko": data["title_ko"], "summary_ko_json": json.dumps(data["summary_ko"][:3], ensure_ascii=False),
                "so_what": data["so_what"], "tags_json": json.dumps(data["tags"][:5], ensure_ascii=False),
                "is_preview": int(bool(data["is_preview"])),
                "translation_pairs_json": json.dumps(pairs, ensure_ascii=False),
                "translation_ko": "\n\n".join(p["ko"] for p in pairs)}, u.add(u2)

    def video(self, row, paragraphs) -> tuple[dict, Usage, bool]:
        """(카드 필드, 사용량, Gemini를 썼는지)."""
        model = self.models.get("long", "claude-sonnet-5-5")
        transcript, used_gemini, usage = None, False, Usage(model)
        if self.gemini and budget.remaining(self.conn, self.settings, "videos") > 0:
            try:
                transcript, _cut, gu = self.gemini.transcribe(row["url"])
                used_gemini = True
                usage = gu
            except LLMError as e:
                log.warning("받아쓰기 실패, 설명으로 요약: %s", e)
        if transcript:
            blocks = [b.strip() for b in re.split(r"\n\s*\n|\n(?=\[\d)", transcript) if b.strip()]
            content = _item_xml(row, blocks, numbered=False)
        else:
            blocks = []
            content = _item_xml(row, paragraphs or ["(설명 없음)"], numbered=False) + \
                "\n받아쓰기 없음: 제목과 설명만으로 요약한다."
        data, u = self.claude.json(model=model, instruction=prompt("video_summary"), content=content,
                                   schema=VIDEO_SCHEMA, max_tokens=6000,
                                   effort=self.limits.get("summary_effort", "medium"))
        usage = usage.add(u)
        fields = {"title_ko": None, "video_oneliner": data["oneliner"],
                  "video_sections_json": json.dumps(data["sections"][:8], ensure_ascii=False),
                  "video_top3_json": json.dumps(data["top3"][:3]),
                  "tags_json": json.dumps(data["tags"][:5], ensure_ascii=False),
                  "from_description": int(not transcript or bool(data["from_description"]))}
        if blocks and self.limits.get("translate_transcript", True):
            pairs, u3 = self.translate(row, blocks)
            usage = usage.add(u3)
            fields["transcript_ko"] = json.dumps(
                [{"t": parse_timestamp(p["orig"]), "orig": p["orig"], "ko": p["ko"]} for p in pairs],
                ensure_ascii=False)
        return fields, usage, used_gemini

    def process_row(self, row) -> None:
        paragraphs = json.loads(row["paragraphs_json"])
        used_gemini = False
        if row["kind"] == "short":
            fields, usage = self.short(row, paragraphs)
        elif row["kind"] == "long":
            fields, usage = self.long(row, paragraphs)
        elif row["kind"] == "video":
            fields, usage, used_gemini = self.video(row, paragraphs)
        else:
            raise LLMError(f"unknown kind {row['kind']}")
        fields.update(item_id=row["id"], kind=row["kind"], model=usage.model, tokens_in=usage.tokens_in,
                      tokens_out=usage.tokens_out, cost_usd=round(usage.cost_usd, 6), created_at=now_iso())
        cols = ", ".join(fields)
        marks = ", ".join("?" for _ in fields)
        with self.conn:
            self.conn.execute(f"INSERT INTO cards({cols}) VALUES ({marks})", list(fields.values()))
            self.conn.execute("UPDATE items SET status = 'done', fail_reason = NULL WHERE id = ?", (row["id"],))
            budget.record(self.conn, self.settings, "ai_items", tokens_in=usage.tokens_in,
                          tokens_out=usage.tokens_out, cost_usd=usage.cost_usd)
            if used_gemini:
                budget.record(self.conn, self.settings, "videos")


PENDING_SQL = """
SELECT i.*, p.name AS person_name, p.affiliation, s.type AS source_type
FROM items i JOIN people p ON p.id = i.person_id JOIN sources s ON s.id = i.source_id
WHERE i.status = 'pending_ai' AND i.role = 'primary'
ORDER BY i.published_at DESC
"""


def process_pending(conn: sqlite3.Connection, settings: dict, processor: Processor | None = None) -> dict[str, int]:
    """처리 대기 항목을 상한 안에서 처리한다. {'processed': n, 'deferred': m, 'failed': k}."""
    rows = conn.execute(PENDING_SQL).fetchall()
    out = {"processed": 0, "deferred": 0, "failed": 0}
    if not rows:
        return out
    try:
        processor = processor or Processor(conn, settings)
    except NotConfigured as e:
        log.warning("AI 처리 건너뜀: %s", e)
        out["deferred"] = len(rows)
        return out
    for idx, row in enumerate(rows):
        if budget.remaining(conn, settings, "ai_items") <= 0:
            out["deferred"] = len(rows) - idx
            log.info("오늘 상한 도달: %d건은 다음 회차로", out["deferred"])
            break
        try:
            processor.process_row(row)
            out["processed"] += 1
        except LLMError as e:
            out["failed"] += 1
            conn.execute("UPDATE items SET status = 'failed', fail_reason = ? WHERE id = ?", (str(e)[:300], row["id"]))
            conn.commit()
            log.warning("처리 실패 item=%d kind=%s: %s", row["id"], row["kind"], e)
        except Exception as e:  # API 장애(429/5xx 재시도 소진, 연결 끊김): 나머지는 다음 회차로
            status = getattr(e, "status_code", None)
            if status is not None and 400 <= status < 500 and status != 429:
                out["failed"] += 1
                conn.execute("UPDATE items SET status = 'failed', fail_reason = ? WHERE id = ?",
                             (f"HTTP {status}", row["id"]))
                conn.commit()
                log.warning("처리 실패 item=%d HTTP %s", row["id"], status)
                continue
            out["deferred"] = len(rows) - idx
            log.exception("API 장애로 중단 (%s): %d건은 다음 회차로", type(e).__name__, out["deferred"])
            break
    return out
