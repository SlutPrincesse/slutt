from agent_system_v9.telemetry.tracer import TraceEvent
from agent_system_v9.distillation.trace_distiller import TraceDistiller
from agent_system_v9.distillation.policy_distiller import PolicyDistiller


def test_trace_distiller():
    events = [
        TraceEvent(kind="tool_call", name="a"),
        TraceEvent(kind="tool_call", name="b"),
        TraceEvent(kind="tool_call", name="a"),
        TraceEvent(kind="tool_call", name="b"),
    ]
    d = TraceDistiller()
    r = d.distill(events)
    assert r["total_events"] == 4
    assert len(r["tool_sequences"]) >= 1


def test_policy_distiller():
    pd = PolicyDistiller()
    m = {"tools": {"t1": {"calls": 10, "errors": 2}}}
    r = pd.distill(m)
    assert "t1" in r["tools"]
    assert r["tools"]["t1"]["success_rate"] == 0.8
