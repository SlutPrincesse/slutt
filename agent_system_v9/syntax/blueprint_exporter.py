"""
Language-Neutral Blueprint Exporter - Compiles modular, language-agnostic design specs directly from codebases
"""
import ast
import json
import threading
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path


class BlueprintType(Enum):
    ARCHITECTURE = "architecture"
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    API = "api"
    DATA_MODEL = "data_model"
    INTERFACE = "interface"


@dataclass
class BlueprintSchema:
    schema_id: str
    blueprint_type: BlueprintType
    name: str
    description: str
    version: str = "1.0"
    components: List[Dict[str, Any]] = field(default_factory=list)
    relationships: List[Dict[str, Any]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_files: List[str] = field(default_factory=list)


class BlueprintExporter:
    def __init__(self):
        self._lock = threading.RLock()
        self._schemas: Dict[str, BlueprintSchema] = {}
        self._exporters: Dict[str, Callable] = {}
        self._register_default_exporters()
    
    def _register_default_exporters(self):
        self._exporters[".py"] = self._export_python
    
    def export_from_file(self, file_path: str, blueprint_type: BlueprintType = BlueprintType.MODULE) -> BlueprintSchema:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(file_path)
        
        ext = path.suffix
        exporter = self._exporters.get(ext)
        if not exporter:
            raise ValueError(f"No exporter for {ext}")
        
        with open(file_path, 'r') as f:
            content = f.read()
        
        schema = exporter(content, file_path, blueprint_type)
        
        with self._lock:
            self._schemas[schema.schema_id] = schema
        
        return schema
    
    def export_from_directory(self, dir_path: str, blueprint_type: BlueprintType = BlueprintType.MODULE) -> List[BlueprintSchema]:
        schemas = []
        for f in Path(dir_path).rglob("*.py"):
            try:
                schemas.append(self.export_from_file(str(f), blueprint_type))
            except Exception:
                pass
        return schemas
    
    def _export_python(self, content: str, file_path: str, blueprint_type: BlueprintType) -> BlueprintSchema:
        schema_id = f"bp_{hash(content) % 1000000}"
        
        try:
            tree = ast.parse(content)
        except SyntaxError:
            tree = None
        
        components = []
        relationships = []
        
        if tree:
            visitor = BlueprintVisitor(file_path)
            visitor.visit(tree)
            components = visitor.components
            relationships = visitor.relationships
        
        schema = BlueprintSchema(
            schema_id=schema_id,
            blueprint_type=blueprint_type,
            name=Path(file_path).stem,
            description=f"Blueprint for {file_path}",
            components=components,
            relationships=relationships,
            source_files=[file_path],
            metadata={"language": "python", "ast_nodes": len(components)}
        )
        
        return schema
    
    def export_to_json(self, schema: BlueprintSchema) -> str:
        data = asdict(schema)
        data["blueprint_type"] = schema.blueprint_type.value
        return json.dumps(data, indent=2)
    
    def export_to_file(self, schema: BlueprintSchema, output_path: str):
        with open(output_path, 'w') as f:
            f.write(self.export_to_json(schema))
    
    def get_schema(self, schema_id: str) -> Optional[BlueprintSchema]:
        with self._lock:
            return self._schemas.get(schema_id)
    
    def list_schemas(self) -> List[BlueprintSchema]:
        with self._lock:
            return list(self._schemas.values())
    
    def register_exporter(self, extension: str, exporter: Callable):
        self._exporters[extension] = exporter


class BlueprintVisitor(ast.NodeVisitor):
    def __init__(self, file_path: str):
        self.file_path = file_path
        self.components = []
        self.relationships = []
    
    def visit_ClassDef(self, node):
        self.components.append({
            "type": "class",
            "name": node.name,
            "line": node.lineno,
            "methods": [n.name for n in node.body if isinstance(n, ast.FunctionDef)],
            "bases": [ast.unparse(b) for b in node.bases],
            "decorators": [ast.unparse(d) for d in node.decorator_list]
        })
        self.generic_visit(node)
    
    def visit_FunctionDef(self, node):
        self.components.append({
            "type": "function",
            "name": node.name,
            "line": node.lineno,
            "args": [a.arg for a in node.args.args],
            "returns": ast.unparse(node.returns) if node.returns else None,
            "decorators": [ast.unparse(d) for d in node.decorator_list],
            "is_async": isinstance(node, ast.AsyncFunctionDef)
        })
        self.generic_visit(node)
    
    def visit_Import(self, node):
        for alias in node.names:
            self.relationships.append({
                "type": "import",
                "source": self.file_path,
                "target": alias.name,
                "alias": alias.asname
            })
        self.generic_visit(node)
    
    def visit_ImportFrom(self, node):
        module = node.module or ""
        for alias in node.names:
            self.relationships.append({
                "type": "import_from",
                "source": self.file_path,
                "target": f"{module}.{alias.name}",
                "alias": alias.asname
            })
        self.generic_visit(node)


_blueprint_exporter: Optional[BlueprintExporter] = None

def get_blueprint_exporter() -> BlueprintExporter:
    global _blueprint_exporter
    if _blueprint_exporter is None:
        _blueprint_exporter = BlueprintExporter()
    return _blueprint_exporter