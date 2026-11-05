"""Model proxy: audit any RAG app, in any language, by pointing its model base URL here.

    OpenAI-compatible:  base_url = http://127.0.0.1:8100/proxy/openai/v1
    Anthropic:          base_url = http://127.0.0.1:8100/proxy/anthropic

Each request is forwarded unchanged to the real API (WITTGENSTEIN_OPENAI_UPSTREAM,
default https://api.openai.com -- or any OpenAI-compatible server: Ollama, vLLM,
LM Studio, LiteLLM; WITTGENSTEIN_ANTHROPIC_UPSTREAM, default https://api.anthropic.com),
and the response, streamed or not, is returned to the app as it arrives. Only after the
response is complete is the request read for a question and retrieved passages
(live/prompt_parse.py) and, if it has them, checked in a background thread and
recorded in the local audit feed. The app never waits on the check.

The app's own API key passes through to the upstream and is never stored or logged.
Requests are accepted only from this machine. Headers starting with X-Wittgenstein-
are not forwarded (X-Wittgenstein-Source names the app in the feed).
"""

from __future__ import annotations

import json
import logging
import os
import threading
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from wittgenstein.live.audit_log import audit_log
from wittgenstein.live.prompt_parse import ParsedRequest, parse

log = logging.getLogger("wittgenstein.proxy")
router = APIRouter(prefix="/proxy", tags=["proxy"])

UPSTREAMS = {
    "openai": ("WITTGENSTEIN_OPENAI_UPSTREAM", "https://api.openai.com"),
    "anthropic": ("WITTGENSTEIN_ANTHROPIC_UPSTREAM", "https://api.anthropic.com"),
}
_LOCAL = {"127.0.0.1", "::1", "localhost", "testclient"}
_DROP_REQUEST = {"host", "content-length", "connection", "accept-encoding", "transfer-encoding", "keep-alive"}
_DROP_RESPONSE = {"content-length", "content-encoding", "transfer-encoding", "connection", "keep-alive"}

#: Swappable for tests.
client_factory: Callable[[], httpx.AsyncClient] = lambda: httpx.AsyncClient(  # noqa: E731
    timeout=httpx.Timeout(600.0, connect=10.0)
)
#: Swappable for tests (run the audit inline instead of in a thread).
run_in_background: Callable[[Callable[[], None]], None] = lambda fn: threading.Thread(  # noqa: E731
    target=fn, name="wittgenstein-proxy-audit", daemon=True
).start()


def upstream(provider: str) -> str:
    env, default = UPSTREAMS[provider]
    return os.environ.get(env, default).rstrip("/")


@router.api_route("/{provider}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE"])
async def proxy(provider: str, path: str, request: Request) -> Response:
    if (request.client.host if request.client else "") not in _LOCAL:
        raise HTTPException(403, "The model proxy only accepts requests from this machine.")
    if provider not in UPSTREAMS:
        raise HTTPException(404, f"Unknown provider {provider!r}; use one of {sorted(UPSTREAMS)}.")
    url = f"{upstream(provider)}/{path}"
    if request.url.query:
        url += f"?{request.url.query}"
    body = await request.body()
    headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() not in _DROP_REQUEST and not k.lower().startswith("x-wittgenstein")
    }
    headers["accept-encoding"] = "identity"  # pass the body through as-is
    source = request.headers.get("x-wittgenstein-source") or os.environ.get("WITTGENSTEIN_SOURCE")

    payload: dict[str, Any] | None = None
    parsed: ParsedRequest | None = None
    if request.method == "POST" and _auditable(provider, path):
        try:
            payload = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = None
        if isinstance(payload, dict):
            parsed = parse(payload.get("messages") or [], payload.get("system"))

    client = client_factory()
    try:
        resp = await client.send(
            client.build_request(request.method, url, headers=headers, content=body), stream=True
        )
    except httpx.HTTPError as e:
        await client.aclose()
        raise HTTPException(502, f"Couldn't reach {upstream(provider)}: {type(e).__name__}") from e
    out_headers = {k: v for k, v in resp.headers.items() if k.lower() not in _DROP_RESPONSE}
    streaming = bool(payload and payload.get("stream")) or "text/event-stream" in resp.headers.get(
        "content-type", ""
    )

    def audit(raw: bytes) -> None:
        if parsed is None or resp.status_code >= 300:
            return
        answer = _stream_text(provider, raw) if streaming else _response_text(provider, raw)
        if answer:
            model = payload.get("model") if payload else None
            run_in_background(lambda: _record(parsed, answer, provider, model, source))

    if streaming:

        async def relay() -> AsyncIterator[bytes]:
            chunks: list[bytes] = []
            try:
                async for chunk in resp.aiter_bytes():
                    chunks.append(chunk)
                    yield chunk
            finally:
                await resp.aclose()
                await client.aclose()
                audit(b"".join(chunks))

        return StreamingResponse(
            relay(), status_code=resp.status_code, headers=out_headers, media_type=resp.headers.get("content-type")
        )
    data = await resp.aread()
    await resp.aclose()
    await client.aclose()
    audit(data)
    return Response(
        data, status_code=resp.status_code, headers=out_headers, media_type=resp.headers.get("content-type")
    )


def _auditable(provider: str, path: str) -> bool:
    p = path.rstrip("/")
    return p.endswith("chat/completions") if provider == "openai" else p.endswith("messages")


def _response_text(provider: str, raw: bytes) -> str:
    try:
        d = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ""
    if provider == "openai":
        try:
            c = d["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return ""
        return c if isinstance(c, str) else ""
    return "".join(
        b.get("text", "") for b in d.get("content", []) if isinstance(b, dict) and b.get("type") == "text"
    )


def _stream_text(provider: str, raw: bytes) -> str:
    parts: list[str] = []
    for line in raw.decode("utf-8", errors="replace").splitlines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data or data == "[DONE]":
            continue
        try:
            ev = json.loads(data)
        except json.JSONDecodeError:
            continue
        if provider == "openai":
            for ch in ev.get("choices") or []:
                piece = (ch.get("delta") or {}).get("content")
                if isinstance(piece, str):
                    parts.append(piece)
        elif ev.get("type") == "content_block_delta":
            d = ev.get("delta") or {}
            if d.get("type") == "text_delta":
                parts.append(d.get("text", ""))
    return "".join(parts)


def _record(parsed: ParsedRequest, answer: str, provider: str, model: str | None, source: str | None) -> None:
    from wittgenstein.api.routes.live import AuditRequest, _check_one

    try:
        req = AuditRequest.model_validate(
            dict(
                query=parsed.question,
                candidates=[{"id": f"p{i + 1}", "text": t[:20_000]} for i, t in enumerate(parsed.passages[:500])],
                answer=answer[:20_000],
                pipeline={"name": f"{provider} proxy", "llm": model},
                source=source or f"{provider} proxy",
            )
        )
        report = _check_one(req)
        body = req.model_dump(exclude={"source"}, exclude_none=True)
        audit_log().add(body, report, req.source)
    except Exception as e:  # noqa: BLE001 -- an audit failure never affects the app's request
        log.warning("Wittgenstein proxy: couldn't audit a response (%s: %s)", type(e).__name__, e)


__all__ = ["router", "upstream"]
