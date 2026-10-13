"""
Hook Engine - Extensible hook system for reactive pipelines
"""
import asyncio
import time
import uuid
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class HookPhase(Enum):
    PRE = "pre"
    POST = "post"
    ERROR = "error"
    FINALLY = "finally"


class HookPriority(Enum):
    FIRST = -100
    HIGH = -50
    NORMAL = 0
    LOW = 50
    LAST = 100


@dataclass
class Hook:
    hook_id: str
    name: str
    phase: HookPhase
    handler: Callable
    priority: HookPriority = HookPriority.NORMAL
    condition: Callable | None = None
    async_handler: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def matches(self, context: dict[str, Any]) -> bool:
        if self.condition:
            try:
                return self.condition(context)
            except Exception:
                return False
        return True


@dataclass
class HookContext:
    hook_id: str
    hook_name: str
    phase: HookPhase
    input_data: Any
    output_data: Any = None
    error: Exception | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    start_time: float = field(default_factory=time.time)
    end_time: float | None = None

    @property
    def duration(self) -> float:
        if self.end_time:
            return self.end_time - self.start_time
        return time.time() - self.start_time


class HookEngine:
    def __init__(self):
        self.hooks: dict[str, list[Hook]] = defaultdict(list)
        self.global_hooks: list[Hook] = []
        self._lock = asyncio.Lock()

    def register(
        self,
        name: str,
        phase: HookPhase,
        handler: Callable,
        priority: HookPriority = HookPriority.NORMAL,
        condition: Callable | None = None,
        metadata: dict[str, Any] = None,
    ) -> str:
        hook_id = str(uuid.uuid4())
        hook = Hook(
            hook_id=hook_id,
            name=name,
            phase=phase,
            handler=handler,
            priority=priority,
            condition=condition,
            async_handler=asyncio.iscoroutinefunction(handler),
            metadata=metadata or {},
        )
        self.hooks[phase.value].append(hook)
        self.hooks[phase.value].sort(key=lambda h: h.priority.value)
        return hook_id

    def register_global(
        self,
        name: str,
        handler: Callable,
        priority: HookPriority = HookPriority.NORMAL,
        condition: Callable | None = None,
        metadata: dict[str, Any] = None,
    ) -> str:
        hook_id = str(uuid.uuid4())
        hook = Hook(
            hook_id=hook_id,
            name=name,
            phase=HookPhase.PRE,
            handler=handler,
            priority=priority,
            condition=condition,
            async_handler=asyncio.iscoroutinefunction(handler),
            metadata=metadata or {},
        )
        self.global_hooks.append(hook)
        self.global_hooks.sort(key=lambda h: h.priority.value)
        return hook_id

    def unregister(self, hook_id: str) -> bool:
        for phase_hooks in self.hooks.values():
            for i, hook in enumerate(phase_hooks):
                if hook.hook_id == hook_id:
                    phase_hooks.pop(i)
                    return True
        for i, hook in enumerate(self.global_hooks):
            if hook.hook_id == hook_id:
                self.global_hooks.pop(i)
                return True
        return False

    async def execute_phase(
        self,
        phase: HookPhase,
        context: HookContext,
    ) -> HookContext:
        hooks = self.hooks.get(phase.value, [])

        for hook in hooks:
            if hook.matches(context.__dict__):
                try:
                    if hook.async_handler:
                        await hook.handler(context)
                    else:
                        hook.handler(context)
                except Exception as e:
                    context.error = e
                    if phase != HookPhase.ERROR:
                        await self.execute_phase(HookPhase.ERROR, context)
                    break

        return context

    async def execute_all(
        self,
        input_data: Any,
        phases: list[HookPhase] = None,
    ) -> Any:
        if phases is None:
            phases = [HookPhase.PRE, HookPhase.POST]

        context = HookContext(
            hook_id="",
            hook_name="",
            phase=HookPhase.PRE,
            input_data=input_data,
        )

        for phase in phases:
            context.phase = phase
            context = await self.execute_phase(phase, context)
            if context.error and phase != HookPhase.ERROR:
                break

        return context.output_data or context.input_data

    def get_hooks(self, phase: HookPhase) -> list[Hook]:
        return self.hooks.get(phase.value, [])

    def list_all_hooks(self) -> dict[str, list[Hook]]:
        return {phase: hooks for phase, hooks in self.hooks.items()}


