"""Git-worktree sharding for isolated parallel agents.

Each agent runs in its own git worktree on its own branch. Diffs are collected
and presented for HUMAN review -- there is deliberately no automatic merge of
divergent code (the riskiest part of the original design).
"""
from __future__ import annotations

import subprocess
from pathlib import Path


class WorktreeSharder:
    def __init__(self, repo: Path, n: int = 3, branch: str = "main"):
        self.repo = Path(repo)
        self.n = max(1, n)
        self.branch = branch
        self.shadow_dir = self.repo / ".shadow"

    def _git(self, *args, cwd=None):
        return subprocess.run(
            ["git", *args],
            cwd=cwd or self.repo,
            capture_output=True,
            text=True,
            check=True,
        )

    def create(self):
        self._git("rev-parse", "--is-inside-work-tree")
        self.shadow_dir.mkdir(exist_ok=True)
        worktrees = []
        for i in range(self.n):
            name = f"shadow_{i}"
            path = self.shadow_dir / name
            if path.exists():
                self._git("worktree", "remove", str(path), "--force")
            self._git("worktree", "add", "-b", name, str(path), self.branch)
            worktrees.append(path)
        return worktrees

    def collect_diffs(self, worktrees):
        diffs = {}
        for wt in worktrees:
            # intent-to-add so untracked agent output also appears in the diff
            self._git("add", "-A", "-N", cwd=wt)
            r = self._git("diff", self.branch, cwd=wt)
            diffs[str(wt)] = r.stdout or "(no changes)"
        return diffs

    def adopt(self, index: int):
        self._git("merge", f"shadow_{index}", "--no-edit")

    def cleanup(self, worktrees):
        for wt in worktrees:
            try:
                self._git("worktree", "remove", str(wt), "--force")
            except subprocess.CalledProcessError:
                pass
        for i in range(self.n):
            try:
                self._git("branch", "-D", f"shadow_{i}")
            except subprocess.CalledProcessError:
                pass
