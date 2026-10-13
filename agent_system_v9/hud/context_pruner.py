"""
AST Context Pruning Engine - Strips extraneous syntax, comments, and boilerplate from active context
"""
import ast
import re
import threading
from typing import Dict, List, Optional, Any, Callable, Set
from dataclasses import dataclass, field
from enum import Enum


class PruningLevel(Enum):
    MINIMAL = "minimal"      # Remove only comments and whitespace
    STANDARD = "standard"    # Remove comments, docstrings, type hints
    AGGRESSIVE = "aggressive"  # Remove all non-essential, keep only logic
    LOGIC_ONLY = "logic_only"  # Keep only control flow and calls


@dataclass
class PruningResult:
    original_code: str
    pruned_code: str
    original_tokens: int
    pruned_tokens: int
    compression_ratio: float
    removed_elements: List[str] = field(default_factory=list)
    preserved_elements: List[str] = field(default_factory=list)


class ASTContextPruner:
    def __init__(self, level: PruningLevel = PruningLevel.STANDARD):
        self.level = level
        self._lock = threading.RLock()
        self._preserve_patterns: List[re.Pattern] = []
        self._remove_patterns: List[re.Pattern] = []
        self._compile_patterns()
    
    def _compile_patterns(self):
        # Patterns to preserve (never remove)
        self._preserve_patterns = [
            re.compile(r'\b(def|class|async|await|return|yield|raise|import|from)\b'),
            re.compile(r'\b(if|else|elif|for|while|try|except|finally|with|match|case)\b'),
            re.compile(r'[{}()\[\]]'),
            re.compile(r'["\'].*?["\']'),  # Strings
        ]
        
        # Patterns to remove based on level
        self._remove_patterns = {
            PruningLevel.MINIMAL: [
                re.compile(r'#.*$', re.MULTILINE),
                re.compile(r'\s+', re.MULTILINE),
            ],
            PruningLevel.STANDARD: [
                re.compile(r'#.*$', re.MULTILINE),
                re.compile(r'""".*?"""', re.DOTALL),
                re.compile(r"'''.*?'''", re.DOTALL),
                re.compile(r':\s*\w+(\[\w+\])?\s*=', re.MULTILINE),  # Type hints in assignments
            ],
            PruningLevel.AGGRESSIVE: [
                re.compile(r'#.*$', re.MULTILINE),
                re.compile(r'""".*?"""', re.DOTALL),
                re.compile(r"'''.*?'''", re.DOTALL),
                re.compile(r':\s*\w+(\[\w+\])?\s*[=,)]', re.MULTILINE),  # All type hints
                re.compile(r'=\s*[^,\n\)]+', re.MULTILINE),  # Default values
                re.compile(r'\b(pass|continue|break)\b', re.MULTILINE),
            ],
            PruningLevel.LOGIC_ONLY: [
                re.compile(r'#.*$', re.MULTILINE),
                re.compile(r'""".*?"""', re.DOTALL),
                re.compile(r"'''.*?'''", re.DOTALL),
                re.compile(r':\s*\w+(\[\w+\])?\s*[=,)]', re.MULTILINE),
                re.compile(r'=\s*[^,\n\)]+', re.MULTILINE),
                re.compile(r'\b(pass|continue|break|del)\b', re.MULTILINE),
                re.compile(r'\b(import|from)\s+.*$', re.MULTILINE),
            ]
        }
    
    def prune(self, code: str, level: PruningLevel = None) -> PruningResult:
        level = level or self.level
        
        original_tokens = self._estimate_tokens(code)
        pruned = code
        removed = []
        preserved = []
        
        if level == PruningLevel.MINIMAL:
            pruned, removed, preserved = self._prune_minimal(pruned)
        elif level == PruningLevel.STANDARD:
            pruned, removed, preserved = self._prune_standard(pruned)
        elif level == PruningLevel.AGGRESSIVE:
            pruned, removed, preserved = self._prune_aggressive(pruned)
        elif level == PruningLevel.LOGIC_ONLY:
            pruned, removed, preserved = self._prune_logic_only(pruned)
        
        # Normalize whitespace
        pruned = re.sub(r'\n{3,}', '\n\n', pruned)
        pruned = re.sub(r'[ \t]+', ' ', pruned)
        
        pruned_tokens = self._estimate_tokens(pruned)
        ratio = pruned_tokens / original_tokens if original_tokens > 0 else 1.0
        
        return PruningResult(
            original_code=code,
            pruned_code=pruned.strip(),
            original_tokens=original_tokens,
            pruned_tokens=pruned_tokens,
            compression_ratio=ratio,
            removed_elements=removed,
            preserved_elements=preserved
        )
    
    def _prune_minimal(self, code: str) -> Tuple[str, List[str], List[str]]:
        removed = []
        preserved = []
        
        # Remove comments
        pruned = re.sub(r'#.*$', '', code, flags=re.MULTILINE)
        if pruned != code:
            removed.append("comments")
        
        # Normalize whitespace
        pruned = re.sub(r'[ \t]+', ' ', pruned)
        if pruned != code:
            removed.append("excess_whitespace")
        
        preserved.append("structure")
        preserved.append("docstrings")
        preserved.append("type_hints")
        
        return pruned, removed, preserved
    
    def _prune_standard(self, code: str) -> Tuple[str, List[str], List[str]]:
        pruned, removed, preserved = self._prune_minimal(code)
        
        # Remove docstrings
        docstring_pattern = re.compile(r'""".*?"""', re.DOTALL)
        if docstring_pattern.search(pruned):
            pruned = docstring_pattern.sub('', pruned)
            removed.append("docstrings")
        
        docstring_pattern2 = re.compile(r"'''.*?'''", re.DOTALL)
        if docstring_pattern2.search(pruned):
            pruned = docstring_pattern2.sub('', pruned)
            removed.append("docstrings_single")
        
        # Remove inline type hints from assignments
        pruned = re.sub(r':\s*\w+(\[\w+\])?\s*=', ' =', pruned)
        if pruned != code:
            removed.append("inline_type_hints")
        
        preserved.extend(["structure", "function_signatures", "control_flow"])
        
        return pruned, removed, preserved
    
    def _prune_aggressive(self, code: str) -> Tuple[str, List[str], List[str]]:
        pruned, removed, preserved = self._prune_standard(code)
        
        # Remove all type hints
        pruned = re.sub(r':\s*\w+(\[\w+\])?\s*[=,)]', lambda m: m.group().replace(m.group(1), ''), pruned)
        removed.append("all_type_hints")
        
        # Remove default values
        pruned = re.sub(r'=\s*[^,\n\)]+', '', pruned)
        removed.append("default_values")
        
        # Remove pass/continue/break
        pruned = re.sub(r'\b(pass|continue|break)\b', '', pruned)
        removed.append("noop_statements")
        
        preserved.extend(["core_logic", "function_calls", "control_flow"])
        
        return pruned, removed, preserved
    
    def _prune_logic_only(self, code: str) -> Tuple[str, List[str], List[str]]:
        pruned, removed, preserved = self._prune_aggressive(code)
        
        # Remove imports
        pruned = re.sub(r'\b(import|from)\s+.*$', '', pruned, flags=re.MULTILINE)
        removed.append("imports")
        
        # Remove del statements
        pruned = re.sub(r'\bdel\b', '', pruned)
        removed.append("del_statements")
        
        # Keep only essential
        preserved.extend(["control_flow", "function_calls", "assignments"])
        
        return pruned, removed, preserved
    
    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)
    
    def prune_ast(self, code: str, level: PruningLevel = None) -> PruningResult:
        """AST-aware pruning"""
        level = level or self.level
        
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return self.prune(code, level)
        
        # Walk AST and remove nodes based on level
        pruner = ASTPrunerVisitor(level)
        pruner.visit(tree)
        
        try:
            pruned = ast.unparse(tree)
        except Exception:
            pruned = code
        
        original_tokens = self._estimate_tokens(code)
        pruned_tokens = self._estimate_tokens(pruned)
        
        return PruningResult(
            original_code=code,
            pruned_code=pruned,
            original_tokens=original_tokens,
            pruned_tokens=pruned_tokens,
            compression_ratio=pruned_tokens / original_tokens if original_tokens > 0 else 1.0,
            removed_elements=pruner.removed,
            preserved_elements=pruner.preserved
        )
    
    def batch_prune(self, codes: List[str], level: PruningLevel = None) -> List[PruningResult]:
        return [self.prune(code, level) for code in codes]


