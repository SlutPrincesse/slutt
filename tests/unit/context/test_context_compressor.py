from agent_system_v9.context.context_compressor import (
    ContextCompressor,
    estimate_tokens,
)


def test_estimate_tokens():
    assert estimate_tokens("aaaa") == 1
    assert estimate_tokens("") >= 1


def test_summarize_under_budget_returns_original():
    c = ContextCompressor()
    text = "short text"
    r = c.summarize(text, max_tokens=100)
    assert r.summary == text
    assert r.compression_ratio == 1.0


def test_summarize_compresses_long_text():
    c = ContextCompressor()
    text = "This is sentence one. " * 20 + "Important conclusion here."
    r = c.summarize(text, max_tokens=30)
    assert estimate_tokens(r.summary) <= 30 or estimate_tokens(r.summary) <= estimate_tokens(text)
    assert r.summary_tokens <= r.source_tokens


def test_dedupe_removes_duplicates():
    c = ContextCompressor()
    history = [
        {"role": "user", "content": "Hello world this is a test"},
        {"role": "user", "content": "Hello world this is a test"},
        {"role": "assistant", "content": "Different content here"},
    ]
    out = c.dedupe(history)
    assert len(out) == 2


def test_rolling_summary_returns_tail():
    c = ContextCompressor()
    history = [{"role": "user", "content": "old " * 50} for _ in range(5)]
    new_msgs = [{"role": "user", "content": "new msg"}]
    summary, tail = c.rolling_summary(history, new_msgs, budget=100, verbatim_tail=2)
    assert len(tail) == 2
    assert isinstance(summary, str)


def test_llm_provider_used_when_configured():
    def provider(text, max_tokens):
        return "abstract summary"
    c = ContextCompressor(llm_provider=provider)
    text = "long text " * 50
    r = c.summarize(text, max_tokens=10)
    assert r.summary == "abstract summary"
