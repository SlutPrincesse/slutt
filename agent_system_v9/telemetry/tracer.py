"""Trace & telemetry foundation: standardized trace schema + JSONL persistence."""
from __future__ import annotations

import json
import time
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class TraceEvent:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    kind: str = ""  # tool_call, llm_call, decision, outcome
    name: str = ""
    input: dict[str, Any] = field(default_factory=dict)
    output: dict[str, Any] = field(default_factory=dict)
    latency_ms: float = 0.0
    cost: float = 0.0
    success: bool = True
    error: str | None = None
    timestamp: str = field(default_factory=lambda: __import__("datetime").datetime.utcnow().isoformat())
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class Tracer:
    def __init__(self, log_path: Path | None = None, episodic_store=None):
        self.log_path = log_path
        self.episodic_store = episodic_store
        self._events: list[TraceEvent] = []

    def record(self, event: TraceEvent) -> None:
        self._events.append(event)
        if self.log_path:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a") as f:
                f.write(json.dumps(event.to_dict()) + "\n")
        if self.episodic_store is not None:
            try:
                from agent_system_v9.memory.episodic_store import Episode, EpisodeType, EpisodeStatus
                ep = Episode(
                    id=event.id,
                    episode_type=EpisodeType.TOOL_INVOCATION if event.kind == "tool_call" else EpisodeType.OBSERVATION,
                    title=event.name,
                    description=event.kind,
                    status=EpisodeStatus.COMPLETED if event.success else EpisodeStatus.FAILED,
                    context=event.metadata,
                    input_data=event.input,
                    output_data=event.output,
                    error=event.error,
                    tags=[event.kind],
                )
                self.episodic_store.add_episode(ep)
            except Exception:
                pass

    def span(self, kind: str, name: str, input_data: dict[str, Any] | None = None):
        return _Span(self, kind, name, input_data or {})

    def events(self) -> list[TraceEvent]:
        return list(self._events)

    def aggregate(self) -> dict[str, Any]:
        by_name: dict[str, dict[str, Any]] = {}
        for e in self._events:
            entry = by_name.setdefault(e.name, {"calls": 0, "errors": 0, "latency_ms": 0.0, "cost": 0.0})
            entry["calls"] += 1
            if not e.success:
                entry["errors"] += 1
            entry["latency_ms"] += e.latency_ms
            entry["cost"] += e.cost
        return by_name

    def clear(self) -> None:
        self._events.clear()


class _Span:
    def __init__(self, tracer: Tracer, kind: str, name: str, input_data: dict[str, Any]):
        self.tracer = tracer
        self.kind = kind
        self.name = name
        self.input = input_data
        self.start = 0.0
        self.event: TraceEvent | None = None

    def __enter__(self):
        self.start = time.monotonic()
        try:
            from .otel import get_tracer as _get_otel
            self._otel_span = _get_otel().start_span(self.name)
        except Exception:
            self._otel_span = None
        return self

    def __exit__(self, exc_type, exc, tb):
        latency = (time.monotonic() - self.start) * 1000
        ev = TraceEvent(
            kind=self.kind,
            name=self.name,
            input=self.input,
            latency_ms=latency,
            success=exc is None,
            error=str(exc) if exc else None,
        )
        self.tracer.record(ev)
        if getattr(self, "_otel_span", None) is not None:
            try:
                self._otel_span.set_attribute("success", ev.success)
                self._otel_span.__exit__(exc_type, exc, tb)
            except Exception:
                pass
        self.event = ev
        return False
