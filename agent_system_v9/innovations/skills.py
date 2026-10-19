"""Skill crystallization: compress successful workflows into reusable macros."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Skill:
    name: str
    steps: list[str] = field(default_factory=list)
    success_count: int = 0


class SkillCrystallizer:
    def __init__(self):
        self._skills: dict[str, Skill] = {}

    def crystallize(self, name: str, steps: list[str]) -> Skill:
        if name in self._skills:
            self._skills[name].steps = steps
            self._skills[name].success_count += 1
        else:
            self._skills[name] = Skill(name=name, steps=steps, success_count=1)
        return self._skills[name]

    def get(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def list_skills(self) -> list[Skill]:
        return list(self._skills.values())

    def match(self, task: str) -> Skill | None:
        for s in self._skills.values():
            if s.name.lower() in task.lower():
                return s
        return None
