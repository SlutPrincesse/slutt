"""
Integrity Verifier - File and system integrity verification
"""
import hashlib
import os
import json
import time
import threading
from typing import Dict, List, Optional, Any, Set, Callable
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from collections import defaultdict
import hmac


class IntegrityStatus(Enum):
    VERIFIED = "verified"
    MODIFIED = "modified"
    MISSING = "missing"
    NEW = "new"
    ERROR = "error"
    SKIPPED = "skipped"


class HashAlgorithm(Enum):
    SHA256 = "sha256"
    SHA512 = "sha512"
    BLAKE2B = "blake2b"
    SHA3_256 = "sha3_256"


@dataclass
class FileIntegrityRecord:
    path: str
    algorithm: HashAlgorithm
    hash: str
    size: int
    mtime: float
    mode: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    verified_at: Optional[float] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "algorithm": self.algorithm.value,
            "hash": self.hash,
            "size": self.size,
            "mtime": self.mtime,
            "mode": self.mode,
            "metadata": self.metadata,
            "verified_at": self.verified_at,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'FileIntegrityRecord':
        return cls(
            path=data["path"],
            algorithm=HashAlgorithm(data["algorithm"]),
            hash=data["hash"],
            size=data["size"],
            mtime=data["mtime"],
            mode=data["mode"],
            metadata=data.get("metadata", {}),
            verified_at=data.get("verified_at"),
        )


@dataclass
class VerificationResult:
    path: str
    status: IntegrityStatus
    expected: Optional[FileIntegrityRecord] = None
    actual: Optional[FileIntegrityRecord] = None
    error: Optional[str] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "path": self.path,
            "status": self.status.value,
            "expected": self.expected.to_dict() if self.expected else None,
            "actual": self.actual.to_dict() if self.actual else None,
            "error": self.error,
            "timestamp": self.timestamp,
        }


@dataclass
class IntegrityReport:
    scan_id: str
    root_path: str
    results: List[VerificationResult]
    scan_duration: float
    total_files: int
    verified: int
    modified: int
    missing: int
    new_files: int
    errors: int
    timestamp: float = field(default_factory=time.time)

    def summary(self) -> Dict[str, int]:
        return {
            "total": self.total_files,
            "verified": self.verified,
            "modified": self.modified,
            "missing": self.missing,
            "new": self.new_files,
            "errors": self.errors,
        }


class Hasher:
    def __init__(self, algorithm: HashAlgorithm = HashAlgorithm.SHA256):
        self.algorithm = algorithm

    def hash_file(self, path: str) -> str:
        hasher = self._get_hasher()
        try:
            with open(path, 'rb') as f:
                for chunk in iter(lambda: f.read(8192), b''):
                    hasher.update(chunk)
        except Exception:
            return ""
        return hasher.hexdigest()

    def hash_data(self, data: bytes) -> str:
        hasher = self._get_hasher()
        hasher.update(data)
        return hasher.hexdigest()

    def _get_hasher(self):
        if self.algorithm == HashAlgorithm.SHA256:
            return hashlib.sha256()
        elif self.algorithm == HashAlgorithm.SHA512:
            return hashlib.sha512()
        elif self.algorithm == HashAlgorithm.BLAKE2B:
            return hashlib.blake2b()
        elif self.algorithm == HashAlgorithm.SHA3_256:
            return hashlib.sha3_256()
        return hashlib.sha256()


class IntegrityStore:
    def __init__(self, store_path: str):
        self.store_path = store_path
        self.records: Dict[str, FileIntegrityRecord] = {}
        self._lock = threading.RLock()
        self._load()

    def _load(self):
        if not os.path.exists(self.store_path):
            return
        try:
            with open(self.store_path, 'r') as f:
                data = json.load(f)
                for record_data in data.get("records", []):
                    record = FileIntegrityRecord.from_dict(record_data)
                    self.records[record.path] = record
        except Exception:
            pass

    def save(self):
        with self._lock:
            data = {
                "version": 1,
                "algorithm": list(self.records.values())[0].algorithm.value if self.records else HashAlgorithm.SHA256.value,
                "records": [r.to_dict() for r in self.records.values()],
            }
            with open(self.store_path, 'w') as f:
                json.dump(data, f, indent=2)

    def add(self, record: FileIntegrityRecord):
        with self._lock:
            self.records[record.path] = record

    def get(self, path: str) -> Optional[FileIntegrityRecord]:
        with self._lock:
            return self.records.get(path)

    def remove(self, path: str) -> bool:
        with self._lock:
            if path in self.records:
                del self.records[path]
                return True
        return False

    def get_all(self) -> Dict[str, FileIntegrityRecord]:
        with self._lock:
            return dict(self.records)

    def clear(self):
        with self._lock:
            self.records.clear()


