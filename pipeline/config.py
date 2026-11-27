"""설정 읽기: config/settings.yaml, config/sources.yaml, config/glossary.yaml.

환경변수 HERMES_<KEY>(최상위 키만)가 settings.yaml 값보다 우선한다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = Path(os.environ.get("HERMES_CONFIG_DIR", REPO_ROOT / "config"))

SOURCE_TYPES = {"rss", "youtube", "bluesky", "rsshub", "x"}
FIELDS = {"AI", "Tech", "Bio"}


@dataclass(frozen=True)
class Source:
    key: str                 # 안정적인 ID: "<사람 slug>:<type>:<주소>"
    person: str
    field: str
    type: str
    url: str                 # 실제로 여는 피드 주소
    handle: str | None
    enabled: bool
    note: str | None = None

    @property
    def platform(self) -> str:
        """분류용 플랫폼: blog(긴 글), sns(길이로 판단), video."""
        if self.type == "youtube":
            return "video"
        if self.type in {"bluesky", "x"}:
            return "sns"
        return "blog"


@dataclass(frozen=True)
class Person:
    name: str
    field: str
    affiliation: str | None
    sources: tuple[Source, ...] = field(default_factory=tuple)


def slugify(text: str) -> str:
    out = []
    for ch in text.lower():
        if ch.isalnum():
            out.append(ch)
        elif out and out[-1] != "-":
            out.append("-")
    return "".join(out).strip("-")


def load_settings(path: Path | None = None) -> dict[str, Any]:
    path = path or CONFIG_DIR / "settings.yaml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for key in list(data):
        env = os.environ.get(f"HERMES_{key.upper()}")
        if env is not None and not isinstance(data[key], (dict, list)):
            data[key] = env
    return data


def _feed_url(raw: dict[str, Any], rsshub_base: str) -> str | None:
    t = raw.get("type")
    if t == "rss":
        url = raw.get("url")
        return None if not url or url == "TODO" else url
    if t == "youtube":
        cid = raw.get("channel_id")
        if not cid or cid == "TODO":
            return None
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"
    if t == "bluesky":
        handle = raw.get("handle")
        if not handle or handle == "TODO":
            return None
        return f"https://bsky.app/profile/{handle}/rss"
    if t == "x":
        handle = raw.get("handle")
        return f"{rsshub_base.rstrip('/')}/twitter/user/{handle}" if handle else None
    if t == "rsshub":
        route = raw.get("route")
        return f"{rsshub_base.rstrip('/')}/{route.lstrip('/')}" if route else None
    return None


def load_people(path: Path | None = None, settings: dict[str, Any] | None = None) -> list[Person]:
    """sources.yaml을 읽는다. 주소가 TODO인 소스는 enabled=False로 둔다."""
    path = path or CONFIG_DIR / "sources.yaml"
    settings = settings or load_settings()
    rsshub_base = settings.get("rsshub", {}).get("base_url", "http://127.0.0.1:1200")
    raw_people = yaml.safe_load(path.read_text(encoding="utf-8")) or []
    people: list[Person] = []
    seen: set[str] = set()
    for p in raw_people:
        name = p["name"]
        fld = p.get("field")
        if fld not in FIELDS:
            raise ValueError(f"{name}: field must be one of {sorted(FIELDS)}, got {fld!r}")
        sources = []
        for raw in p.get("sources", []):
            t = raw.get("type")
            if t not in SOURCE_TYPES:
                raise ValueError(f"{name}: unknown source type {t!r}")
            url = _feed_url(raw, rsshub_base)
            enabled = bool(raw.get("enabled", True)) and url is not None
            ident = raw.get("url") or raw.get("channel_id") or raw.get("handle") or raw.get("route") or "todo"
            key = f"{slugify(name)}:{t}:{ident}"
            if key in seen:
                raise ValueError(f"duplicate source {key}")
            seen.add(key)
            sources.append(Source(key=key, person=name, field=fld, type=t, url=url or "",
                                  handle=raw.get("handle"), enabled=enabled, note=raw.get("note")))
        people.append(Person(name=name, field=fld, affiliation=p.get("affiliation"), sources=tuple(sources)))
    return people


def load_glossary(path: Path | None = None) -> dict[str, Any]:
    path = path or CONFIG_DIR / "glossary.yaml"
    return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
