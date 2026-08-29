from __future__ import annotations

import os
from typing import Any


def adapter_from_env() -> Any | None:
    if os.environ.get("ANTHROPIC_API_KEY"):
        from nexus.browser.adapters.anthropic import AnthropicAdapter

        return AnthropicAdapter()
    if os.environ.get("OPENAI_API_KEY") or os.environ.get("OPENAI_BASE_URL"):
        from nexus.browser.adapters.openai import OpenAIAdapter

        return OpenAIAdapter(base_url=os.environ.get("OPENAI_BASE_URL"))
    if os.environ.get("GEMINI_API_KEY"):
        from nexus.browser.adapters.gemini import GeminiAdapter

        return GeminiAdapter()
    return None
