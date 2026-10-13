"""
Streaming Audio Pipeline - Capture raw PCM/WAV, execute STT, synthesize streaming text to TTS
"""
import hashlib
import queue
import threading
import time
import wave
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

import numpy as np


class AudioFormat(Enum):
    PCM_16 = "pcm_16"
    PCM_24 = "pcm_24"
    PCM_32 = "pcm_32"
    FLOAT_32 = "float_32"
    WAV = "wav"
    MP3 = "mp3"
    OPUS = "opus"


class AudioState(Enum):
    IDLE = "idle"
    RECORDING = "recording"
    PROCESSING = "processing"
    PLAYING = "playing"
    ERROR = "error"


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1
    format: AudioFormat = AudioFormat.PCM_16
    chunk_size: int = 1024
    buffer_duration: float = 5.0  # seconds
    vad_threshold: float = 0.01
    silence_timeout: float = 2.0


@dataclass
class AudioStream:
    stream_id: str
    config: AudioConfig
    state: AudioState = AudioState.IDLE
    data: bytes = b""
    timestamp: float = field(default_factory=time.time)
    metadata: dict[str, Any] = field(default_factory=dict)


class StreamingAudioPipeline:
    def __init__(self, config: AudioConfig = None):
        self.config = config or AudioConfig()
        self._streams: dict[str, AudioStream] = {}
        self._audio_queue: queue.Queue = queue.Queue()
        self._stt_queue: queue.Queue = queue.Queue()
        self._tts_queue: queue.Queue = queue.Queue()
        self._lock = threading.RLock()
        self._running = False
        self._worker_threads: list[threading.Thread] = []
        self._callbacks: dict[str, list[Callable]] = {
            "audio_chunk": [],
            "stt_result": [],
            "tts_chunk": [],
            "state_change": [],
            "error": []
        }
        self._vad_enabled = True
        self._stt_engine = None
        self._tts_engine = None

    def start(self):
        if self._running:
            return
        self._running = True

        # Start worker threads
        self._worker_threads = [
            threading.Thread(target=self._audio_processor, daemon=True),
            threading.Thread(target=self._stt_processor, daemon=True),
            threading.Thread(target=self._tts_processor, daemon=True),
        ]

        for t in self._worker_threads:
            t.start()

    def stop(self):
        self._running = False
        for t in self._worker_threads:
            t.join(timeout=2.0)
        self._worker_threads.clear()

    def create_stream(self, config: AudioConfig = None) -> str:
        stream_id = hashlib.sha256(f"{time.time()}{threading.current_thread().ident}".encode()).hexdigest()[:8]
        stream_config = config or self.config

        stream = AudioStream(
            stream_id=stream_id,
            config=stream_config,
            state=AudioState.IDLE
        )

        with self._lock:
            self._streams[stream_id] = stream

        return stream_id

    def write_audio(self, stream_id: str, data: bytes) -> bool:
        with self._lock:
            stream = self._streams.get(stream_id)
            if not stream:
                return False

            if stream.state == AudioState.IDLE:
                stream.state = AudioState.RECORDING
                self._notify_state_change(stream_id, AudioState.RECORDING)

            stream.data += data
            stream.timestamp = time.time()

        try:
            self._audio_queue.put_nowait((stream_id, data))
            return True
        except queue.Full:
            return False

    def read_audio(self, stream_id: str, max_chunks: int = 10) -> list[bytes]:
        chunks = []
        with self._lock:
            stream = self._streams.get(stream_id)
            if not stream:
                return chunks

        # In a real implementation, this would read from a ring buffer
        # For now, return the accumulated data
        return [stream.data] if stream.data else []

    def start_stt(self, stream_id: str, language: str = "en") -> bool:
        with self._lock:
            stream = self._streams.get(stream_id)
            if not stream:
                return False

            stream.state = AudioState.PROCESSING
            stream.metadata["stt_language"] = language
            self._notify_state_change(stream_id, AudioState.PROCESSING)

        try:
            self._stt_queue.put_nowait((stream_id, language))
            return True
        except queue.Full:
            return False

    def start_tts(self, stream_id: str, text: str, voice: str = "default") -> bool:
        with self._lock:
            stream = self._streams.get(stream_id)
            if not stream:
                return False

            stream.state = AudioState.PROCESSING
            self._notify_state_change(stream_id, AudioState.PROCESSING)

        try:
            self._tts_queue.put_nowait((stream_id, text, voice))
            return True
        except queue.Full:
            return False

    def stop_stream(self, stream_id: str) -> bool:
        with self._lock:
            stream = self._streams.get(stream_id)
            if not stream:
                return False

            stream.state = AudioState.IDLE
            self._notify_state_change(stream_id, AudioState.IDLE)
        return True

    def close_stream(self, stream_id: str) -> bool:
        with self._lock:
            stream = self._streams.pop(stream_id, None)
            if not stream:
                return False

        return True

    def get_stream(self, stream_id: str) -> AudioStream | None:
        with self._lock:
            return self._streams.get(stream_id)

    def list_streams(self) -> list[AudioStream]:
        with self._lock:
            return list(self._streams.values())

    def set_stt_engine(self, engine: Callable[[bytes, str], str]):
        """Set STT engine: (audio_data, language) -> text"""
        self._stt_engine = engine

    def set_tts_engine(self, engine: Callable[[str, str], bytes]):
        """Set TTS engine: (text, voice) -> audio_data"""
        self._tts_engine = engine

    def register_callback(self, event: str, callback: Callable):
        if event in self._callbacks:
            self._callbacks[event].append(callback)

    def _audio_processor(self):
        while self._running:
            try:
                stream_id, data = self._audio_queue.get(timeout=0.1)

                # VAD processing
                if self._vad_enabled and self._is_speech(data):
                    self._notify_audio_chunk(stream_id, data)

                # Buffer management
                with self._lock:
                    stream = self._streams.get(stream_id)
                    if stream and len(stream.data) > stream.config.sample_rate * stream.config.buffer_duration * 2:
                        # Trim old data
                        stream.data = stream.data[-int(stream.config.sample_rate * stream.config.buffer_duration * 2):]

            except queue.Empty:
                continue
            except Exception as e:
                self._notify_error("audio_processor", str(e))

    def _stt_processor(self):
        while self._running:
            try:
                stream_id, language = self._stt_queue.get(timeout=0.1)

                with self._lock:
                    stream = self._streams.get(stream_id)
                    if not stream:
                        continue
                    audio_data = stream.data

                if self._stt_engine and audio_data:
                    try:
                        text = self._stt_engine(audio_data, language)
                        self._notify_stt_result(stream_id, text, language)
                    except Exception as e:
                        self._notify_error("stt", str(e))

                with self._lock:
                    stream = self._streams.get(stream_id)
                    if stream:
                        stream.state = AudioState.IDLE
                        self._notify_state_change(stream_id, AudioState.IDLE)

            except queue.Empty:
                continue
            except Exception as e:
                self._notify_error("stt_processor", str(e))

    def _tts_processor(self):
        while self._running:
            try:
                stream_id, text, voice = self._tts_queue.get(timeout=0.1)

                if self._tts_engine and text:
                    try:
                        audio_data = self._tts_engine(text, voice)
                        self._notify_tts_chunk(stream_id, audio_data)
                    except Exception as e:
                        self._notify_error("tts", str(e))

                with self._lock:
                    stream = self._streams.get(stream_id)
                    if stream:
                        stream.state = AudioState.IDLE
                        self._notify_state_change(stream_id, AudioState.IDLE)

            except queue.Empty:
                continue
            except Exception as e:
                self._notify_error("tts_processor", str(e))

    def _is_speech(self, data: bytes) -> bool:
        if len(data) < 2:
            return False

        # Simple energy-based VAD
        audio_array = np.frombuffer(data, dtype=np.int16)
        energy = np.mean(np.abs(audio_array)) / 32768.0
        return energy > self.config.vad_threshold

    def _notify_audio_chunk(self, stream_id: str, data: bytes):
        for cb in self._callbacks["audio_chunk"]:
            try:
                cb(stream_id, data)
            except Exception:
                pass

    def _notify_stt_result(self, stream_id: str, text: str, language: str):
        for cb in self._callbacks["stt_result"]:
            try:
                cb(stream_id, text, language)
            except Exception:
                pass

    def _notify_tts_chunk(self, stream_id: str, data: bytes):
        for cb in self._callbacks["tts_chunk"]:
            try:
                cb(stream_id, data)
            except Exception:
                pass

    def _notify_state_change(self, stream_id: str, state: AudioState):
        for cb in self._callbacks["state_change"]:
            try:
                cb(stream_id, state)
            except Exception:
                pass

    def _notify_error(self, source: str, error: str):
        for cb in self._callbacks["error"]:
            try:
                cb(source, error)
            except Exception:
                pass

    def save_wav(self, stream_id: str, filepath: str) -> bool:
        with self._lock:
            stream = self._streams.get(stream_id)
            if not stream or not stream.data:
                return False

        try:
            with wave.open(filepath, 'wb') as wf:
                wf.setnchannels(stream.config.channels)
                wf.setsampwidth(2)  # 16-bit
                wf.setframerate(stream.config.sample_rate)
                wf.writeframes(stream.data)
            return True
        except Exception:
            return False


_audio_pipeline: StreamingAudioPipeline | None = None


def get_audio_pipeline() -> StreamingAudioPipeline:
    global _audio_pipeline
    if _audio_pipeline is None:
        from ..core.config import config
        cfg = AudioConfig(
            sample_rate=config.get_param("multimodal", "audio_sample_rate", 16000),
        )
        _audio_pipeline = StreamingAudioPipeline(cfg)
        _audio_pipeline.start()
    return _audio_pipeline
