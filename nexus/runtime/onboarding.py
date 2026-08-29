"""First-run onboarding wizard for Nexus."""

from __future__ import annotations

import getpass
import os
import sys
from pathlib import Path
from typing import Any

from nexus.config import NexusConfig, load_config, write_default_config


def _prompt(msg: str, default: str | None = None) -> str:
    if default is None:
        return input(msg).strip()
    v = input(f"{msg} [{default}]: ").strip()
    return v if v else default


def _prompt_yes_no(msg: str, default: bool) -> bool:
    d = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{msg} ({d}): ").strip().lower()
        if not raw:
            return default
        if raw in {"y", "yes"}:
            return True
        if raw in {"n", "no"}:
            return False


def _slugify_workspace_name(name: str, *, fallback: str = "Nexus") -> str:
    s = str(name or "").strip()
    if not s:
        return fallback
    out: list[str] = []
    for ch in s:
        if ch.isalnum():
            out.append(ch)
        elif ch in {"_", "-"}:
            out.append(ch)
        elif ch.isspace():
            out.append("-")
    slug = "".join(out).strip("-_")
    return slug[:64] if slug else fallback


def _prompt_provider(current: str | None) -> str:
    cur = (current or "nim").strip().lower() or "nim"
    if cur not in {"nim", "openrouter", "groq"}:
        cur = "nim"
    choices = [("1", "nim"), ("2", "openrouter"), ("3", "groq")]
    cur_num = next((n for n, name in choices if name == cur), "1")
    while True:
        print("Choose provider:")
        for n, name in choices:
            mark = " (current)" if name == cur else ""
            print(f"  {n}) {name}{mark}")
        raw = _prompt("Provider number", default=cur_num).strip().lower()
        for n, name in choices:
            if raw == n:
                return name
        if raw in {"nim", "openrouter", "groq"}:
            return raw
        print("Invalid provider. Choose 1/2/3.")


def run_onboarding(
    *,
    config_path: str | None = None,
    force: bool = False,
) -> Path:
    """Run the first-run onboarding wizard.

    Configures provider, API key, workspace, and tool root.
    Returns the path to the env file.
    """
    if not sys.stdin.isatty():
        raise SystemExit(
            "First-run onboarding requires an interactive terminal. "
            "Create ./config/.env with an API key and rerun."
        )

    cfg = load_config(config_path)

    print("Nexus first-run setup\n")
    print("This will:")
    print("- store your provider API key in a .env file")
    print("- set a workspace directory for Nexus state")
    print("- set a disk access root for filesystem tools\n")

    env_path = Path("./config/.env").expanduser().resolve()
    env_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"Using env file: {env_path}")

    provider = _prompt_provider(cfg.provider)
    if provider == "nim":
        existing_key = (
            os.getenv("NVIDIA_API_KEY") or os.getenv("NIM_API_KEY") or os.getenv("NVIDIA_NIM_API_KEY") or ""
        ).strip()
        key_prompt = "NVIDIA_API_KEY (input hidden; leave blank to keep existing env value)"
        api_key = getpass.getpass(f"{key_prompt}: ").strip() or existing_key
        if not api_key:
            raise SystemExit("NVIDIA_API_KEY is required.")
        _set_env_var(env_path, "NVIDIA_API_KEY", api_key)
    elif provider == "openrouter":
        existing_key = (os.getenv("OPENROUTER_API_KEY") or os.getenv("OPENAI_API_KEY") or "").strip()
        key_prompt = "OPENROUTER_API_KEY (input hidden; leave blank to keep existing env value)"
        api_key = getpass.getpass(f"{key_prompt}: ").strip() or existing_key
        if not api_key:
            raise SystemExit("OPENROUTER_API_KEY is required.")
        _set_env_var(env_path, "OPENROUTER_API_KEY", api_key)
    else:
        existing_key = (os.getenv("GROQ_API_KEY") or os.getenv("GROQ_KEY") or "").strip()
        key_prompt = "GROQ_API_KEY (input hidden; leave blank to keep existing env value)"
        api_key = getpass.getpass(f"{key_prompt}: ").strip() or existing_key
        if not api_key:
            raise SystemExit("GROQ_API_KEY is required.")
        _set_env_var(env_path, "GROQ_API_KEY", api_key)

    base_url_default = (
        "https://integrate.api.nvidia.com/v1"
        if provider == "nim"
        else ("https://openrouter.ai/api/v1" if provider == "openrouter" else "https://api.groq.com/openai/v1")
    )
    base_url = _prompt("Base URL", default=base_url_default).strip() or base_url_default

    model = _prompt("Model id (blank = auto-select at runtime)", default="").strip() or None

    assistant_name = _prompt("Bot name", default=(cfg.assistant_name or "Nexus")).strip() or "Nexus"
    assistant_tone = _prompt(
        "Bot tone (one sentence)",
        default=(cfg.assistant_tone or "Direct, pragmatic, concise."),
    ).strip()

    try:
        max_tool_steps = int(
            _prompt("Max tool steps per request", default=str(cfg.max_tool_steps))
        )
    except ValueError:
        max_tool_steps = 50
    if max_tool_steps < 1:
        max_tool_steps = 50

    try:
        task_timer_minutes = int(
            _prompt("Task timer interval (minutes; 0 disables)", default=str(cfg.task_timer_minutes))
        )
    except ValueError:
        task_timer_minutes = 30
    if task_timer_minutes < 0:
        task_timer_minutes = 30

    default_workspace_root = (Path.cwd() / "workspace").resolve()
    workspace_root_dir = _prompt(
        "Workspace root directory",
        default=str(default_workspace_root),
    ).strip()
    workspace_root_p = Path(workspace_root_dir).expanduser().resolve()
    workspace_root_p.mkdir(parents=True, exist_ok=True)

    base_ws_name = _slugify_workspace_name(assistant_name, fallback="Nexus")
    workspace_p = (workspace_root_p / base_ws_name).resolve()
    workspace_p.mkdir(parents=True, exist_ok=True)

    default_tool_root = str(Path.cwd().resolve())
    while True:
        tool_root = _prompt(
            "Disk access root for fs_* tools (enter / for full disk access)",
            default=default_tool_root,
        ).strip()
        tool_root_p = Path(tool_root).expanduser().resolve()

        try:
            workspace_p.relative_to(tool_root_p)
        except Exception:
            print("\nWorkspace must be within tool_root so Nexus can update persona/tools/tasks.")
            print(f"- workspace: {workspace_p}")
            print(f"- tool_root:  {tool_root_p}\n")
            continue
        break

    if str(tool_root_p) != "/":
        tool_root_p.mkdir(parents=True, exist_ok=True)

    _ensure_workspace_docs(
        workspace_p=workspace_p,
        assistant_name=assistant_name,
        assistant_tone=assistant_tone,
        task_timer_minutes=task_timer_minutes,
        max_tool_steps=max_tool_steps,
    )

    new_cfg = NexusConfig(
        provider=provider,
        base_url=base_url,
        model=model or cfg.model,
        assistant_name=assistant_name,
        assistant_tone=assistant_tone,
        max_tool_steps=int(max_tool_steps),
        workspace_dir=str(workspace_p),
        tool_root=str(tool_root_p),
        task_timer_minutes=int(task_timer_minutes),
        memory_db=str(workspace_p / "mem" / "memory.sqlite3"),
    )

    cfg_out = Path(config_path or "./config/config.json").expanduser().resolve()
    cfg_out.parent.mkdir(parents=True, exist_ok=True)
    _save_config(cfg_out, new_cfg)

    print("\nSetup complete.")
    print(f"- config: {cfg_out}")
    print(f"- env:    {env_path}")
    print(f"- workspace: {workspace_p}")
    print(f"- tool_root: {tool_root_p}")
    print(f"- task timer minutes: {int(task_timer_minutes)}")
    print(f"- max tool steps: {int(max_tool_steps)}")
    print("\nNext:")
    print("- run:    nexus serve")

    return env_path


