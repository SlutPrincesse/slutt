"""
Local inference bridge using llama-server HTTP API
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx


class LocalInference:
    def __init__(self, base_url: str = "http://localhost:8080/v1"):
        self.base_url = base_url
        self.client: httpx.AsyncClient | None = None

    async def ensure_client(self):
        if self.client is None:
            self.client = httpx.AsyncClient(base_url=self.base_url, timeout=300.0)
        return self.client

    async def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7, max_tokens: int = 2048) -> str:
        c = await self.ensure_client()
        try:
            r = await c.post("/chat/completions", json={
                "model": "local",
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            })
            r.raise_for_status()
            data = r.json()
            return data["choices"][0]["message"]["content"]
        except Exception as e:
            return f"ERR:{e}"

    async def complete(self, prompt: str, **kw) -> str:
        return await self.chat([{"role": "user", "content": prompt}], **kw)


async def get_local_inference(base_url: Optional[str] = None) -> LocalInference:
    url = base_url or os.getenv("LOCAL_LLM_BASE_URL") or "http://localhost:8080/v1"
    return LocalInference(url)
