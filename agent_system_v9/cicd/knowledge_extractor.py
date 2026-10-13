"""
Knowledge Extractor - Extracts knowledge from code, docs, and executions
"""
import ast
import hashlib
import re
import time
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


class KnowledgeType(Enum):
    PATTERN = "pattern"
    ANTI_PATTERN = "anti_pattern"
    BEST_PRACTICE = "best_practice"
    DECISION = "decision"
    FACT = "fact"
    HEURISTIC = "heuristic"
    RULE = "rule"
    METRIC = "metric"


class Confidence(Enum):
    LOW = 0.3
    MEDIUM = 0.6
    HIGH = 0.8
    VERY_HIGH = 0.95


@dataclass
class KnowledgeItem:
    knowledge_id: str
    knowledge_type: KnowledgeType
    title: str
    content: str
    source: str
    tags: list[str] = field(default_factory=list)
    confidence: float = 0.5
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    usage_count: int = 0
    validated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "knowledge_id": self.knowledge_id,
            "type": self.knowledge_type.value,
            "title": self.title,
            "content": self.content,
            "source": self.source,
            "tags": self.tags,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "usage_count": self.usage_count,
            "validated": self.validated,
        }


@dataclass
class ExtractedKnowledge:
    items: list[KnowledgeItem]
    source_type: str
    source_path: str
    extracted_at: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class CodePatternExtractor:
    def __init__(self):
        self.patterns = {
            "singleton": self._detect_singleton,
            "factory": self._detect_factory,
            "observer": self._detect_observer,
            "strategy": self._detect_strategy,
            "decorator": self._detect_decorator,
            "adapter": self._detect_adapter,
            "facade": self._detect_facade,
            "proxy": self._detect_proxy,
        }

        self.anti_patterns = {
            "god_class": self._detect_god_class,
            "spaghetti_code": self._detect_spaghetti,
            "copy_paste": self._detect_copy_paste,
            "long_method": self._detect_long_method,
            "large_class": self._detect_large_class,
            "dead_code": self._detect_dead_code,
        }

    def extract(self, file_path: str) -> ExtractedKnowledge:
        try:
            source = Path(file_path).read_text(encoding='utf-8', errors='ignore')
            tree = ast.parse(source)
        except Exception:
            return ExtractedKnowledge([], "code", file_path)

        items = []

        for pattern_name, detector in self.patterns.items():
            matches = detector(tree, source)
            for match in matches:
                items.append(KnowledgeItem(
                    knowledge_id=hashlib.md5(f"{pattern_name}:{file_path}:{match}".encode()).hexdigest()[:12],
                    knowledge_type=KnowledgeType.PATTERN,
                    title=f"Design Pattern: {pattern_name.title()}",
                    content=match,
                    source=file_path,
                    tags=["design_pattern", pattern_name],
                    confidence=0.7,
                ))

        for pattern_name, detector in self.anti_patterns.items():
            matches = detector(tree, source)
            for match in matches:
                items.append(KnowledgeItem(
                    knowledge_id=hashlib.md5(f"anti_{pattern_name}:{file_path}:{match}".encode()).hexdigest()[:12],
                    knowledge_type=KnowledgeType.ANTI_PATTERN,
                    title=f"Anti-pattern: {pattern_name.replace('_', ' ').title()}",
                    content=match,
                    source=file_path,
                    tags=["anti_pattern", pattern_name],
                    confidence=0.6,
                ))

        items.extend(self._extract_complexity_knowledge(tree, file_path))
        items.extend(self._extract_naming_knowledge(tree, file_path))

        return ExtractedKnowledge(items, "code", file_path)

    def _detect_singleton(self, tree: ast.AST, source: str) -> list[str]:
        matches = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and item.name == "__new__":
                        matches.append(f"Singleton pattern detected in class {node.name}")
        return matches

    def _detect_factory(self, tree: ast.AST, source: str) -> list[str]:
        matches = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                if "factory" in node.name.lower() or "create" in node.name.lower():
                    if any(isinstance(n, ast.Return) and isinstance(n.value, ast.Call) for n in ast.walk(node)):
                        matches.append(f"Factory pattern detected in function {node.name}")
        return matches

    def _detect_observer(self, tree: ast.AST, source: str) -> list[str]:
        matches = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                if "subscribe" in methods and "notify" in methods:
                    matches.append(f"Observer pattern detected in class {node.name}")
        return matches

    def _detect_strategy(self, tree: ast.AST, source: str) -> list[str]:
        matches = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for item in node.body:
                    if isinstance(item, ast.FunctionDef) and "strategy" in item.name.lower():
                        matches.append(f"Strategy pattern detected in class {node.name}")
        return matches

    def _detect_decorator(self, tree: ast.AST, source: str) -> list[str]:
        matches = []
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) and node.decorator_list:
                matches.append(f"Decorator pattern used in function {node.name}")
        return matches

    def _detect_adapter(self, tree: ast.AST, source: str) -> list[str]:
        matches = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
                if "Adapter" in str(bases) or "adapter" in node.name.lower():
                    matches.append(f"Adapter pattern detected in class {node.name}")
        return matches

    def _detect_facade(self, tree: ast.AST, source: str) -> list[str]:
        matches = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if "facade" in node.name.lower():
                    matches.append(f"Facade pattern detected in class {node.name}")
        return matches

    def _detect_proxy(self, tree: ast.AST, source: str) -> list[str]:
        matches = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                if "proxy" in node.name.lower():
                    matches.append(f"Proxy pattern detected in class {node.name}")
        return matches

    def _detect_god_class(self, tree: ast.AST, source: str) -> list[str]:
        matches = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = [n for n in node.body if isinstance(n, ast.FunctionDef)]
                attrs = [n for n in node.body if isinstance(n, ast.Assign)]
                if len(methods) > 20 or len(attrs) > 15:
                    matches.append(f"God class detected: {node.name} ({len(methods)} methods, {len(attrs)} attributes)")
        return matches

    def _detect_spaghetti(self, tree: ast.AST, source: str) -> list[str]:
        matches = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                complexity = self._calc_complexity(node)
                if complexity > 20:
                    matches.append(f"High complexity function: {node.name} (complexity: {complexity})")
        return matches

    def _detect_copy_paste(self, tree: ast.AST, source: str) -> list[str]:
        matches = []
        lines = source.split('\n')
        line_hashes = {}

        for i, line in enumerate(lines):
            stripped = line.strip()
            if len(stripped) > 30:
                h = hashlib.md5(stripped.encode()).hexdigest()[:8]
                if h in line_hashes:
                    matches.append(f"Potential copy-paste at line {i + 1} (similar to line {line_hashes[h] + 1})")
                else:
                    line_hashes[h] = i
        return matches

    def _detect_long_method(self, tree: ast.AST, source: str) -> list[str]:
        matches = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                lines = getattr(node, 'end_lineno', node.lineno) - node.lineno + 1
                if lines > 50:
                    matches.append(f"Long method: {node.name} ({lines} lines)")
        return matches

    def _detect_large_class(self, tree: ast.AST, source: str) -> list[str]:
        matches = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                total_lines = getattr(node, 'end_lineno', node.lineno) - node.lineno + 1
                if total_lines > 500:
                    matches.append(f"Large class: {node.name} ({total_lines} lines)")
        return matches

    def _detect_dead_code(self, tree: ast.AST, source: str) -> list[str]:
        matches = []
        defined = set()
        used = set()

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                if not node.name.startswith('_'):
                    defined.add(node.name)
            elif isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                used.add(node.id)

        unused = defined - used
        for name in unused:
            matches.append(f"Potentially unused definition: {name}")

        return matches

    def _calc_complexity(self, node: ast.AST) -> int:
        complexity = 1
        for child in ast.walk(node):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.ExceptHandler, ast.With, ast.BoolOp)):
                complexity += 1
        return complexity

    def _extract_complexity_knowledge(self, tree: ast.AST, file_path: str) -> list[KnowledgeItem]:
        items = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                complexity = self._calc_complexity(node)
                if complexity > 10:
                    items.append(KnowledgeItem(
                        knowledge_id=hashlib.md5(f"complexity:{file_path}:{node.name}".encode()).hexdigest()[:12],
                        knowledge_type=KnowledgeType.METRIC,
                        title=f"High Complexity: {node.name}",
                        content=f"Function {node.name} has cyclomatic complexity {complexity}",
                        source=file_path,
                        tags=["complexity", "refactoring_candidate"],
                        confidence=0.8,
                        metadata={"complexity": complexity, "function": node.name},
                    ))
        return items

    def _extract_naming_knowledge(self, tree: ast.AST, file_path: str) -> list[KnowledgeItem]:
        items = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.ClassDef)):
                if node.name != node.name.lower() and '_' in node.name:
                    items.append(KnowledgeItem(
                        knowledge_id=hashlib.md5(f"naming:{file_path}:{node.name}".encode()).hexdigest()[:12],
                        knowledge_type=KnowledgeType.BEST_PRACTICE,
                        title=f"Naming Convention: {node.name}",
                        content=f"{type(node).__name__} {node.name} uses mixed naming convention",
                        source=file_path,
                        tags=["naming", "style"],
                        confidence=0.5,
                    ))
        return items


