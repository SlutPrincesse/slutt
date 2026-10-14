"""
Utilities for AGENT_SYSTEM_V9
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import List, Optional


def find_gguf_models(search_paths: Optional[List[Path]] = None) -> List[Path]:
    """Find GGUF model files in common locations."""
    if search_paths is None:
        search_paths = [
            Path.home() / "Downloads",
            Path.home() / "Documents",
            Path.home() / ".cache" / "lmdeploy",
            Path.home() / ".local" / "share" / "llama.cpp",
            Path.home() / ".local" / "share" / "models",
            Path.home() / "models",
            Path("/models"),
            Path("/opt/models"),
            Path.cwd() / "models",
        ]

    models = []
    for loc in search_paths:
        if loc.exists() and loc.is_dir():
            try:
                for ext in ["*.gguf", "*.GGUF"]:
                    models.extend(loc.glob(ext))
                for p in loc.rglob("*.gguf"):
                    models.append(p)
            except Exception:
                continue

    # Deduplicate
    seen = set()
    unique = []
    for m in models:
        key = str(m.resolve())
        if key not in seen:
            seen.add(key)
            unique.append(m)
    return unique


def get_api_config() -> tuple[Optional[str], Optional[str]]:
    """Get API key and base URL from environment."""
    api_key = os.environ.get("OPENAI_API_KEY") or os.environ.get("LLM_API_KEY")
    api_base = os.environ.get("OPENAI_API_BASE") or os.environ.get("LLM_BASE_URL")
    return api_key, api_base


def set_api_config(api_key: Optional[str] = None, api_base: Optional[str] = None) -> None:
    """Set API configuration in environment."""
    if api_key:
        os.environ["OPENAI_API_KEY"] = api_key
        os.environ["LLM_API_KEY"] = api_key
    if api_base:
        os.environ["OPENAI_API_BASE"] = api_base
        os.environ["LLM_BASE_URL"] = api_base
