"""
Artifact Bundler - Packaging and distribution of deployment artifacts
"""
import hashlib
import json
import tarfile
import zipfile
import time
import asyncio
from typing import Dict, List, Optional, Any, Set, Callable, IO, Tuple
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from collections import defaultdict
import tempfile
import shutil


class BundleFormat(Enum):
    TAR_GZ = "tar.gz"
    ZIP = "zip"
    TAR = "tar"
    DIR = "dir"


class CompressionLevel(Enum):
    NONE = 0
    LOW = 1
    MEDIUM = 6
    HIGH = 9


@dataclass
class Artifact:
    artifact_id: str
    name: str
    version: str
    path: str
    size: int
    hash: str
    content_type: str = "application/octet-stream"
    metadata: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "artifact_id": self.artifact_id,
            "name": self.name,
            "version": self.version,
            "path": self.path,
            "size": self.size,
            "hash": self.hash,
            "content_type": self.content_type,
            "metadata": self.metadata,
            "dependencies": self.dependencies,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Artifact':
        return cls(**data)


@dataclass
class BundleManifest:
    bundle_id: str
    name: str
    version: str
    artifacts: List[Artifact] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    hash: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "bundle_id": self.bundle_id,
            "name": self.name,
            "version": self.version,
            "artifacts": [a.to_dict() for a in self.artifacts],
            "metadata": self.metadata,
            "created_at": self.created_at,
            "hash": self.hash,
        }


@dataclass
class BundleConfig:
    format: BundleFormat = BundleFormat.TAR_GZ
    compression: CompressionLevel = CompressionLevel.MEDIUM
    include_manifest: bool = True
    verify_hashes: bool = True
    sign: bool = False
    signing_key: Optional[str] = None


class ArtifactHasher:
    @staticmethod
    def hash_file(file_path: str, algorithm: str = "sha256") -> str:
        hasher = hashlib.new(algorithm)
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                hasher.update(chunk)
        return hasher.hexdigest()

    @staticmethod
    def hash_data(data: bytes, algorithm: str = "sha256") -> str:
        hasher = hashlib.new(algorithm)
        hasher.update(data)
        return hasher.hexdigest()

    @staticmethod
    def verify_file(file_path: str, expected_hash: str, algorithm: str = "sha256") -> bool:
        return ArtifactHasher.hash_file(file_path, algorithm) == expected_hash


class ArtifactCollector:
    def __init__(self, root_path: str):
        self.root_path = Path(root_path)

    def collect(
        self,
        patterns: List[str] = None,
        exclude_patterns: List[str] = None,
    ) -> List[Artifact]:
        if patterns is None:
            patterns = ["**/*"]
        if exclude_patterns is None:
            exclude_patterns = ["**/__pycache__/**", "**/.git/**", "**/*.pyc"]
        
        artifacts = []
        for pattern in patterns:
            for file_path in self.root_path.glob(pattern):
                if file_path.is_file():
                    if self._should_exclude(file_path, exclude_patterns):
                        continue
                    
                    rel_path = file_path.relative_to(self.root_path)
                    artifact = Artifact(
                        artifact_id=hashlib.sha256(str(rel_path).encode()).hexdigest()[:16],
                        name=file_path.name,
                        version="1.0.0",
                        path=str(rel_path),
                        size=file_path.stat().st_size,
                        hash=ArtifactHasher.hash_file(str(file_path)),
                    )
                    artifacts.append(artifact)
        
        return artifacts

    def _should_exclude(self, path: Path, patterns: List[str]) -> bool:
        import fnmatch
        rel_path = str(path.relative_to(self.root_path))
        for pattern in patterns:
            if fnmatch.fnmatch(rel_path, pattern) or fnmatch.fnmatch(path.name, pattern):
                return True
        return False


