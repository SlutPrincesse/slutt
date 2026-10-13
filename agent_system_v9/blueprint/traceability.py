"""
Traceability Inspector - Tracks code-to-requirements traceability
"""
import hashlib
import json
import re
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from collections import defaultdict


class TraceabilityType(Enum):
    REQUIREMENT_TO_CODE = "requirement_to_code"
    CODE_TO_REQUIREMENT = "code_to_requirement"
    TEST_TO_CODE = "test_to_code"
    CODE_TO_TEST = "code_to_test"
    DOC_TO_CODE = "doc_to_code"
    CODE_TO_DOC = "code_to_doc"
    DEPENDENCY = "dependency"


class CoverageStatus(Enum):
    COVERED = "covered"
    PARTIAL = "partial"
    UNCOVERED = "uncovered"
    OBSOLETE = "obsolete"


@dataclass
class TraceLink:
    link_id: str
    source_type: str
    source_id: str
    target_type: str
    target_id: str
    traceability_type: TraceabilityType
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=lambda: __import__('time').time())

    def to_dict(self) -> Dict[str, Any]:
        return {
            "link_id": self.link_id,
            "source_type": self.source_type,
            "source_id": self.source_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "traceability_type": self.traceability_type.value,
            "confidence": self.confidence,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TraceLink':
        return cls(
            link_id=data["link_id"],
            source_type=data["source_type"],
            source_id=data["source_id"],
            target_type=data["target_type"],
            target_id=data["target_id"],
            traceability_type=TraceabilityType(data["traceability_type"]),
            confidence=data.get("confidence", 1.0),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", __import__('time').time()),
        )


@dataclass
class Requirement:
    req_id: str
    title: str
    description: str
    priority: str = "medium"
    status: str = "open"
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "req_id": self.req_id,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "tags": self.tags,
            "metadata": self.metadata,
        }


@dataclass
class CodeElement:
    element_id: str
    element_type: str
    name: str
    file_path: str
    line_start: int
    line_end: int
    signature: str = ""
    docstring: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "element_id": self.element_id,
            "element_type": self.element_type,
            "name": self.name,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "signature": self.signature,
            "docstring": self.docstring,
            "metadata": self.metadata,
        }


@dataclass
class CoverageReport:
    requirement_id: str
    status: CoverageStatus
    linked_elements: List[CodeElement]
    missing_elements: List[str]
    coverage_percentage: float
    gaps: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "status": self.status.value,
            "linked_elements": [e.to_dict() for e in self.linked_elements],
            "missing_elements": self.missing_elements,
            "coverage_percentage": self.coverage_percentage,
            "gaps": self.gaps,
        }


