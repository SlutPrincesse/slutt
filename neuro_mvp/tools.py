"""Consent-gated tool registry.

Opt-in only. Tools are registered from an EXISTING local file (never fetched
from the network). Each install requires explicit human approval and records a
sha256 + source path so the binary can be verified later.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path
from typing import Callable

DEFAULT_REGISTRY = Path.home() / ".human" / "tools"
MANIFEST = DEFAULT_REGISTRY / "manifest.json"
BIN_DIR = DEFAULT_REGISTRY / "bin"

ApprovalFn = Callable[[str, str], bool]


class ToolRegistry:
    def __init__(self, manifest: Path = MANIFEST):
        self.manifest_path = Path(manifest)
        self.tools = self._load()

    def _load(self) -> dict:
        if self.manifest_path.exists():
            try:
                return json.loads(self.manifest_path.read_text())
            except json.JSONDecodeError:
                pass
        return {"tools": []}

    def save(self) -> None:
        self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(json.dumps(self.tools, indent=2))

    @staticmethod
    def _sha256(path: Path) -> str:
        h = hashlib.sha256()
        h.update(path.read_bytes())
        return h.hexdigest()

    def install(self, name: str, source: Path, approval: ApprovalFn) -> bool:
        source = Path(source)
        if not source.exists():
            raise FileNotFoundError(source)
        # No network. The tool must already exist locally.
        if not approval(name, str(source)):
            return False
        BIN_DIR.mkdir(parents=True, exist_ok=True)
        dest = BIN_DIR / name
        shutil.copy(source, dest)
        dest.chmod(0o755)
        self.tools["tools"].append(
            {
                "name": name,
                "source": str(source),
                "installed": str(dest),
                "sha256": self._sha256(dest),
            }
        )
        self.save()
        return True

    def remove(self, name: str) -> None:
        self.tools["tools"] = [t for t in self.tools["tools"] if t["name"] != name]
        self.save()

    def list(self) -> list:
        return self.tools["tools"]
