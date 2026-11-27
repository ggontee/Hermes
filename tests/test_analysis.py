from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from pipeline import budget, db
from pipeline.analysis import ANALYSIS_SCHEMA, Analyzer, build_input, card_row, claim_next
from pipeline.config import load_settings
from pipeline.llm import Claude
from pipeline.tana import (FileStore, TanaAuth, TanaMCP, TanaToken, created_node_id, md_to_nodes, research_paste,
                           rpc_result)

REPO = Path(__file__).resolve().parent.parent


def _resp(text, stop="end_turn"):
    return SimpleNamespace(stop_reason=stop, stop_details=None, content=[SimpleNamespace(type="text", text=text)],
                           usage=SimpleNamespace(input_tokens=30000, output_tokens=3000))


class FakeMessages:
    def __init__(self, stop="end_turn"):
        self.calls = []
        self.stop = stop

    def create(self, **kw):
        self.calls.append(kw)
        assert kw["output_config"]["format"]["schema"] == ANALYSIS_SCHEMA
        return _resp(json.dumps({"title": "프롬프트 인젝션 정리", "conclusion": "권한 설계가 먼저다",
                                 "body_md": "## 핵심\n- 주장 #1\n  - 근거 [[x]]\n\n## 더 볼 것\n확인 필요:: 수치",
                                 "topic": "에이전트 보안", "confidence": "중간"}, ensure_ascii=False), self.stop)


class FakeTana:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def import_paste(self, parent, content):
        self.calls.append((parent, content))
        if self.fail:
            raise RuntimeError("boom")
        return 'Successfully imported 9 node(s)\nParent node: P\nCreated nodes:\n- NodeAbc123 ("프롬프트")\n- Other99999 ("x")'


@pytest.fixture
def settings():
    s = copy.deepcopy(load_settings(REPO / "config" / "settings.yaml"))
    s["tana"]["parent_node_id"] = "PARENT"
    return s


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    c.execute("INSERT INTO people(name, field, affiliation) VALUES ('Simon Willison', 'AI', 'Datasette')")
    c.execute("INSERT INTO sources(key, person_id, type, url) VALUES ('s', 1, 'rss', 'https://e.com/feed')")
    c.execute("""INSERT INTO items(source_id, person_id, external_id, url, canonical_url, published_at, platform, kind,
                 title_orig, paragraphs_json, char_count, content_hash, fetched_at)
                 VALUES (1, 1, 'x', 'https://e.com/p', 'https://e.com/p', '2026-11-26T00:00:00+00:00', 'blog', 'long',
                 'Prompt injection', '["Para one.", "Para two."]', 18, 'h', '2026-11-26')""")
    c.execute("""INSERT INTO cards(item_id, kind, title_ko, summary_ko_json, so_what, status, user_comment, created_at)
                 VALUES (1, 'long', '프롬프트 인젝션', '["a","b","c"]', '중요', 'kept', '우리 제품에 적용?', '2026-11-26')""")
    c.execute("INSERT INTO analyses(card_id, question, created_at) VALUES (1, '비용은?', datetime('now'))")
    c.commit()
    return c


def make(conn, settings, messages=None, tana=None):
    claude = Claude(settings, {"keep": []}, client=SimpleNamespace(beta=SimpleNamespace(messages=messages or FakeMessages())))
    return Analyzer(conn, settings, claude=claude, tana=tana)


def test_build_input_has_comment_question_and_paragraph_ids(conn):
    text = build_input(card_row(conn, 1), "비용은?", 1000)
    assert "[p1] Para one." in text and "<user_comment>우리 제품에 적용?</user_comment>" in text
    assert "<user_question>비용은?</user_question>" in text and "Simon Willison (Datasette)" in text


def test_drain_done_records_usage_and_saves_to_tana(conn, settings):
    tana = FakeTana()
    msgs = FakeMessages()
    out = make(conn, settings, msgs, tana).drain()
    assert out == {"done": 1, "failed": 0}
    row = conn.execute("SELECT * FROM analyses").fetchone()
    assert row["status"] == "done" and row["title"] == "프롬프트 인젝션 정리"
    assert row["content_md"].startswith("> **결론** 권한 설계가 먼저다")
    assert row["tana_node_id"] == "NodeAbc123" and row["error"] is None
    assert budget.used(conn, settings, "analyses") == 1
    assert msgs.calls[0]["model"] == "claude-sonnet-5-5"
    parent, paste = tana.calls[0]
    assert parent == "PARENT" and paste.startswith("%%tana%%\n- 프롬프트 인젝션 정리 #[[Research]]")
    assert "  - Topic:: 에이전트 보안" in paste and "  - 신뢰도:: 중간" in paste and "[[date:" in paste
    assert "  - 원문: https://e.com/p" in paste