class TraceabilityInspector:
    def __init__(self):
        self.requirements: Dict[str, Requirement] = {}
        self.code_elements: Dict[str, CodeElement] = {}
        self.links: List[TraceLink] = []
        self._link_index: Dict[str, List[TraceLink]] = defaultdict(list)
        self._requirement_patterns = [
            r'(?i)(REQ|REQUIREMENT|USER STORY|US)[\s\-_:#]*([A-Z0-9\-]+)',
            r'(?i)(JIRA|TICKET|ISSUE)[\s\-_:#]*([A-Z0-9\-]+)',
            r'(?i)@requirement\s+([A-Z0-9\-]+)',
            r'(?i)#(\d+)',
        ]

    def add_requirement(self, requirement: Requirement):
        self.requirements[requirement.req_id] = requirement

    def load_requirements(self, path: str, format: str = "json"):
        if format == "json":
            data = json.loads(Path(path).read_text())
            for req_data in data:
                self.add_requirement(Requirement(**req_data))
        elif format == "markdown":
            self._parse_markdown_requirements(path)

    def _parse_markdown_requirements(self, path: str):
        content = Path(path).read_text()
        sections = re.split(r'^##\s+', content, flags=re.MULTILINE)
        
        for section in sections[1:]:
            lines = section.strip().split('\n')
            title = lines[0].strip()
            req_id_match = re.search(r'(?i)(REQ|REQUIREMENT|US)[\s\-_:#]*([A-Z0-9\-]+)', title)
            req_id = req_id_match.group(2) if req_id_match else hashlib.md5(title.encode()).hexdigest()[:8]
            
            description = '\n'.join(lines[1:]).strip()
            self.add_requirement(Requirement(req_id=req_id, title=title, description=description))

    def scan_codebase(self, root_path: str, extensions: List[str] = None):
        if extensions is None:
            extensions = ['.py', '.js', '.ts', '.java', '.go', '.rs', '.cpp', '.cs']
        
        for ext in extensions:
            for file_path in Path(root_path).rglob(f'*{ext}'):
                self._scan_file(str(file_path))

    def _scan_file(self, file_path: str):
        try:
            content = Path(file_path).read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return

        lines = content.split('\n')
        
        for i, line in enumerate(lines):
            req_ids = self._extract_requirement_ids(line)
            for req_id in req_ids:
                element_id = f"{file_path}:{i+1}"
                self._create_link(req_id, "requirement", element_id, "code", TraceabilityType.REQUIREMENT_TO_CODE)

        functions = self._extract_functions(content, file_path)
        for func in functions:
            self.code_elements[func.element_id] = func
            req_ids = self._extract_requirement_ids(func.docstring)
            for req_id in req_ids:
                self._create_link(req_id, "requirement", func.element_id, "code", TraceabilityType.REQUIREMENT_TO_CODE)

    def _extract_requirement_ids(self, text: str) -> List[str]:
        ids = []
        for pattern in self._requirement_patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                if isinstance(match, tuple):
                    ids.append(match[-1])
                else:
                    ids.append(match)
        return list(set(ids))

    def _extract_functions(self, content: str, file_path: str) -> List[CodeElement]:
        elements = []
        lines = content.split('\n')
        
        if file_path.endswith('.py'):
            elements.extend(self._extract_python_functions(content, file_path, lines))
        elif file_path.endswith(('.js', '.ts')):
            elements.extend(self._extract_js_functions(content, file_path, lines))
        
        return elements

    def _extract_python_functions(self, content: str, file_path: str, lines: List[str]) -> List[CodeElement]:
        import ast
        elements = []
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    element_id = f"{file_path}:{node.lineno}"
                    docstring = ast.get_docstring(node) or ""
                    signature = f"def {node.name}(...)"
                    if isinstance(node, ast.ClassDef):
                        signature = f"class {node.name}"
                    
                    elements.append(CodeElement(
                        element_id=element_id,
                        element_type="function" if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) else "class",
                        name=node.name,
                        file_path=file_path,
                        line_start=node.lineno,
                        line_end=getattr(node, 'end_lineno', node.lineno),
                        signature=signature,
                        docstring=docstring,
                    ))
        except SyntaxError:
            pass
        return elements

    def _extract_js_functions(self, content: str, file_path: str, lines: List[str]) -> List[CodeElement]:
        elements = []
        func_pattern = re.compile(r'(?:export\s+)?(?:async\s+)?function\s+(\w+)\s*\(|(\w+)\s*[:=]\s*(?:async\s+)?function\s*\(')
        
        for i, line in enumerate(lines):
            match = func_pattern.search(line)
            if match:
                name = match.group(1) or match.group(2)
                element_id = f"{file_path}:{i+1}"
                elements.append(CodeElement(
                    element_id=element_id,
                    element_type="function",
                    name=name,
                    file_path=file_path,
                    line_start=i+1,
                    line_end=i+1,
                    signature=line.strip(),
                ))
        return elements

    def _create_link(self, source_id: str, source_type: str, target_id: str, target_type: str, trace_type: TraceabilityType):
        link_id = hashlib.md5(f"{source_id}:{target_id}:{trace_type.value}".encode()).hexdigest()[:12]
        
        link = TraceLink(
            link_id=link_id,
            source_type=source_type,
            source_id=source_id,
            target_type=target_type,
            target_id=target_id,
            traceability_type=trace_type,
        )
        
        self.links.append(link)
        self._link_index[source_id].append(link)
        self._link_index[target_id].append(link)

    def get_links_for_requirement(self, req_id: str) -> List[TraceLink]:
        return self._link_index.get(req_id, [])

    def get_links_for_code(self, element_id: str) -> List[TraceLink]:
        return self._link_index.get(element_id, [])

    def check_coverage(self) -> List[CoverageReport]:
        reports = []
        
        for req_id, req in self.requirements.items():
            links = self.get_links_for_requirement(req_id)
            code_links = [l for l in links if l.target_type == "code"]
            
            linked_elements = []
            for link in code_links:
                if link.target_id in self.code_elements:
                    linked_elements.append(self.code_elements[link.target_id])
            
            if not linked_elements:
                status = CoverageStatus.UNCOVERED
                coverage = 0.0
            elif len(linked_elements) == 1:
                status = CoverageStatus.PARTIAL
                coverage = 50.0
            else:
                status = CoverageStatus.COVERED
                coverage = 100.0
            
            reports.append(CoverageReport(
                requirement_id=req_id,
                status=status,
                linked_elements=linked_elements,
                missing_elements=[],
                coverage_percentage=coverage,
                gaps=["No implementation found"] if status == CoverageStatus.UNCOVERED else [],
            ))
        
        return reports

    def generate_traceability_matrix(self) -> Dict[str, Any]:
        matrix = {
            "requirements": {},
            "code_elements": {},
            "links": [l.to_dict() for l in self.links],
        }
        
        for req_id, req in self.requirements.items():
            links = self.get_links_for_requirement(req_id)
            matrix["requirements"][req_id] = {
                "requirement": req.to_dict(),
                "linked_code": [l.target_id for l in links if l.target_type == "code"],
                "linked_tests": [l.target_id for l in links if l.target_type == "test"],
            }
        
        for elem_id, elem in self.code_elements.items():
            links = self.get_links_for_code(elem_id)
            matrix["code_elements"][elem_id] = {
                "element": elem.to_dict(),
                "linked_requirements": [l.source_id for l in links if l.source_type == "requirement"],
                "linked_tests": [l.target_id for l in links if l.target_type == "test"],
            }
        
        return matrix

    def export(self, path: str, format: str = "json"):
        data = {
            "requirements": {k: v.to_dict() for k, v in self.requirements.items()},
            "code_elements": {k: v.to_dict() for k, v in self.code_elements.items()},
            "links": [l.to_dict() for l in self.links],
        }
        
        if format == "json":
            Path(path).write_text(json.dumps(data, indent=2))
        elif format == "markdown":
            self._export_markdown(path, data)

    def _export_markdown(self, path: str, data: Dict):
        lines = ["# Traceability Report\n"]
        
        lines.append("## Requirements\n")
        for req_id, req in data["requirements"].items():
            lines.append(f"### {req_id}: {req['title']}\n")
            lines.append(f"{req['description']}\n")
            links = [l for l in data["links"] if l["source_id"] == req_id and l["target_type"] == "code"]
            if links:
                lines.append("**Linked Code:**\n")
                for link in links:
                    lines.append(f"- {link['target_id']}\n")
            lines.append("\n")
        
        Path(path).write_text('\n'.join(lines))


