"""Nexus chat provider clients."""

from typing import Any

from nexus.runtime.providers.base import ChatClient
from nexus.runtime.providers.groq import GroqChatClient
from nexus.runtime.providers.nim import NimChatClient
from nexus.runtime.providers.openrouter import OpenRouterChatClient

__all__ = [
    "ChatClient",
    "NimChatClient",
    "OpenRouterChatClient",
    "GroqChatClient",
]


def create_client(provider: str, cfg: Any) -> ChatClient:
    """Factory: create the appropriate chat client for a provider name."""
    p = (provider or "nim").strip().lower()
    if p == "nim":
        return NimChatClient.from_config(cfg)
    if p == "openrouter":
        return OpenRouterChatClient.from_config(cfg)
    if p == "groq":
        return GroqChatClient.from_config(cfg)
    raise ValueError(f"Unknown provider: {provider!r}")