class DocumentationExtractor:
    def __init__(self):
        self.section_patterns = [
            (r'^#+\s+(.+)$', 'heading'),
            (r'^(?:TODO|FIXME|HACK|NOTE|BUG):\s*(.+)$', 'annotation'),
            (r'```(\w+)?\n([\s\S]*?)\n```', 'code_block'),
        ]

    def extract(self, file_path: str) -> ExtractedKnowledge:
        try:
            content = Path(file_path).read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return ExtractedKnowledge([], "documentation", file_path)

        items = []

        for pattern, ptype in self.section_patterns:
            for match in re.finditer(pattern, content, re.MULTILINE):
                if ptype == 'annotation':
                    items.append(KnowledgeItem(
                        knowledge_id=hashlib.md5(f"annotation:{file_path}:{match.group(1)}".encode()).hexdigest()[:12],
                        knowledge_type=KnowledgeType.FACT,
                        title=f"Code Annotation: {match.group(1)[:50]}",
                        content=match.group(1),
                        source=file_path,
                        tags=["annotation", "todo" if "TODO" in match.group(1) else "note"],
                        confidence=0.9,
                    ))

        return ExtractedKnowledge(items, "documentation", file_path)


class ExecutionKnowledgeExtractor:
    def __init__(self):
        self.execution_history: list[dict] = []

    def record_execution(self, context: dict[str, Any]):
        self.execution_history.append({
            **context,
            "timestamp": time.time(),
        })

    def extract_patterns(self) -> ExtractedKnowledge:
        if len(self.execution_history) < 5:
            return ExtractedKnowledge([], "execution", "history")

        items = []

        error_patterns = defaultdict(int)
        for exec in self.execution_history:
            if exec.get("error"):
                error_patterns[exec["error"][:100]] += 1

        for error, count in error_patterns.items():
            if count >= 3:
                items.append(KnowledgeItem(
                    knowledge_id=hashlib.md5(f"recurring_error:{error}".encode()).hexdigest()[:12],
                    knowledge_type=KnowledgeType.HEURISTIC,
                    title="Recurring Error Pattern",
                    content=f"Error '{error}' occurred {count} times",
                    source="execution_history",
                    tags=["error", "recurring"],
                    confidence=0.8,
                    metadata={"count": count, "error": error},
                ))

        success_paths = defaultdict(int)
        for exec in self.execution_history:
            if exec.get("success"):
                path = exec.get("path", "unknown")
                success_paths[path] += 1

        for path, count in success_paths.items():
            if count >= 10:
                items.append(KnowledgeItem(
                    knowledge_id=hashlib.md5(f"success_path:{path}".encode()).hexdigest()[:12],
                    knowledge_type=KnowledgeType.HEURISTIC,
                    title="Successful Execution Path",
                    content=f"Path '{path}' succeeded {count} times",
                    source="execution_history",
                    tags=["success", "pattern"],
                    confidence=0.7,
                    metadata={"count": count, "path": path},
                ))

        return ExtractedKnowledge(items, "execution", "history")


