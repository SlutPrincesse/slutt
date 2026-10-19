import tempfile
from pathlib import Path

from agent_system_v9.context.context_window import (
    ContextMessage,
    ContextWindow,
    estimate_tokens,
)


def test_estimate_tokens_basic():
    assert estimate_tokens("aaaa") == 1
    assert estimate_tokens("") >= 1


def test_context_message_autocalculates_tokens():
    msg = ContextMessage(role="user", content="a" * 20)
    assert msg.tokens == 5


def test_append_adds_message():
    window = ContextWindow(session_id="test", budget_tokens=10000, verbatim_tail=3)
    msg = window.append("user", "hello")
    assert len(window.get_messages()) == 1
    assert msg.content == "hello"


def test_budget_enforcement_no_compression_under_budget():
    window = ContextWindow(session_id="test", budget_tokens=10000, verbatim_tail=2)
    for i in range(5):
        window.append("user", f"message {i}")
    assert len(window.messages) == 5
    assert window._running_summary == ""


def test_compression_triggers_when_exceeding_budget():
    budget = 100
    window = ContextWindow(session_id="test", budget_tokens=budget, verbatim_tail=2)
    for i in range(10):
        window.append("user", "x" * 50)
    total = window.get_total_tokens()
    assert total <= budget
    assert window._running_summary != ""
    assert len(window.messages) == 2


def test_verbatim_tail_preserved():
    budget = 80
    window = ContextWindow(session_id="test", budget_tokens=budget, verbatim_tail=3)
    for i in range(6):
        window.append("user", "y" * 30)
    messages = window.messages
    assert len(messages) == 3


def test_get_messages_for_model_shape():
    budget = 10000
    window = ContextWindow(session_id="test", budget_tokens=budget, verbatim_tail=2)
    window.append("user", "hello")
    window.append("assistant", "hi")
    model_msgs = window.get_messages_for_model()
    for m in model_msgs:
        assert "role" in m
        assert "content" in m


def test_get_messages_for_model_includes_compressed_memory():
    budget = 50
    window = ContextWindow(session_id="test", budget_tokens=budget, verbatim_tail=1)
    for i in range(5):
        window.append("user", "z" * 40)
    model_msgs = window.get_messages_for_model()
    assert len(model_msgs) > 0
    assert model_msgs[0]["role"] == "system"
    assert "Compressed conversation memory" in model_msgs[0]["content"]


def test_persist_load_roundtrip():
    budget = 50
    window = ContextWindow(session_id="test-session", budget_tokens=budget, verbatim_tail=1)
    for i in range(5):
        window.append("user", f"msg{i} " * 10)
    with tempfile.TemporaryDirectory() as td:
        path = Path(td) / "window.json"
        window.save(path)
        window2 = ContextWindow(session_id="other", storage_path=path)
        assert window2.session_id == "test-session"
        assert window2.budget_tokens == budget
        assert window2.verbatim_tail == 1
        assert window2._running_summary == window._running_summary
        assert len(window2.messages) == len(window.messages)


def test_get_stats():
    window = ContextWindow(session_id="stats-test", budget_tokens=1000, verbatim_tail=4)
    window.append("user", "hello")
    stats = window.get_stats()
    assert stats["session_id"] == "stats-test"
    assert stats["budget_tokens"] == 1000
    assert stats["verbatim_tail"] == 4
    assert stats["message_count"] == 1
    assert "total_tokens" in stats
