import os
import json
import asyncio
import subprocess
from pathlib import Path
from typing import Any, AsyncIterator, Dict, List, Optional
from dataclasses import dataclass, field
from concurrent.futures import ThreadPoolExecutor

import httpx

try:
    from llama_cpp import Llama
    LLAMA_CPP_AVAILABLE = True
except ImportError:
    Llama = None
    LLAMA_CPP_AVAILABLE = False

from .base import (
    LLMProvider,
    ModelInfo,
    LLMResponse,
    LLMChunk,
    ProviderType,
    ProviderError,
)


@dataclass
class LlamaCppConfig:
    model_path: str
    base_url: Optional[str] = None
    n_gpu_layers: int = -1
    n_ctx: int = 8192
    n_batch: int = 512
    n_threads: int = 0
    n_threads_batch: int = 0
    rope_freq_base: float = 10000.0
    rope_freq_scale: float = 1.0
    yarn_ext_factor: float = 1.0
    yarn_attn_factor: float = 1.0
    yarn_beta_fast: float = 32.0
    yarn_beta_slow: float = 1.0
    yarn_orig_ctx: int = 0
    mul_mat_q: bool = True
    offload_kqv: bool = True
    flash_attn: bool = False
    numa: bool = False
    seed: int = -1
    verbose: bool = False
    use_mmap: bool = True
    use_mlock: bool = False
    embedding: bool = False
    kv_cache_quant: bool = True
    speculative: Optional[str] = None
    n_draft: int = 5
    n_predict: int = -1
    temperature: float = 0.7
    top_p: float = 0.95
    top_k: int = 40
    min_p: float = 0.05
    typical_p: float = 1.0
    repeat_penalty: float = 1.1
    repeat_last_n: int = 64
    penalize_nl: bool = True
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    mirostat: int = 0
    mirostat_tau: float = 5.0
    mirostat_eta: float = 0.1
    grammar: Optional[str] = None
    json_schema: Optional[str] = None
    logits_all: bool = False
    stopping_criteria: Optional[List[str]] = None


