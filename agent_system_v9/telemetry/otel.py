"""Optional OpenTelemetry tracing (no-op if unavailable)."""
from __future__ import annotations

try:
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
    _OTEL = True
except Exception:
    _OTEL = False


def get_tracer(name: str = "agent_system_v9"):
    if _OTEL:
        try:
            provider = TracerProvider()
            provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
            trace.set_tracer_provider(provider)
            return trace.get_tracer(name)
        except Exception:
            pass
    # no-op tracer
    class _NoopSpan:
        def __enter__(self): return self
        def __exit__(self, *a): return False
        def set_attribute(self, *a, **k): pass
    class _NoopTracer:
        def start_span(self, name, **kw): return _NoopSpan()
        def start_as_current_span(self, name, **kw): return _NoopSpan()
    return _NoopTracer()
