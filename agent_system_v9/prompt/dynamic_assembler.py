"""
Dynamic Prompt Assembler - Stitches prompt snippets based on tags (git-diff, env-vars, os-type)
"""
import os
import platform
import re
import subprocess
import threading
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class SnippetType(Enum):
    SYSTEM = "system"
    CONTEXT = "context"
    TASK = "task"
    CONSTRAINT = "constraint"
    EXAMPLE = "example"
    TOOL = "tool"
    MEMORY = "memory"


@dataclass
class PromptSnippet:
    snippet_id: str
    name: str
    content: str
    snippet_type: SnippetType
    tags: list[str] = field(default_factory=list)
    conditions: dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    dependencies: list[str] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class AssemblyContext:
    git_diff: str | None = None
    env_vars: dict[str, str] = field(default_factory=dict)
    os_type: str = ""
    os_version: str = ""
    python_version: str = ""
    working_dir: str = ""
    project_files: list[str] = field(default_factory=list)
    recent_errors: list[str] = field(default_factory=list)
    active_tools: list[str] = field(default_factory=list)
    memory_context: dict[str, Any] = field(default_factory=dict)
    custom: dict[str, Any] = field(default_factory=dict)


class DynamicPromptAssembler:
    def __init__(self):
        self._snippets: dict[str, PromptSnippet] = {}
        self._tag_index: dict[str, list[str]] = defaultdict(list)
        self._type_index: dict[SnippetType, list[str]] = defaultdict(list)
        self._lock = threading.RLock()
        self._context_providers: dict[str, Callable[[], Any]] = {}
        self._register_default_snippets()
        self._register_default_context_providers()

    def _register_default_context_providers(self):
        self._context_providers["git_diff"] = self._get_git_diff
        self._context_providers["env_vars"] = lambda: dict(os.environ)
        self._context_providers["os_type"] = lambda: platform.system().lower()
        self._context_providers["os_version"] = lambda: platform.release()
        self._context_providers["python_version"] = lambda: platform.python_version()
        self._context_providers["working_dir"] = lambda: os.getcwd()
        self._context_providers["project_files"] = self._get_project_files

    def _get_git_diff(self) -> str | None:
        try:
            result = subprocess.run(
                ["git", "diff", "--no-color", "HEAD~1..HEAD"],
                capture_output=True, text=True, timeout=5, cwd=os.getcwd()
            )
            if result.returncode == 0 and result.stdout.strip():
                return result.stdout[:5000]  # Limit size
        except Exception:
            pass
        return None

    def _get_project_files(self) -> list[str]:
        try:
            result = subprocess.run(
                ["git", "ls-files"],
                capture_output=True, text=True, timeout=5, cwd=os.getcwd()
            )
            if result.returncode == 0:
                return result.stdout.strip().split('\n')[:100]
        except Exception:
            pass
        return []

    def _register_default_snippets(self):
        # System snippets
        self.register_snippet(PromptSnippet(
            snippet_id="sys_base",
            name="Base System Prompt",
            content="You are an expert software engineer. Provide accurate, concise, and practical solutions.",
            snippet_type=SnippetType.SYSTEM,
            tags=["base", "system"],
            priority=100
        ))

        self.register_snippet(PromptSnippet(
            snippet_id="sys_code_style",
            name="Code Style Guidelines",
            content="Follow existing code conventions. Use type hints. Write clean, maintainable code. No unnecessary comments.",
            snippet_type=SnippetType.CONSTRAINT,
            tags=["code_style", "constraints"],
            priority=90
        ))

        # Context snippets
        self.register_snippet(PromptSnippet(
            snippet_id="ctx_git_diff",
            name="Git Diff Context",
            content="Recent changes:\n{git_diff}",
            snippet_type=SnippetType.CONTEXT,
            tags=["git", "diff", "context"],
            conditions={"git_diff": {"exists": True}},
            variables=["git_diff"],
            priority=80
        ))

        self.register_snippet(PromptSnippet(
            snippet_id="ctx_env",
            name="Environment Context",
            content="Environment: OS={os_type} {os_version}, Python={python_version}, Dir={working_dir}",
            snippet_type=SnippetType.CONTEXT,
            tags=["env", "context"],
            variables=["os_type", "os_version", "python_version", "working_dir"],
            priority=70
        ))

        # Task snippets
        self.register_snippet(PromptSnippet(
            snippet_id="task_debug",
            name="Debug Task",
            content="Debug the following issue: {task_description}\n\nError details:\n{recent_errors}",
            snippet_type=SnippetType.TASK,
            tags=["debug", "task"],
            variables=["task_description", "recent_errors"],
            priority=85
        ))

        self.register_snippet(PromptSnippet(
            snippet_id="task_refactor",
            name="Refactor Task",
            content="Refactor the code to improve: {refactor_goals}\n\nFiles to consider:\n{project_files}",
            snippet_type=SnippetType.TASK,
            tags=["refactor", "task"],
            variables=["refactor_goals", "project_files"],
            priority=85
        ))

        # Tool snippets
        self.register_snippet(PromptSnippet(
            snippet_id="tool_grep",
            name="Grep Tool",
            content="Use grep/glob to search code. Pattern: {search_pattern}",
            snippet_type=SnippetType.TOOL,
            tags=["tool", "search"],
            variables=["search_pattern"],
            priority=60
        ))

        # Memory snippets
        self.register_snippet(PromptSnippet(
            snippet_id="mem_patterns",
            name="Learned Patterns",
            content="Previously successful patterns:\n{memory_context}",
            snippet_type=SnippetType.MEMORY,
            tags=["memory", "patterns"],
            variables=["memory_context"],
            priority=50
        ))

    def register_snippet(self, snippet: PromptSnippet):
        with self._lock:
            self._snippets[snippet.snippet_id] = snippet
            for tag in snippet.tags:
                self._tag_index[tag].append(snippet.snippet_id)
            self._type_index[snippet.snippet_type].append(snippet.snippet_id)

    def unregister_snippet(self, snippet_id: str) -> bool:
        with self._lock:
            snippet = self._snippets.pop(snippet_id, None)
            if not snippet:
                return False

            for tag in snippet.tags:
                if snippet_id in self._tag_index[tag]:
                    self._tag_index[tag].remove(snippet_id)

            if snippet_id in self._type_index[snippet.snippet_type]:
                self._type_index[snippet.snippet_type].remove(snippet_id)

            return True

    def assemble(self, context: AssemblyContext,
                 required_tags: list[str] = None,
                 excluded_tags: list[str] = None,
                 max_tokens: int = 8000) -> str:
        # Gather context
        full_context = self._gather_context(context)

        # Select snippets
        selected = self._select_snippets(full_context, required_tags, excluded_tags)

        # Resolve dependencies and order
        ordered = self._resolve_dependencies(selected)

        # Render snippets
        rendered = []
        total_tokens = 0

        for snippet in ordered:
            rendered_content = self._render_snippet(snippet, full_context)
            snippet_tokens = self._estimate_tokens(rendered_content)

            if total_tokens + snippet_tokens > max_tokens:
                # Try to truncate
                if total_tokens < max_tokens * 0.9:
                    remaining = max_tokens - total_tokens
                    rendered_content = self._truncate_to_tokens(rendered_content, remaining)
                    rendered.append(rendered_content)
                    total_tokens += self._estimate_tokens(rendered_content)
                break

            rendered.append(rendered_content)
            total_tokens += snippet_tokens

        return "\n\n".join(rendered)

    def _gather_context(self, context: AssemblyContext) -> dict[str, Any]:
        ctx = {
            "git_diff": context.git_diff,
            "env_vars": context.env_vars,
            "os_type": context.os_type or platform.system().lower(),
            "os_version": context.os_version or platform.release(),
            "python_version": context.python_version or platform.python_version(),
            "working_dir": context.working_dir or os.getcwd(),
            "project_files": context.project_files,
            "recent_errors": context.recent_errors,
            "active_tools": context.active_tools,
            "memory_context": context.memory_context,
        }

        # Add custom context
        ctx.update(context.custom)

        # Call context providers for missing values
        for key, provider in self._context_providers.items():
            if key not in ctx or ctx[key] is None:
                try:
                    ctx[key] = provider()
                except Exception:
                    ctx[key] = None

        return ctx

    def _select_snippets(self, context: dict[str, Any],
                        required_tags: list[str] = None,
                        excluded_tags: list[str] = None) -> list[PromptSnippet]:
        required_tags = required_tags or []
        excluded_tags = excluded_tags or []

        candidate_ids = set()

        # Start with required tags
        if required_tags:
            for tag in required_tags:
                candidate_ids.update(self._tag_index.get(tag, []))
        else:
            # All snippets as candidates
            candidate_ids = set(self._snippets.keys())

        # Filter by conditions
        selected = []
        for snippet_id in candidate_ids:
            snippet = self._snippets.get(snippet_id)
            if not snippet:
                continue

            # Check excluded tags
            if any(tag in excluded_tags for tag in snippet.tags):
                continue

            # Check conditions
            if self._check_conditions(snippet.conditions, context):
                selected.append(snippet)

        # Sort by priority (descending)
        selected.sort(key=lambda s: -s.priority)
        return selected

    def _check_conditions(self, conditions: dict[str, Any], context: dict[str, Any]) -> bool:
        for key, condition in conditions.items():
            context_value = context.get(key)

            if isinstance(condition, dict):
                if "exists" in condition:
                    if condition["exists"] and not context_value:
                        return False
                    if not condition["exists"] and context_value:
                        return False
                if "equals" in condition:
                    if context_value != condition["equals"]:
                        return False
                if "contains" in condition:
                    if not context_value or condition["contains"] not in str(context_value):
                        return False
                if "matches" in condition:
                    if not context_value or not re.search(condition["matches"], str(context_value)):
                        return False
            elif condition is True:
                if not context_value:
                    return False
            elif condition is False:
                if context_value:
                    return False

        return True

    def _resolve_dependencies(self, snippets: list[PromptSnippet]) -> list[PromptSnippet]:
        # Topological sort based on dependencies
        snippet_map = {s.snippet_id: s for s in snippets}
        visited = set()
        result = []

        def visit(snippet_id: str):
            if snippet_id in visited:
                return
            if snippet_id not in snippet_map:
                return

            snippet = snippet_map[snippet_id]
            for dep_id in snippet.dependencies:
                if dep_id in snippet_map:
                    visit(dep_id)

            visited.add(snippet_id)
            result.append(snippet)

        for snippet in snippets:
            visit(snippet.snippet_id)

        return result

    def _render_snippet(self, snippet: PromptSnippet, context: dict[str, Any]) -> str:
        content = snippet.content

        # Replace variables
        for var in snippet.variables:
            placeholder = f"{{{var}}}"
            value = context.get(var, "")
            if isinstance(value, (list, dict)):
                value = json.dumps(value, indent=2)
            content = content.replace(placeholder, str(value))

        return content

    def _estimate_tokens(self, text: str) -> int:
        # Rough estimation: ~4 chars per token
        return len(text) // 4

    def _truncate_to_tokens(self, text: str, max_tokens: int) -> str:
        max_chars = max_tokens * 4
        if len(text) <= max_chars:
            return text
        return text[:max_chars] + "... [truncated]"

    def register_context_provider(self, name: str, provider: Callable[[], Any]):
        self._context_providers[name] = provider

    def get_snippet(self, snippet_id: str) -> PromptSnippet | None:
        with self._lock:
            return self._snippets.get(snippet_id)

    def list_snippets(self, snippet_type: SnippetType | None = None,
                      tags: list[str] = None) -> list[PromptSnippet]:
        with self._lock:
            if snippet_type:
                ids = self._type_index.get(snippet_type, [])
            elif tags:
                ids = set()
                for tag in tags:
                    ids.update(self._tag_index.get(tag, []))
                ids = list(ids)
            else:
                ids = list(self._snippets.keys())

            return [self._snippets[sid] for sid in ids if sid in self._snippets]


import json

_assembler: DynamicPromptAssembler | None = None


def get_prompt_assembler() -> DynamicPromptAssembler:
    global _assembler
    if _assembler is None:
        _assembler = DynamicPromptAssembler()
    return _assembler