class ArtifactBundler:
    def __init__(self, config: BundleConfig = None):
        self.config = config or BundleConfig()
        self.collector = ArtifactCollector(".")
        self.hasher = ArtifactHasher()

    def set_source(self, source_path: str):
        self.collector = ArtifactCollector(source_path)

    def create_bundle(
        self,
        name: str,
        version: str,
        artifacts: List[Artifact] = None,
        output_path: str = None,
        metadata: Dict[str, Any] = None,
    ) -> BundleManifest:
        if artifacts is None:
            artifacts = self.collector.collect()
        
        bundle_id = hashlib.sha256(f"{name}:{version}:{time.time()}".encode()).hexdigest()[:16]
        
        manifest = BundleManifest(
            bundle_id=bundle_id,
            name=name,
            version=version,
            artifacts=artifacts,
            metadata=metadata or {},
        )
        
        manifest.hash = self._compute_manifest_hash(manifest)
        
        if output_path:
            self._write_bundle(manifest, output_path)
        
        return manifest

    def _compute_manifest_hash(self, manifest: BundleManifest) -> str:
        data = json.dumps({
            "bundle_id": manifest.bundle_id,
            "name": manifest.name,
            "version": manifest.version,
            "artifacts": sorted([a.hash for a in manifest.artifacts]),
        }, sort_keys=True).encode()
        return hashlib.sha256(data).hexdigest()

    def _write_bundle(self, manifest: BundleManifest, output_path: str):
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        
        if self.config.format == BundleFormat.TAR_GZ:
            self._write_tar_gz(manifest, output)
        elif self.config.format == BundleFormat.ZIP:
            self._write_zip(manifest, output)
        elif self.config.format == BundleFormat.TAR:
            self._write_tar(manifest, output)
        elif self.config.format == BundleFormat.DIR:
            self._write_dir(manifest, output)

    def _write_tar_gz(self, manifest: BundleManifest, output: Path):
        with tarfile.open(output, f"w:gz", compresslevel=self.config.compression.value) as tar:
            if self.config.include_manifest:
                manifest_data = json.dumps(manifest.to_dict(), indent=2).encode()
                manifest_info = tarfile.TarInfo(name="manifest.json")
                manifest_info.size = len(manifest_data)
                tar.addfile(manifest_info, io.BytesIO(manifest_data))
            
            for artifact in manifest.artifacts:
                src = self.collector.root_path / artifact.path
                if src.exists():
                    tar.add(src, arcname=artifact.path)

    def _write_zip(self, manifest: BundleManifest, output: Path):
        with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED, compresslevel=self.config.compression.value) as zf:
            if self.config.include_manifest:
                manifest_data = json.dumps(manifest.to_dict(), indent=2).encode()
                zf.writestr("manifest.json", manifest_data)
            
            for artifact in manifest.artifacts:
                src = self.collector.root_path / artifact.path
                if src.exists():
                    zf.write(src, artifact.path)

    def _write_tar(self, manifest: BundleManifest, output: Path):
        with tarfile.open(output, "w") as tar:
            if self.config.include_manifest:
                manifest_data = json.dumps(manifest.to_dict(), indent=2).encode()
                manifest_info = tarfile.TarInfo(name="manifest.json")
                manifest_info.size = len(manifest_data)
                tar.addfile(manifest_info, io.BytesIO(manifest_data))
            
            for artifact in manifest.artifacts:
                src = self.collector.root_path / artifact.path
                if src.exists():
                    tar.add(src, arcname=artifact.path)

    def _write_dir(self, manifest: BundleManifest, output: Path):
        output.mkdir(parents=True, exist_ok=True)
        
        if self.config.include_manifest:
            (output / "manifest.json").write_text(json.dumps(manifest.to_dict(), indent=2))
        
        for artifact in manifest.artifacts:
            src = self.collector.root_path / artifact.path
            if src.exists():
                dst = output / artifact.path
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dst)

    def extract_bundle(self, bundle_path: str, extract_to: str) -> BundleManifest:
        path = Path(bundle_path)
        extract_path = Path(extract_to)
        extract_path.mkdir(parents=True, exist_ok=True)
        
        manifest = None
        
        if self.config.format == BundleFormat.TAR_GZ or self.config.format == BundleFormat.TAR:
            with tarfile.open(path, "r:*") as tar:
                tar.extractall(extract_path)
                manifest_file = extract_path / "manifest.json"
                if manifest_file.exists():
                    manifest = BundleManifest(**json.loads(manifest_file.read_text()))
        elif self.config.format == BundleFormat.ZIP:
            with zipfile.ZipFile(path, 'r') as zf:
                zf.extractall(extract_path)
                manifest_file = extract_path / "manifest.json"
                if manifest_file.exists():
                    manifest = BundleManifest(**json.loads(manifest_file.read_text()))
        
        if not manifest:
            manifest = self._reconstruct_manifest(extract_path)
        
        return manifest

    def _reconstruct_manifest(self, extract_path: Path) -> BundleManifest:
        artifacts = []
        for file_path in extract_path.rglob("*"):
            if file_path.is_file() and file_path.name != "manifest.json":
                rel_path = file_path.relative_to(extract_path)
                artifact = Artifact(
                    artifact_id=hashlib.sha256(str(rel_path).encode()).hexdigest()[:16],
                    name=file_path.name,
                    version="1.0.0",
                    path=str(rel_path),
                    size=file_path.stat().st_size,
                    hash=ArtifactHasher.hash_file(str(file_path)),
                )
                artifacts.append(artifact)
        
        return BundleManifest(
            bundle_id=hashlib.sha256(f"reconstructed:{time.time()}".encode()).hexdigest()[:16],
            name=extract_path.name,
            version="1.0.0",
            artifacts=artifacts,
        )

    def verify_bundle(self, bundle_path: str) -> Dict[str, Any]:
        manifest = self.extract_bundle(bundle_path, tempfile.mkdtemp())
        results = {
            "valid": True,
            "artifacts_verified": 0,
            "artifacts_failed": 0,
            "errors": [],
        }
        
        for artifact in manifest.artifacts:
            file_path = Path(bundle_path).parent / artifact.path
            if file_path.exists():
                if self.hasher.verify_file(str(file_path), artifact.hash):
                    results["artifacts_verified"] += 1
                else:
                    results["valid"] = False
                    results["artifacts_failed"] += 1
                    results["errors"].append(f"Hash mismatch: {artifact.path}")
            else:
                results["valid"] = False
                results["artifacts_failed"] += 1
                results["errors"].append(f"Missing file: {artifact.path}")
        
        return results