def test_tana_failure_keeps_analysis_and_retries(conn, settings):
    tana = FakeTana(fail=True)
    w = make(conn, settings, tana=tana)
    w.drain()
    row = conn.execute("SELECT * FROM analyses").fetchone()
    assert row["status"] == "done" and row["tana_node_id"] is None and row["error"].startswith("Tana 저장 실패")
    tana.fail = False
    assert w.retry_tana() == 1
    assert conn.execute("SELECT tana_node_id FROM analyses").fetchone()[0] == "NodeAbc123"


def test_without_tana_parent_only_stores_locally(conn, settings):
    settings["tana"]["parent_node_id"] = ""
    w = make(conn, settings)
    assert w.tana is None
    assert w.drain()["done"] == 1


def test_truncated_marks_failed(conn, settings):
    out = make(conn, settings, FakeMessages(stop="max_tokens"), FakeTana()).drain()
    assert out == {"done": 0, "failed": 1}
    assert conn.execute("SELECT status FROM analyses").fetchone()[0] == "failed"


def test_api_outage_requeues(conn, settings):
    class Down(FakeMessages):
        def create(self, **kw):
            raise ConnectionError("down")
    with pytest.raises(ConnectionError):
        make(conn, settings, Down(), FakeTana()).drain()
    assert conn.execute("SELECT status FROM analyses").fetchone()[0] == "queued"


def test_recover_and_claim(conn, settings):
    conn.execute("UPDATE analyses SET status = 'running'")
    conn.commit()
    assert claim_next(conn) is None
    make(conn, settings).recover()
    assert claim_next(conn)["id"] == 1
    assert claim_next(conn) is None


# ── Tana ──

def test_paste_escapes_tana_syntax():
    nodes = md_to_nodes("## 핵심\n- 주장 #1\n  - 근거 [[x]]\n본문 a::b")
    assert nodes == [(0, "**핵심**"), (1, "주장 ＃1"), (2, "근거 [ [x] ]"), (1, "본문 a:b")]
    p = research_paste(title="T #x", topic="t", confidence="높음", date="2026-11-27", url="u", conclusion="c",
                       body_md="## h\n- a", question=None, tana={"tag": "Research"})
    assert p.splitlines()[1] == "- T ＃x #[[Research]]"
    assert p.splitlines()[-2:] == ["  - **h**", "    - a"]


def test_created_node_id():
    assert created_node_id('Created nodes:\n- abcDEF_123 ("x")') == "abcDEF_123"
    assert created_node_id("nothing") == ""


def test_rpc_result_sse():
    text = 'event: message\ndata: {"jsonrpc":"2.0","id":1,"result":{"ok":1}}\n\n'
    assert rpc_result(text, "text/event-stream") == {"ok": 1}


def test_auth_refresh_and_mcp_call(tmp_path):
    now = datetime(2026, 11, 27, tzinfo=timezone.utc)
    store = FileStore(tmp_path / "tok.json")
    store.write(json.dumps({"access_token": "old", "refresh_token": "r1", "client_id": "c", "token_endpoint": "https://auth/token",
                            "resource": "https://app.tana.inc/mcp", "expires_at": (now + timedelta(minutes=1)).isoformat()}))
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(req)
        if str(req.url) == "https://auth/token":
            assert b"refresh_token=r1" in req.content
            return httpx.Response(200, json={"access_token": "new", "refresh_token": "r2", "expires_in": 3600})
        assert req.headers["authorization"] == "Bearer new"
        body = json.loads(req.content)
        if body["method"] == "initialize":
            return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": {}}, headers={"mcp-session-id": "S1"})
        if body["method"] == "notifications/initialized":
            return httpx.Response(202)
        assert req.headers["mcp-session-id"] == "S1"
        assert body["params"] == {"name": "import_tana_paste", "arguments": {"parentNodeId": "P", "content": "x"}}
        return httpx.Response(200, headers={"content-type": "text/event-stream"},
                              text='data: {"jsonrpc":"2.0","id":3,"result":{"content":[{"type":"text","text":"Created nodes:\\n- Node123456 (\\"x\\")"}]}}\n\n')

    client = httpx.Client(transport=httpx.MockTransport(handler))
    mcp = TanaMCP(TanaAuth(store, client, now=lambda: now), client, "https://app.tana.inc/mcp")
    assert created_node_id(mcp.import_paste("P", "x")) == "Node123456"
    saved = TanaToken.parse(store.read())
    assert saved.access_token == "new" and saved.refresh_token == "r2"
