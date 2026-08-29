"""SessionManager: interactive skill session lifecycle.

Port of skill-router's SessionManager class and helper functions:
- SessionManager: start/end/activate/deactivate/track/review/status
- interactive_select, parse_selection, format_report, format_json
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Any

log = logging.getLogger(__name__)


class SessionManager:
    """Manages active skill sessions: user selection, usage tracking, and
    periodic review to detect stale or low-value skills.

    State file (JSON) stores:
      - session_id: short identifier
      - created_at: ISO timestamp
      - task_desc: the original task description
      - active_skills: { skill_name: { activated_at, call_count, last_used_at, last_note } }
      - history: list of { action, skill, ts } entries
    """

    IDLE_THRESHOLD_SECONDS = 600
    MIN_CALLS_BEFORE_REVIEW = 2
    LOW_USAGE_RATIO = 0.15

    def __init__(self, state_file=None):
        if state_file is None:
            state_file = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                ".session",
                "session_state.json",
            )
        self.state_file = state_file
        self.state = self._load_state()

    def _load_state(self):
        """Load session state from disk, or create empty state."""
        if os.path.isfile(self.state_file):
            try:
                with open(self.state_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {
            "session_id": None,
            "created_at": None,
            "task_desc": "",
            "active_skills": {},
            "history": [],
        }

    def _save_state(self):
        """Persist state to disk."""
        os.makedirs(os.path.dirname(self.state_file), exist_ok=True)
        with open(self.state_file, "w", encoding="utf-8") as f:
            json.dump(self.state, f, ensure_ascii=False, indent=2)

    def start_session(self, task_desc, selected_skills):
        """Start a new session with user-selected skills."""
        now = datetime.now().isoformat()
        self.state = {
            "session_id": now.replace(":", "").replace("-", "")[:14],
            "created_at": now,
            "task_desc": task_desc,
            "active_skills": {},
            "history": [],
        }
        for skill_name in selected_skills:
            self.state["active_skills"][skill_name] = {
                "activated_at": now,
                "call_count": 0,
                "last_used_at": None,
                "last_note": "",
            }
            self.state["history"].append(
                {"action": "activate", "skill": skill_name, "ts": now}
            )
        self._save_state()
        return self.get_status()

    def end_session(self):
        """End the current session, clearing all state."""
        old_id = self.state.get("session_id")
        self.state = {
            "session_id": None,
            "created_at": None,
            "task_desc": "",
            "active_skills": {},
            "history": [],
        }
        self._save_state()
        return old_id

    def is_active(self):
        """Check if a session is currently active."""
        return self.state.get("session_id") is not None

    def activate(self, skill_name):
        """Add a skill to the active session."""
        if not self.is_active():
            return {"error": "No active session. Start a session first."}
        if skill_name in self.state["active_skills"]:
            return {"error": f"Skill '{skill_name}' is already active."}
        now = datetime.now().isoformat()
        self.state["active_skills"][skill_name] = {
            "activated_at": now,
            "call_count": 0,
            "last_used_at": None,
            "last_note": "",
        }
        self.state["history"].append(
            {"action": "activate", "skill": skill_name, "ts": now}
        )
        self._save_state()
        return {"activated": skill_name}

    def deactivate(self, skill_name, reason=""):
        """Remove a skill from the active session."""
        if not self.is_active():
            return {"error": "No active session."}
        if skill_name not in self.state["active_skills"]:
            return {"error": f"Skill '{skill_name}' is not active."}
        del self.state["active_skills"][skill_name]
        now = datetime.now().isoformat()
        self.state["history"].append(
            {
                "action": "deactivate",
                "skill": skill_name,
                "ts": now,
                "reason": reason,
            }
        )
        self._save_state()
        return {"deactivated": skill_name, "reason": reason}

    def track_usage(self, skill_name, note=""):
        """Record that a skill was used."""
        if not self.is_active():
            return {"error": "No active session."}
        if skill_name not in self.state["active_skills"]:
            return {"error": f"Skill '{skill_name}' is not in active session."}
        info = self.state["active_skills"][skill_name]
        info["call_count"] += 1
        info["last_used_at"] = datetime.now().isoformat()
        if note:
            info["last_note"] = note
        self.state["history"].append(
            {
                "action": "track",
                "skill": skill_name,
                "ts": info["last_used_at"],
                "note": note,
            }
        )
        self._save_state()
        return {
            "skill": skill_name,
            "call_count": info["call_count"],
            "last_used_at": info["last_used_at"],
        }

    def review(self):
        """Analyze active skills and flag stale or low-value ones."""
        if not self.is_active():
            return {"error": "No active session."}

        now = datetime.now()
        suggestions = []
        healthy = []
        active = self.state["active_skills"]

        if not active:
            return {
                "suggestions": [],
                "healthy": [],
                "summary": "No active skills in session.",
            }

        session_start = datetime.fromisoformat(self.state["created_at"])
        session_minutes = max((now - session_start).total_seconds() / 60.0, 1.0)

        for skill_name, info in active.items():
            call_count = info.get("call_count", 0)
            last_used_str = info.get("last_used_at")
            activated_str = info.get("activated_at", now.isoformat())

            if call_count == 0:
                activated_time = datetime.fromisoformat(activated_str)
                idle_since_activation = (now - activated_time).total_seconds()
                if idle_since_activation > self.IDLE_THRESHOLD_SECONDS:
                    suggestions.append({
                        "skill": skill_name,
                        "reason": "never_used",
                        "severity": "high",
                        "detail": (
                            f"Activated {int(idle_since_activation / 60)} min ago, "
                            f"never called once."
                        ),
                    })
                else:
                    suggestions.append({
                        "skill": skill_name,
                        "reason": "never_used",
                        "severity": "low",
                        "detail": (
                            f"Activated but never called "
                            f"({int(idle_since_activation / 60)} min ago)."
                        ),
                    })
            else:
                last_used = datetime.fromisoformat(last_used_str)
                idle_seconds = (now - last_used).total_seconds()
                if idle_seconds > self.IDLE_THRESHOLD_SECONDS:
                    suggestions.append({
                        "skill": skill_name,
                        "reason": "idle",
                        "severity": "medium",
                        "detail": (
                            f"Last used {int(idle_seconds / 60)} min ago "
                            f"({call_count} total calls)."
                        ),
                    })
                elif (call_count >= self.MIN_CALLS_BEFORE_REVIEW and
                      (call_count / session_minutes) < self.LOW_USAGE_RATIO):
                    suggestions.append({
                        "skill": skill_name,
                        "reason": "low_efficiency",
                        "severity": "medium",
                        "detail": (
                            f"Only {call_count} calls in "
                            f"{int(session_minutes)} min "
                            f"({call_count / session_minutes:.2f} calls/min)."
                        ),
                    })
                else:
                    healthy.append(skill_name)

        summary_parts = []
        if suggestions:
            summary_parts.append(
                f"{len(suggestions)} skill(s) flagged for review"
            )
        if healthy:
            summary_parts.append(
                f"{len(healthy)} skill(s) healthy"
            )
        summary = "; ".join(summary_parts) if summary_parts else "No active skills."

        return {
            "suggestions": suggestions,
            "healthy": healthy,
            "summary": summary,
        }

    def get_status(self):
        """Returns full session snapshot as dict."""
        return {
            "session_id": self.state.get("session_id"),
            "created_at": self.state.get("created_at"),
            "task_desc": self.state.get("task_desc", ""),
            "active_skills": {
                name: {
                    "activated_at": info.get("activated_at"),
                    "call_count": info.get("call_count", 0),
                    "last_used_at": info.get("last_used_at"),
                    "last_note": info.get("last_note", ""),
                }
                for name, info in self.state.get("active_skills", {}).items()
            },
            "history_count": len(self.state.get("history", [])),
        }


def interactive_select(matches, allow_custom=True):
    """Convert match results into a structured candidate list for user selection."""
    if not matches:
        return []
    candidates = []
    for i, m in enumerate(matches, 1):
        candidates.append({
            "index": i,
            "name": m["skill_name"],
            "display_name": m["display_name"],
            "score": m["score"],
            "recommendation": m["recommendation"],
            "reasons": m.get("reasons", []),
            "path": m.get("path", ""),
            "tools": m.get("tools", []),
        })
    return candidates


def parse_selection(user_input, candidates):
    """Parse user input into a list of skill names."""
    text = user_input.strip().lower()
    if text in ("all", "*", "."):
        return [c["name"] for c in candidates]
    if text in ("none", "n", "0", ""):
        return []
    selected = []
    parts = re.split(r"[,，\s]+", text)
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            idx = int(part) - 1
            if 0 <= idx < len(candidates):
                selected.append(candidates[idx]["name"])
        else:
            for c in candidates:
                if part in c["name"].lower() or part in c["display_name"].lower():
                    selected.append(c["name"])
                    break
    return selected


def format_report(task, matches, elapsed_ms=0):
    """Format results as a human-readable text report."""
    lines = []
    lines.append(f"Task: {task}")
    lines.append(f"Scanned: {len(matches)} skills matched")
    lines.append(f"Time: {elapsed_ms}ms")
    lines.append("")
    for i, m in enumerate(matches, 1):
        lines.append(f"{i}. {m['display_name']} ({m['skill_name']})")
        lines.append(f"   Score: {m['score']:.1f} | {m['recommendation']}")
        if m.get("description"):
            lines.append(f"   {m['description'][:120]}")
        if m.get("tools"):
            lines.append(f"   Tools: {', '.join(m['tools'][:5])}")
        lines.append("")
    return "\n".join(lines)


def format_json(task, matches, elapsed_ms=0):
    """Format results as a JSON dict."""
    return {
        "task": task,
        "scanned": len(matches),
        "elapsed_ms": elapsed_ms,
        "matched": [
            {
                "skill_name": m["skill_name"],
                "display_name": m["display_name"],
                "score": m["score"],
                "recommendation": m["recommendation"],
                "tier": m.get("tier", ""),
                "path": m.get("path", ""),
                "tools": m.get("tools", []),
                "reasons": m.get("reasons", []),
            }
            for m in matches
        ],
    }
