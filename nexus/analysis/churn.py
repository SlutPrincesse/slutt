"""Git churn: how often each file changes, straight from `git log`.

Churn alone is noise and complexity alone is static — but a file that is
both complex *and* frequently edited is where the next bug lives. Codi
multiplies the two into a churn-risk ranking. Requires git in PATH and a
repository; degrades to empty data silently otherwise (still zero
Python dependencies).
"""

from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ChurnInfo:
    """Change frequency for one file over the analysis window."""

    path: str
    commits: int
    authors: int


def collect_churn(root: Path, since: str = "12 months") -> dict[str, ChurnInfo]:
    """Map repo-relative path -> ChurnInfo, or {} when git is unavailable."""
    base = root if root.is_dir() else root.parent
    try:
        out = subprocess.run(
            ["git", "-C", str(base), "log", f"--since={since}",
             "--name-only", "--format=%an"],
            capture_output=True, text=True, timeout=30,
            encoding="utf-8", errors="replace",
        )
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if out.returncode != 0:
        return {}

    commits: dict[str, int] = {}
    authors: dict[str, set[str]] = {}
    current_author = ""
    for line in out.stdout.splitlines():
        if not line:
            continue
        if line.endswith(".py"):
            path = line.replace("\\", "/")
            commits[path] = commits.get(path, 0) + 1
            authors.setdefault(path, set()).add(current_author)
        else:
            current_author = line
    return {
        p: ChurnInfo(path=p, commits=c, authors=len(authors.get(p, ())))
        for p, c in commits.items()
    }


def churn_risk(
    churn: dict[str, ChurnInfo], complexity_by_file: dict[str, float]
) -> list[tuple[str, int, float, float]]:
    """Rank files by commits x avg complexity: (path, commits, avg_cx, risk)."""
    ranked = [
        (path, info.commits, cx, round(info.commits * cx, 1))
        for path, info in churn.items()
        if (cx := complexity_by_file.get(path, 0.0)) > 0
    ]
    ranked.sort(key=lambda r: r[3], reverse=True)
    return ranked
