"""Patch-based (unified diff) editing utilities."""
from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any


def make_unified_diff(old: str, new: str, filename: str = "file") -> str:
    return "".join(difflib.unified_diff(
        old.splitlines(keepends=True),
        new.splitlines(keepends=True),
        fromfile=f"a/{filename}",
        tofile=f"b/{filename}",
    ))


def apply_unified_diff(path: str, diff: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"success": False, "error": f"not found: {path}"}
    try:
        lines = p.read_text(encoding="utf-8").splitlines(keepends=True)
        # Ensure trailing newline consistency
        if lines and not lines[-1].endswith("\n"):
            lines[-1] += "\n"
        result = list(lines)
        # Parse hunks
        hunks = re.findall(r"@@ -(\d+),?(\d*) \+(\d+),?(\d*) @@\n(.*?)(?=\n@@ |\Z)", diff, re.S)
        # Apply in reverse order to preserve line numbers
        offsets = []
        for (old_start, old_count, new_start, new_count, body) in hunks:
            old_start = int(old_start)
            old_count = int(old_count) if old_count else 1
            body_lines = body.split("\n")
            # reconstruct
            old_lines = []
            new_lines = []
            for bl in body_lines:
                if bl.startswith("-"):
                    old_lines.append(bl[1:] + ("\n" if not bl[1:].endswith("\n") else ""))
                elif bl.startswith("+"):
                    new_lines.append(bl[1:] + ("\n" if not bl[1:].endswith("\n") else ""))
                elif bl.startswith(" "):
                    old_lines.append(bl[1:] + ("\n" if not bl[1:].endswith("\n") else ""))
                    new_lines.append(bl[1:] + ("\n" if not bl[1:].endswith("\n") else ""))
                elif bl == "":
                    continue
            # find position
            pos = old_start - 1
            # verify
            if result[pos:pos + len(old_lines)] == old_lines:
                result[pos:pos + len(old_lines)] = new_lines
        p.write_text("".join(result), encoding="utf-8")
        return {"success": True, "path": str(p)}
    except Exception as e:
        return {"success": False, "error": str(e)}
