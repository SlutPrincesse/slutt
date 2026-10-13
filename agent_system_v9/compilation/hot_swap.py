"""
Hot Swap Loader - Dynamic module loading and hot reloading
"""
import sys
import importlib
import importlib.util
import asyncio
import time
import hashlib
import threading
from typing import Dict, List, Optional, Any, Callable, Set, Type
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from collections import defaultdict
from contextlib import contextmanager


class LoadStatus(Enum):
    UNLOADED = "unloaded"
    LOADING = "loading"
    LOADED = "loaded"
    RELOADING = "reloading"
    FAILED = "failed"


@dataclass
class ModuleInfo:
    name: str
    file_path: str
    spec: Any = None
    module: Any = None
    status: LoadStatus = LoadStatus.UNLOADED
    version: int = 0
    last_modified: float = 0
    checksum: str = ""
    dependencies: List[str] = field(default_factory=list)
    dependents: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    loaded_at: Optional[float] = None
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "file_path": self.file_path,
            "status": self.status.value,
            "version": self.version,
            "last_modified": self.last_modified,
            "checksum": self.checksum,
            "dependencies": self.dependencies,
            "dependents": self.dependents,
            "metadata": self.metadata,
            "loaded_at": self.loaded_at,
            "error": self.error,
        }


@dataclass
class ReloadEvent:
    module_name: str
    old_version: int
    new_version: int
    timestamp: float = field(default_factory=time.time)
    success: bool = True
    error: Optional[str] = None


class HotSwapLoader:
    def __init__(self, watch_interval: float = 1.0):
        self.modules: Dict[str, ModuleInfo] = {}
        self.watch_interval = watch_interval
        self.callbacks: List[Callable] = []
        self._running = False
        self._watch_task: Optional[asyncio.Task] = None
        self._lock = threading.RLock()
        self._module_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.reload_history: List[ReloadEvent] = []

    def load_module(self, name: str, file_path: str = None) -> ModuleInfo:
        with self._lock:
            if name in self.modules:
                return self.modules[name]

            if file_path is None:
                file_path = self._find_module_path(name)

            info = ModuleInfo(name=name, file_path=file_path)
            self.modules[name] = info
            return self._do_load(info)

    def _find_module_path(self, name: str) -> str:
        spec = importlib.util.find_spec(name)
        if spec and spec.origin:
            return spec.origin
        return f"{name.replace('.', '/')}.py"

    def _do_load(self, info: ModuleInfo) -> ModuleInfo:
        info.status = LoadStatus.LOADING
        try:
            import os
            stat = os.stat(info.file_path)
            info.last_modified = stat.st_mtime
            info.checksum = self._compute_checksum(info.file_path)

            spec = importlib.util.spec_from_file_location(info.name, info.file_path)
            if spec is None:
                raise ImportError(f"Could not load spec for {info.name}")

            module = importlib.util.module_from_spec(spec)
            info.spec = spec
            info.module = module

            sys.modules[info.name] = module
            spec.loader.exec_module(module)

            info.status = LoadStatus.LOADED
            info.version += 1
            info.loaded_at = time.time()
            info.error = None

            self._register_dependencies(info)
        except Exception as e:
            info.status = LoadStatus.FAILED
            info.error = str(e)
        
        return info

    def _compute_checksum(self, file_path: str) -> str:
        try:
            content = Path(file_path).read_bytes()
            return hashlib.md5(content).hexdigest()
        except Exception:
            return ""

    def _register_dependencies(self, info: ModuleInfo):
        if info.module and hasattr(info.module, '__file__'):
            try:
                source = Path(info.file_path).read_text()
                tree = __import__('ast').parse(source)
                for node in __import__('ast').walk(tree):
                    if isinstance(node, __import__('ast').Import):
                        for alias in node.names:
                            info.dependencies.append(alias.name)
                    elif isinstance(node, __import__('ast').ImportFrom):
                        module = node.module or ""
                        for alias in node.names:
                            info.dependencies.append(f"{module}.{alias.name}")
            except Exception:
                pass

    def unload_module(self, name: str) -> bool:
        with self._lock:
            if name not in self.modules:
                return False
            
            info = self.modules[name]
            if info.module and name in sys.modules:
                del sys.modules[name]
            
            info.status = LoadStatus.UNLOADED
            info.module = None
            info.spec = None
            return True

    def reload_module(self, name: str) -> ReloadEvent:
        with self._lock:
            if name not in self.modules:
                return ReloadEvent(name, 0, 0, success=False, error="Module not loaded")
            
            info = self.modules[name]
            old_version = info.version
            
            info.status = LoadStatus.RELOADING
            try:
                if info.module and name in sys.modules:
                    del sys.modules[name]
                
                import os
                stat = os.stat(info.file_path)
                new_checksum = self._compute_checksum(info.file_path)
                
                if new_checksum == info.checksum:
                    info.status = LoadStatus.LOADED
                    return ReloadEvent(name, old_version, info.version, success=True)
                
                spec = importlib.util.spec_from_file_location(info.name, info.file_path)
                module = importlib.util.module_from_spec(spec)
                info.spec = spec
                info.module = module
                
                sys.modules[name] = module
                spec.loader.exec_module(module)
                
                info.status = LoadStatus.LOADED
                info.version += 1
                info.checksum = new_checksum
                info.last_modified = stat.st_mtime
                info.loaded_at = time.time()
                info.error = None
                
                event = ReloadEvent(name, old_version, info.version, success=True)
            except Exception as e:
                info.status = LoadStatus.FAILED
                info.error = str(e)
                event = ReloadEvent(name, old_version, info.version, success=False, error=str(e))
            
            self.reload_history.append(event)
            if len(self.reload_history) > 1000:
                self.reload_history = self.reload_history[-1000:]
            
            for callback in self.callbacks:
                try:
                    if asyncio.iscoroutinefunction(callback):
                        asyncio.create_task(callback(event))
                    else:
                        callback(event)
                except Exception:
                    pass
            
            return event

    def get_module(self, name: str) -> Optional[ModuleInfo]:
        with self._lock:
            return self.modules.get(name)

    def get_loaded_module(self, name: str) -> Any:
        with self._lock:
            info = self.modules.get(name)
            if info and info.status == LoadStatus.LOADED:
                return info.module
        return None

    def is_loaded(self, name: str) -> bool:
        with self._lock:
            info = self.modules.get(name)
            return info is not None and info.status == LoadStatus.LOADED

    def on_reload(self, callback: Callable):
        self.callbacks.append(callback)

    async def start_watching(self):
        self._running = True
        self._watch_task = asyncio.create_task(self._watch_loop())

    async def stop_watching(self):
        self._running = False
        if self._watch_task:
            self._watch_task.cancel()
            try:
                await self._watch_task
            except asyncio.CancelledError:
                pass

    async def _watch_loop(self):
        while self._running:
            await asyncio.sleep(self.watch_interval)
            await self._check_for_changes()

    async def _check_for_changes(self):
        for name, info in list(self.modules.items()):
            if info.status != LoadStatus.LOADED:
                continue
            
            try:
                import os
                mtime = os.path.getmtime(info.file_path)
                if mtime > info.last_modified:
                    self.reload_module(name)
            except Exception:
                pass

    def get_dependency_graph(self) -> Dict[str, List[str]]:
        with self._lock:
            return {name: info.dependencies for name, info in self.modules.items()}

    def get_reload_history(self) -> List[ReloadEvent]:
        return list(self.reload_history)


