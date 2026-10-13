"""
Memory Compiler - Compiles code to memory for hot execution
"""
import ast
import asyncio
import hashlib
import pathlib
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Set


class CompilationTarget(Enum):
    BYTECODE = "bytecode"
    AST = "ast"
    SOURCE = "source"
    NATIVE = "native"


class CompilationStatus(Enum):
    PENDING = "pending"
    COMPILING = "compiling"
    COMPILED = "compiled"
    FAILED = "failed"
    CACHED = "cached"


@dataclass
class CompilationUnit:
    unit_id: str
    source: str
    file_path: str = "<memory>"
    target: CompilationTarget = CompilationTarget.BYTECODE
    status: CompilationStatus = CompilationStatus.PENDING
    compiled_code: Any = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    compiled_at: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "file_path": self.file_path,
            "target": self.target.value,
            "status": self.status.value,
            "error": self.error,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "compiled_at": self.compiled_at,
        }


@dataclass
class CompilationResult:
    unit: CompilationUnit
    success: bool
    output: Any = None
    error: str | None = None
    duration: float = 0.0


class MemoryCache:
    def __init__(self, max_size: int = 1000, ttl: float = 3600) -> None:
        self.max_size = max_size
        self.ttl = ttl
        self.cache: dict[str, CompilationUnit] = {}
        self.access_times: dict[str, float] = {}
        self._lock = threading.RLock()

    def get(self, key: str) -> CompilationUnit | None:
        with self._lock:
            unit = self.cache.get(key)
            if unit and time.time() - self.access_times.get(key, 0) < self.ttl:
                self.access_times[key] = time.time()
                return unit
            if unit:
                self.cache.pop(key, None)
                self.access_times.pop(key, None)
            return None

    def set(self, key: str, unit: CompilationUnit) -> None:
        with self._lock:
            if len(self.cache) >= self.max_size and key not in self.cache:
                oldest = min(self.access_times, key=self.access_times.get)
                self.cache.pop(oldest, None)
                self.access_times.pop(oldest, None)

            self.cache[key] = unit
            self.access_times[key] = time.time()

    def invalidate(self, key: str) -> bool:
        with self._lock:
            if key in self.cache:
                self.cache.pop(key)
                self.access_times.pop(key, None)
                return True
        return False

    def clear(self) -> None:
        with self._lock:
            self.cache.clear()
            self.access_times.clear()


class BaseCompiler(ABC):
    @abstractmethod
    def compile(self, unit: CompilationUnit) -> CompilationResult:
        pass

    @abstractmethod
    def execute(self, unit: CompilationUnit, *args: Any, **kwargs: Any) -> Any:
        pass


class BytecodeCompiler(BaseCompiler):
    def compile(self, unit: CompilationUnit) -> CompilationResult:
        start = time.time()
        try:
            tree = ast.parse(unit.source)
            code_obj = compile(tree, unit.file_path, 'exec')
            unit.compiled_code = code_obj
            unit.status = CompilationStatus.COMPILED
            unit.compiled_at = time.time()
            return CompilationResult(unit, True, code_obj, duration=time.time() - start)
        except Exception as e:
            unit.status = CompilationStatus.FAILED
            unit.error = str(e)
            return CompilationResult(unit, False, error=str(e), duration=time.time() - start)

    def execute(self, unit: CompilationUnit, *args: Any, **kwargs: Any) -> Any:
        if unit.compiled_code:
            namespace: dict[str, Any] = {}
            exec(unit.compiled_code, namespace, namespace)
            return namespace
        return None


class ASTCompiler(BaseCompiler):
    def compile(self, unit: CompilationUnit) -> CompilationResult:
        start = time.time()
        try:
            tree = ast.parse(unit.source)
            unit.compiled_code = tree
            unit.status = CompilationStatus.COMPILED
            unit.compiled_at = time.time()
            return CompilationResult(unit, True, tree, duration=time.time() - start)
        except Exception as e:
            unit.status = CompilationStatus.FAILED
            unit.error = str(e)
            return CompilationResult(unit, False, error=str(e), duration=time.time() - start)

    def execute(self, unit: CompilationUnit, *args: Any, **kwargs: Any) -> Any:
        if unit.compiled_code:
            code_obj = compile(unit.compiled_code, unit.file_path, 'exec')
            namespace: dict[str, Any] = {}
            exec(code_obj, namespace, namespace)
            return namespace
        return None


