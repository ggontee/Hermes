"""Claude와 Gemini 호출. 모든 Claude 응답은 JSON 스키마로 고정한다(output_config.format).

비밀값은 환경변수로만 받는다: ANTHROPIC_API_KEY, GEMINI_API_KEY.
로그에는 모델, 토큰 수, 상태만 남긴다. 원문과 응답 본문은 남기지 않는다.
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from pathlib import Path

import httpx
import yaml

log = logging.getLogger(__name__)

PROMPTS = Path(__file__).parent / "prompts"
FALLBACK_BETA = "server-side-fallback-2026-07-01"
GEMINI_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/models"


class LLMError(Exception):
    """이 항목만 실패로 두고 다음 항목으로 넘어가면 되는 오류."""


class Refused(LLMError):
    pass


class Truncated(LLMError):
    pass


class NotConfigured(Exception):
    """키가 없다. 회차 전체에서 해당 처리를 건너뛴다."""


@dataclass
class Usage:
    model: str
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0

    def add(self, other: "Usage") -> "Usage":
        return Usage(self.model if self.model == other.model else f"{self.model}+{other.model}",
                     self.tokens_in + other.tokens_in, self.tokens_out + other.tokens_out,
                     self.cost_usd + other.cost_usd)


def prompt(name: str) -> str:
    return (PROMPTS / f"{name}.md").read_text(encoding="utf-8").strip()


def system_prompt(glossary: dict) -> str:
    g = yaml.safe_dump(glossary, allow_unicode=True, sort_keys=False).strip()
    return prompt("common").replace("{glossary}", g)


def price(settings: dict, model: str, tokens_in: int, tokens_out: int) -> float:
    p = settings.get("pricing", {}).get(model)
    if not p:
        return 0.0
    return tokens_in / 1e6 * p["input"] + tokens_out / 1e6 * p["output"]


class Claude:
    """client는 테스트에서 가짜로 바꿔 끼울 수 있다 (client.beta.messages.create만 쓴다)."""

    def __init__(self, settings: dict, glossary: dict, client=None):
        self.settings = settings
        self.system = system_prompt(glossary)
        if client is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                raise NotConfigured("ANTHROPIC_API_KEY 없음")
            import anthropic
            client = anthropic.Anthropic(max_retries=3, timeout=600)
        self.client = client

    def json(self, *, model: str, instruction: str, content: str, schema: dict,
             max_tokens: int, effort: str = "medium") -> tuple[dict, Usage]:
        """지시 + 입력을 보내고 schema에 맞는 JSON을 돌려받는다. JSON이 깨지면 한 번 다시 묻는다."""
        last_err: Exception | None = None
        total = Usage(model)
        for attempt in range(2):
            resp = self._create(model=model, max_tokens=max_tokens, effort=effort, schema=schema,
                                user=f"{instruction}\n\n{content}")
            u = resp.usage
            used = Usage(model, u.input_tokens, u.output_tokens,
                         price(self.settings, model, u.input_tokens, u.output_tokens))
            total = total.add(used) if attempt else used
            if resp.stop_reason == "refusal":
                cat = getattr(getattr(resp, "stop_details", None), "category", None)
                raise Refused(f"refusal ({cat})")
            if resp.stop_reason == "max_tokens":
                raise Truncated(f"max_tokens {max_tokens}")
            text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "")
            try:
                data = json.loads(text)
                _check_required(data, schema)
                return data, total
            except (json.JSONDecodeError, ValueError) as e:
                last_err = e
                log.warning("JSON 검증 실패 (%s), 다시 묻는다", type(e).__name__)
        raise LLMError(f"JSON 검증 실패: {last_err}")

    def _create(self, *, model, max_tokens, effort, schema, user):
        return self.client.beta.messages.create(
            model=model,
            max_tokens=max_tokens,
            system=self.system,
            messages=[{"role": "user", "content": user}],
            output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}},
            betas=[FALLBACK_BETA],
            fallbacks="default",   # 지원하지 않는 모델(Haiku)에서는 그 모델로만 돈다
        )


def _check_required(data, schema: dict) -> None:
    if schema.get("type") == "object":
        if not isinstance(data, dict):
            raise ValueError("object 아님")
        for k in schema.get("required", []):
            if k not in data:
                raise ValueError(f"필드 없음: {k}")


class Gemini:
    """YouTube 받아쓰기. Octopus gateway/src/gemini.ts와 같은 방식(generateContent + fileData)."""

    def __init__(self, settings: dict, client: httpx.Client | None = None):
        self.settings = settings
        self.key = os.environ.get("GEMINI_API_KEY")
        if not self.key:
            raise NotConfigured("GEMINI_API_KEY 없음")
        self.client = client or httpx.Client(timeout=600)
        self.model = settings.get("models", {}).get("transcribe", "gemini-3.5-flash-lite")

    def transcribe(self, video_url: str) -> tuple[str, bool, Usage]:
        """(받아쓴 글, 잘림 여부, 사용량). 앞 max_minutes분만 받아쓴다."""
        v = self.settings.get("video", {})
        max_minutes = int(v.get("max_minutes", 180))
        body = {
            "contents": [{"role": "user", "parts": [
                {"fileData": {"fileUri": video_url}, "videoMetadata": {"endOffset": f"{max_minutes * 60}s"}},
                {"text": prompt("transcribe")},
            ]}],
            "generationConfig": {"mediaResolution": "MEDIA_RESOLUTION_LOW",
                                 "maxOutputTokens": int(v.get("transcript_max_tokens", 65536))},
        }
        try:
            r = self.client.post(f"{GEMINI_ENDPOINT}/{self.model}:generateContent", json=body,
                                 headers={"x-goog-api-key": self.key})
        except httpx.HTTPError as e:
            raise LLMError(f"Gemini 연결 실패: {type(e).__name__}") from e
        if r.status_code != 200:
            raise LLMError(f"Gemini HTTP {r.status_code}")
        j = r.json()
        cand = (j.get("candidates") or [{}])[0]
        parts = (cand.get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p.get("text"), str) and not p.get("thought")).strip()
        finish = cand.get("finishReason", "")
        um = j.get("usageMetadata") or {}
        tin, tout = int(um.get("promptTokenCount") or 0), int(um.get("candidatesTokenCount") or 0)
        usage = Usage(self.model, tin, tout, price(self.settings, self.model, tin, tout))
        if not text:
            block = (j.get("promptFeedback") or {}).get("blockReason")
            raise LLMError(f"Gemini 빈 응답 ({block or finish or '이유 없음'})")
        return text, finish == "MAX_TOKENS", usage