class PipelineHookEngine(HookEngine):
    def __init__(self):
        super().__init__()
        self.pipelines: dict[str, list[str]] = {}

    def define_pipeline(self, name: str, hook_names: list[str]):
        self.pipelines[name] = hook_names

    async def execute_pipeline(self, name: str, input_data: Any) -> Any:
        hook_names = self.pipelines.get(name, [])
        context = HookContext(
            hook_id="",
            hook_name=name,
            phase=HookPhase.PRE,
            input_data=input_data,
        )

        for hook_name in hook_names:
            context.hook_name = hook_name
            for phase in [HookPhase.PRE, HookPhase.POST]:
                context.phase = phase
                hooks = [h for h in self.hooks.get(phase.value, []) if h.name == hook_name]
                for hook in hooks:
                    if hook.matches(context.__dict__):
                        try:
                            if hook.async_handler:
                                await hook.handler(context)
                            else:
                                hook.handler(context)
                        except Exception as e:
                            context.error = e
                            await self.execute_phase(HookPhase.ERROR, context)
                            break

        return context.output_data or context.input_data


class ConditionalHookEngine(HookEngine):
    def __init__(self):
        super().__init__()
        self.conditions: dict[str, Callable] = {}

    def register_condition(self, name: str, condition: Callable):
        self.conditions[name] = condition

    def register_with_condition(
        self,
        name: str,
        phase: HookPhase,
        handler: Callable,
        condition_name: str,
        priority: HookPriority = HookPriority.NORMAL,
        metadata: dict[str, Any] = None,
    ) -> str:
        condition = self.conditions.get(condition_name)
        if not condition:
            raise ValueError(f"Condition not found: {condition_name}")

        return self.register(name, phase, handler, priority, condition, metadata)


class AsyncHookEngine(HookEngine):
    def __init__(self, max_concurrent: int = 10):
        super().__init__()
        self.semaphore = asyncio.Semaphore(max_concurrent)
        self.results: dict[str, Any] = {}

    async def execute_phase(
        self,
        phase: HookPhase,
        context: HookContext,
    ) -> HookContext:
        hooks = self.hooks.get(phase.value, [])

        async def run_hook(hook: Hook):
            async with self.semaphore:
                if hook.matches(context.__dict__):
                    try:
                        if hook.async_handler:
                            await hook.handler(context)
                        else:
                            hook.handler(context)
                    except Exception as e:
                        context.error = e

        await asyncio.gather(*[run_hook(hook) for hook in hooks])
        return context


class HookMetrics:
    def __init__(self):
        self.counters: dict[str, int] = defaultdict(int)
        self.durations: dict[str, list[float]] = defaultdict(list)
        self.errors: dict[str, int] = defaultdict(int)
        self._lock = asyncio.Lock()

    async def record(self, hook_name: str, duration: float, error: bool = False):
        async with self._lock:
            self.counters[hook_name] += 1
            self.durations[hook_name].append(duration)
            if error:
                self.errors[hook_name] += 1

    def get_stats(self, hook_name: str) -> dict[str, Any]:
        durations = self.durations.get(hook_name, [])
        return {
            "count": self.counters.get(hook_name, 0),
            "errors": self.errors.get(hook_name, 0),
            "avg_duration": sum(durations) / len(durations) if durations else 0,
            "max_duration": max(durations) if durations else 0,
            "min_duration": min(durations) if durations else 0,
        }


class DecoratorHooks:
    def __init__(self, engine: HookEngine):
        self.engine = engine

    def pre(self, name: str = None, priority: HookPriority = HookPriority.NORMAL):
        def decorator(func: Callable):
            hook_name = name or func.__name__
            self.engine.register(hook_name, HookPhase.PRE, func, priority)
            return func
        return decorator

    def post(self, name: str = None, priority: HookPriority = HookPriority.NORMAL):
        def decorator(func: Callable):
            hook_name = name or func.__name__
            self.engine.register(hook_name, HookPhase.POST, func, priority)
            return func
        return decorator

    def error(self, name: str = None, priority: HookPriority = HookPriority.NORMAL):
        def decorator(func: Callable):
            hook_name = name or func.__name__
            self.engine.register(hook_name, HookPhase.ERROR, func, priority)
            return func
        return decorator

    def finally_(self, name: str = None, priority: HookPriority = HookPriority.NORMAL):
        def decorator(func: Callable):
            hook_name = name or func.__name__
            self.engine.register(hook_name, HookPhase.FINALLY, func, priority)
            return func
        return decorator
