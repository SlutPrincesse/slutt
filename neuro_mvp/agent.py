"""Pluggable agent runner.

The "agent" is whatever turns (task, worktree, seed) into a code change.
By default it shells out to a user-supplied command and exposes the task via
environment variables (OVERLORD_WORKTREE / OVERLORD_TASK / OVERLORD_SEED).
DEMO mode simulates a change so the pipeline is runnable fully offline.

No hard-coded model or network calls.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Optional


class AgentRunner:
    def __init__(self, command: Optional[str] = None, demo: bool = False):
        self.command = command
        self.demo = demo

    def run(self, worktree: Path, task: str, seed: int) -> int:
        env = dict(
            os.environ,
            OVERLORD_WORKTREE=str(worktree),
            OVERLORD_TASK=task,
            OVERLORD_SEED=str(seed),
        )
        if self.demo:
            (worktree / f".shadow_change_{seed}.txt").write_text(
                f"demo agent change for: {task} (seed {seed})\n"
            )
            return 0
        if not self.command:
            raise RuntimeError("No agent command configured. Pass --agent-cmd or --demo.")
        cmd = self.command
        if "{worktree}" in cmd or "{task}" in cmd or "{seed}" in cmd:
            cmd = cmd.format(worktree=worktree, task=task, seed=seed)
        return subprocess.run(cmd, shell=True, env=env, cwd=worktree).returncode