class LlamaCppProvider(LLMProvider):
    def __init__(self, config: LlamaCppConfig):
        super().__init__(config.model_path)
        self.config = config
        self._llama: Optional[Llama] = None
        self._server_process: Optional[subprocess.Popen] = None
        self._client: Optional[httpx.AsyncClient] = None
        self._executor = ThreadPoolExecutor(max_workers=2)
        self._kv_cache: Dict[str, Any] = {}
        self._model_info = self._build_model_info()

    def _build_model_info(self) -> ModelInfo:
        model_name = Path(self.config.model_path).stem
        return ModelInfo(
            name=model_name,
            provider=ProviderType.LLAMACPP,
            max_context=self.config.n_ctx,
            supports_streaming=True,
            supports_tools=True,
            supports_vision=False,
            supports_audio=False,
            capabilities=[
                "chat", "tools", "streaming", "json_mode", "grammar",
                "kv_cache_reuse", "batch_inference", "speculative_decoding",
                "context_splitting", "gguf_auto_discovery"
            ],
            metadata={
                "model_path": self.config.model_path,
                "n_gpu_layers": self.config.n_gpu_layers,
                "n_ctx": self.config.n_ctx,
                "n_batch": self.config.n_batch,
                "flash_attn": self.config.flash_attn,
                "kv_cache_quant": self.config.kv_cache_quant,
                "speculative": self.config.speculative,
            }
        )

    def _initialize_llama(self) -> Llama:
        if not LLAMA_CPP_AVAILABLE:
            raise ProviderError("llama-cpp-python not installed. Install with: pip install llama-cpp-python", ProviderType.LLAMACPP)
        if self._llama is None:
            self._llama = Llama(
                model_path=self.config.model_path,
                n_gpu_layers=self.config.n_gpu_layers,
                n_ctx=self.config.n_ctx,
                n_batch=self.config.n_batch,
                n_threads=self.config.n_threads or os.cpu_count(),
                n_threads_batch=self.config.n_threads_batch or os.cpu_count(),
                rope_freq_base=self.config.rope_freq_base,
                rope_freq_scale=self.config.rope_freq_scale,
                yarn_ext_factor=self.config.yarn_ext_factor,
                yarn_attn_factor=self.config.yarn_attn_factor,
                yarn_beta_fast=self.config.yarn_beta_fast,
                yarn_beta_slow=self.config.yarn_beta_slow,
                yarn_orig_ctx=self.config.yarn_orig_ctx,
                mul_mat_q=self.config.mul_mat_q,
                offload_kqv=self.config.offload_kqv,
                flash_attn=self.config.flash_attn,
                numa=self.config.numa,
                seed=self.config.seed,
                verbose=self.config.verbose,
                use_mmap=self.config.use_mmap,
                use_mlock=self.config.use_mlock,
                embedding=self.config.embedding,
                kv_cache_quant=self.config.kv_cache_quant,
            )
        return self._llama

    async def _ensure_server(self) -> str:
        if self.config.base_url:
            return self.config.base_url
        
        if self._server_process is None or self._server_process.poll() is not None:
            port = 8080
            self._server_process = subprocess.Popen([
                "llama-server",
                "-m", self.config.model_path,
                "--port", str(port),
                "--ctx-size", str(self.config.n_ctx),
                "--batch-size", str(self.config.n_batch),
                "--n-gpu-layers", str(self.config.n_gpu_layers),
                "--threads", str(self.config.n_threads or os.cpu_count()),
                "--cache-type-k", "q8_0" if self.config.kv_cache_quant else "f16",
                "--cache-type-v", "q8_0" if self.config.kv_cache_quant else "f16",
            ] + (["--flash-attn"] if self.config.flash_attn else []) +
            (["--speculative", self.config.speculative, "--n-draft", str(self.config.n_draft)] if self.config.speculative else []))
            
            await asyncio.sleep(2)
        
        return f"http://localhost:{port}"

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            base_url = await self._ensure_server()
            self._client = httpx.AsyncClient(base_url=base_url, timeout=120.0)
        return self._client

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None
        if self._server_process:
            self._server_process.terminate()
            self._server_process.wait(timeout=5)
            self._server_process = None
        if self._llama:
            del self._llama
            self._llama = None
        self._executor.shutdown(wait=True)

    async def chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> LLMResponse:
        llama = self._initialize_llama()
        
        prompt = self._messages_to_prompt(messages)
        
        completion = await asyncio.get_event_loop().run_in_executor(
            self._executor,
            lambda: llama.create_chat_completion(
                messages=messages,
                tools=tools,
                tool_choice="auto" if tools else "none",
                temperature=kwargs.get("temperature", self.config.temperature),
                top_p=kwargs.get("top_p", self.config.top_p),
                top_k=kwargs.get("top_k", self.config.top_k),
                min_p=kwargs.get("min_p", self.config.min_p),
                typical_p=kwargs.get("typical_p", self.config.typical_p),
                repeat_penalty=kwargs.get("repeat_penalty", self.config.repeat_penalty),
                repeat_last_n=kwargs.get("repeat_last_n", self.config.repeat_last_n),
                penalize_nl=self.config.penalize_nl,
                presence_penalty=kwargs.get("presence_penalty", self.config.presence_penalty),
                frequency_penalty=kwargs.get("frequency_penalty", self.config.frequency_penalty),
                mirostat=kwargs.get("mirostat", self.config.mirostat),
                mirostat_tau=kwargs.get("mirostat_tau", self.config.mirostat_tau),
                mirostat_eta=kwargs.get("mirostat_eta", self.config.mirostat_eta),
                grammar=kwargs.get("grammar", self.config.grammar),
                json_schema=kwargs.get("json_schema", self.config.json_schema),
                max_tokens=kwargs.get("max_tokens", self.config.n_predict),
                stop=kwargs.get("stop", self.config.stopping_criteria),
                stream=False,
            )
        )
        
        return self._parse_completion(completion)

    async def stream_chat(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncIterator[LLMChunk]:
        llama = self._initialize_llama()
        
        stream = await asyncio.get_event_loop().run_in_executor(
            self._executor,
            lambda: llama.create_chat_completion(
                messages=messages,
                tools=tools,
                tool_choice="auto" if tools else "none",
                temperature=kwargs.get("temperature", self.config.temperature),
                top_p=kwargs.get("top_p", self.config.top_p),
                top_k=kwargs.get("top_k", self.config.top_k),
                min_p=kwargs.get("min_p", self.config.min_p),
                typical_p=kwargs.get("typical_p", self.config.typical_p),
                repeat_penalty=kwargs.get("repeat_penalty", self.config.repeat_penalty),
                repeat_last_n=kwargs.get("repeat_last_n", self.config.repeat_last_n),
                penalize_nl=self.config.penalize_nl,
                presence_penalty=kwargs.get("presence_penalty", self.config.presence_penalty),
                frequency_penalty=kwargs.get("frequency_penalty", self.config.frequency_penalty),
                mirostat=kwargs.get("mirostat", self.config.mirostat),
                mirostat_tau=kwargs.get("mirostat_tau", self.config.mirostat_tau),
                mirostat_eta=kwargs.get("mirostat_eta", self.config.mirostat_eta),
                grammar=kwargs.get("grammar", self.config.grammar),
                json_schema=kwargs.get("json_schema", self.config.json_schema),
                max_tokens=kwargs.get("max_tokens", self.config.n_predict),
                stop=kwargs.get("stop", self.config.stopping_criteria),
                stream=True,
            )
        )
        
        for chunk in stream:
            yield self._parse_stream_chunk(chunk)

    def _messages_to_prompt(self, messages: List[Dict[str, Any]]) -> str:
        prompt_parts = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            if role == "system":
                prompt_parts.append(f"<|system|>\n{content}")
            elif role == "user":
                prompt_parts.append(f"<|user|>\n{content}")
            elif role == "assistant":
                prompt_parts.append(f"<|assistant|>\n{content}")
            elif role == "tool":
                prompt_parts.append(f"<|tool|>\n{content}")
        prompt_parts.append("<|assistant|>")
        return "\n".join(prompt_parts)

    def _parse_completion(self, completion: Dict[str, Any]) -> LLMResponse:
        choice = completion["choices"][0]
        message = choice["message"]
        usage = completion.get("usage", {})
        
        input_tokens = usage.get("prompt_tokens", 0)
        output_tokens = usage.get("completion_tokens", 0)
        
        return LLMResponse(
            content=message.get("content", "") or "",
            tool_calls=message.get("tool_calls", []),
            finish_reason=choice.get("finish_reason", "stop"),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=input_tokens + output_tokens,
            model=self.config.model_path,
            provider=self.provider_type,
            metadata={
                "model_path": self.config.model_path,
                "n_ctx": self.config.n_ctx,
            }
        )

    def _parse_stream_chunk(self, chunk: Dict[str, Any]) -> LLMChunk:
        choice = chunk["choices"][0]
        delta = choice.get("delta", {})
        
        return LLMChunk(
            delta=delta.get("content", "") or "",
            tool_calls=delta.get("tool_calls", []),
            finish_reason=choice.get("finish_reason"),
            is_final=choice.get("finish_reason") is not None,
        )

    def estimate_cost(self, input_tokens: int, output_tokens: int) -> float:
        return 0.0

    def get_model_info(self) -> ModelInfo:
        return self._model_info

    def get_kv_cache_stats(self) -> Dict[str, Any]:
        return {
            "entries": len(self._kv_cache),
            "total_size_mb": sum(len(str(v)) for v in self._kv_cache.values()) / (1024 * 1024),
        }

    async def batch_inference(self, requests: List[Dict[str, Any]]) -> List[LLMResponse]:
        llama = self._initialize_llama()
        
        async def process_request(req):
            return await self.chat(**req)
        
        results = await asyncio.gather(*[process_request(r) for r in requests])
        return results

    @classmethod
    def from_env(cls) -> "LlamaCppProvider":
        model_path = os.getenv("LLAMACPP_MODEL_PATH")
        if not model_path:
            raise ValueError("LLAMACPP_MODEL_PATH not set")
        
        config = LlamaCppConfig(
            model_path=model_path,
            base_url=os.getenv("LLAMACPP_BASE_URL"),
            n_gpu_layers=int(os.getenv("LLAMACPP_N_GPU_LAYERS", "-1")),
            n_ctx=int(os.getenv("LLAMACPP_CTX_SIZE", "8192")),
            n_batch=int(os.getenv("LLAMACPP_BATCH_SIZE", "512")),
            n_threads=int(os.getenv("LLAMACPP_N_THREADS", "0")),
            flash_attn=os.getenv("LLAMACPP_FLASH_ATTN", "false").lower() == "true",
            kv_cache_quant=os.getenv("LLAMACPP_KV_CACHE_QUANT", "true").lower() == "true",
            speculative=os.getenv("LLAMACPP_SPECULATIVE"),
        )
        return cls(config)

    @classmethod
    def discover_gguf_models(cls, search_paths: List[str] = None) -> List[str]:
        if search_paths is None:
            search_paths = [
                os.getenv("LLAMACPP_MODEL_DIR", "~/.cache/llama.cpp/models"),
                "/models",
                "/workspace/models",
                "./models",
            ]
        
        models = []
        for path_str in search_paths:
            path = Path(path_str).expanduser()
            if path.exists():
                for gguf in path.rglob("*.gguf"):
                    models.append(str(gguf))
        return models


async def create_llamacpp_provider(**kwargs) -> LlamaCppProvider:
    provider = LlamaCppProvider.from_env()
    for key, value in kwargs.items():
        if hasattr(provider.config, key):
            setattr(provider.config, key, value)
    return provider