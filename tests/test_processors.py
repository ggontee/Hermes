from __future__ import annotations

import copy
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from pipeline import budget, db
from pipeline.config import load_people, load_settings
from pipeline.llm import Claude, Usage
from pipeline.normalize import Item
from pipeline.processors import (LONG_SUMMARY_SCHEMA, SHORT_SCHEMA, TRANSLATE_SCHEMA, VIDEO_SCHEMA,
                                 Processor, chunk_paragraphs, is_korean, parse_timestamp, process_pending)
from pipeline.store import store_item, sync_config

FIX = Path(__file__).parent / "fixtures"
REPO = Path(__file__).resolve().parent.parent


class FakeMessages:
    """client.beta.messages.create 흉내. 스키마를 보고 그럴듯한 JSON을 돌려준다."""

    def __init__(self, *, refuse=False, bad_json_once=False):
        self.calls = []
        self.refuse = refuse
        self.bad_json_once = bad_json_once

    def create(self, **kw):
        self.calls.append(kw)
        schema = kw["output_config"]["format"]["schema"]
        user = kw["messages"][0]["content"]
        if self.refuse:
            return _resp("", stop="refusal")
        if self.bad_json_once:
            self.bad_json_once = False
            return _resp("{not json")
        props = set(schema["properties"])
        if props == set(SHORT_SCHEMA["properties"]):
            out = {"translation_ko": "번역된 짧은 글", "quote_translation_ko": None, "lang_detected": "en"}
        elif props == set(LONG_SUMMARY_SCHEMA["properties"]):
            out = {"title_ko": "제목", "summary_ko": ["하나", "둘", "셋", "넷"], "so_what": "중요하다",
                   "tags": ["a", "b"], "is_preview": False}
        elif props == set(TRANSLATE_SCHEMA["properties"]):
            ids = re.findall(r"\[(p\d+)\]", user.split("<body>")[1])
            out = {"paragraphs": [{"id": i, "ko": f"번역 {i}"} for i in ids]}
        elif props == set(VIDEO_SCHEMA["properties"]):
            out = {"oneliner": "한 줄", "sections": [{"t": 0, "title": "도입", "summary": "요약"}],
                   "top3": [0], "tags": ["eval"], "from_description": "받아쓰기 없음" in user}
        else:
            raise AssertionError("unknown schema")
        return _resp(json.dumps(out, ensure_ascii=False))


def _resp(text, stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, stop_details=None,
                           content=[SimpleNamespace(type="text", text=text)],
                           usage=SimpleNamespace(input_tokens=1000, output_tokens=200))


class FakeGemini:
    def __init__(self):
        self.calls = 0

    def transcribe(self, url):
        self.calls += 1
        return "[00:00] Hello and welcome.\n\n[01:05] Now about evals.", False, \
            Usage("gemini-3.5-flash-lite", 40000, 2000, 0.017)


@pytest.fixture
def settings():
    s = copy.deepcopy(load_settings(REPO / "config" / "settings.yaml"))
    s["ai"]["translate_chunk_chars"] = 30
    return s


@pytest.fixture
def setup(tmp_path, settings):
    conn = db.connect(tmp_path / "t.db")
    people = load_people(FIX / "sources.yaml", settings=settings)
    ids = sync_config(conn, people)
    person = people[0]
    keys = {s.type: s.key for s in person.sources if s.url}

    def add(platform, ext, paragraphs, title="", url=None):
        src = {"blog": "rss", "sns": "bluesky", "video": "youtube"}[platform]
        it = Item(source_key=keys[src], person=person.name, field="AI", platform=platform, external_id=ext,
                  url=url or f"https://example.com/{ext}", published_at=datetime(2026, 11, 26, tzinfo=timezone.utc),
                  title=title, paragraphs=paragraphs)
        assert store_item(conn, it, source_id=ids[keys[src]], person=person, settings=settings) == "new"
    return conn, add


def make_processor(conn, settings, messages, gemini=None):
    claude = Claude(settings, {"keep": ["Claude"]}, client=SimpleNamespace(beta=SimpleNamespace(messages=messages)))
    return Processor(conn, settings, claude=claude, gemini=gemini)


def test_helpers():
    assert is_korean("이건 한국어 글이다 with a word")
    assert not is_korean("This is English")
    assert parse_timestamp("[01:05] x") == 65
    assert parse_timestamp("[1:02:03] x") == 3723
    chunks = chunk_paragraphs(["a" * 20, "b" * 20, "c" * 5], 30)
    assert [s for s, _ in chunks] == [1, 2]