class JITCompiler:
    def __init__(self) -> None:
        self.compilers: dict[CompilationTarget, BaseCompiler] = {
            CompilationTarget.BYTECODE: BytecodeCompiler(),
            CompilationTarget.AST: ASTCompiler(),
        }
        self.cache = MemoryCache()
        self.compilation_history: list[CompilationResult] = []
        self._lock = threading.RLock()

    def register_compiler(self, target: CompilationTarget, compiler: BaseCompiler) -> None:
        self.compilers[target] = compiler

    def compile(
        self,
        source: str,
        target: CompilationTarget = CompilationTarget.BYTECODE,
        file_path: str = "<memory>",
        use_cache: bool = True,
    ) -> CompilationResult:
        cache_key = hashlib.md5(f"{source}:{target.value}".encode()).hexdigest()

        if use_cache:
            cached = self.cache.get(cache_key)
            if cached and cached.status == CompilationStatus.COMPILED:
                cached.status = CompilationStatus.CACHED
                return CompilationResult(cached, True, cached.compiled_code, duration=0)

        unit = CompilationUnit(
            unit_id=cache_key,
            source=source,
            file_path=file_path,
            target=target,
        )

        if target not in self.compilers:
            return CompilationResult(unit, False, error=f"No compiler for target: {target}")

        compiler = self.compilers[target]
        result = compiler.compile(unit)

        with self._lock:
            self.compilation_history.append(result)
            if len(self.compilation_history) > 1000:
                self.compilation_history = self.compilation_history[-1000:]

        if result.success and use_cache:
            self.cache.set(cache_key, unit)

        return result

    def execute(
        self,
        source: str,
        target: CompilationTarget = CompilationTarget.BYTECODE,
        *args: Any,
        **kwargs: Any
    ) -> Any:
        result = self.compile(source, target)
        if not result.success:
            raise RuntimeError(f"Compilation failed: {result.error}")

        compiler = self.compilers[target]
        return compiler.execute(result.unit, *args, **kwargs)

    def compile_async(
        self,
        source: str,
        target: CompilationTarget = CompilationTarget.BYTECODE,
    ) -> Awaitable[CompilationResult]:
        return asyncio.get_event_loop().run_in_executor(None, self.compile, source, target)

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            total = len(self.compilation_history)
            successful = sum(1 for r in self.compilation_history if r.success)
            failed = total - successful
            avg_duration = sum(r.duration for r in self.compilation_history) / max(total, 1)
            return {
                "total_compilations": total,
                "successful": successful,
                "failed": failed,
                "success_rate": successful / max(total, 1),
                "avg_duration": avg_duration,
                "cache_size": len(self.cache.cache),
            }


class HotReloader:
    def __init__(self, jit_compiler: JITCompiler) -> None:
        self.jit = jit_compiler
        self.watched_files: dict[str, dict[str, Any]] = {}
        self.callbacks: list[Callable[[str, CompilationResult], Any]] = []
        self._running = False
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    def watch_file(self, file_path: str, target: CompilationTarget = CompilationTarget.BYTECODE) -> None:
        self.watched_files[file_path] = {
            "target": target,
            "last_mtime": pathlib.Path(file_path).stat().st_mtime if pathlib.Path(file_path).exists() else 0,
        }

    def on_reload(self, callback: Callable[[str, CompilationResult], Any]) -> None:
        self.callbacks.append(callback)

    async def _watch_loop(self) -> None:
        while self._running:
            await asyncio.sleep(1.0)
            for file_path, info in self.watched_files.items():
                try:
                    mtime = pathlib.Path(file_path).stat().st_mtime
                    if mtime > info["last_mtime"]:
                        info["last_mtime"] = mtime
                        source = pathlib.Path(file_path).read_text()
                        result = self.jit.compile(source, info["target"], file_path)
                        for callback in self.callbacks:
                            try:
                                if asyncio.iscoroutinefunction(callback):
                                    await callback(file_path, result)
                                else:
                                    callback(file_path, result)
                            except Exception:
                                pass
                except Exception:
                    pass


class CompilationPipeline:
    def __init__(self) -> None:
        self.stages: list[Callable[[str], str]] = []
        self.jit = JITCompiler()

    def add_stage(self, stage: Callable[[str], str]) -> None:
        self.stages.append(stage)

    def compile(self, source: str, target: CompilationTarget = CompilationTarget.BYTECODE) -> CompilationResult:
        current = source
        for stage in self.stages:
            current = stage(current)
        return self.jit.compile(current, target)


class IncrementalCompiler:
    def __init__(self, jit_compiler: JITCompiler) -> None:
        self.jit = jit_compiler
        self.dependency_graph: defaultdict[str, Set[str]] = defaultdict(set)
        self._lock = threading.RLock()

    def add_dependency(self, source_file: str, dependency: str) -> None:
        with self._lock:
            self.dependency_graph[source_file].add(dependency)

    def compile_project(self, file_paths: list[str]) -> dict[str, CompilationResult]:
        results: dict[str, CompilationResult] = {}
        for file_path in file_paths:
            source = pathlib.Path(file_path).read_text()
            result = self.jit.compile(source, file_path=file_path)
            results[file_path] = result
        return results

    def recompile_changed(self, file_path: str) -> dict[str, CompilationResult]:
        with self._lock:
            affected: set[str] = {file_path}
            for src, deps in self.dependency_graph.items():
                if file_path in deps:
                    affected.add(src)

        results: dict[str, CompilationResult] = {}
        for f in affected:
            if f == file_path:
                source = pathlib.Path(f).read_text()
                results[f] = self.jit.compile(source, file_path=f)
        return results