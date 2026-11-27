from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
import pytest

from pipeline import db
from pipeline.classify import classify, sns_length
from pipeline.config import load_people, load_settings
from pipeline.normalize import Item, canonical_url, html_to_paragraphs
from pipeline.run import run_once
from pipeline.store import store_item, sync_config, title_similarity

FIX = Path(__file__).parent / "fixtures"
REPO = Path(__file__).resolve().parent.parent


@pytest.fixture
def settings():
    s = copy.deepcopy(load_settings(REPO / "config" / "settings.yaml"))
    s["collect"]["first_run_lookback_hours"] = 24 * 365 * 10
    return s


@pytest.fixture
def conn(tmp_path):
    return db.connect(tmp_path / "t.db")


def feeds_transport(mapping: dict[str, str]) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        for prefix, name in mapping.items():
            if str(request.url).startswith(prefix):
                return httpx.Response(200, content=(FIX / name).read_bytes())
        return httpx.Response(404)
    return httpx.MockTransport(handler)


# ── config ──

def test_real_sources_yaml_loads():
    people = load_people(REPO / "config" / "sources.yaml", settings=load_settings(REPO / "config" / "settings.yaml"))
    assert len(people) >= 20
    for p in people:
        for s in p.sources:
            if s.type == "x":
                assert not s.enabled, f"{s.key}: X는 2단계까지 꺼 둔다"
            if s.enabled:
                assert s.url.startswith("http")


def test_todo_sources_are_disabled(settings):
    people = load_people(FIX / "sources.yaml", settings=settings)
    by_type = {s.type: s for s in people[0].sources if s.url != ""}
    assert by_type["youtube"].url.endswith("channel_id=UCexample")
    assert by_type["bluesky"].url == "https://bsky.app/profile/example.bsky.social/rss"
    todo = [s for s in people[0].sources if s.type == "rss" and not s.url]
    assert todo and not todo[0].enabled


# ── normalize / classify ──

def test_canonical_url():
    assert canonical_url("https://www.Example.com/a/?utm_source=x&id=3#frag") == "https://example.com/a?id=3"
    assert canonical_url("https://youtu.be/abc") == canonical_url("https://www.youtube.com/watch?v=abc&t=10s")


def test_html_to_paragraphs():
    paras, imgs, links = html_to_paragraphs('<p>Hi <a href="https://x.com/y">x</a></p><ul><li>a</li></ul><img src="https://i/1.png">')
    assert paras == ["Hi x", "• a"]
    assert imgs == ["https://i/1.png"]
    assert links == ["https://x.com/y"]


def test_classify_rules():
    assert classify("video", "x" * 10) == "video"
    assert classify("blog", "short") == "long"
    assert classify("sns", "a" * 500) == "short"
    assert classify("sns", "a" * 501) == "long"
    # 링크는 한 글자로 센다
    assert sns_length("a" * 490 + " https://example.com/" + "b" * 200) == 492


def test_title_similarity():
    assert title_similarity("Building a better eval harness | Podcast", "Building a better eval harness") == 1.0
    assert title_similarity("Completely different", "Building a better eval harness") < 0.5


# ── store / dedupe ──

def _item(source_key, platform, **kw):
    base = dict(source_key=source_key, person="Example Person", field="AI", platform=platform,
                external_id=kw.pop("external_id", "id1"), url=kw.pop("url", "https://blog.example.com/p"),
                published_at=kw.pop("published_at", datetime(2026, 11, 26, 10, tzinfo=timezone.utc)),
                title=kw.pop("title", "Title"), paragraphs=kw.pop("paragraphs", ["body"]))
    base.update(kw)
    return Item(**base)


