"""
Unified UI - Cohesive TUI + Web Interface for AGENT_SYSTEM_V9
"""
from __future__ import annotations

try:
    from .app import UnifiedApp, run_unified
    __all__ = ["UnifiedApp", "run_unified"]
except Exception:
    __all__ = []