class ASTPrunerVisitor(ast.NodeTransformer):
    def __init__(self, level: PruningLevel):
        self.level = level
        self.removed = []
        self.preserved = []
    
    def visit_FunctionDef(self, node):
        if self.level in (PruningLevel.AGGRESSIVE, PruningLevel.LOGIC_ONLY):
            # Remove docstring
            if (node.body and isinstance(node.body[0], ast.Expr) 
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
                self.removed.append("docstring")
                node.body = node.body[1:]
            
            # Remove type hints
            if self.level == PruningLevel.LOGIC_ONLY:
                node.returns = None
                for arg in node.args.args:
                    arg.annotation = None
        
        self.preserved.append(f"function:{node.name}")
        return self.generic_visit(node)
    
    def visit_ClassDef(self, node):
        if self.level in (PruningLevel.AGGRESSIVE, PruningLevel.LOGIC_ONLY):
            # Remove docstring
            if (node.body and isinstance(node.body[0], ast.Expr) 
                and isinstance(node.body[0].value, ast.Constant)
                and isinstance(node.body[0].value.value, str)):
                self.removed.append("docstring")
                node.body = node.body[1:]
        
        self.preserved.append(f"class:{node.name}")
        return self.generic_visit(node)
    
    def visit_Assign(self, node):
        if self.level == PruningLevel.LOGIC_ONLY:
            # Remove type annotations
            for target in node.targets:
                if isinstance(target, ast.AnnAssign):
                    self.removed.append("type_annotation")
                    return ast.Assign(targets=[target.target], value=target.value)
        return self.generic_visit(node)
    
    def visit_Pass(self, node):
        if self.level in (PruningLevel.AGGRESSIVE, PruningLevel.LOGIC_ONLY):
            self.removed.append("pass")
            return None
        return node
    
    def visit_Import(self, node):
        if self.level == PruningLevel.LOGIC_ONLY:
            self.removed.append("import")
            return None
        return node
    
    def visit_ImportFrom(self, node):
        if self.level == PruningLevel.LOGIC_ONLY:
            self.removed.append("import_from")
            return None
        return node


_context_pruner: Optional[ASTContextPruner] = None

def get_context_pruner() -> ASTContextPruner:
    global _context_pruner
    if _context_pruner is None:
        _context_pruner = ASTContextPruner()
    return _context_pruner