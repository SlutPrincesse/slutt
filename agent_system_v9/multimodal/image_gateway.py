"""
Image Generation Gateway - Direct API bridge connecting agent triggers to visual asset endpoints
"""
import base64
import hashlib
import io
import threading
import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from PIL import Image


class ImageModel(Enum):
    DALLE_3 = "dall-e-3"
    DALLE_2 = "dall-e-2"
    MIDJOURNEY = "midjourney"
    STABLE_DIFFUSION = "stable-diffusion"
    STABLE_DIFFUSION_XL = "sdxl"
    FLUX = "flux"
    CUSTOM = "custom"


class ImageFormat(Enum):
    PNG = "png"
    JPEG = "jpeg"
    WEBP = "webp"
    BMP = "bmp"


@dataclass
class ImageRequest:
    request_id: str
    prompt: str
    model: ImageModel = ImageModel.STABLE_DIFFUSION_XL
    negative_prompt: str = ""
    width: int = 1024
    height: int = 1024
    steps: int = 30
    cfg_scale: float = 7.0
    seed: int | None = None
    format: ImageFormat = ImageFormat.PNG
    quality: str = "standard"
    style: str = "natural"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ImageResponse:
    request_id: str
    image_data: bytes
    format: ImageFormat
    width: int
    height: int
    model: ImageModel
    prompt: str
    seed: int
    generation_time: float
    metadata: dict[str, Any] = field(default_factory=dict)
    error: str | None = None