def _set_env_var(env_path: Path, key: str, value: str) -> None:
    """Set an env var in a .env file, creating the file if needed."""
    lines: list[str] = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
    out: list[str] = []
    found = False
    for ln in lines:
        if ln.startswith(f"{key}="):
            out.append(f"{key}={value}")
            found = True
        else:
            out.append(ln)
    if not found:
        out.append(f"{key}={value}")
    env_path.write_text("\n".join(out).rstrip("\n") + "\n", encoding="utf-8")


def _ensure_workspace_docs(
    *,
    workspace_p: Path,
    assistant_name: str,
    assistant_tone: str,
    task_timer_minutes: int,
    max_tool_steps: int,
) -> None:
    persona_path = workspace_p / "persona.md"
    if not persona_path.exists():
        persona_path.write_text(
            "\n".join([
                "# persona",
                "",
                "This is the bot's persistent persona file.",
                "",
                "## Name",
                assistant_name.strip() or "Nexus",
                "",
                "## Tone",
                assistant_tone.strip() or "(not set)",
                "",
                "## Persona",
                "- Mission:",
                "",
            ]) + "\n",
            encoding="utf-8",
        )

    tools_path = workspace_p / "tools.md"
    if not tools_path.exists():
        tools_path.write_text(
            "\n".join([
                "# tools",
                "",
                "Concise tool index for Nexus.",
                "",
                "## Built-ins",
                "- fs_*: fs_read, fs_write, fs_mkdir, fs_list, fs_stat, fs_glob, fs_diff, fs_rm, fs_mv, fs_cp",
                "- search/web/http: text_search, web_search, web_fetch, http_request_json, timer_api_get",
                "- memory_*: memory_add, memory_get, memory_search, memory_delete",
                "- task_*: task_list, task_add, task_update, task_disable, task_enable, task_run_now",
                "- doc_*: doc_ingest, doc_search, doc_get, doc_list, doc_delete",
                "- shell: sh_exec",
                "",
            ]) + "\n",
            encoding="utf-8",
        )

    tasks_path = workspace_p / "tasks.md"
    if not tasks_path.exists():
        tasks_path.write_text(
            "\n".join([
                "# tasks",
                "",
                "This file is the task list for Nexus's task timer.",
                "",
                "## Format",
                "- Each enabled task is one line: `<minutes>-<task>`",
                "  - Example: `30-check weather` (runs about every 30 minutes).",
                "- Disable a task by commenting it out: `# 30-check weather`",
                "",
                "## How It Works",
                f"- Interval minutes (config): {int(task_timer_minutes)}",
                "- Every tick, the task timer checks which tasks are due.",
                "",
                "## Tasks",
                "<!-- Add tasks below -->",
                "",
            ]) + "\n",
            encoding="utf-8",
        )

    (workspace_p / "Journal").mkdir(parents=True, exist_ok=True)


def _save_config(path: Path, cfg: NexusConfig) -> None:
    """Save NexusConfig to a JSON file."""
    import json
    from dataclasses import fields

    data = {fld.name: getattr(cfg, fld.name) for fld in fields(cfg)}
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