class DependencyAnalyzer:
    def __init__(self, inspector: TraceabilityInspector):
        self.inspector = inspector

    def analyze_dependencies(self, root_path: str) -> Dict[str, List[str]]:
        dependencies = defaultdict(set)
        
        for ext in ['.py', '.js', '.ts']:
            for file_path in Path(root_path).rglob(f'*{ext}'):
                deps = self._extract_dependencies(str(file_path))
                rel_path = str(file_path.relative_to(root_path))
                dependencies[rel_path] = deps
        
        return {k: list(v) for k, v in dependencies.items()}

    def _extract_dependencies(self, file_path: str) -> Set[str]:
        deps = set()
        try:
            content = Path(file_path).read_text(encoding='utf-8', errors='ignore')
        except Exception:
            return deps

        if file_path.endswith('.py'):
            import_pattern = re.compile(r'^(?:from\s+(\S+)\s+)?import\s+(\S+)', re.MULTILINE)
            for match in import_pattern.finditer(content):
                module = match.group(1) or match.group(2)
                if module and not module.startswith('.'):
                    deps.add(module.split('.')[0])
        
        elif file_path.endswith(('.js', '.ts')):
            import_pattern = re.compile(r'import\s+(?:.*?\s+from\s+)?[\'"]([^\'"]+)[\'"]')
            for match in import_pattern.finditer(content):
                module = match.group(1)
                if module.startswith('.'):
                    deps.add(module)
                else:
                    deps.add(module.split('/')[0])
        
        return deps

    def find_circular_dependencies(self, dependencies: Dict[str, List[str]]) -> List[List[str]]:
        visited = set()
        rec_stack = set()
        cycles = []

        def dfs(node: str, path: List[str]):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in dependencies.get(node, []):
                if neighbor not in visited:
                    dfs(neighbor, path.copy())
                elif neighbor in rec_stack:
                    cycle_start = path.index(neighbor)
                    cycles.append(path[cycle_start:] + [neighbor])

            rec_stack.remove(node)

        for node in dependencies:
            if node not in visited:
                dfs(node, [])

        return cycles