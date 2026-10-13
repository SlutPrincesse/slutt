import os
import json
import time
import asyncio
from typing import Any, AsyncIterator, Dict, List, Optional
from dataclasses import dataclass, field

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

from .base import (
    LLMProvider,
    ModelInfo,
    LLMResponse,
    LLMChunk,
    ProviderType,
    ProviderError,
    RateLimitError,
    AuthenticationError,
    ModelNotFoundError,
)


@dataclass
class OpenAICompatibleConfig:
    api_key: str
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o"
    organization: Optional[str] = None
    timeout: float = 60.0
    max_retries: int = 3
    default_headers: Dict[str, str] = field(default_factory=dict)
    extra_body: Dict[str, Any] = field(default_factory=dict)


class OpenAICompatibleProvider(LLMProvider):
    SUPPORTED_PROVIDERS = {
        "openai": {"base_url": "https://api.openai.com/v1", "models": ["gpt-4o", "gpt-4o-mini", "gpt-4-turbo", "gpt-3.5-turbo"]},
        "deepseek": {"base_url": "https://api.deepseek.com/v1", "models": ["deepseek-chat", "deepseek-coder"]},
        "kimi": {"base_url": "https://api.moonshot.cn/v1", "models": ["moonshot-v1-8k", "moonshot-v1-32k", "moonshot-v1-128k"]},
        "qwen": {"base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1", "models": ["qwen-max", "qwen-plus", "qwen-turbo"]},
        "openrouter": {"base_url": "https://openrouter.ai/api/v1", "models": ["openrouter/auto"]},
        "omniroute": {"base_url": "https://api.omniroute.ai/v1", "models": ["omniroute/auto"]},
    }

    MODEL_COSTS = {
        "gpt-4o": {"input": 2.50, "output": 10.00},
        "gpt-4o-mini": {"input": 0.15, "output": 0.60},
        "gpt-4-turbo": {"input": 10.00, "output": 30.00},
        "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
        "deepseek-chat": {"input": 0.14, "output": 0.28},
        "deepseek-coder": {"input": 0.14, "output": 0.28},
        "moonshot-v1-8k": {"input": 0.12, "output": 0.12},
        "moonshot-v1-32k": {"input": 0.24, "output": 0.24},
        "moonshot-v1-128k": {"input": 0.60, "output": 0.60},
        "qwen-max": {"input": 0.40, "output": 1.20},
        "qwen-plus": {"input": 0.10, "output": 0.30},
        "qwen-turbo": {"input": 0.02, "output": 0.06},
    }

    def __init__(self, config: OpenAICompatibleConfig):
        super().__init__(config.model)
        self.config = config
        self._client: Optional[httpx.AsyncClient] = None
        self._model_info = self._build_model_info()

    def _build_model_info(self) -> ModelInfo:
        costs = self.MODEL_COSTS.get(self.config.model, {"input": 0.0, "output": 0.0})
        provider_name = self._detect_provider()
        
        return ModelInfo(
            name=self.config.model,
            provider=ProviderType.OPENAI_COMPATIBLE,
            max_context=self._get_max_context(),
            supports_streaming=True,
            supports_tools=True,
            supports_vision="vision" in self.config.model.lower() or "gpt-4o" in self.config.model,
            input_cost_per_1k=costs["input"],
            output_cost_per_1k=costs["output"],
            capabilities=["chat", "tools", "streaming", "json_mode"],
            metadata={
                "provider_name": provider_name,
                "base_url": self.config.base_url,
                "input_cost_per_1k": costs["input"],
                "output_cost_per_1k": costs["output"],
            }
        )

    def _detect_provider(self) -> str:
        for name, info in self.SUPPORTED_PROVIDERS.items():
            if info["base_url"] in self.config.base_url:
                return name
        return "custom"

    def _get_max_context(self) -> int:
        context_map = {
            "gpt-4o": 128000,
            "gpt-4o-mini": 128000,
            "gpt-4-turbo": 128000,
            "gpt-3.5-turbo": 16385,
            "deepseek-chat": 32768,
            "deepseek-coder": 32768,
            "moonshot-v1-8k": 8192,
            "moonshot-v1-32k": 32768,
            "moonshot-v1-128k": 131072,
            "qwen-max": 32768,
            "qwen-plus": 32768,
            "qwen-turbo": 32768,
        }
        return context_map.get(self.config.model, 4096)

    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {
                "Authorization": f"Bearer {self.config.api_key}",
                "Content-Type": "application/json",
                **self.config.default_headers,
            }
            if self.config.organization:
                headers["OpenAI-Organization"] = self.config.organization
            
            self._client = httpx.AsyncClient(
                base_url=self.config.base_url,
                headers=headers,
                timeout=self.config.timeout,
            )
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    @retry(
        wait=wait_exponential(multiplier=1, min=1, max=60),
        stop=stop_after_attempt(3),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError, RateLimitError)),
    )
    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            **self.config.extra_body,
            **kwargs,
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        response = await self._post_with_retry("/chat/completions", payload)
        return self._parse_response(response)

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncIterator[LLMChunk]:
        payload = {
            "model": self.config.model,
            "messages": messages,
            "stream": True,
            **self.config.extra_body,
            **kwargs,
        }
        
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

        async with self.client.stream("POST", "/chat/completions", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or line == "data: [DONE]":
                    continue
                if line.startswith("data: "):
                    line = line[6:]
                try:
                    chunk_data = json.loads(line)
                    yield self._parse_stream_chunk(chunk_data)
                except json.JSONDecodeError:
                    continue

    async def _post_with_retry(self, endpoint: str, payload: Dict[str, Any]) -> httpx.Response:
        try:
            response = await self.client.post(endpoint, json=payload)
            
            if response.status_code == 429:
                retry_after = int(response.headers.get("Retry-After", "60"))
                raise RateLimitError("Rate limit exceeded", self.provider_type, retry_after)
            elif response.status_code == 401:
                raise AuthenticationError("Invalid API key", self.provider_type)
            elif response.status_code == 404:
                raise ModelNotFoundError(f"Model not found: {self.config.model}", self.provider_type, self.config.model)
            
            response.raise_for_status()
            return response
        except httpx.TimeoutException as e:
            raise ProviderError(f"Request timeout: {e}", self.provider_type, "TIMEOUT")
        except httpx.NetworkError as e:
            raise ProviderError(f"Network error: {e}", self.provider_type, "NETWORK_ERROR")

    def _parse_response(self, response: httpx.Response) -> LLMResponse:
        data = response.json()
        choice = data["choices"][0]
        message = choice["message"]
        
        usage = data.get("usage", {})
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        
        return LLMResponse(
            content=message.get("content", "") or "",
            tool_calls=message.get("tool_calls", []),
            finish_reason=choice.get("finish_reason", "stop"),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            model=data.get("model", self.config.model),
            provider=self.provider_type,
            metadata={
                "input_cost_per_1k": self._model_info.input_cost_per_1k,
                "output_cost_per_1k": self._model_info.output_cost_per_1k,
            }
        )

    def _parse_stream_chunk(self, data: Dict[str, Any]) -> LLMChunk:
        choice = data["choices"][0]
        delta = choice.get("delta", {})
        
        return LLMChunk(
            delta=delta.get("content", "") or "",
            tool_calls=delta.get("tool_calls", []),
            finish_reason=choice.get("finish_reason"),
            is_final=choice.get("finish_reason") is not None,
        )

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens / 1000.0) * self._model_info.input_cost_per_1k + \
               (output_tokens / 1000.0) * self._model_info.output_cost_per_1k

    def get_model_info(self) -> ModelInfo:
        return self._model_info

    @classmethod
    def from_env(cls, provider: str = "openai", model: Optional[str] = None) -> "OpenAICompatibleProvider":
        provider_config = cls.SUPPORTED_PROVIDERS.get(provider.lower())
        if not provider_config:
            raise ValueError(f"Unknown provider: {provider}. Supported: {list(cls.SUPPORTED_PROVIDERS.keys())}")
        
        api_key = os.getenv(f"{provider.upper()}_API_KEY") or os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(f"API key not found. Set {provider.upper()}_API_KEY or OPENAI_API_KEY")
        
        base_url = os.getenv(f"{provider.upper()}_BASE_URL", provider_config["base_url"])
        model = model or os.getenv("MODEL", provider_config["models"][0])
        
        config = OpenAICompatibleConfig(
            api_key=api_key,
            base_url=base_url,
            model=model,
        )
        return cls(config)

    @classmethod
    def list_models(cls, provider: str) -> List[str]:
        provider_config = cls.SUPPORTED_PROVIDERS.get(provider.lower())
        if not provider_config:
            return []
        return provider_config["models"]


async def create_openai_compatible_provider(
    provider: str = "openai",
    model: Optional[str] = None,
    **kwargs
) -> OpenAICompatibleProvider:
    provider_instance = OpenAICompatibleProvider.from_env(provider, model)
    for key, value in kwargs.items():
        if hasattr(provider_instance.config, key):
            setattr(provider_instance.config, key, value)
    return provider_instance