import io


class ArtifactRegistry:
    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.index: Dict[str, Artifact] = {}
        self.bundles: Dict[str, BundleManifest] = {}

    def register_artifact(self, artifact: Artifact) -> str:
        self.index[artifact.artifact_id] = artifact
        return artifact.artifact_id

    def register_bundle(self, manifest: BundleManifest) -> str:
        self.bundles[manifest.bundle_id] = manifest
        return manifest.bundle_id

    def get_artifact(self, artifact_id: str) -> Optional[Artifact]:
        return self.index.get(artifact_id)

    def get_bundle(self, bundle_id: str) -> Optional[BundleManifest]:
        return self.bundles.get(bundle_id)

    def list_artifacts(self, name_filter: str = None) -> List[Artifact]:
        artifacts = list(self.index.values())
        if name_filter:
            artifacts = [a for a in artifacts if name_filter in a.name]
        return artifacts

    def list_bundles(self, name_filter: str = None) -> List[BundleManifest]:
        bundles = list(self.bundles.values())
        if name_filter:
            bundles = [b for b in bundles if name_filter in b.name]
        return bundles

    def save_index(self):
        index_file = self.storage_path / "index.json"
        index_file.write_text(json.dumps({
            "artifacts": {k: v.to_dict() for k, v in self.index.items()},
            "bundles": {k: v.to_dict() for k, v in self.bundles.items()},
        }, indent=2))

    def load_index(self):
        index_file = self.storage_path / "index.json"
        if index_file.exists():
            data = json.loads(index_file.read_text())
            for k, v in data.get("artifacts", {}).items():
                self.index[k] = Artifact.from_dict(v)
            for k, v in data.get("bundles", {}).items():
                self.bundles[k] = BundleManifest(**v)


class DependencyResolver:
    def __init__(self, registry: ArtifactRegistry):
        self.registry = registry

    def resolve(self, artifact_ids: List[str]) -> List[Artifact]:
        resolved = []
        visited = set()
        
        def visit(art_id: str):
            if art_id in visited:
                return
            visited.add(art_id)
            
            artifact = self.registry.get_artifact(art_id)
            if artifact:
                for dep in artifact.dependencies:
                    visit(dep)
                resolved.append(artifact)
        
        for art_id in artifact_ids:
            visit(art_id)
        
        return resolved

    def check_conflicts(self, artifact_ids: List[str]) -> List[Tuple[str, str]]:
        conflicts = []
        seen = {}
        
        for art_id in artifact_ids:
            artifact = self.registry.get_artifact(art_id)
            if artifact:
                key = (artifact.name, artifact.version)
                if key in seen:
                    conflicts.append((seen[key], art_id))
                else:
                    seen[key] = art_id
        
        return conflicts