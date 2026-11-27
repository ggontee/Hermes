"""소스 하나를 열어 Item 목록으로 돌려준다.

모든 소스는 RSS/Atom이다 (원본 피드, YouTube 채널 피드, Bluesky 공식 피드, RSSHub).
형식별 차이는 entry → Item 변환에서만 다룬다.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import feedparser
import httpx

from ..config import Source
from ..normalize import Item, html_to_paragraphs, parse_time


class FetchError(Exception):
    pass


def fetch_feed(url: str, *, timeout: float, user_agent: str, client: httpx.Client | None = None) -> bytes:
    own = client is None
    client = client or httpx.Client(follow_redirects=True, timeout=timeout,
                                    headers={"User-Agent": user_agent})
    try:
        r = client.get(url)
    except httpx.HTTPError as e:
        raise FetchError(f"{type(e).__name__}: {e}") from e
    finally:
        if own:
            client.close()
    if r.status_code != 200:
        raise FetchError(f"HTTP {r.status_code}")
    return r.content


def parse_entries(source: Source, body: bytes) -> list[Item]:
    feed = feedparser.parse(body)
    if feed.bozo and not feed.entries:
        raise FetchError(f"parse error: {feed.bozo_exception}")
    items = []
    for e in feed.entries:
        item = _entry_to_item(source, e)
        if item is not None:
            items.append(item)
    return items


def _entry_html(e) -> str:
    if e.get("content"):
        return max((c.get("value", "") for c in e.content), key=len)
    return e.get("summary", "") or e.get("description", "")


def _entry_to_item(source: Source, e) -> Item | None:
    link = e.get("link") or ""
    ext_id = e.get("yt_videoid") or e.get("id") or link
    if not ext_id:
        return None
    published = parse_time(e.get("published_parsed") or e.get("updated_parsed"))
    title = (e.get("title") or "").strip()

    if source.type == "youtube":
        desc = ""
        if e.get("media_group"):
            desc = e.get("media_description", "")
        desc = desc or e.get("summary", "")
        paragraphs = [p.strip() for p in desc.split("\n\n") if p.strip()]
        thumbs = [t.get("url") for t in e.get("media_thumbnail", []) if t.get("url")]
        if not thumbs and e.get("yt_videoid"):
            thumbs = [f"https://i.ytimg.com/vi/{e.yt_videoid}/hqdefault.jpg"]
        return Item(source_key=source.key, person=source.person, field=source.field,
                    platform="video", external_id=str(ext_id), url=link, published_at=published,
                    title=title, paragraphs=paragraphs, media=thumbs, links=[])

    paragraphs, images, links = html_to_paragraphs(_entry_html(e))
    if source.platform == "sns":
        # Bluesky·X 피드의 title은 본문 앞부분을 반복하는 경우가 많다
        title = ""
        if not paragraphs and e.get("title"):
            paragraphs = [e.title.strip()]
    return Item(source_key=source.key, person=source.person, field=source.field,
                platform=source.platform, external_id=str(ext_id), url=link, published_at=published,
                title=title, paragraphs=paragraphs, media=images, links=links)


def collect(source: Source, *, since: datetime | None, settings: dict, client: httpx.Client | None = None) -> list[Item]:
    """소스 하나를 수집한다. since 이후 글만, 최신순으로 상한까지."""
    c = settings.get("collect", {})
    body = fetch_feed(source.url, timeout=c.get("timeout_seconds", 20),
                      user_agent=c.get("user_agent", "HermesFeedReader/0.1"), client=client)
    items = parse_entries(source, body)
    if since is None:
        since = datetime.now(timezone.utc) - timedelta(hours=c.get("first_run_lookback_hours", 72))
    items = [i for i in items if i.published_at > since]
    items.sort(key=lambda i: i.published_at, reverse=True)
    return items[: c.get("max_items_per_source", 20)]
