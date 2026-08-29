"""Nexus runtime subsystem: agent loop, providers, tools, and integrations."""

from nexus.runtime.agent import AgentResult, run_agent
from nexus.runtime.providers.base import (
    ChatClient,
    build_chat_payload,
    extract_chat_text,
    extract_finish_reason,
    fetch_openai_models,
    model_ids_from_entries,
)

__all__ = [
    "AgentResult",
    "ChatClient",
    "run_agent",
    "build_chat_payload",
    "extract_chat_text",
    "extract_finish_reason",
    "fetch_openai_models",
    "model_ids_from_entries",
]