def test_all_three_kinds(setup, settings):
    conn, add = setup
    add("sns", "s1", ["Short English post"])
    add("blog", "b1", ["First paragraph here", "Second paragraph here", "Third one"], title="A post title")
    add("video", "v1", ["video description"], title="A video")
    msgs = FakeMessages()
    gem = FakeGemini()
    out = process_pending(conn, settings, processor=make_processor(conn, settings, msgs, gem))
    assert out == {"processed": 3, "deferred": 0, "failed": 0}

    cards = {r["kind"]: r for r in conn.execute("SELECT * FROM cards")}
    assert cards["short"]["translation_ko"] == "번역된 짧은 글"
    long = cards["long"]
    assert long["title_ko"] == "제목"
    assert json.loads(long["summary_ko_json"]) == ["하나", "둘", "셋"]
    pairs = json.loads(long["translation_pairs_json"])
    assert [p["id"] for p in pairs] == ["p1", "p2", "p3"] and all(p["ko"] for p in pairs)
    video = cards["video"]
    assert video["video_oneliner"] == "한 줄" and video["from_description"] == 0
    transcript = json.loads(video["transcript_ko"])
    assert [t["t"] for t in transcript] == [0, 65]

    # 모델 배분과 공통 지시
    models = [c["model"] for c in msgs.calls]
    assert models[0] in ("claude-haiku-5-5", "claude-sonnet-5-5")
    assert "claude-haiku-5-5" in models and "claude-sonnet-5-5" in models
    assert all("<glossary>" in c["system"] for c in msgs.calls)
    assert all(c["fallbacks"] == "default" for c in msgs.calls)

    assert budget.used(conn, settings, "ai_items") == 3
    assert budget.used(conn, settings, "videos") == 1
    assert conn.execute("SELECT COUNT(*) FROM items WHERE status = 'done'").fetchone()[0] == 3


def test_korean_short_skips_model(setup, settings):
    conn, add = setup
    add("sns", "k1", ["한국어로 쓴 짧은 글이다"])
    msgs = FakeMessages()
    process_pending(conn, settings, processor=make_processor(conn, settings, msgs))
    assert msgs.calls == []
    assert conn.execute("SELECT translation_ko FROM cards").fetchone()[0] == "한국어로 쓴 짧은 글이다"


def test_video_without_gemini_uses_description(setup, settings):
    conn, add = setup
    add("video", "v2", ["desc"], title="Video")
    msgs = FakeMessages()
    proc = make_processor(conn, settings, msgs)
    proc._gemini_checked = True  # 키 없음과 같다
    process_pending(conn, settings, processor=proc)
    card = conn.execute("SELECT * FROM cards").fetchone()
    assert card["from_description"] == 1 and card["transcript_ko"] is None


def test_cap_defers(setup, settings):
    conn, add = setup
    settings["budget"]["ai_items_per_day"] = 1
    add("sns", "a", ["one"])
    add("sns", "b", ["two"])
    out = process_pending(conn, settings, processor=make_processor(conn, settings, FakeMessages()))
    assert out == {"processed": 1, "deferred": 1, "failed": 0}
    assert conn.execute("SELECT COUNT(*) FROM items WHERE status = 'pending_ai'").fetchone()[0] == 1


def test_refusal_marks_failed_and_continues(setup, settings):
    conn, add = setup
    add("sns", "a", ["one"])
    out = process_pending(conn, settings, processor=make_processor(conn, settings, FakeMessages(refuse=True)))
    assert out["failed"] == 1
    row = conn.execute("SELECT status, fail_reason FROM items").fetchone()
    assert row["status"] == "failed" and row["fail_reason"].startswith("refusal")


def test_bad_json_retried_once(setup, settings):
    conn, add = setup
    add("sns", "a", ["one"])
    msgs = FakeMessages(bad_json_once=True)
    out = process_pending(conn, settings, processor=make_processor(conn, settings, msgs))
    assert out["processed"] == 1 and len(msgs.calls) == 2


def test_api_outage_defers_rest(setup, settings):
    conn, add = setup
    add("sns", "a", ["one"])
    add("sns", "b", ["two"])

    class Boom(Exception):
        status_code = 529

    class Down(FakeMessages):
        def create(self, **kw):
            raise Boom()

    out = process_pending(conn, settings, processor=make_processor(conn, settings, Down()))
    assert out == {"processed": 0, "deferred": 2, "failed": 0}


def test_no_api_key_defers(setup, settings, monkeypatch):
    conn, add = setup
    add("sns", "a", ["one"])
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    out = process_pending(conn, settings)
    assert out == {"processed": 0, "deferred": 1, "failed": 0}
