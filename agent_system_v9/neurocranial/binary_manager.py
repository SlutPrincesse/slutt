"""
Global Binary Directory Manager - Organizes, links, and registers verified binaries to tool manifest
"""
import os
import subprocess
import hashlib
import threading
import json
import time
import shutil
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field, asdict
from enum import Enum
from pathlib import Path


class BinaryStatus(Enum):
    UNVERIFIED = "unverified"
    VERIFIED = "verified"
    BLOCKED = "blocked"
    OUTDATED = "outdated"
    MISSING = "missing"


@dataclass
class BinaryEntry:
    binary_id: str
    name: str
    version: str
    path: str
    source: str  # "system", "package_manager", "custom", "downloaded"
    checksum: str
    status: BinaryStatus = BinaryStatus.UNVERIFIED
    installed_at: float = field(default_factory=time.time)
    verified_at: Optional[float] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    provides: List[str] = field(default_factory=list)  # Tool names this binary provides
    
    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BinaryEntry':
        data["status"] = BinaryStatus(data["status"])
        return cls(**data)


class GlobalBinaryManager:
    def __init__(self, binary_dir: str = None, manifest_path: str = None):
        self.binary_dir = Path(binary_dir) if binary_dir else Path.home() / ".agent_v9" / "bin"
        self.binary_dir.mkdir(parents=True, exist_ok=True)
        
        self.manifest_path = Path(manifest_path) if manifest_path else self.binary_dir / "manifest.json"
        self._binaries: Dict[str, BinaryEntry] = {}
        self._name_index: Dict[str, List[str]] = {}  # name -> binary_ids
        self._provides_index: Dict[str, str] = {}  # tool -> binary_id
        self._lock = threading.RLock()
        self._load_manifest()
    
    def _load_manifest(self):
        if self.manifest_path.exists():
            try:
                with open(self.manifest_path, 'r') as f:
                    data = json.load(f)
                
                for entry_data in data.get("binaries", []):
                    entry = BinaryEntry.from_dict(entry_data)
                    self._binaries[entry.binary_id] = entry
                    self._index_entry(entry)
            except Exception:
                pass
    
    def _save_manifest(self):
        try:
            data = {
                "version": 1,
                "updated_at": time.time(),
                "binaries": [entry.to_dict() for entry in self._binaries.values()]
            }
            with open(self.manifest_path, 'w') as f:
                json.dump(data, f, indent=2)
        except Exception:
            pass
    
    def _index_entry(self, entry: BinaryEntry):
        if entry.name not in self._name_index:
            self._name_index[entry.name] = []
        self._name_index[entry.name].append(entry.binary_id)
        
        for tool in entry.provides:
            self._provides_index[tool] = entry.binary_id
    
    def _unindex_entry(self, entry: BinaryEntry):
        if entry.name in self._name_index:
            if entry.binary_id in self._name_index[entry.name]:
                self._name_index[entry.name].remove(entry.binary_id)
            if not self._name_index[entry.name]:
                del self._name_index[entry.name]
        
        for tool in entry.provides:
            if self._provides_index.get(tool) == entry.binary_id:
                del self._provides_index[tool]
    
    def scan_system_binaries(self) -> List[BinaryEntry]:
        """Scan PATH for binaries and register them"""
        entries = []
        path_dirs = os.environ.get("PATH", "").split(os.pathsep)
        
        for path_dir in path_dirs:
            if not os.path.isdir(path_dir):
                continue
            
            try:
                for filename in os.listdir(path_dir):
                    filepath = os.path.join(path_dir, filename)
                    if not os.path.isfile(filepath) or not os.access(filepath, os.X_OK):
                        continue
                    
                    # Skip if already registered
                    if self.find_by_path(filepath):
                        continue
                    
                    entry = self.register_binary(
                        name=filename,
                        path=filepath,
                        source="system"
                    )
                    if entry:
                        entries.append(entry)
            except Exception:
                continue
        
        return entries
    
    def register_binary(self, name: str, path: str, source: str = "custom",
                       version: str = "", provides: List[str] = None,
                       dependencies: List[str] = None,
                       metadata: Dict[str, Any] = None) -> Optional[BinaryEntry]:
        
        path = os.path.abspath(path)
        if not os.path.exists(path):
            return None
        
        # Calculate checksum
        checksum = self._calculate_checksum(path)
        
        # Try to get version if not provided
        if not version:
            version = self._get_version(path)
        
        # Determine provides if not specified
        if provides is None:
            provides = [name]
        
        binary_id = hashlib.sha256(f"{name}:{path}:{checksum}".encode()).hexdigest()[:16]
        
        # Check if already exists
        with self._lock:
            if binary_id in self._binaries:
                return self._binaries[binary_id]
        
        entry = BinaryEntry(
            binary_id=binary_id,
            name=name,
            version=version,
            path=path,
            source=source,
            checksum=checksum,
            provides=provides,
            dependencies=dependencies or [],
            metadata=metadata or {}
        )
        
        with self._lock:
            self._binaries[binary_id] = entry
            self._index_entry(entry)
            self._save_manifest()
        
        return entry
    
    def _calculate_checksum(self, path: str) -> str:
        try:
            hasher = hashlib.sha256()
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    hasher.update(chunk)
            return hasher.hexdigest()
        except Exception:
            return ""
    
    def _get_version(self, path: str) -> str:
        try:
            result = subprocess.run([path, "--version"], capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                output = result.stdout.strip()
                # Extract version number
                import re
                match = re.search(r'(\d+\.\d+\.\d+)', output)
                if match:
                    return match.group(1)
                return output[:50]
        except Exception:
            pass
        return "unknown"
    
    def verify_binary(self, binary_id: str, expected_checksum: str = None) -> bool:
        with self._lock:
            entry = self._binaries.get(binary_id)
            if not entry:
                return False
        
        # Recalculate checksum
        current_checksum = self._calculate_checksum(entry.path)
        
        if expected_checksum and current_checksum != expected_checksum:
            with self._lock:
                entry.status = BinaryStatus.BLOCKED
                self._save_manifest()
            return False
        
        if current_checksum != entry.checksum:
            with self._lock:
                entry.status = BinaryStatus.BLOCKED
                self._save_manifest()
            return False
        
        with self._lock:
            entry.status = BinaryStatus.VERIFIED
            entry.verified_at = time.time()
            self._save_manifest()
        
        return True
    
    def verify_all(self) -> Dict[str, bool]:
        results = {}
        with self._lock:
            binary_ids = list(self._binaries.keys())
        
        for binary_id in binary_ids:
            results[binary_id] = self.verify_binary(binary_id)
        
        return results
    
    def find_by_name(self, name: str) -> List[BinaryEntry]:
        with self._lock:
            binary_ids = self._name_index.get(name, [])
            return [self._binaries[bid] for bid in binary_ids if bid in self._binaries]
    
    def find_by_path(self, path: str) -> Optional[BinaryEntry]:
        path = os.path.abspath(path)
        with self._lock:
            for entry in self._binaries.values():
                if os.path.abspath(entry.path) == path:
                    return entry
        return None
    
    def find_by_tool(self, tool_name: str) -> Optional[BinaryEntry]:
        with self._lock:
            binary_id = self._provides_index.get(tool_name)
            if binary_id:
                return self._binaries.get(binary_id)
        return None
    
    def get_binary_path(self, tool_name: str) -> Optional[str]:
        entry = self.find_by_tool(tool_name)
        return entry.path if entry else None
    
    def execute(self, tool_name: str, args: List[str], **kwargs) -> subprocess.CompletedProcess:
        entry = self.find_by_tool(tool_name)
        if not entry:
            raise FileNotFoundError(f"Tool not found: {tool_name}")
        
        if entry.status == BinaryStatus.BLOCKED:
            raise RuntimeError(f"Binary blocked: {tool_name}")
        
        cmd = [entry.path] + args
        return subprocess.run(cmd, **kwargs)
    
    def link_binary(self, binary_id: str, link_name: str = None) -> bool:
        with self._lock:
            entry = self._binaries.get(binary_id)
            if not entry:
                return False
        
        link_name = link_name or entry.name
        link_path = self.binary_dir / link_name
        
        try:
            if link_path.exists() or link_path.is_symlink():
                link_path.unlink()
            link_path.symlink_to(entry.path)
            return True
        except Exception:
            return False
    
    def unlink_binary(self, link_name: str) -> bool:
        link_path = self.binary_dir / link_name
        try:
            if link_path.is_symlink():
                link_path.unlink()
                return True
        except Exception:
            pass
        return False
    
    def remove_binary(self, binary_id: str) -> bool:
        with self._lock:
            entry = self._binaries.pop(binary_id, None)
            if not entry:
                return False
            
            self._unindex_entry(entry)
            self._save_manifest()
        
        return True
    
    def list_binaries(self, status: BinaryStatus = None) -> List[BinaryEntry]:
        with self._lock:
            entries = list(self._binaries.values())
        
        if status:
            entries = [e for e in entries if e.status == status]
        
        return entries
    
    def get_tool_manifest(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "tools": {
                    tool: {
                        "binary_id": bid,
                        "path": self._binaries[bid].path,
                        "version": self._binaries[bid].version,
                        "status": self._binaries[bid].status.value
                    }
                    for tool, bid in self._provides_index.items()
                    if bid in self._binaries
                },
                "total_binaries": len(self._binaries),
                "verified": len([e for e in self._binaries.values() if e.status == BinaryStatus.VERIFIED])
            }
    
    def update_binary(self, binary_id: str, new_path: str) -> bool:
        with self._lock:
            entry = self._binaries.get(binary_id)
            if not entry:
                return False
        
        if not os.path.exists(new_path):
            return False
        
        # Verify new binary
        new_checksum = self._calculate_checksum(new_path)
        new_version = self._get_version(new_path)
        
        with self._lock:
            entry.path = new_path
            entry.checksum = new_checksum
            entry.version = new_version
            entry.status = BinaryStatus.UNVERIFIED
            entry.verified_at = None
            self._save_manifest()
        
        return self.verify_binary(binary_id)
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            status_counts = {}
            for status in BinaryStatus:
                status_counts[status.value] = len([e for e in self._binaries.values() if e.status == status])
            
            return {
                "total": len(self._binaries),
                "by_status": status_counts,
                "by_source": {},
                "tools_provided": len(self._provides_index)
            }


_binary_manager: Optional[GlobalBinaryManager] = None

def get_binary_manager() -> GlobalBinaryManager:
    global _binary_manager
    if _binary_manager is None:
        _binary_manager = GlobalBinaryManager()
        _binary_manager.scan_system_binaries()
    return _binary_manager