"""Unit tests for agent helpers (no live LLM)."""

from __future__ import annotations

from server.agent import MAX_HISTORY_MESSAGES, _trim_history


def test_trim_history_keeps_short_lists():
    history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
    assert _trim_history(history) == history


def test_trim_history_does_not_orphan_tool_messages():
    history = []
    for i in range(MAX_HISTORY_MESSAGES + 5):
        history.append({"role": "user", "content": f"u{i}"})
        history.append({"role": "assistant", "content": "", "tool_calls": [{"id": f"c{i}"}]})
        history.append({"role": "tool", "tool_call_id": f"c{i}", "content": "{}"})
        history.append({"role": "assistant", "content": f"a{i}"})
    trimmed = _trim_history(history)
    assert len(trimmed) <= MAX_HISTORY_MESSAGES + 4
    if trimmed:
        assert trimmed[0].get("role") != "tool"
        if trimmed[0].get("role") == "assistant":
            assert not trimmed[0].get("tool_calls")
