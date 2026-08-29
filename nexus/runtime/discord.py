"""Discord bot integration for Nexus.

Requires discord.py (install with: pip install -e '.[discord]').
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any

from nexus.runtime.agent import run_agent
from nexus.runtime.providers.base import extract_finish_reason
from nexus.runtime.tools.fs import ToolContext

log = logging.getLogger(__name__)

DISCORD_MESSAGE_LIMIT = 2000


def _safe_label(s: str, *, fallback: str = "base", max_len: int = 80) -> str:
    out: list[str] = []
    for ch in (s or "").strip():
        if ch.isalnum() or ch in {"-", "_"}:
            out.append(ch)
        elif ch.isspace():
            out.append("-")
    v = "".join(out).strip("-_")
    if not v:
        return fallback
    return v[: int(max_len)]


def _split_discord_message(text: str, limit: int = DISCORD_MESSAGE_LIMIT) -> list[str]:
    """Split a message into chunks that fit Discord's message limit."""
    if not str(text or "").strip():
        return ["(no response)"]
    if len(text) <= limit:
        return [text]

    lines = text.splitlines(True)
    chunks: list[str] = []
    cur = ""
    in_code = False

    def flush() -> None:
        nonlocal cur
        if not cur:
            return
        if in_code:
            if not cur.endswith("\n"):
                cur += "\n"
            cur += "```"
        chunks.append(cur.rstrip("\n"))
        cur = ""

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_code:
                in_code = True
            else:
                in_code = False

        while line and len(line) > limit:
            head = line[:limit]
            line = line[limit:]
            if cur:
                flush()
            chunks.append(head.rstrip("\n"))

        reserve = len("\n```") if in_code else 0
        if cur and (len(cur) + len(line) > (limit - reserve)):
            flush()
            if in_code:
                cur = "```\n"

        if len(line) > limit:
            chunks.append(line[:limit].rstrip("\n"))
            continue

        cur += line

    if cur:
        flush()
    return [c for c in chunks if c.strip() != ""]


class DiscordSession:
    """Represents a single Discord conversation session."""

    def __init__(
        self,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
    ) -> None:
        self.messages: list[dict[str, Any]] = []
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens


def _init_session_db(db_path: Path) -> None:
    """Initialize the SQLite session store."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    con.execute(
        """
        CREATE TABLE IF NOT EXISTS discord_sessions_v3 (
          bot_id INTEGER NOT NULL,
          platform TEXT NOT NULL,
          conversation_key TEXT NOT NULL,
          last_channel_id INTEGER,
          messages_json TEXT NOT NULL,
          updated_at INTEGER NOT NULL,
          PRIMARY KEY(bot_id, platform, conversation_key)
        );
        """
    )
    con.execute(
        "CREATE INDEX IF NOT EXISTS idx_discord_sessions_v3_updated_at ON discord_sessions_v3(updated_at);"
    )
    con.commit()
    con.close()


def _load_session(db_path: Path, *, bot_id: int, key: str) -> list[dict[str, Any]]:
    """Load a session's messages from the DB."""
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    try:
        row = con.execute(
            "SELECT messages_json FROM discord_sessions_v3 WHERE bot_id=? AND platform='discord' AND conversation_key=?;",
            (int(bot_id), str(key)),
        ).fetchone()
        if not row:
            return []
        obj = json.loads(row[0])
        return obj if isinstance(obj, list) else []
    finally:
        con.close()


def _save_session(db_path: Path, *, bot_id: int, channel_id: int, key: str, messages: list[dict[str, Any]]) -> None:
    """Save a session's messages to the DB."""
    con = sqlite3.connect(str(db_path))
    con.execute("PRAGMA journal_mode=WAL;")
    con.execute("PRAGMA synchronous=NORMAL;")
    try:
        con.execute(
            """
            INSERT INTO discord_sessions_v3 (bot_id, platform, conversation_key, last_channel_id, messages_json, updated_at)
            VALUES (?, 'discord', ?, ?, ?, ?)
            ON CONFLICT(bot_id, platform, conversation_key) DO UPDATE SET
              last_channel_id=excluded.last_channel_id,
              messages_json=excluded.messages_json,
              updated_at=excluded.updated_at
            """,
            (int(bot_id), str(key), int(channel_id), json.dumps(messages, ensure_ascii=True), int(time.time())),
        )
        con.commit()
    finally:
        con.close()


