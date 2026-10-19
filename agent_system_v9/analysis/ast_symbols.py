"""Tree-sitter based symbol extraction (graceful when unavailable)."""
from __future__ import annotations

from pathlib import Path
from typing import Any


def extract_symbols(path: str) -> dict[str, Any]:
    p = Path(path)
    if not p.exists():
        return {"success": False, "error": f"not found: {path}"}
    try:
        import tree_sitter_python as tspython
        from tree_sitter import Language, Parser
        lang = Language(tspython.language())
        parser = Parser(lang)
        code = p.read_bytes()
        tree = parser.parse(code)
        symbols = []
        def walk(node):
            if node.type in ("function_definition", "class_definition"):
                name_node = node.child_by_field_name("name")
                if name_node:
                    symbols.append({"type": node.type, "name": name_node.text.decode(), "line": node.start_point[0] + 1})
            for child in node.children:
                walk(child)
        walk(tree.root_node)
        return {"success": True, "symbols": symbols}
    except Exception as e:
        # fallback: regex
        try:
            import re
            text = p.read_text(encoding="utf-8", errors="replace")
            symbols = []
            for m in re.finditer(r"^(?:def|class)\s+(\w+)", text, re.M):
                symbols.append({"type": "unknown", "name": m.group(1), "line": text[:m.start()].count("\n") + 1})
            return {"success": True, "symbols": symbols, "fallback": True, "error": str(e)}
        except Exception as e2:
            return {"success": False, "error": str(e2)}
