"""Base protocol and shared helpers for Nexus chat providers."""

from __future__ import annotations

import os
from typing import Any


def first_env(*names: str) -> str | None:
    for n in names:
        v = os.getenv(n)
        if v and v.strip():
            return v.strip()
    return None


def extract_finish_reason(resp: dict[str, Any]) -> str | None:
    try:
        choices = resp.get("choices")
        if not isinstance(choices, list) or not choices:
            return None
        c0 = choices[0] if isinstance(choices[0], dict) else None
        if not isinstance(c0, dict):
            return None
        fr = c0.get("finish_reason") or c0.get("stop_reason") or c0.get("finishReason")
        return fr.strip() if isinstance(fr, str) and fr.strip() else None
    except Exception:
        return None


def fetch_openai_models(
    *,
    base_url: str,
    headers: dict[str, str],
    timeout_s: float,
) -> list[dict[str, Any]]:
    import urllib.request

    url = base_url.rstrip("/") + "/models"
    req = urllib.request.Request(url, method="GET")
    for k, v in headers.items():
        req.add_header(k, v)
    with urllib.request.urlopen(req, timeout=float(timeout_s)) as resp:
        raw = resp.read()
        data = __import__("json").loads(raw.decode("utf-8"))
    items = data.get("data")
    if not isinstance(items, list):
        return []
    return [m for m in items if isinstance(m, dict)]


def model_ids_from_entries(models: list[dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for m in models:
        mid = m.get("id")
        if isinstance(mid, str) and mid.strip():
            ids.append(mid.strip())
    return sorted(set(ids), key=str.lower)


def build_chat_payload(
    *,
    model: str,
    messages: list[dict[str, Any]],
    temperature: float,
    max_tokens: int,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": str(model),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    if tools:
        payload["tools"] = tools
        payload["tool_choice"] = "auto"
    return payload


def extract_chat_text(resp: dict[str, Any]) -> str:
    choices = resp.get("choices")
    if not isinstance(choices, list) or not choices:
        raise RuntimeError("Unexpected response: missing choices")
    msg = choices[0].get("message") if isinstance(choices[0], dict) else None
    if not isinstance(msg, dict):
        raise RuntimeError("Unexpected response: missing message")
    content = msg.get("content")
    if content is None:
        tool_calls = msg.get("tool_calls")
        if tool_calls:
            return "[tool call requested; tool execution not implemented in nexus yet]"
        return ""
    if not isinstance(content, str):
        return str(content)
    return content


class ChatClient:
    """Protocol/interface for chat provider clients."""

    def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        temperature: float,
        max_tokens: int,
        tools: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        ...

    def extract_text(self, resp: dict[str, Any]) -> str:
        ...
