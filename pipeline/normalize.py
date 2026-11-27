"""피드 항목을 공통 Item 형태로 바꾼다."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from bs4 import BeautifulSoup

TRACKING_PARAMS = re.compile(r"^(utm_|ref$|ref_src$|s$|si$|fbclid$|gclid$|mc_|source$)")
URL_RE = re.compile(r"https?://[^\s<>\"')\]]+")


@dataclass
class Item:
    source_key: str
    person: str
    field: str
    platform: str            # blog | sns | video
    external_id: str
    url: str
    published_at: datetime
    title: str
    paragraphs: list[str]
    media: list[str] = field(default_factory=list)
    links: list[str] = field(default_factory=list)
    duration_seconds: int | None = None

    @property
    def text(self) -> str:
        return "\n\n".join(self.paragraphs)

    @property
    def canonical_url(self) -> str:
        return canonical_url(self.url)

    @property
    def content_hash(self) -> str:
        norm = re.sub(r"\s+", " ", self.text).strip().lower()
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:32]


def canonical_url(url: str) -> str:
    """추적 파라미터, 프래그먼트, 끝 슬래시, www를 없앤 비교용 URL."""
    if not url:
        return ""
    parts = urlsplit(url.strip())
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host in {"youtu.be"}:
        vid = parts.path.strip("/")
        return f"https://youtube.com/watch?v={vid}"
    if host in {"m.youtube.com", "music.youtube.com"}:
        host = "youtube.com"
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
             if not TRACKING_PARAMS.match(k.lower())]
    if host == "youtube.com":
        query = [(k, v) for k, v in query if k == "v"]
    path = parts.path.rstrip("/") or "/"
    return urlunsplit(("https", host, path, urlencode(sorted(query)), ""))


def html_to_paragraphs(html: str) -> tuple[list[str], list[str], list[str]]:
    """HTML을 (문단 목록, 이미지 URL, 링크 URL)로 나눈다."""
    if not html:
        return [], [], []
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style", "iframe", "noscript"]):
        tag.decompose()
    images = [img.get("src") for img in soup.find_all("img") if img.get("src")]
    links = [a.get("href") for a in soup.find_all("a") if (a.get("href") or "").startswith("http")]
    blocks = soup.find_all(["p", "li", "h1", "h2", "h3", "h4", "blockquote", "pre"])
    paragraphs: list[str] = []
    if blocks:
        for b in blocks:
            if b.find_parent(["li", "blockquote"]) and b.name == "p":
                continue  # 목록·인용 안의 p는 바깥 블록에서 한 번만
            text = b.get_text(" " if b.name != "pre" else "", strip=b.name != "pre")
            text = text if b.name == "pre" else re.sub(r"\s+", " ", text).strip()
            if text:
                paragraphs.append(("• " + text) if b.name == "li" else text)
    else:
        text = soup.get_text("\n")
        paragraphs = [re.sub(r"[ \t]+", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
        paragraphs = [p for p in paragraphs if p]
    for p in paragraphs:
        for u in URL_RE.findall(p):
            if u not in links:
                links.append(u)
    return paragraphs, images, links


def parse_time(value) -> datetime:
    """feedparser의 struct_time 또는 None을 UTC datetime으로."""
    if value is None:
        return datetime.now(timezone.utc)
    return datetime(*value[:6], tzinfo=timezone.utc)
