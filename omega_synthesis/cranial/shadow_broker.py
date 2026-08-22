import ast
import json
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from cranial.harvester import HarvesterEngine


@dataclass
class SkillCard:
    tool_name: str
    language: str
    public_signatures: List[str]
    execution_params: Dict[str, Any]
    sub_dependencies: List[str]
    risk_score: float
    install_path: str
    raw_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "language": self.language,
            "public_signatures": self.public_signatures,
            "execution_params": self.execution_params,
            "sub_dependencies": self.sub_dependencies,
            "risk_score": self.risk_score,
            "install_path": self.install_path,
            "raw_path": self.raw_path,
        }


class ShadowBroker:
    def __init__(self, registry_path: str = ".human/tools/manifest.json"):
        self.registry_path = Path(registry_path)
        self.registry_path.parent.mkdir(parents=True, exist_ok=True)
        self.harvester = HarvesterEngine()
        self._registry: Dict[str, SkillCard] = {}
        self._load_registry()

    def _load_registry(self) -> None:
        if self.registry_path.exists():
            data = json.loads(self.registry_path.read_text())
            for item in data:
                card = SkillCard(**item)
                self._registry[card.tool_name] = card

    def _save_registry(self) -> None:
        self.registry_path.write_text(
            json.dumps([c.to_dict() for c in self._registry.values()], indent=2)
        )

    def discover(self, query: str) -> List[Dict[str, str]]:
        print(f"[ShadowBroker] Searching for: {query}")
        return [
            {"name": "demo-cli", "url": "https://github.com/example/demo-cli", "language": "rust"},
            {"name": "mcp-server", "url": "https://github.com/example/mcp-server", "language": "python"},
        ]

    def ast_mine(self, repo_path: str) -> SkillCard:
        signatures: List[str] = []
        language = "unknown"
        root = Path(repo_path)
        for file in root.rglob("*.py"):
            try:
                source = file.read_text()
                tree = ast.parse(source)
                language = "python"
                for node in ast.walk(tree):
                    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        args = [a.arg for a in node.args.args]
                        signatures.append(f"{node.name}({', '.join(args)})")
            except Exception:
                continue

        risk_score = self._compute_risk_score(repo_path)
        card = SkillCard(
            tool_name=root.name,
            language=language,
            public_signatures=signatures[:10],
            execution_params={"binary": root.name},
            sub_dependencies=[],
            risk_score=risk_score,
            install_path=str(root),
            raw_path=repo_path,
        )
        return card

    def _compute_risk_score(self, path: str) -> float:
        score = 0.1
        try:
            for file in Path(path).rglob("*"):
                if file.is_file() and file.suffix in {".rs", ".c", ".cpp", ".go"}:
                    score += 0.1
                if file.is_file() and file.suffix in {".py"}:
                    text = file.read_text(errors="ignore")
                    if "ctypes" in text or "subprocess" in text:
                        score += 0.15
        except Exception:
            pass
        return min(score, 1.0)

    def compile_tool_plan(self, card: SkillCard) -> List[Dict[str, Any]]:
        return [
            {"step": "clone", "target": card.raw_path},
            {"step": "analyze", "target": card.tool_name},
            {"step": "compile", "target": card.tool_name},
            {"step": "register", "target": card.tool_name},
        ]

    def request_consent(self, card: SkillCard) -> bool:
        print("\n[ConsentGate] Tool Registration Request")
        print(f"  Name      : {card.tool_name}")
        print(f"  Language  : {card.language}")
        print(f"  Risk      : {card.risk_score:.2f}")
        print(f"  Install   : {card.install_path}")
        print(f"  Signatures: {len(card.public_signatures)}")
        choice = input("[ConsentGate] Approve registration? [y/N]: ").strip().lower()
        return choice == "y"

    def register(self, card: SkillCard) -> None:
        if not self.request_consent(card):
            print("[ShadowBroker] Registration cancelled by user.")
            return

        dest = Path.home() / ".human" / "bin" / card.tool_name
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            src = Path(card.raw_path) / card.tool_name
            if src.exists():
                dest.write_bytes(src.read_bytes())
        except Exception as exc:
            print(f"[ShadowBroker] Registration failed: {exc}")
            return

        self._registry[card.tool_name] = card
        self._save_registry()
        print(f"[ShadowBroker] Registered {card.tool_name}")

    def ingest_repo(self, repo_url: str) -> Optional[SkillCard]:
        with tempfile.TemporaryDirectory() as tmp:
            try:
                subprocess.run(["git", "clone", "--depth=1", repo_url, tmp], check=True, capture_output=True)
            except Exception as exc:
                print(f"[ShadowBroker] Clone failed: {exc}")
                return None

            card = self.ast_mine(tmp)
            plan = self.compile_tool_plan(card)
            print(f"[ShadowBroker] Plan: {plan}")
            if self.request_consent(card):
                dest = Path.home() / ".human" / "bin" / card.tool_name
                dest.parent.mkdir(parents=True, exist_ok=True)
                try:
                    subprocess.run(["cp", "-r", tmp, str(dest.parent / card.tool_name)], check=True, capture_output=True)
                except Exception as exc:
                    print(f"[ShadowBroker] Install failed: {exc}")
                    return None
                self._registry[card.tool_name] = card
                self._save_registry()
                print(f"[ShadowBroker] Ingested {card.tool_name}")
                return card
            print("[ShadowBroker] Ingestion rejected.")
            return None

    def list_registered(self) -> List[SkillCard]:
        return list(self._registry.values())
