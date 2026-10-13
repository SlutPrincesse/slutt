import asyncio
import sys
from collections.abc import Callable
from contextlib import contextmanager
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class HookPriority(Enum):
    LOW = 0
    NORMAL = 50
    HIGH = 100
    CRITICAL = 200


@dataclass
class HookedException:
    exception: BaseException
    exc_type: type[BaseException]
    exc_value: BaseException
    exc_traceback: Any
    frame: Any
    timestamp: float
    context: dict[str, Any] = field(default_factory=dict)
    handled: bool = False
    synthesis_requested: bool = False
    suggested_tool_name: str | None = None
    suggested_tool_spec: dict[str, Any] | None = None


class ExceptionHookInterceptor:
    _instance: Optional["ExceptionHookInterceptor"] = None
    _original_excepthook: Callable | None = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._hooks: list[Callable[[HookedException], Any]] = []
        self._async_hooks: list[Callable[[HookedException], Any]] = []
        self._exception_counts: dict[str, int] = {}
        self._synthesis_threshold = 3
        self._enabled = True
        self._initialized = True

    @classmethod
    def get_instance(cls) -> "ExceptionHookInterceptor":
        if cls._instance is None:
            cls._instance = ExceptionHookInterceptor()
        return cls._instance

    def install(self):
        if self._original_excepthook is None:
            self._original_excepthook = sys.excepthook
            sys.excepthook = self._handle_exception

    def uninstall(self):
        if self._original_excepthook is not None:
            sys.excepthook = self._original_excepthook
            self._original_excepthook = None

    def _handle_exception(self, exc_type: type[BaseException], exc_value: BaseException, exc_traceback: Any):
        frame = exc_traceback.tb_frame if exc_traceback else None
        while frame and frame.f_back:
            frame = frame.f_back

        hooked = HookedException(
            exception=exc_value,
            exc_type=exc_type,
            exc_value=exc_value,
            exc_traceback=exc_traceback,
            frame=frame,
            timestamp=asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0,
            context=self._extract_context(frame),
        )

        self._exception_counts[exc_type.__name__] = self._exception_counts.get(exc_type.__name__, 0) + 1

        if self._enabled:
            for hook in self._hooks:
                try:
                    hook(hooked)
                except Exception:
                    pass

            if self._exception_counts[exc_type.__name__] >= self._synthesis_threshold:
                hooked.synthesis_requested = True
                hooked.suggested_tool_name = f"handle_{exc_type.__name__.lower()}"
                hooked.suggested_tool_spec = self._generate_tool_spec(exc_type, exc_value, frame)

        if self._original_excepthook:
            self._original_excepthook(exc_type, exc_value, exc_traceback)

    def _extract_context(self, frame: Any) -> dict[str, Any]:
        if not frame:
            return {}
        context = {
            "filename": frame.f_code.co_filename,
            "function": frame.f_code.co_name,
            "lineno": frame.f_lineno,
            "locals": {k: repr(v)[:200] for k, v in frame.f_locals.items() if not k.startswith("_")},
            "globals": {k: repr(v)[:200] for k, v in frame.f_globals.items() if not k.startswith("_") and k in ("self", "cls", "config", "settings")},
        }
        return context

    def _generate_tool_spec(self, exc_type: type[BaseException], exc_value: BaseException, frame: Any) -> dict[str, Any]:
        return {
            "name": f"handle_{exc_type.__name__.lower()}",
            "description": f"Auto-generated handler for {exc_type.__name__}: {str(exc_value)[:100]}",
            "parameters": {
                "type": "object",
                "properties": {
                    "error_message": {"type": "string", "description": "The error message"},
                    "context": {"type": "object", "description": "Execution context when error occurred"},
                    "retry": {"type": "boolean", "default": True, "description": "Whether to retry the operation"},
                },
                "required": ["error_message"],
            },
            "returns": {
                "type": "object",
                "properties": {
                    "recovered": {"type": "boolean"},
                    "result": {"type": "any"},
                    "fallback_used": {"type": "boolean"},
                },
            },
        }

    def register_hook(self, hook: Callable[[HookedException], Any], priority: HookPriority = HookPriority.NORMAL):
        self._hooks.append(hook)
        self._hooks.sort(key=lambda h: getattr(h, "_priority", HookPriority.NORMAL.value), reverse=True)

    def register_async_hook(self, hook: Callable[[HookedException], Any], priority: HookPriority = HookPriority.NORMAL):
        hook._priority = priority.value
        self._async_hooks.append(hook)
        self._async_hooks.sort(key=lambda h: getattr(h, "_priority", HookPriority.NORMAL.value), reverse=True)

    async def trigger_async_hooks(self, hooked: HookedException):
        for hook in self._async_hooks:
            try:
                if asyncio.iscoroutinefunction(hook):
                    await hook(hooked)
                else:
                    hook(hooked)
            except Exception:
                pass

    def set_synthesis_threshold(self, threshold: int):
        self._synthesis_threshold = threshold

    def enable(self):
        self._enabled = True

    def disable(self):
        self._enabled = False

    def get_exception_stats(self) -> dict[str, int]:
        return self._exception_counts.copy()

    @contextmanager
    def capture_exceptions(self):
        old_hook = sys.excepthook
        sys.excepthook = self._handle_exception
        try:
            yield self
        finally:
            sys.excepthook = old_hook
