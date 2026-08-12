"""Unit tests for debug cost estimates."""

from __future__ import annotations

from types import SimpleNamespace

from server.usage import add_response_usage, build_debug, empty_usage, estimate_cost_usd


def test_gpt4o_cost_matches_published_rates():
    # 1M input + 1M output = $2.50 + $10.00
    assert estimate_cost_usd("gpt-4o", 1_000_000, 1_000_000) == 12.5


def test_cached_tokens_use_half_input_rate():
    cost = estimate_cost_usd("gpt-4o", 1_000_000, 0, cached_tokens=1_000_000)
    assert cost == 1.25


def test_build_debug_includes_model_tools_and_cost():
    usage = empty_usage()
    usage["api_calls"] = 2
    usage["prompt_tokens"] = 1000
    usage["completion_tokens"] = 200
    usage["total_tokens"] = 1200
    debug = build_debug(
        model="gpt-4o",
        tool_calls=[{"name": "lookup_order", "arguments": {"order_number": "#W001"}}],
        usage=usage,
    )
    assert debug["model"] == "gpt-4o"
    assert debug["tool_calls"][0]["name"] == "lookup_order"
    assert debug["cost_usd"] > 0
    assert debug["api_calls"] == 2


def test_add_response_usage_reads_openai_shape():
    bucket = empty_usage()
    response = SimpleNamespace(
        usage=SimpleNamespace(
            prompt_tokens=10,
            completion_tokens=5,
            prompt_tokens_details=SimpleNamespace(cached_tokens=2),
        )
    )
    add_response_usage(bucket, response)
    assert bucket["api_calls"] == 1
    assert bucket["prompt_tokens"] == 10
    assert bucket["completion_tokens"] == 5
    assert bucket["cached_tokens"] == 2
    assert bucket["total_tokens"] == 15