class IntegrityVerifier:
    def __init__(
        self,
        store: IntegrityStore,
        algorithm: HashAlgorithm = HashAlgorithm.SHA256,
        follow_symlinks: bool = False,
        exclude_patterns: List[str] = None,
    ):
        self.store = store
        self.hasher = Hasher(algorithm)
        self.follow_symlinks = follow_symlinks
        self.exclude_patterns = exclude_patterns or [
            "*.pyc", "__pycache__", ".git", ".svn", ".hg",
            "*.tmp", "*.temp", "*.log", "*.pid", "*.lock",
            "node_modules", ".venv", "venv", "env",
        ]
        self._lock = threading.RLock()
        self.callbacks: List[Callable[[VerificationResult], None]] = []

    def add_callback(self, callback: Callable[[VerificationResult], None]):
        self.callbacks.append(callback)

    def _should_exclude(self, path: str) -> bool:
        path_obj = Path(path)
        for pattern in self.exclude_patterns:
            if path_obj.match(pattern) or any(p.match(pattern) for p in path_obj.parents):
                return True
        return False

    def _get_file_record(self, path: str) -> FileIntegrityRecord:
        stat = os.stat(path, follow_symlinks=self.follow_symlinks)
        file_hash = self.hasher.hash_file(path)
        return FileIntegrityRecord(
            path=path,
            algorithm=self.hasher.algorithm,
            hash=file_hash,
            size=stat.st_size,
            mtime=stat.st_mtime,
            mode=stat.st_mode,
        )

    def verify_file(self, path: str) -> VerificationResult:
        if self._should_exclude(path):
            return VerificationResult(path=path, status=IntegrityStatus.SKIPPED)

        expected = self.store.get(path)
        if not expected:
            actual = self._get_file_record(path)
            if actual.hash:
                result = VerificationResult(
                    path=path,
                    status=IntegrityStatus.NEW,
                    actual=actual,
                )
            else:
                result = VerificationResult(
                    path=path,
                    status=IntegrityStatus.ERROR,
                    error="Failed to hash file",
                )
        else:
            actual = self._get_file_record(path)
            if not actual.hash:
                result = VerificationResult(
                    path=path,
                    status=IntegrityStatus.ERROR,
                    expected=expected,
                    error="Failed to hash file",
                )
            elif actual.hash == expected.hash:
                actual.verified_at = time.time()
                result = VerificationResult(
                    path=path,
                    status=IntegrityStatus.VERIFIED,
                    expected=expected,
                    actual=actual,
                )
            else:
                result = VerificationResult(
                    path=path,
                    status=IntegrityStatus.MODIFIED,
                    expected=expected,
                    actual=actual,
                )

        for callback in self.callbacks:
            try:
                callback(result)
            except Exception:
                pass

        return result

    def verify_directory(self, root_path: str) -> IntegrityReport:
        import time
        start_time = time.time()
        
        root = Path(root_path).resolve()
        all_files = []
        
        for file_path in root.rglob('*'):
            if file_path.is_file() and not self._should_exclude(str(file_path)):
                all_files.append(str(file_path))

        results = []
        verified = 0
        modified = 0
        missing = 0
        new_files = 0
        errors = 0

        for file_path in all_files:
            result = self.verify_file(file_path)
            results.append(result)
            
            if result.status == IntegrityStatus.VERIFIED:
                verified += 1
            elif result.status == IntegrityStatus.MODIFIED:
                modified += 1
            elif result.status == IntegrityStatus.MISSING:
                missing += 1
            elif result.status == IntegrityStatus.NEW:
                new_files += 1
            elif result.status == IntegrityStatus.ERROR:
                errors += 1

        stored_paths = set(self.store.get_all().keys())
        scanned_paths = set(all_files)
        for stored_path in stored_paths - scanned_paths:
            if not self._should_exclude(stored_path):
                result = VerificationResult(
                    path=stored_path,
                    status=IntegrityStatus.MISSING,
                    expected=self.store.get(stored_path),
                )
                results.append(result)
                missing += 1

        duration = time.time() - start_time
        scan_id = hashlib.md5(f"{root_path}:{time.time()}".encode()).hexdigest()[:12]

        report = IntegrityReport(
            scan_id=scan_id,
            root_path=str(root),
            results=results,
            scan_duration=duration,
            total_files=len(all_files) + missing,
            verified=verified,
            modified=modified,
            missing=missing,
            new_files=new_files,
            errors=errors,
        )
        
        return report

    def initialize_baseline(self, root_path: str) -> IntegrityReport:
        root = Path(root_path).resolve()
        count = 0
        
        for file_path in root.rglob('*'):
            if file_path.is_file() and not self._should_exclude(str(file_path)):
                record = self._get_file_record(str(file_path))
                if record.hash:
                    self.store.add(record)
                    count += 1

        self.store.save()
        
        return IntegrityReport(
            scan_id=hashlib.md5(f"baseline:{root_path}:{time.time()}".encode()).hexdigest()[:12],
            root_path=str(root),
            results=[],
            scan_duration=0,
            total_files=count,
            verified=0,
            modified=0,
            missing=0,
            new_files=count,
            errors=0,
        )

    def update_baseline(self, root_path: str, force: bool = False) -> IntegrityReport:
        report = self.verify_directory(root_path)
        
        for result in report.results:
            if result.status in (IntegrityStatus.VERIFIED, IntegrityStatus.NEW) and result.actual:
                self.store.add(result.actual)
            elif result.status == IntegrityStatus.MODIFIED and force and result.actual:
                self.store.add(result.actual)
            elif result.status == IntegrityStatus.MISSING:
                self.store.remove(result.path)

        self.store.save()
        return report

    def sign_baseline(self, key: bytes) -> str:
        data = json.dumps([r.to_dict() for r in self.store.get_all().values()], sort_keys=True).encode()
        return hmac.new(key, data, hashlib.sha256).hexdigest()

    def verify_signature(self, key: bytes, signature: str) -> bool:
        data = json.dumps([r.to_dict() for r in self.store.get_all().values()], sort_keys=True).encode()
        expected = hmac.new(key, data, hashlib.sha256).hexdigest()
        return hmac.compare_digest(expected, signature)