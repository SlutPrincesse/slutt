"""Skill alias resolution maps."""

from __future__ import annotations

from nexus.skills.constants import SKILL_NAME_ALIASES, CN_EN_KEYWORD_MAP

NAME_ALIASES: dict[str, str] = dict(SKILL_NAME_ALIASES)

CN_EN_ALIASES: dict[str, str] = dict(CN_EN_KEYWORD_MAP)

CATEGORY_ALIASES: dict[str, list[str]] = {
    "browser": ["browser", "web", "scraping"],
    "code": ["code_analysis", "lint", "complexity", "codi"],
    "data": ["data", "pandas", "sql"],
    "dev": ["devops", "deploy", "infra"],
    "doc": ["documentation", "markdown"],
    "ml": ["machine_learning", "pytorch", "tensorflow"],
    "productivity": ["todo", "notes", "calendar"],
    "security": ["security", "scan", "audit"],
    "test": ["testing", "pytest", "coverage"],
    "web": ["web", "api", "rest", "graphql"],
}
