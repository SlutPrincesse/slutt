"""Unified configuration layer for Nexus."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import Any, Optional


@dataclass
class NexusConfig:
    """Top-level Nexus configuration."""

    # Core
    app_name: str = "nexus"
    log_level: str = "info"
    log_file: str = "./config/nexus.log"

    # Skills
    skills_dir: str = "./config/skills"
    skill_roots: list[str] = field(default_factory=list)

    # Runtime
    provider: str = "nim"
    base_url: str = "https://integrate.api.nvidia.com/v1"
    model: str = "auto"
    temperature: float = 0.7
    max_tokens: int = 1024
    max_tool_steps: int = 50
    tool_root: str = "."
    workspace_dir: str = "./workspace"
    assistant_name: str = "Nexus"
    assistant_tone: str = "Direct, pragmatic, concise."

    # Task timer
    task_timer_minutes: int = 30

    # Web UI
    web_ui_enabled: bool = True
    web_ui_port: int = 3000

    # Memory
    memory_db: str = "./config/memory.sqlite3"

    # Shell
    enable_shell: bool = True
    shell_timeout_s: float = 20.0
    shell_max_output_bytes: int = 200_000
    shell_block_network: bool = False

    # Custom tools
    enable_custom_tools: bool = True
    custom_tools_dir: str = "./workspace/skills/tools"
    custom_tools_block_network: bool = False

    # Web
    web_max_bytes: int = 500_000
    web_user_agent: str = "nexus/0.1.0 (+https://github.com/nexus/nexus)"

    # Tool limits
    tool_max_read_bytes: int = 200_000
    tool_max_write_bytes: int = 2_000_000
    tool_max_list_entries: int = 2000

    # Discord
    discord_bot_token: str = ""
    discord_session_scope: str = "channel"

    # Timer Discord
    timer_discord_notify: bool = True
    timer_discord_channel_id: str = ""
    timer_discord_bot_token: str = ""
    timer_discord_webhook_url: str = ""
    timer_discord_timeout_s: float = 10.0
    timer_discord_context: bool = True
    timer_discord_context_max_messages: int = 24
    timer_discord_context_max_chars: int = 12000

    # Google
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = ""
    google_default_scopes: str = "openid email https://www.googleapis.com/auth/calendar.readonly https://www.googleapis.com/auth/gmail.readonly"
    google_oauth_timeout_s: float = 20.0
    google_connect_expires_s: int = 900

    # Routing
    router_host: str = "127.0.0.1"
    router_port: int = 8080
    router_api_key: str = ""
    router_config: str = ""
    router_log_path: str = ""
    router_cors_origins: str = ""
    enable_prometheus: bool = True
    health_check_upstream: bool = False
    max_request_body_bytes: int = 10_485_760
    upstream_max_retries: int = 3
    upstream_retry_backoff_seconds: float = 0.5

    # Depfix
    depfix_cache_dir: str = ""
    depfix_cache_retention_days: int = 30
    depfix_cache_auto_cleanup: bool = True
    depfix_cache_renewal_seconds: int = 3600
    depfix_cache_deletion_grace_hours: int = 24
    depfix_max_io_workers: int = 16
    depfix_log_level: str = "INFO"
    depfix_uv: str = ""

    # Browser
    chrome_executable: str = ""
    browser_stealth: bool = False
    browser_headless: bool = True


def _get_env(key: str, default: Any = None) -> Any:
    val = os.environ.get(key)
    if val is None or val == "":
        return default
    return val


def _bool(val: Any) -> bool:
    if isinstance(val, bool):
        return val
    if isinstance(val, str):
        return val.lower() in ("1", "true", "yes", "on")
    return bool(val)


def load_config(path: Optional[str] = None) -> NexusConfig:
    """Load Nexus config from JSON file with env overrides."""
    cfg = NexusConfig()

    # Load from file if present
    if path is None:
        candidates = [
            os.environ.get("NEXUS_CONFIG_DIR", "./config") + "/config.json",
            "./config/config.json",
        ]
        for c in candidates:
            if Path(c).exists():
                path = c
                break

    if path and Path(path).exists():
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        for fld in fields(cfg):
            key = fld.name
            if key in data:
                setattr(cfg, key, data[key])

    # Apply env overrides
    env_map = {
        "NEXUS_LOG_LEVEL": "log_level",
        "NEXUS_LOG_FILE": "log_file",
        "NEXUS_SKILLS_DIR": "skills_dir",
        "NEXUS_PROVIDER": "provider",
        "NEXUS_BASE_URL": "base_url",
        "NEXUS_MODEL": "model",
        "NEXUS_TEMPERATURE": ("temperature", float),
        "NEXUS_MAX_TOKENS": ("max_tokens", int),
        "NEXUS_MAX_TOOL_STEPS": ("max_tool_steps", int),
        "NEXUS_TOOL_ROOT": "tool_root",
        "NEXUS_WORKSPACE_DIR": "workspace_dir",
        "NEXUS_ASSISTANT_NAME": "assistant_name",
        "NEXUS_ASSISTANT_TONE": "assistant_tone",
        "NEXUS_TASK_TIMER_MINUTES": ("task_timer_minutes", int),
        "NEXUS_WEB_UI_ENABLED": ("web_ui_enabled", _bool),
        "NEXUS_WEB_UI_PORT": ("web_ui_port", int),
        "NEXUS_MEMORY_DB": "memory_db",
        "NEXUS_ENABLE_SHELL": ("enable_shell", _bool),
        "NEXUS_SHELL_TIMEOUT_S": ("shell_timeout_s", float),
        "NEXUS_SHELL_MAX_OUTPUT_BYTES": ("shell_max_output_bytes", int),
        "NEXUS_SHELL_BLOCK_NETWORK": ("shell_block_network", _bool),
        "NEXUS_ENABLE_CUSTOM_TOOLS": ("enable_custom_tools", _bool),
        "NEXUS_CUSTOM_TOOLS_DIR": "custom_tools_dir",
        "NEXUS_CUSTOM_TOOLS_BLOCK_NETWORK": ("custom_tools_block_network", _bool),
        "NEXUS_WEB_MAX_BYTES": ("web_max_bytes", int),
        "NEXUS_WEB_USER_AGENT": "web_user_agent",
        "NEXUS_TOOL_MAX_READ_BYTES": ("tool_max_read_bytes", int),
        "NEXUS_TOOL_MAX_WRITE_BYTES": ("tool_max_write_bytes", int),
        "NEXUS_TOOL_MAX_LIST_ENTRIES": ("tool_max_list_entries", int),
        "NEXUS_DISCORD_BOT_TOKEN": "discord_bot_token",
        "NEXUS_DISCORD_SESSION_SCOPE": "discord_session_scope",
        "NEXUS_TIMER_DISCORD_NOTIFY": ("timer_discord_notify", _bool),
        "NEXUS_TIMER_DISCORD_CHANNEL_ID": "timer_discord_channel_id",
        "NEXUS_TIMER_DISCORD_BOT_TOKEN": "timer_discord_bot_token",
        "NEXUS_TIMER_DISCORD_WEBHOOK_URL": "timer_discord_webhook_url",
        "NEXUS_TIMER_DISCORD_TIMEOUT_S": ("timer_discord_timeout_s", float),
        "NEXUS_TIMER_DISCORD_CONTEXT": ("timer_discord_context", _bool),
        "NEXUS_TIMER_DISCORD_CONTEXT_MAX_MESSAGES": ("timer_discord_context_max_messages", int),
        "NEXUS_TIMER_DISCORD_CONTEXT_MAX_CHARS": ("timer_discord_context_max_chars", int),
        "NEXUS_ROUTER_HOST": "router_host",
        "NEXUS_ROUTER_PORT": ("router_port", int),
        "NEXUS_ROUTER_API_KEY": "router_api_key",
        "NEXUS_ROUTER_CONFIG": "router_config",
        "NEXUS_ROUTER_LOG_PATH": "router_log_path",
        "NEXUS_ROUTER_CORS_ORIGINS": "router_cors_origins",
        "NEXUS_ENABLE_PROMETHEUS": ("enable_prometheus", _bool),
        "NEXUS_HEALTH_CHECK_UPSTREAM": ("health_check_upstream", _bool),
        "NEXUS_MAX_REQUEST_BODY_BYTES": ("max_request_body_bytes", int),
        "NEXUS_UPSTREAM_MAX_RETRIES": ("upstream_max_retries", int),
        "NEXUS_UPSTREAM_RETRY_BACKOFF_SECONDS": ("upstream_retry_backoff_seconds", float),
        "NEXUS_CHROME_EXECUTABLE": "chrome_executable",
        "NEXUS_BROWSER_STEALTH": ("browser_stealth", _bool),
        "NEXUS_BROWSER_HEADLESS": ("browser_headless", _bool),
        "NEXUS_DEPFIX_CACHE_DIR": "depfix_cache_dir",
        "NEXUS_DEPFIX_CACHE_RETENTION_DAYS": ("depfix_cache_retention_days", int),
        "NEXUS_DEPFIX_CACHE_AUTO_CLEANUP": ("depfix_cache_auto_cleanup", _bool),
        "NEXUS_DEPFIX_CACHE_RENEWAL_SECONDS": ("depfix_cache_renewal_seconds", int),
        "NEXUS_DEPFIX_CACHE_DELETION_GRACE_HOURS": ("depfix_cache_deletion_grace_hours", int),
        "NEXUS_DEPFIX_MAX_IO_WORKERS": ("depfix_max_io_workers", int),
        "NEXUS_DEPFIX_LOG_LEVEL": "depfix_log_level",
        "NEXUS_DEPFIX_UV": "depfix_uv",
    }

    for env_key, cfg_key in env_map.items():
        val = _get_env(env_key)
        if val is not None:
            if isinstance(cfg_key, tuple):
                setattr(cfg, cfg_key[0], cfg_key[1](val))
            else:
                setattr(cfg, cfg_key, val)

    # Backward-compatible aliases (deprecated)
    _backward_compat = {
        "FREECLAW_PROVIDER": "provider",
        "FREECLAW_BASE_URL": "base_url",
        "FREECLAW_MODEL": "model",
        "FREECLAW_TEMPERATURE": ("temperature", float),
        "FREECLAW_MAX_TOKENS": ("max_tokens", int),
        "FREECLAW_MAX_TOOL_STEPS": ("max_tool_steps", int),
        "FREECLAW_TOOL_ROOT": "tool_root",
        "FREECLAW_WORKSPACE_DIR": "workspace_dir",
        "FREECLAW_ASSISTANT_NAME": "assistant_name",
        "FREECLAW_ASSISTANT_TONE": "assistant_tone",
        "FREECLAW_TASK_TIMER_MINUTES": ("task_timer_minutes", int),
        "FREECLAW_WEB_UI_ENABLED": ("web_ui_enabled", _bool),
        "FREECLAW_WEB_UI_PORT": ("web_ui_port", int),
        "FREECLAW_MEMORY_DB": "memory_db",
        "FREECLAW_ENABLE_SHELL": ("enable_shell", _bool),
        "FREECLAW_SHELL_TIMEOUT_S": ("shell_timeout_s", float),
        "FREECLAW_SHELL_MAX_OUTPUT_BYTES": ("shell_max_output_bytes", int),
        "FREECLAW_SHELL_BLOCK_NETWORK": ("shell_block_network", _bool),
        "FREECLAW_ENABLE_CUSTOM_TOOLS": ("enable_custom_tools", _bool),
        "FREECLAW_CUSTOM_TOOLS_DIR": "custom_tools_dir",
        "FREECLAW_CUSTOM_TOOLS_BLOCK_NETWORK": ("custom_tools_block_network", _bool),
        "FREECLAW_WEB_MAX_BYTES": ("web_max_bytes", int),
        "FREECLAW_WEB_USER_AGENT": "web_user_agent",
        "FREECLAW_TOOL_MAX_READ_BYTES": ("tool_max_read_bytes", int),
        "FREECLAW_TOOL_MAX_WRITE_BYTES": ("tool_max_write_bytes", int),
        "FREECLAW_TOOL_MAX_LIST_ENTRIES": ("tool_max_list_entries", int),
        "FREECLAW_DISCORD_BOT_TOKEN": "discord_bot_token",
        "FREECLAW_DISCORD_SESSION_SCOPE": "discord_session_scope",
        "FREECLAW_TIMER_DISCORD_NOTIFY": ("timer_discord_notify", _bool),
        "FREECLAW_TIMER_DISCORD_CHANNEL_ID": "timer_discord_channel_id",
        "FREECLAW_TIMER_DISCORD_BOT_TOKEN": "timer_discord_bot_token",
        "FREECLAW_TIMER_DISCORD_WEBHOOK_URL": "timer_discord_webhook_url",
        "FREECLAW_TIMER_DISCORD_TIMEOUT_S": ("timer_discord_timeout_s", float),
        "FREECLAW_TIMER_DISCORD_CONTEXT": ("timer_discord_context", _bool),
        "FREECLAW_TIMER_DISCORD_CONTEXT_MAX_MESSAGES": ("timer_discord_context_max_messages", int),
        "FREECLAW_TIMER_DISCORD_CONTEXT_MAX_CHARS": ("timer_discord_context_max_chars", int),
        "FREECLAW_GOOGLE_CLIENT_ID": "google_client_id",
        "FREECLAW_GOOGLE_CLIENT_SECRET": "google_client_secret",
        "FREECLAW_GOOGLE_REDIRECT_URI": "google_redirect_uri",
        "FREECLAW_GOOGLE_DEFAULT_SCOPES": "google_default_scopes",
        "FREECLAW_GOOGLE_OAUTH_TIMEOUT_S": ("google_oauth_timeout_s", float),
        "FREECLAW_GOOGLE_CONNECT_EXPIRES_S": ("google_connect_expires_s", int),
        "NVIDIA_API_KEY": "nvidia_api_key",
        "NIM_API_KEY": "nvidia_api_key",
        "NVIDIA_NIM_API_KEY": "nvidia_api_key",
        "OPENROUTER_API_KEY": "openrouter_api_key",
        "OPENAI_API_KEY": "openai_api_key",
        "GROQ_API_KEY": "groq_api_key",
        "GROQ_KEY": "groq_api_key",
        "HERMES_SKILLS_DIR": "skills_dir",
        "DEPFIX_CACHE_DIR": "depfix_cache_dir",
        "DEPFIX_LOG_LEVEL": "depfix_log_level",
        "DEPFIX_UV": "depfix_uv",
        "CHROME_EXECUTABLE": "chrome_executable",
    }

    for env_key, cfg_key in _backward_compat.items():
        val = _get_env(env_key)
        if val is not None:
            if isinstance(cfg_key, tuple):
                setattr(cfg, cfg_key[0], cfg_key[1](val))
            else:
                setattr(cfg, cfg_key, val)

    return cfg


def write_default_config(path: str = "./config/config.json") -> None:
    """Write default config to file."""
    cfg = NexusConfig()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    data = {fld.name: getattr(cfg, fld.name) for fld in fields(cfg)}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
