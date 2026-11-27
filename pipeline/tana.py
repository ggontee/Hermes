"""Tana 원격 MCP 클라이언트 (심화 분석 결과를 #Research 노드로 저장).

Octopus gateway/src/tana.ts와 같은 방식이다.
- 토큰은 Secrets Manager `hermes/tana-token`에 JSON으로 있다. 받는 법은 Octopus의
  `scripts/oauth-capture.ts tana --secret hermes/tana-token`.
- 액세스 토큰은 1시간이다. 만료 5분 전이면 refresh_token으로 갱신하고, 새 값을 같은 비밀에 다시 쓴다.
- 노드 내용은 로그·오류에 남기지 않는다.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Protocol

import httpx

TANA_MCP_URL = "https://app.tana.inc/mcp"
REFRESH_MARGIN = timedelta(minutes=5)
TIMEOUT = 20.0


class TanaError(Exception):
    pass


class AuthError(TanaError):
    pass


# ── 토큰 저장소 ──

class TokenStore(Protocol):
    def read(self) -> str: ...
    def write(self, value: str) -> None: ...


class FileStore:
    """개발·테스트용."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def read(self) -> str:
        return self.path.read_text(encoding="utf-8")

    def write(self, value: str) -> None:
        self.path.write_text(value, encoding="utf-8")
        os.chmod(self.path, 0o600)


