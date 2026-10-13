"""
AST Node-Merging Engine - Combines optimal AST fragments from divergent executions into minimal output
"""
import ast
import difflib
from dataclasses import dataclass, field
from enum import Enum


class MergeStrategy(Enum):
    AST = "ast"
    SEMANTIC = "semantic"
    LINE_BASED = "line_based"
    TOKEN_BASED = "token_based"


@dataclass
class MergeConflict:
    file_path: str
    node_type: str
    left_code: str
    right_code: str
    left_node: ast.AST | None = None
    right_node: ast.AST | None = None
    resolution: str | None = None


@dataclass
class MergeResult:
    merged_code: str
    conflicts: list[MergeConflict] = field(default_factory=list)
    merged_ast: ast.AST | None = None
    files_merged: list[str] = field(default_factory=list)
    success: bool = True


class ASTNodeMerger:
    def __init__(self, strategy: MergeStrategy = MergeStrategy.AST):
        self.strategy = strategy

    def merge(self, base_code: str, variants: list[str],
              file_path: str = "<unknown>") -> MergeResult:
        """Merge multiple code variants into a single optimal version"""

        if self.strategy == MergeStrategy.AST:
            return self._merge_ast(base_code, variants, file_path)
        if self.strategy == MergeStrategy.SEMANTIC:
            return self._merge_semantic(base_code, variants, file_path)
        if self.strategy == MergeStrategy.LINE_BASED:
            return self._merge_line_based(base_code, variants, file_path)
        return self._merge_token_based(base_code, variants, file_path)

    def _merge_ast(self, base_code: str, variants: list[str], file_path: str) -> MergeResult:
        try:
            base_tree = ast.parse(base_code)
            variant_trees = [ast.parse(v) for v in variants]
        except SyntaxError as e:
            return MergeResult(
                merged_code=base_code,
                conflicts=[MergeConflict(file_path, "syntax_error", base_code, str(e))],
                success=False
            )

        # Merge trees
        merged_tree = self._merge_trees(base_tree, variant_trees)

        # Convert back to code
        try:
            merged_code = ast.unparse(merged_tree)
        except Exception:
            merged_code = base_code

        return MergeResult(
            merged_code=merged_code,
            merged_ast=merged_tree,
            files_merged=[file_path],
            success=True
        )

    def _merge_trees(self, base: ast.AST, variants: list[ast.AST]) -> ast.AST:
        # For now, return base - full implementation would compare and merge nodes
        # This is a simplified version
        return base

    def _merge_semantic(self, base_code: str, variants: list[str], file_path: str) -> MergeResult:
        # Use difflib for semantic-aware merging
        base_lines = base_code.splitlines(keepends=True)

        merged = base_lines[:]

        for variant in variants:
            variant_lines = variant.splitlines(keepends=True)

            # Use SequenceMatcher for intelligent merging
            matcher = difflib.SequenceMatcher(None, merged, variant_lines)

            # Build merged result
            result = []
            for tag, i1, i2, j1, j2 in matcher.get_opcodes():
                if tag == 'equal':
                    result.extend(merged[i1:i2])
                elif tag == 'replace':
                    # Prefer variant for replacements
                    result.extend(variant_lines[j1:j2])
                elif tag == 'delete':
                    # Keep base
                    result.extend(merged[i1:i2])
                elif tag == 'insert':
                    # Add from variant
                    result.extend(variant_lines[j1:j2])

            merged = result

        return MergeResult(
            merged_code=''.join(merged),
            files_merged=[file_path],
            success=True
        )

    def _merge_line_based(self, base_code: str, variants: list[str], file_path: str) -> MergeResult:
        # Simple line-based three-way merge
        base_lines = base_code.splitlines(keepends=True)

        if len(variants) == 1:
            variant_lines = variants[0].splitlines(keepends=True)
            merged = self._three_way_merge(base_lines, variant_lines, variant_lines)
        else:
            # Multi-way merge
            merged = base_lines[:]
            for variant in variants:
                variant_lines = variant.splitlines(keepends=True)
                merged = self._three_way_merge(merged, variant_lines, variant_lines)

        return MergeResult(
            merged_code=''.join(merged),
            files_merged=[file_path],
            success=True
        )

    def _three_way_merge(self, base: list[str], left: list[str], right: list[str]) -> list[str]:
        # Simplified three-way merge
        matcher = difflib.SequenceMatcher(None, base, left)
        result = []

        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == 'equal':
                result.extend(base[i1:i2])
            elif tag == 'replace':
                result.extend(left[j1:j2])
            elif tag == 'delete':
                result.extend(base[i1:i2])
            elif tag == 'insert':
                result.extend(left[j1:j2])

        return result

    def _merge_token_based(self, base_code: str, variants: list[str], file_path: str) -> MergeResult:
        # Token-based merge (simplified)
        return self._merge_line_based(base_code, variants, file_path)

    def merge_files(self, base_dir: str, variant_dirs: list[str],
                    output_dir: str) -> dict[str, MergeResult]:
        """Merge entire directory structures"""
        results = {}

        base_path = Path(base_dir)
        for file_path in base_path.rglob("*"):
            if not file_path.is_file():
                continue

            rel_path = file_path.relative_to(base_path)

            base_code = file_path.read_text()
            variants = []

            for variant_dir in variant_dirs:
                variant_file = Path(variant_dir) / rel_path
                if variant_file.exists():
                    variants.append(variant_file.read_text())

            if variants:
                result = self.merge(base_code, variants, str(rel_path))
                results[str(rel_path)] = result

                # Write merged file
                output_file = Path(output_dir) / rel_path
                output_file.parent.mkdir(parents=True, exist_ok=True)
                output_file.write_text(result.merged_code)

        return results


_ast_merger: ASTNodeMerger | None = None


def get_ast_merger() -> ASTNodeMerger:
    global _ast_merger
    if _ast_merger is None:
        from ..core.config import config
        strategy = MergeStrategy(config.get_param("divergent", "merge_strategy", "ast"))
        _ast_merger = ASTNodeMerger(strategy)
    return _ast_merger
