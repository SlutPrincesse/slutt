from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Dict, List, Optional
from enum import Enum


class ProviderType(Enum):
    OPENAI_COMPATIBLE = "openai_compatible"
    LLAMACPP = "llamacpp"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    CUSTOM = "custom"


@dataclass
class ModelInfo:
    name: str
    provider: ProviderType
    max_context: int
    supports_streaming: bool = True
    supports_tools: bool = True
    supports_vision: bool = False
    supports_audio: bool = False
    input_cost_per_1k: float = 0.0
    output_cost_per_1k: float = 0.0
    capabilities: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class LLMResponse:
    content: str
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    finish_reason: str = "stop"
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    model: str = ""
    provider: ProviderType = ProviderType.CUSTOM
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def cost(self) -> float:
        return (self.input_tokens / 1000.0) * self.metadata.get("input_cost_per_1k", 0.0) + \
               (self.output_tokens / 1000.0) * self.metadata.get("output_cost_per_1k", 0.0)


@dataclass
class LLMChunk:
    delta: str = ""
    tool_calls: List[Dict[str, Any]] = field(default_factory=list)
    finish_reason: Optional[str] = None
    is_final: bool = False


class LLMProvider(ABC):
    def __init__(self, model: str, **kwargs):
        self.model = model
        self.config = kwargs
        self._model_info: Optional[ModelInfo] = None

    @abstractmethod
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        pass

    @abstractmethod
    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncIterator[LLMChunk]:
        pass

    @abstractmethod
    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        pass

    @abstractmethod
    def get_model_info(self) -> ModelInfo:
        pass

    async def health_check(self) -> bool:
        try:
            await self.chat([{"role": "user", "content": "ping"}], max_tokens=1)
            return True
        except Exception:
            return False

    def supports_feature(self, feature: str) -> bool:
        info = self.get_model_info()
        return feature in info.capabilities

    @property
    def provider_type(self) -> ProviderType:
        return self.get_model_info().provider


class ProviderError(Exception):
    def __init__(self, message: str, provider: ProviderType, code: str = "PROVIDER_ERROR"):
        super().__init__(message)
        self.provider = provider
        self.code = code


class RateLimitError(ProviderError):
    def __init__(self, message: str, provider: ProviderType, retry_after: Optional[int] = None):
        super().__init__(message, provider, "RATE_LIMIT")
        self.retry_after = retry_after


class AuthenticationError(ProviderError):
    def __init__(self, message: str, provider: ProviderType):
        super().__init__(message, provider, "AUTHENTICATION")


class ModelNotFoundError(ProviderError):
    def __init__(self, message: str, provider: ProviderType, model: str):
        super().__init__(message, provider, "MODEL_NOT_FOUND")
        self.model = model