class SecretsManagerStore:
    """AWS CLI로 읽고 쓴다(새 의존성 없이). 값은 표준 입력으로 넘겨 프로세스 목록에 드러나지 않게 한다."""

    def __init__(self, secret_id: str, aws: str | None = None):
        self.secret_id = secret_id
        self.aws = aws or shutil.which("aws") or "/snap/bin/aws"

    def read(self) -> str:
        r = subprocess.run([self.aws, "secretsmanager", "get-secret-value", "--secret-id", self.secret_id,
                            "--query", "SecretString", "--output", "text"], capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise TanaError(f"토큰 읽기 실패 ({self.secret_id}, exit {r.returncode})")
        return r.stdout.strip()

    def write(self, value: str) -> None:
        r = subprocess.run([self.aws, "secretsmanager", "put-secret-value", "--secret-id", self.secret_id,
                            "--secret-string", "file:///dev/stdin"], input=value, capture_output=True, text=True, timeout=30)
        if r.returncode != 0:
            raise TanaError(f"토큰 쓰기 실패 ({self.secret_id}, exit {r.returncode})")


def store_from_settings(settings: dict) -> TokenStore:
    path = os.environ.get("HERMES_TANA_TOKEN_FILE")
    if path:
        return FileStore(path)
    return SecretsManagerStore(settings.get("tana", {}).get("token_secret", "hermes/tana-token"))


# ── 인증 ──

@dataclass
class TanaToken:
    access_token: str
    refresh_token: str
    client_id: str
    token_endpoint: str
    resource: str
    expires_at: str | None = None
    scope: str | None = None

    @classmethod
    def parse(cls, text: str) -> "TanaToken":
        try:
            v = json.loads(text)
        except json.JSONDecodeError:
            raise TanaError("tana token: JSON이 아니다") from None
        for k in ("access_token", "refresh_token", "client_id", "token_endpoint", "resource"):
            if not isinstance(v.get(k), str) or not v[k]:
                raise TanaError(f"tana token: {k}가 없다")
        return cls(**{k: v.get(k) for k in cls.__dataclass_fields__})

    def dumps(self) -> str:
        return json.dumps(self.__dict__)


class TanaAuth:
    def __init__(self, store: TokenStore, client: httpx.Client, now: Callable[[], datetime] | None = None):
        self.store = store
        self.client = client
        self.now = now or (lambda: datetime.now(timezone.utc))
        self.token: TanaToken | None = None

    def _fresh(self, t: TanaToken) -> bool:
        if not t.expires_at:
            return True
        exp = datetime.fromisoformat(t.expires_at.replace("Z", "+00:00"))
        return exp - self.now() > REFRESH_MARGIN

    def access_token(self, force: bool = False) -> str:
        if self.token is None:
            self.token = TanaToken.parse(self.store.read())
        if force or not self._fresh(self.token):
            self.token = self._refresh()
        return self.token.access_token

    def _refresh(self) -> TanaToken:
        # 다른 곳(재인증)에서 비밀을 바꿨을 수 있으니 다시 읽는다.
        cur = TanaToken.parse(self.store.read())
        if self._fresh(cur) and self.token and cur.access_token != self.token.access_token:
            return cur
        r = self.client.post(cur.token_endpoint, data={
            "grant_type": "refresh_token", "refresh_token": cur.refresh_token,
            "client_id": cur.client_id, "resource": cur.resource,
        }, headers={"accept": "application/json"}, timeout=TIMEOUT)
        try:
            body = r.json()
        except ValueError:
            body = {}
        if r.status_code != 200 or not body.get("access_token"):
            raise TanaError(f"tana token refresh HTTP {r.status_code} {body.get('error', '')}".strip())
        exp = body.get("expires_in")
        nxt = TanaToken(
            access_token=body["access_token"],
            refresh_token=body.get("refresh_token") or cur.refresh_token,
            client_id=cur.client_id, token_endpoint=cur.token_endpoint, resource=cur.resource,
            expires_at=(self.now() + timedelta(seconds=int(exp))).isoformat() if exp else None,
            scope=body.get("scope") or cur.scope,
        )
        self.store.write(nxt.dumps())
        return nxt


# ── MCP 호출 ──

def rpc_result(text: str, content_type: str) -> dict:
    """Streamable HTTP 응답(JSON 또는 SSE)에서 JSON-RPC result를 꺼낸다."""
    if "text/event-stream" in content_type:
        payloads = [ln[5:].strip() for ln in text.splitlines() if ln.startswith("data:")]
    else:
        payloads = [text]
    for p in filter(None, payloads):
        msg = json.loads(p)
        if msg.get("error"):
            err = msg["error"]
            raise TanaError(f"tana mcp error {err.get('code', '')}: {str(err.get('message', ''))[:200]}")
        if "result" in msg:
            return msg["result"]
    raise TanaError("tana mcp: result가 없다")


class TanaMCP:
    def __init__(self, auth: TanaAuth, client: httpx.Client, url: str = TANA_MCP_URL):
        self.auth = auth
        self.client = client
        self.url = url
        self.session_id: str | None = None
        self._id = 0

    def _post(self, body: dict, token: str) -> httpx.Response:
        headers = {"authorization": f"Bearer {token}", "content-type": "application/json",
                   "accept": "application/json, text/event-stream"}
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        r = self.client.post(self.url, json=body, headers=headers, timeout=TIMEOUT)
        if r.status_code == 401:
            raise AuthError("tana mcp HTTP 401")
        return r

    def _next(self) -> int:
        self._id += 1
        return self._id

    def _initialize(self, token: str) -> None:
        self.session_id = None
        r = self._post({"jsonrpc": "2.0", "id": self._next(), "method": "initialize", "params": {
            "protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "hermes", "version": "1"}}}, token)
        if r.status_code != 200:
            raise TanaError(f"tana mcp initialize HTTP {r.status_code}")
        rpc_result(r.text, r.headers.get("content-type", ""))
        self.session_id = r.headers.get("mcp-session-id")
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"}, token)

    def _call_once(self, name: str, args: dict, token: str) -> str:
        if not self.session_id:
            self._initialize(token)
        body = {"jsonrpc": "2.0", "id": self._next(), "method": "tools/call", "params": {"name": name, "arguments": args}}
        r = self._post(body, token)
        if r.status_code in (400, 404):  # MCP 세션이 끝났다. 다시 연다.
            self._initialize(token)
            body["id"] = self._next()
            r = self._post(body, token)
        if r.status_code != 200:
            raise TanaError(f"tana mcp {name} HTTP {r.status_code}")
        result = rpc_result(r.text, r.headers.get("content-type", ""))
        out = "\n".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
        if result.get("isError"):
            raise TanaError(f"tana {name} 실패: {out[:160]}")
        return out

    def call(self, name: str, args: dict) -> str:
        try:
            return self._call_once(name, args, self.auth.access_token())
        except AuthError:
            self.session_id = None
            return self._call_once(name, args, self.auth.access_token(force=True))

    def import_paste(self, parent_node_id: str, content: str) -> str:
        return self.call("import_tana_paste", {"parentNodeId": parent_node_id, "content": content})


def connect(settings: dict, client: httpx.Client | None = None) -> TanaMCP:
    client = client or httpx.Client()
    url = settings.get("tana", {}).get("mcp_url", TANA_MCP_URL)
    return TanaMCP(TanaAuth(store_from_settings(settings), client), client, url)


def created_node_id(out: str) -> str:
    """import_tana_paste 결과에서 처음 만든 노드 ID. 형식(Octopus 2026-11-12 확인):
    Created nodes:\\n- <ID> ("이름")"""
    parts = re.split(r"Created nodes:", out, flags=re.I)
    if len(parts) > 1:
        m = re.search(r"^\s*-\s+([A-Za-z0-9_-]{6,40})\s*\(", parts[1], re.M)
        if m:
            return m.group(1)
    m = re.search(r"node-id:\s*([A-Za-z0-9_-]{6,40})", out) or re.search(r'"id"\s*:\s*"([A-Za-z0-9_-]{6,40})"', out)
    return m.group(1) if m else ""


# ── Tana Paste 만들기 ──

def _plain(s: str) -> str:
    """Tana Paste 문법으로 읽히지 않게 한다: #태그, 필드(::), [[참조]], 앞의 '- '."""
    s = s.replace("::", ":").replace("[[", "[ [").replace("]]", "] ]")
    s = re.sub(r"#(?=\S)", "＃", s)
    return s.strip()


def md_to_nodes(md: str) -> list[tuple[int, str]]:
    """Markdown을 (깊이, 글) 목록으로. 제목은 굵게, 목록은 들여쓰기만큼 깊게."""
    out: list[tuple[int, str]] = []
    under_heading = False
    for raw in md.splitlines():
        if not raw.strip():
            continue
        h = re.match(r"^\s*#{1,6}\s+(.*)$", raw)
        li = re.match(r"^(\s*)(?:[-*+]|\d+[.)])\s+(.*)$", raw)
        if h:
            out.append((0, f"**{_plain(h.group(1))}**"))
            under_heading = True
        elif li:
            depth = len(li.group(1).expandtabs(2)) // 2 + (1 if under_heading else 0)
            out.append((depth, _plain(li.group(2))))
        else:
            out.append((1 if under_heading else 0, _plain(raw)))
    return out


def research_paste(*, title: str, topic: str, confidence: str, date: str, url: str, conclusion: str,
                   body_md: str, question: str | None, tana: dict) -> str:
    tag = tana.get("tag", "Research")
    f = {"topic": "Topic", "date": "작성일", "confidence": "신뢰도", **tana.get("fields", {})}
    lines = ["%%tana%%", f"- {_plain(title)} #[[{tag}]]"]
    lines.append(f"  - {f['topic']}:: {_plain(topic)}")
    lines.append(f"  - {f['date']}:: [[date:{date}]]")
    lines.append(f"  - {f['confidence']}:: {_plain(confidence)}")
    lines.append(f"  - 원문: {url}")
    if question:
        lines.append(f"  - 질문: {_plain(question)}")
    lines.append(f"  - **결론** {_plain(conclusion)}")
    for depth, text in md_to_nodes(body_md):
        lines.append(f"{'  ' * (depth + 1)}- {text}")
    return "\n".join(lines) + "\n"
