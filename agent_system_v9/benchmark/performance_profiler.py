"""
Performance Profiler - Runtime performance profiling
"""
import time
import asyncio
import threading
import functools
import hashlib
import cProfile
import pstats
import io
from typing import Dict, List, Optional, Any, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
from contextlib import contextmanager


class ProfilingMode(Enum):
    FUNCTION = "function"
    LINE = "line"
    MEMORY = "memory"
    ASYNC = "async"


@dataclass
class ProfileResult:
    function_name: str
    call_count: int
    total_time: float
    avg_time: float
    min_time: float
    max_time: float
    std_dev: float
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "function_name": self.function_name,
            "call_count": self.call_count,
            "total_time": self.total_time,
            "avg_time": self.avg_time,
            "min_time": self.min_time,
            "max_time": self.max_time,
            "std_dev": self.std_dev,
            "metadata": self.metadata,
        }


@dataclass
class ProfileSession:
    session_id: str
    mode: ProfilingMode
    start_time: float
    end_time: Optional[float] = None
    results: List[ProfileResult] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


class FunctionProfiler:
    def __init__(self):
        self.profiles: Dict[str, List[float]] = defaultdict(list)
        self.call_counts: Dict[str, int] = defaultdict(int)
        self._lock = threading.Lock()

    def profile(self, func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                with self._lock:
                    self.profiles[func.__name__].append(elapsed)
                    self.call_counts[func.__name__] += 1
        return wrapper

    async def aprofile(self, func: Callable) -> Callable:
        @functools.wraps(func)
        async def wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                elapsed = time.perf_counter() - start
                with self._lock:
                    self.profiles[func.__name__].append(elapsed)
                    self.call_counts[func.__name__] += 1
        return wrapper

    def get_results(self) -> List[ProfileResult]:
        with self._lock:
            results = []
            for func_name, times in self.profiles.items():
                if times:
                    results.append(ProfileResult(
                        function_name=func_name,
                        call_count=self.call_counts[func_name],
                        total_time=sum(times),
                        avg_time=sum(times) / len(times),
                        min_time=min(times),
                        max_time=max(times),
                        std_dev=self._std_dev(times),
                    ))
            return results

    def _std_dev(self, values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        return (sum((x - mean) ** 2 for x in values) / len(values)) ** 0.5

    def reset(self):
        with self._lock:
            self.profiles.clear()
            self.call_counts.clear()


class CProfileProfiler:
    def __init__(self):
        self.profiler = cProfile.Profile()
        self.running = False

    def start(self):
        self.profiler.enable()
        self.running = True

    def stop(self):
        self.profiler.disable()
        self.running = False

    def get_stats(self, sort_by: str = 'cumulative') -> str:
        s = io.StringIO()
        stats = pstats.Stats(self.profiler, stream=s)
        stats.sort_stats(sort_by)
        stats.print_stats(50)
        return s.getvalue()

    def get_results(self) -> List[ProfileResult]:
        results = []
        stats = pstats.Stats(self.profiler)
        for func, (cc, nc, tt, ct, callers) in stats.stats.items():
            func_name = f"{func[0]}:{func[1]}({func[2]})"
            results.append(ProfileResult(
                function_name=func_name,
                call_count=nc,
                total_time=tt,
                avg_time=tt / nc if nc > 0 else 0,
                min_time=0,
                max_time=0,
                std_dev=0,
            ))
        return results

    def reset(self):
        self.profiler = cProfile.Profile()


class MemoryProfiler:
    def __init__(self):
        self.snapshots: List[Dict[str, Any]] = []
        self._running = False

    def start(self):
        try:
            import tracemalloc
            tracemalloc.start()
            self._running = True
        except ImportError:
            pass

    def stop(self):
        try:
            import tracemalloc
            tracemalloc.stop()
            self._running = False
        except ImportError:
            pass

    def snapshot(self) -> Dict[str, Any]:
        try:
            import tracemalloc
            snapshot = tracemalloc.take_snapshot()
            stats = snapshot.statistics('lineno')
            return {
                "timestamp": time.time(),
                "total_memory": sum(stat.size for stat in stats),
                "top_allocations": [
                    {"file": str(stat.traceback), "size": stat.size, "count": stat.count}
                    for stat in stats[:10]
                ],
            }
        except ImportError:
            return {}

    def get_results(self) -> List[Dict[str, Any]]:
        return self.snapshots


class AsyncProfiler:
    def __init__(self):
        self.tasks: Dict[str, Dict] = {}
        self._lock = asyncio.Lock()

    async def profile(self, coro: Awaitable, name: str = None) -> Any:
        name = name or f"task_{len(self.tasks)}"
        start = time.perf_counter()
        task = asyncio.create_task(coro)
        self.tasks[name] = {"task": task, "start": start, "name": name}
        
        try:
            result = await task
            elapsed = time.perf_counter() - start
            self.tasks[name]["elapsed"] = elapsed
            self.tasks[name]["success"] = True
            return result
        except Exception as e:
            elapsed = time.perf_counter() - start
            self.tasks[name]["elapsed"] = elapsed
            self.tasks[name]["error"] = str(e)
            raise

    def get_results(self) -> List[ProfileResult]:
        results = []
        for name, info in self.tasks.items():
            if "elapsed" in info:
                results.append(ProfileResult(
                    function_name=name,
                    call_count=1,
                    total_time=info["elapsed"],
                    avg_time=info["elapsed"],
                    min_time=info["elapsed"],
                    max_time=info["elapsed"],
                    std_dev=0,
                    metadata={"success": info.get("success", False)},
                ))
        return results


class PerformanceProfiler:
    def __init__(self):
        self.function_profiler = FunctionProfiler()
        self.cprofile_profiler = CProfileProfiler()
        self.memory_profiler = MemoryProfiler()
        self.async_profiler = AsyncProfiler()
        self.sessions: List[ProfileSession] = []
        self._current_session: Optional[ProfileSession] = None

    @contextmanager
    def session(self, mode: ProfilingMode = ProfilingMode.FUNCTION, metadata: Dict = None):
        session = ProfileSession(
            session_id=hashlib.md5(f"{time.time()}".encode()).hexdigest()[:12],
            mode=mode,
            start_time=time.time(),
            metadata=metadata or {},
        )
        
        if mode == ProfilingMode.FUNCTION:
            self.function_profiler.reset()
        elif mode == ProfilingMode.LINE:
            self.cprofile_profiler.start()
        elif mode == ProfilingMode.MEMORY:
            self.memory_profiler.start()
        
        self._current_session = session
        
        try:
            yield session
        finally:
            session.end_time = time.time()
            
            if mode == ProfilingMode.FUNCTION:
                session.results = self.function_profiler.get_results()
            elif mode == ProfilingMode.LINE:
                self.cprofile_profiler.stop()
                session.results = self.cprofile_profiler.get_results()
            elif mode == ProfilingMode.MEMORY:
                self.memory_profiler.stop()
                session.results = self.memory_profiler.get_results()
            elif mode == ProfilingMode.ASYNC:
                session.results = self.async_profiler.get_results()
            
            self.sessions.append(session)
            self._current_session = None

    def profile_function(self, func: Callable) -> Callable:
        return self.function_profiler.profile(func)

    async def profile_async(self, func: Callable) -> Callable:
        return await self.function_profiler.aprofile(func)

    async def run_async(self, coro: Awaitable, name: str = None) -> Any:
        return await self.async_profiler.profile(coro, name)

    def get_session(self, session_id: str) -> Optional[ProfileSession]:
        for s in self.sessions:
            if s.session_id == session_id:
                return s
        return None

    def get_all_results(self) -> List[ProfileResult]:
        all_results = []
        for session in self.sessions:
            all_results.extend(session.results)
        return all_results

    def get_summary(self) -> Dict[str, Any]:
        all_results = self.get_all_results()
        return {
            "total_functions": len(set(r.function_name for r in all_results)),
            "total_calls": sum(r.call_count for r in all_results),
            "total_time": sum(r.total_time for r in all_results),
            "slowest_functions": sorted(all_results, key=lambda r: r.total_time, reverse=True)[:10],
            "most_called": sorted(all_results, key=lambda r: r.call_count, reverse=True)[:10],
        }


class ProfilerContext:
    def __init__(self, profiler: PerformanceProfiler):
        self.profiler = profiler

    def __enter__(self):
        return self.profiler

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


def profile(mode: ProfilingMode = ProfilingMode.FUNCTION):
    def decorator(func: Callable) -> Callable:
        profiler = PerformanceProfiler()
        
        if asyncio.iscoroutinefunction(func):
            @functools.wraps(func)
            async def async_wrapper(*args, **kwargs):
                with profiler.session(mode):
                    return await func(*args, **kwargs)
            return async_wrapper
        else:
            @functools.wraps(func)
            def sync_wrapper(*args, **kwargs):
                with profiler.session(mode):
                    return func(*args, **kwargs)
            return sync_wrapper
    
    return decorator