async def run_discord_bot(
    *,
    token: str | None = None,
    prefix: str = "!nexus",
    respond_to_all: bool = False,
    system_prompt: str | None = None,
    client: Any = None,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    tool_ctx: ToolContext | None = None,
    enable_tools: bool = True,
    max_tool_steps: int = 50,
    verbose_tools: bool = False,
    history_messages: int = 40,
    session_scope: str = "channel",
    workspace: Path | None = None,
    bot_label: str | None = None,
) -> None:
    """Run the Discord bot.

    This is the main entry point for the Discord integration.
    """
    try:
        import discord  # type: ignore
        from discord import app_commands  # type: ignore
    except Exception as e:
        raise SystemExit(
            "discord.py is not installed. Install with:\n"
            "  pip install -e '.[discord]'\n"
            f"Import error: {e}"
        )

    bot_token = token or os.getenv("DISCORD_BOT_TOKEN") or os.getenv("NEXUS_DISCORD_BOT_TOKEN")
    if not bot_token:
        raise SystemExit("Missing Discord bot token. Set DISCORD_BOT_TOKEN or pass --token.")

    db_path = workspace / "mem" / "discord_sessions.sqlite3" if workspace else Path("./config/discord_sessions.sqlite3")
    _init_session_db(db_path)

    sessions: dict[str, DiscordSession] = {}

    def _get_session(key: str) -> DiscordSession:
        if key not in sessions:
            session = DiscordSession()
            session.messages = _load_session(db_path, bot_id=0, key=key)
            sessions[key] = session
        return sessions[key]

    def _save_session(key: str, channel_id: int) -> None:
        if key in sessions:
            _save_session_db(db_path, bot_id=0, channel_id=channel_id, key=key, messages=sessions[key].messages)

    def _save_session_db(path: Path, *, bot_id: int, channel_id: int, key: str, messages: list[dict[str, Any]]) -> None:
        _save_session(path, bot_id=bot_id, channel_id=channel_id, key=key, messages=messages)

    intents = discord.Intents.default()
    intents.message_content = True
    intents.guilds = True
    intents.messages = True
    intents.dm_messages = True

    bot = discord.Client(intents=intents)
    tree = app_commands.CommandTree(bot)

    @bot.event
    async def on_ready() -> None:
        log.info("Discord bot ready: %s (id=%s)", bot.user, bot.user.id if bot.user else "?")
        await tree.sync()

    async def handle_message(message: Any) -> None:
        if message.author.bot:
            return

        content = message.content.strip()
        if not content:
            return

        is_prefix = content.lower().startswith(prefix.lower())
        is_mention = bot.user and message.mentions and bot.user in message.mentions

        if not is_prefix and not is_respond_to_all and not is_mention:
            return

        if is_prefix:
            content = content[len(prefix):].strip()
        elif is_mention:
            content = content.replace(f"<@{bot.user.id}>", "").replace(f"<@!{bot.user.id}>", "").strip()

        if not content:
            return

        if content.lower() in {"new", "reset"}:
            key = f"channel:{message.channel.id}"
            if key in sessions:
                del sessions[key]
            await message.channel.send("Session reset.")
            return

        if content.lower() == "help":
            await message.channel.send(_help_text(prefix))
            return

        key = f"channel:{message.channel.id}"
        session = _get_session(key)

        if not session.messages and system_prompt:
            session.messages.append({"role": "system", "content": system_prompt})

        session.messages.append({"role": "user", "content": content})

        try:
            result = run_agent(
                client=client,
                messages=session.messages,
                temperature=session.temperature or temperature,
                max_tokens=session.max_tokens or max_tokens,
                enable_tools=enable_tools,
                tool_ctx=tool_ctx,
                max_tool_steps=max_tool_steps,
                verbose_tools=verbose_tools,
            )
            response_text = result.text
        except Exception as e:
            log.exception("agent error")
            response_text = f"(error) {type(e).__name__}: {e}"

        chunks = _split_discord_message(response_text)
        for chunk in chunks:
            await message.channel.send(chunk)

        _save_session(key, message.channel.id)

    @bot.event
    async def on_message(message: Any) -> None:
        try:
            await handle_message(message)
        except Exception as e:
            log.exception("message handler error: %s", e)

    @tree.command(name="help", description="Show help")
    async def slash_help(interaction: Any) -> None:
        await interaction.response.send_message(_help_text(prefix), ephemeral=True)

    @tree.command(name="reset", description="Reset the current session")
    async def slash_reset(interaction: Any) -> None:
        key = f"channel:{interaction.channel_id}"
        if key in sessions:
            del sessions[key]
        await interaction.response.send_message("Session reset.", ephemeral=True)

    await bot.start(bot_token)


def _help_text(prefix: str) -> str:
    return "\n".join([
        "Commands:",
        "",
        f"- `{prefix} <prompt>` chat in the current channel/DM",
        f"- `{prefix} new` start a new conversation",
        f"- `{prefix} reset` clear the current conversation session",
        f"- `{prefix} help` show this help",
        "",
        "Slash commands:",
        "- `/help` show this help",
        "- `/reset` clear session",
    ])
