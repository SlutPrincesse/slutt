import asyncio
import os
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional

from .base import LLMProvider, ProviderError, ProviderType
from .llamacpp import LlamaCppProvider
from .openai_compatible import OpenAICompatibleProvider


class SelectionStrategy(Enum):
    COST_OPTIMAL = "cost_optimal"
    PERFORMANCE = "performance"
    CAPABILITY = "capability"
    ROUND_ROBIN = "round_robin"
    PRIORITY = "priority"


@dataclass
class ProviderRegistration:
    provider: LLMProvider
    priority: int = 0
    enabled: bool = True
    tags: list[str] = field(default_factory=list)
    health_check_interval: int = 60
    last_health_check: float = 0
    is_healthy: bool = True
    consecutive_failures: int = 0
    max_failures: int = 3


class ProviderRegistry:
    _instance: Optional["ProviderRegistry"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._providers: dict[str, ProviderRegistration] = {}
        self._selection_strategy = SelectionStrategy.COST_OPTIMAL
        self._fallback_chain: list[str] = []
        self._health_check_task: asyncio.Task | None = None
        self._initialized = True

    @classmethod
    def get_instance(cls) -> "ProviderRegistry":
        if cls._instance is None:
            cls._instance = ProviderRegistry()
        return cls._instance

    def register(
        self,
        name: str,
        provider: LLMProvider,
        priority: int = 0,
        tags: list[str] = None,
        enabled: bool = True,
    ) -> None:
        self._providers[name] = ProviderRegistration(
            provider=provider,
            priority=priority,
            enabled=enabled,
            tags=tags or [],
        )
        self._rebuild_fallback_chain()

    def unregister(self, name: str) -> bool:
        if name in self._providers:
            del self._providers[name]
            self._rebuild_fallback_chain()
            return True
        return False

    def get(self, name: str) -> LLMProvider | None:
        reg = self._providers.get(name)
        return reg.provider if reg else None

    def get_all(self) -> dict[str, LLMProvider]:
        return {name: reg.provider for name, reg in self._providers.items() if reg.enabled}

    def get_healthy(self) -> dict[str, LLMProvider]:
        return {name: reg.provider for name, reg in self._providers.items()
                if reg.enabled and reg.is_healthy}

    def select_provider(
        self,
        strategy: SelectionStrategy = None,
        required_capabilities: list[str] = None,
        max_cost_per_1k: float = None,
    ) -> LLMProvider | None:
        strategy = strategy or self._selection_strategy
        healthy = self.get_healthy()

        if not healthy:
            return None

        if required_capabilities:
            healthy = {
                name: p for name, p in healthy.items()
                if all(p.supports_feature(c) for c in required_capabilities)
            }

        if max_cost_per_1k is not None:
            healthy = {
                name: p for name, p in healthy.items()
                if p.get_model_info().input_cost_per_1k <= max_cost_per_1k
            }

        if not healthy:
            return None

        if strategy == SelectionStrategy.COST_OPTIMAL:
            return min(healthy.values(), key=lambda p: p.get_model_info().input_cost_per_1k)
        if strategy == SelectionStrategy.PERFORMANCE:
            return max(healthy.values(), key=lambda p: p.get_model_info().max_context)
        if strategy == SelectionStrategy.CAPABILITY:
            return max(healthy.values(), key=lambda p: len(p.get_model_info().capabilities))
        if strategy == SelectionStrategy.PRIORITY:
            regs = [(name, self._providers[name]) for name in healthy.keys()]
            regs.sort(key=lambda x: x[1].priority, reverse=True)
            return regs[0][1].provider if regs else None
        if strategy == SelectionStrategy.ROUND_ROBIN:
            names = list(healthy.keys())
            if hasattr(self, '_rr_index'):
                self._rr_index = (self._rr_index + 1) % len(names)
            else:
                self._rr_index = 0
            return healthy[names[self._rr_index]]

        return list(healthy.values())[0]

    async def health_check_all(self) -> dict[str, bool]:
        results = {}
        for name, reg in self._providers.items():
            if not reg.enabled:
                results[name] = False
                continue
            try:
                is_healthy = await reg.provider.health_check()
                reg.is_healthy = is_healthy
                reg.consecutive_failures = 0 if is_healthy else reg.consecutive_failures + 1
                if reg.consecutive_failures >= reg.max_failures:
                    reg.enabled = False
                results[name] = is_healthy
            except Exception:
                reg.is_healthy = False
                reg.consecutive_failures += 1
                if reg.consecutive_failures >= reg.max_failures:
                    reg.enabled = False
                results[name] = False
        self._rebuild_fallback_chain()
        return results

    def _rebuild_fallback_chain(self):
        enabled = [
            (name, reg) for name, reg in self._providers.items()
            if reg.enabled and reg.is_healthy
        ]
        enabled.sort(key=lambda x: x[1].priority, reverse=True)
        self._fallback_chain = [name for name, _ in enabled]

    def get_fallback_chain(self) -> list[str]:
        return self._fallback_chain.copy()

    def set_selection_strategy(self, strategy: SelectionStrategy):
        self._selection_strategy = strategy

    async def start_health_checks(self, interval: int = 60):
        if self._health_check_task:
            self._health_check_task.cancel()

        async def health_check_loop():
            while True:
                await asyncio.sleep(interval)
                await self.health_check_all()

        self._health_check_task = asyncio.create_task(health_check_loop())

    async def stop_health_checks(self):
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None

    async def close_all(self):
        await self.stop_health_checks()
        for reg in self._providers.values():
            if hasattr(reg.provider, 'close'):
                await reg.provider.close()
        self._providers.clear()
        self._fallback_chain.clear()


class ProviderFactory:
    PROVIDER_CLASSES = {
        ProviderType.OPENAI_COMPATIBLE: OpenAICompatibleProvider,
        ProviderType.LLAMACPP: LlamaCppProvider,
    }

    @classmethod
    def register_provider_class(cls, provider_type: ProviderType, provider_class: type[LLMProvider]):
        cls.PROVIDER_CLASSES[provider_type] = provider_class

    @classmethod
    async def create_from_config(cls, config: dict[str, Any]) -> LLMProvider:
        provider_type = ProviderType(config.get("type", "openai_compatible"))
        provider_class = cls.PROVIDER_CLASSES.get(provider_type)

        if not provider_class:
            raise ProviderError(f"Unknown provider type: {provider_type}", provider_type)

        if provider_type == ProviderType.OPENAI_COMPATIBLE:
            return await OpenAICompatibleProvider.from_env(
                config.get("provider", "openai"),
                config.get("model")
            )
        if provider_type == ProviderType.LLAMACPP:
            return LlamaCppProvider.from_env()

        raise ProviderError(f"Factory not implemented for: {provider_type}", provider_type)

    @classmethod
    async def auto_detect_and_register(cls, registry: ProviderRegistry = None) -> ProviderRegistry:
        registry = registry or ProviderRegistry.get_instance()

        openai_key = os.getenv("OPENAI_API_KEY")
        if openai_key:
            try:
                provider = await OpenAICompatibleProvider.from_env("openai")
                registry.register("openai", provider, priority=10, tags=["cloud", "general"])
            except Exception:
                pass

        for provider_name in ["deepseek", "kimi", "qwen", "openrouter", "omniroute"]:
            api_key = os.getenv(f"{provider_name.upper()}_API_KEY")
            if api_key:
                try:
                    provider = await OpenAICompatibleProvider.from_env(provider_name)
                    registry.register(provider_name, provider, priority=5, tags=["cloud", "general"])
                except Exception:
                    pass

        llamacpp_model = os.getenv("LLAMACPP_MODEL_PATH")
        if llamacpp_model:
            try:
                provider = LlamaCppProvider.from_env()
                registry.register("llamacpp", provider, priority=15, tags=["local", "private", "offline"])
            except Exception:
                pass

        return registry


async def initialize_provider_registry(config: dict[str, Any] | None = None) -> ProviderRegistry:
    registry = ProviderRegistry.get_instance()

    if config and "providers" in config:
        for name, provider_config in config["providers"].items():
            provider = await ProviderFactory.create_from_config(provider_config)
            registry.register(
                name,
                provider,
                priority=provider_config.get("priority", 0),
                tags=provider_config.get("tags", []),
                enabled=provider_config.get("enabled", True),
            )
    else:
        await ProviderFactory.auto_detect_and_register(registry)

    if config and "selection_strategy" in config:
        registry.set_selection_strategy(SelectionStrategy(config["selection_strategy"]))

    await registry.start_health_checks()

    return registry
