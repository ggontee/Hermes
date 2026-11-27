"""유형 분류 (dev-spec 5장, 결정 7).

- YouTube → video
- 블로그·뉴스레터 → 길이와 상관없이 long
- SNS → 원문 short_max_chars(기본 500자) 이하 short, 넘으면 long
"""
from __future__ import annotations

import re

URL_RE = re.compile(r"https?://\S+")


def sns_length(text: str) -> int:
    """SNS 길이: 링크는 한 글자로 센다 (긴 URL 때문에 long이 되지 않게)."""
    return len(URL_RE.sub("·", text).strip())


def classify(platform: str, text: str, short_max_chars: int = 500) -> str:
    if platform == "video":
        return "video"
    if platform == "blog":
        return "long"
    if platform == "sns":
        return "short" if sns_length(text) <= short_max_chars else "long"
    raise ValueError(f"unknown platform {platform!r}")