class PluginManager:
    def __init__(self, loader: HotSwapLoader):
        self.loader = loader
        self.plugins: Dict[str, Dict[str, Any]] = {}
        self.plugin_interfaces: Dict[str, Type] = {}

    def register_interface(self, name: str, interface: Type):
        self.plugin_interfaces[name] = interface

    def load_plugin(self, name: str, file_path: str, interface: str = None) -> bool:
        info = self.loader.load_module(name, file_path)
        if info.status != LoadStatus.LOADED:
            return False
        
        if interface and interface in self.plugin_interfaces:
            if not isinstance(info.module, self.plugin_interfaces[interface]):
                return False
        
        self.plugins[name] = {
            "module": info.module,
            "interface": interface,
            "info": info,
        }
        return True

    def unload_plugin(self, name: str) -> bool:
        if name in self.plugins:
            del self.plugins[name]
        return self.loader.unload_module(name)

    def reload_plugin(self, name: str) -> ReloadEvent:
        event = self.loader.reload_module(name)
        if event.success and name in self.plugins:
            info = self.loader.get_module(name)
            self.plugins[name]["module"] = info.module
            self.plugins[name]["info"] = info
        return event

    def get_plugin(self, name: str) -> Optional[Any]:
        return self.plugins.get(name, {}).get("module")

    def list_plugins(self) -> List[str]:
        return list(self.plugins.keys())


class IsolatedLoader:
    def __init__(self):
        self.loaders: Dict[str, HotSwapLoader] = {}
        self._lock = threading.RLock()

    def create_loader(self, name: str) -> HotSwapLoader:
        with self._lock:
            loader = HotSwapLoader()
            self.loaders[name] = loader
            return loader

    def get_loader(self, name: str) -> Optional[HotSwapLoader]:
        with self._lock:
            return self.loaders.get(name)

    def remove_loader(self, name: str) -> bool:
        with self._lock:
            if name in self.loaders:
                del self.loaders[name]
                return True
        return False


class LazyLoader:
    def __init__(self, loader: HotSwapLoader):
        self.loader = loader
        self.proxies: Dict[str, Any] = {}

    def get_module(self, name: str, file_path: str = None) -> Any:
        if name not in self.proxies:
            self.proxies[name] = LazyModuleProxy(name, file_path, self.loader)
        return self.proxies[name]


class LazyModuleProxy:
    def __init__(self, name: str, file_path: str, loader: HotSwapLoader):
        self.name = name
        self.file_path = file_path
        self.loader = loader
        self._module = None
        self._loaded = False

    def _ensure_loaded(self):
        if not self._loaded:
            info = self.loader.load_module(self.name, self.file_path)
            self._module = info.module
            self._loaded = True

    def __getattr__(self, item: str) -> Any:
        self._ensure_loaded()
        return getattr(self._module, item)

    def __setattr__(self, name: str, value: Any):
        if name in ['name', 'file_path', 'loader', '_module', '_loaded']:
            super().__setattr__(name, value)
        else:
            self._ensure_loaded()
            setattr(self._module, name, value)


@contextmanager
def temporary_module(name: str, source: str):
    import tempfile
    with tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False) as f:
        f.write(source)
        temp_path = f.name
    
    try:
        loader = HotSwapLoader()
        info = loader.load_module(name, temp_path)
        yield info.module
    finally:
        loader.unload_module(name)
        try:
            import os
            os.unlink(temp_path)
        except Exception:
            pass