class KnowledgeExtractor:
    def __init__(self):
        self.code_extractor = CodePatternExtractor()
        self.doc_extractor = DocumentationExtractor()
        self.exec_extractor = ExecutionKnowledgeExtractor()
        self.knowledge_base: dict[str, KnowledgeItem] = {}

    def extract_from_file(self, file_path: str) -> ExtractedKnowledge:
        if file_path.endswith('.py'):
            return self.code_extractor.extract(file_path)
        if file_path.endswith(('.md', '.rst', '.txt')):
            return self.doc_extractor.extract(file_path)
        return ExtractedKnowledge([], "unknown", file_path)

    def extract_from_directory(self, root_path: str, extensions: list[str] = None) -> list[ExtractedKnowledge]:
        if extensions is None:
            extensions = ['.py', '.md', '.txt', '.rst']

        results = []
        for ext in extensions:
            for file_path in Path(root_path).rglob(f'*{ext}'):
                try:
                    result = self.extract_from_file(str(file_path))
                    if result.items:
                        results.append(result)
                        for item in result.items:
                            self.knowledge_base[item.knowledge_id] = item
                except Exception:
                    pass

        return results

    def record_execution(self, context: dict[str, Any]):
        self.exec_extractor.record_execution(context)

    def extract_execution_patterns(self) -> ExtractedKnowledge:
        result = self.exec_extractor.extract_patterns()
        for item in result.items:
            self.knowledge_base[item.knowledge_id] = item
        return result

    def get_knowledge(self, knowledge_id: str) -> KnowledgeItem | None:
        return self.knowledge_base.get(knowledge_id)

    def search(self, query: str = "", knowledge_type: KnowledgeType = None, tags: list[str] = None) -> list[KnowledgeItem]:
        results = []
        for item in self.knowledge_base.values():
            if query and query.lower() not in item.title.lower() and query.lower() not in item.content.lower():
                continue
            if knowledge_type and item.knowledge_type != knowledge_type:
                continue
            if tags and not any(tag in item.tags for tag in tags):
                continue
            results.append(item)
        return results

    def export(self, path: str, format: str = "json"):
        data = {k: v.to_dict() for k, v in self.knowledge_base.items()}
        if format == "json":
            Path(path).write_text(json.dumps(data, indent=2))
        elif format == "yaml":
            Path(path).write_text(yaml.dump(data))

    def import_knowledge(self, path: str):
        data = json.loads(Path(path).read_text())
        for k, v in data.items():
            self.knowledge_base[k] = KnowledgeItem(**v)


import json

import yaml
