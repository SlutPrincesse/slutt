import tempfile
from pathlib import Path

from agent_system_v9.telemetry.tracer import Tracer, TraceEvent


def test_record_and_aggregate():
    with tempfile.TemporaryDirectory() as td:
        log = Path(td) / "t.jsonl"
        tr = Tracer(log_path=log)
        tr.record(TraceEvent(kind="tool_call", name="t1", success=True, latency_ms=5.0))
        tr.record(TraceEvent(kind="tool_call", name="t1", success=False, latency_ms=2.0, error="e"))
        agg = tr.aggregate()
        assert agg["t1"]["calls"] == 2
        assert agg["t1"]["errors"] == 1
        assert log.exists()