class ImageGenerationGateway:
    def __init__(self, max_concurrent: int = 4):
        self.max_concurrent = max_concurrent
        self._requests: dict[str, ImageRequest] = {}
        self._responses: dict[str, ImageResponse] = {}
        self._queue: deque = deque()
        self._active_count = 0
        self._lock = threading.RLock()
        self._running = False
        self._worker_thread: threading.Thread | None = None
        self._providers: dict[ImageModel, Callable] = {}
        self._default_provider: Callable | None = None
        self._callbacks: dict[str, list[Callable]] = {
            "generation_started": [],
            "generation_completed": [],
            "generation_failed": [],
            "progress": []
        }
        self._cache: dict[str, ImageResponse] = {}
        self._cache_size = 100

    def start(self):
        if self._running:
            return
        self._running = True
        self._worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._worker_thread.start()

    def stop(self):
        self._running = False
        if self._worker_thread:
            self._worker_thread.join(timeout=10.0)

    def register_provider(self, model: ImageModel, provider: Callable[[ImageRequest], ImageResponse]):
        """Register a provider function for a specific model"""
        self._providers[model] = provider

    def set_default_provider(self, provider: Callable[[ImageRequest], ImageResponse]):
        self._default_provider = provider

    def generate(self, request: ImageRequest) -> str:
        with self._lock:
            self._requests[request.request_id] = request
            self._queue.append(request.request_id)

        self._notify_generation_started(request)
        return request.request_id

    def generate_async(self, prompt: str, **kwargs) -> str:
        request_id = hashlib.sha256(f"{prompt}{time.time()}".encode()).hexdigest()[:12]
        request = ImageRequest(request_id=request_id, prompt=prompt, **kwargs)
        return self.generate(request)

    def get_response(self, request_id: str) -> ImageResponse | None:
        with self._lock:
            return self._responses.get(request_id)

    def wait_for_response(self, request_id: str, timeout: float = 60.0) -> ImageResponse | None:
        start = time.time()
        while time.time() - start < timeout:
            response = self.get_response(request_id)
            if response:
                return response
            time.sleep(0.1)
        return None

    def cancel(self, request_id: str) -> bool:
        with self._lock:
            if request_id in self._queue:
                self._queue.remove(request_id)
                return True
            # Can't cancel already processing requests easily
            return False

    def list_pending(self) -> list[ImageRequest]:
        with self._lock:
            return [self._requests[rid] for rid in self._queue if rid in self._requests]

    def list_completed(self, limit: int = 50) -> list[ImageResponse]:
        with self._lock:
            responses = list(self._responses.values())
            responses.sort(key=lambda r: r.generation_time, reverse=True)
            return responses[:limit]

    def register_callback(self, event: str, callback: Callable):
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _worker_loop(self):
        while self._running:
            request_id = None

            with self._lock:
                if self._active_count >= self.max_concurrent:
                    time.sleep(0.1)
                    continue

                if self._queue:
                    request_id = self._queue.popleft()
                    self._active_count += 1

            if request_id:
                self._process_request(request_id)
            else:
                time.sleep(0.1)

    def _process_request(self, request_id: str):
        with self._lock:
            request = self._requests.get(request_id)
            if not request:
                self._active_count -= 1
                return

        start_time = time.time()

        try:
            # Check cache
            cache_key = self._get_cache_key(request)
            with self._lock:
                if cache_key in self._cache:
                    cached = self._cache[cache_key]
                    cached.metadata["cached"] = True
                    self._responses[request_id] = cached
                    self._notify_generation_completed(cached)
                    self._active_count -= 1
                    return

            # Get provider
            provider = self._providers.get(request.model, self._default_provider)
            if not provider:
                raise RuntimeError(f"No provider for model {request.model}")

            # Generate
            response = provider(request)
            response.generation_time = time.time() - start_time
            response.request_id = request_id

            # Cache if successful
            if not response.error:
                with self._lock:
                    self._cache[cache_key] = response
                    if len(self._cache) > self._cache_size:
                        # Remove oldest
                        oldest = min(self._cache.keys(), key=lambda k: self._cache[k].generation_time)
                        del self._cache[oldest]

            with self._lock:
                self._responses[request_id] = response

            if response.error:
                self._notify_generation_failed(request_id, response.error)
            else:
                self._notify_generation_completed(response)

        except Exception as e:
            response = ImageResponse(
                request_id=request_id,
                image_data=b"",
                format=request.format,
                width=request.width,
                height=request.height,
                model=request.model,
                prompt=request.prompt,
                seed=request.seed or 0,
                generation_time=time.time() - start_time,
                error=str(e)
            )
            with self._lock:
                self._responses[request_id] = response
            self._notify_generation_failed(request_id, str(e))

        finally:
            with self._lock:
                self._active_count -= 1

    def _get_cache_key(self, request: ImageRequest) -> str:
        key_parts = [
            request.prompt,
            request.negative_prompt,
            str(request.width),
            str(request.height),
            str(request.steps),
            str(request.cfg_scale),
            str(request.seed or ""),
            request.model.value,
            request.style
        ]
        return hashlib.sha256("|".join(key_parts).encode()).hexdigest()[:32]

    def _notify_generation_started(self, request: ImageRequest):
        for cb in self._callbacks["generation_started"]:
            try:
                cb(request)
            except Exception:
                pass

    def _notify_generation_completed(self, response: ImageResponse):
        for cb in self._callbacks["generation_completed"]:
            try:
                cb(response)
            except Exception:
                pass

    def _notify_generation_failed(self, request_id: str, error: str):
        for cb in self._callbacks["generation_failed"]:
            try:
                cb(request_id, error)
            except Exception:
                pass

    def save_image(self, response: ImageResponse, filepath: str) -> bool:
        try:
            img = Image.open(io.BytesIO(response.image_data))
            img.save(filepath, format=response.format.value.upper())
            return True
        except Exception:
            return False

    def get_image_base64(self, response: ImageResponse) -> str:
        return base64.b64encode(response.image_data).decode('utf-8')

    def clear_cache(self):
        with self._lock:
            self._cache.clear()


_image_gateway: ImageGenerationGateway | None = None


def get_image_gateway() -> ImageGenerationGateway:
    global _image_gateway
    if _image_gateway is None:
        _image_gateway = ImageGenerationGateway()
        _image_gateway.start()
    return _image_gateway
