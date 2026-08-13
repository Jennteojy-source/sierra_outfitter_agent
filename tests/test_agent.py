"""Unit tests for agent helpers (no live LLM)."""

from __future__ import annotations

from server.agent import (
    MAX_HISTORY_MESSAGES,
    _drop_old_images,
    _last_user_text,
    _latest_user_has_image,
    _messages_for_model,
    _trim_history,
)


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


def test_last_user_text_uses_actual_utterance():
    history = [
        {"role": "user", "content": "any coupons?"},
        {"role": "assistant", "content": "checking"},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "I'd like the Early Risers Promotion"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,xx"}},
            ],
        },
    ]
    assert "Early Risers" in _last_user_text(history)


def test_drop_old_images_keeps_only_latest_user_image():
    old = {
        "role": "user",
        "content": [
            {"type": "text", "text": "first photo"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,OLD"}},
        ],
    }
    reply = {"role": "assistant", "content": "got it"}
    latest = {
        "role": "user",
        "content": [
            {"type": "text", "text": "second photo"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,NEW"}},
        ],
    }
    cleaned = _drop_old_images([old, reply, latest])
    assert cleaned[0]["content"] == "first photo"
    assert isinstance(cleaned[2]["content"], list)
    assert cleaned[2]["content"][1]["image_url"]["url"].endswith("NEW")


def test_messages_for_model_strips_old_images_after_trim():
    history = []
    for i in range(3):
        history.append(
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": f"img {i}"},
                    {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{i}"}},
                ],
            }
        )
        history.append({"role": "assistant", "content": f"ok {i}"})
    prepared = _messages_for_model(history)
    image_msgs = [
        m for m in prepared
        if isinstance(m.get("content"), list)
    ]
    assert len(image_msgs) == 1


def test_latest_user_has_image():
    text_only = [{"role": "user", "content": "hi"}]
    assert _latest_user_has_image(text_only) is False
    with_photo = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "do you sell this"},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64,xx"}},
            ],
        }
    ]
    assert _latest_user_has_image(with_photo) is True
