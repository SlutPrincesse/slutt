"""Task Timer runtime: periodically checks and executes due tasks."""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any

from nexus.runtime.agent import AgentResult, run_agent
from nexus.runtime.tools.fs import ToolContext

log = logging.getLogger(__name__)

_TASK_RE = re.compile(r"^(\s*)(#\s*)?(\d{1,6})\s*-\s*(.+?)\s*$")


def _tasks_path(workspace: Path) -> Path:
    return workspace / "tasks.md"


def _state_path(workspace: Path) -> Path:
    return workspace / "mem" / "task_timer_state.json"


def _task_key(minutes: int, task: str) -> str:
    return f"dotime:{int(minutes)}:{str(task).strip().lower()}"


def _ensure_tasks_md(workspace: Path) -> None:
    p = _tasks_path(workspace)
    if p.exists():
        return
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# tasks\n\n## Tasks\n<!-- Add tasks below -->\n", encoding="utf-8")


def _read_lines(workspace: Path) -> list[str]:
    _ensure_tasks_md(workspace)
    p = _tasks_path(workspace)
    data = p.read_text(encoding="utf-8", errors="replace")
    return data.splitlines()


def _parse_entries(lines: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    n = 0
    for i, ln in enumerate(lines):
        m = _TASK_RE.match(ln)
        if not m:
            continue
        minutes = int(m.group(3))
        task = (m.group(4) or "").strip()
        if minutes <= 0 or not task:
            continue
        n += 1
        out.append({
            "id": n,
            "line_idx": i,
            "minutes": minutes,
            "task": task,
            "enabled": (m.group(2) is None),
            "raw_line": ln,
        })
    return out


def _read_last_run(path: Path) -> dict[str, int]:
    try:
        if not path.exists() or not path.is_file():
            return {}
        obj = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        if not isinstance(obj, dict):
            return {}
        lr = obj.get("last_run")
        if not isinstance(lr, dict):
            return {}
        out: dict[str, int] = {}
        for k, v in lr.items():
            if not isinstance(k, str):
                continue
            try:
                out[k] = int(v)
            except Exception:
                continue
        return out
    except Exception:
        return {}


def _load_last_run(workspace: Path) -> dict[str, int]:
    return _read_last_run(_state_path(workspace))


def _save_last_run(workspace: Path, last_run: dict[str, int]) -> None:
    p = _state_path(workspace)
    p.parent.mkdir(parents=True, exist_ok=True)
    obj = {"version": 1, "last_run": {str(k): int(v) for k, v in (last_run or {}).items()}}
    p.write_text(json.dumps(obj, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def compute_due_tasks(
    workspace: Path,
    *,
    now_s: int | None = None,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Compute which tasks are due based on dotime and last run state.

    Returns (due_tasks, summary_counts).
    """
    lines = _read_lines(workspace)
    entries = _parse_entries(lines)
    last_run = _load_last_run(workspace)
    now = int(now_s or time.time())

    total = len(entries)
    enabled = [e for e in entries if e["enabled"]]
    due: list[dict[str, Any]] = []

    for e in enabled:
        k = _task_key(e["minutes"], e["task"])
        last = last_run.get(k)
        if last is None:
            due.append({
                "id": e["id"],
                "minutes": e["minutes"],
                "task": e["task"],
                "last_run_s": None,
                "elapsed_minutes": None,
                "raw": e["raw_line"],
            })
            continue

        elapsed_s = max(0, now - int(last))
        elapsed_min = elapsed_s // 60
        if elapsed_s >= int(e["minutes"]) * 60:
            due.append({
                "id": e["id"],
                "minutes": e["minutes"],
                "task": e["task"],
                "last_run_s": int(last),
                "elapsed_minutes": int(elapsed_min),
                "raw": e["raw_line"],
            })

    summary = {
        "total": int(total),
        "enabled": int(len(enabled)),
        "due": int(len(due)),
    }
    return due, summary


def run_due_tasks(
    *,
    client: Any,
    workspace: Path,
    tool_ctx: ToolContext | None,
    system_prompt: str,
    temperature: float = 0.7,
    max_tokens: int = 1024,
    max_tool_steps: int = 50,
    enable_tools: bool = True,
    verbose_tools: bool = False,
) -> AgentResult:
    """Run all currently due tasks in a single agent turn.

    Updates last_run state for successfully completed tasks.
    """
    due, summary = compute_due_tasks(workspace)
    if not due:
        return AgentResult(
            text="[no tasks due]",
            raw_last_response={},
            steps=0,
        )

    task_lines = []
    for d in due:
        elapsed = d.get("elapsed_minutes")
        if elapsed is not None:
            task_lines.append(f"- {d['task']} (elapsed: {elapsed} minutes)")
        else:
            task_lines.append(f"- {d['task']} (never run)")

    user_msg = (
        "The following tasks are due. Please execute each one in order:\n"
        + "\n".join(task_lines)
        + "\n\nAfter completing each task, briefly note what you did."
    )

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_msg},
    ]

    result = run_agent(
        client=client,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        enable_tools=enable_tools,
        tool_ctx=tool_ctx,
        max_tool_steps=max_tool_steps,
        verbose_tools=verbose_tools,
    )

    if not result.text.startswith("["):
        now = int(time.time())
        last_run = _load_last_run(workspace)
        for d in due:
            k = _task_key(d["minutes"], d["task"])
            last_run[k] = now
        _save_last_run(workspace, last_run)

    return result