def test_dedupe_link_merge_and_same_content(conn, settings):
    people = load_people(FIX / "sources.yaml", settings=settings)
    person = people[0]
    ids = sync_config(conn, people)
    keys = {s.type: s.key for s in person.sources if s.url}
    blog, yt, bsky = ids[keys["rss"]], ids[keys["youtube"]], ids[keys["bluesky"]]

    post = _item(keys["rss"], "blog", external_id="b1", url="https://blog.example.com/eval/",
                 title="Building a better eval harness", paragraphs=["p1 " * 50])
    assert store_item(conn, post, source_id=blog, person=person, settings=settings) == "new"
    # 같은 소스, 같은 ID → known
    assert store_item(conn, post, source_id=blog, person=person, settings=settings) == "known"

    # SNS가 그 글을 링크 → 작성자 한마디로 묶임
    note = _item(keys["bluesky"], "sns", external_id="s1", url="https://bsky.app/p/1",
                 title="", paragraphs=["New post: https://blog.example.com/eval"],
                 links=["https://blog.example.com/eval?utm_source=bsky"])
    assert store_item(conn, note, source_id=bsky, person=person, settings=settings) == "merged"

    # 같은 제목의 영상 → 영상이 기준, 글은 alt
    video = _item(keys["youtube"], "video", external_id="v1", url="https://www.youtube.com/watch?v=abc",
                  title="Building a better eval harness | Podcast", paragraphs=["desc"],
                  published_at=datetime(2026, 11, 26, 20, tzinfo=timezone.utc))
    assert store_item(conn, video, source_id=yt, person=person, settings=settings) == "merged"

    rows = {r["external_id"]: r for r in conn.execute("SELECT * FROM items")}
    vid = rows["v1"]["id"]
    assert rows["v1"]["role"] == "primary" and rows["v1"]["status"] == "pending_ai"
    assert rows["b1"]["role"] == "alt" and rows["b1"]["group_id"] == vid
    assert rows["s1"]["role"] == "note" and rows["s1"]["group_id"] == vid
    pending = conn.execute("SELECT COUNT(*) FROM items WHERE status = 'pending_ai'").fetchone()[0]
    assert pending == 1, "묶음은 AI 처리를 한 번만 한다"


def test_exact_duplicate_across_sources(conn, settings):
    people = load_people(FIX / "sources.yaml", settings=settings)
    person = people[0]
    ids = sync_config(conn, people)
    keys = {s.type: s.key for s in person.sources if s.url}
    text = ["same body " * 20]
    a = _item(keys["rss"], "blog", external_id="a", url="https://blog.example.com/x", paragraphs=text)
    b = _item(keys["rss"], "blog", external_id="b", url="https://substack.example.com/x", paragraphs=text)
    assert store_item(conn, a, source_id=ids[keys["rss"]], person=person, settings=settings) == "new"
    assert store_item(conn, b, source_id=ids[keys["rss"]], person=person, settings=settings) == "dup"


# ── 한 회차 전체 ──

def test_run_once_end_to_end(conn, settings):
    people = load_people(FIX / "sources.yaml", settings=settings)
    client = httpx.Client(transport=feeds_transport({
        "https://blog.example.com/feed.xml": "blog.xml",
        "https://www.youtube.com/feeds/videos.xml": "youtube.xml",
        "https://bsky.app/profile/example.bsky.social/rss": "bluesky.xml",
    }))
    stats = run_once(ai=True, conn=conn, settings=settings, people=people, client=client)
    assert stats["errors"] == 0
    assert stats["fetched_sources"] == 3

    rows = {r["external_id"]: dict(r) for r in conn.execute("SELECT * FROM items")}
    video = rows["abc123XYZ"]
    blog = rows["https://blog.example.com/eval-harness/"]
    note = rows["at://did:plc:x/app.bsky.feed.post/3aaa"]
    short = rows["at://did:plc:x/app.bsky.feed.post/3bbb"]
    held = rows["at://did:plc:x/app.bsky.feed.post/3ccc"]

    assert video["kind"] == "video" and video["role"] == "primary"
    assert blog["role"] == "alt" and blog["group_id"] == video["id"]
    assert note["role"] == "note" and note["group_id"] == video["id"]
    assert short["kind"] == "short" and short["status"] == "pending_ai"
    assert held["status"] == "held"
    assert "old" not in rows or rows["old"]["published_at"] < "2025"
    assert json.loads(blog["paragraphs_json"])[0].startswith("First paragraph")

    # 두 번째 회차: 새 글 없음, 보류 글은 기다림이 끝나 따로 카드가 된다
    stats2 = run_once(ai=False, conn=conn, settings=settings, people=people, client=client)
    assert stats2["new_items"] == 0
    status = conn.execute("SELECT status FROM items WHERE external_id = ?",
                          ("at://did:plc:x/app.bsky.feed.post/3ccc",)).fetchone()[0]
    assert status == "pending_ai"

    src = conn.execute("SELECT last_error, last_success_at FROM sources WHERE type = 'rss' AND url != ''").fetchone()
    assert src["last_error"] is None and src["last_success_at"]


def test_fetch_error_recorded(conn, settings):
    people = load_people(FIX / "sources.yaml", settings=settings)
    client = httpx.Client(transport=feeds_transport({}))
    stats = run_once(ai=False, conn=conn, settings=settings, people=people, client=client)
    assert stats["errors"] == 3
    errs = [r[0] for r in conn.execute("SELECT last_error FROM sources WHERE enabled = 1")]
    assert all(e == "HTTP 404" for e in errs)
