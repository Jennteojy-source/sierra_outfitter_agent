"""Token usage + estimated USD cost for debug traces."""

from __future__ import annotations

from typing import Any

# USD per 1M tokens: (input, cached_input, output)
# Source: OpenAI API pricing, Aug 2026.
_RATES: dict[str, tuple[float, float, float]] = {
    "gpt-4o": (2.50, 1.25, 10.00),
    "gpt-4o-mini": (0.15, 0.075, 0.60),
    "gpt-4.1": (2.00, 0.50, 8.00),
    "gpt-4.1-mini": (0.40, 0.10, 1.60),
    "gpt-4.1-nano": (0.10, 0.025, 0.40),
}


def empty_usage() -> dict[str, int]:
    return {
        "api_calls": 0,
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "cached_tokens": 0,
        "total_tokens": 0,
    }


def _rates_for(model: str) -> tuple[float, float, float]:
    key = (model or "").lower().strip()
    if key in _RATES:
        return _RATES[key]
    for name, rates in _RATES.items():
        if key.startswith(name):
            return rates
    return _RATES["gpt-4o"]


def estimate_cost_usd(
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    cached_tokens: int = 0,
) -> float:
    inp, cached, out = _rates_for(model)
    uncached = max(int(prompt_tokens) - int(cached_tokens), 0)
    return (
        uncached * inp + int(cached_tokens) * cached + int(completion_tokens) * out
    ) / 1_000_000


def add_response_usage(bucket: dict[str, int], response: Any) -> None:
    usage = getattr(response, "usage", None)
    if usage is None:
        return
    prompt = int(getattr(usage, "prompt_tokens", 0) or 0)
    completion = int(getattr(usage, "completion_tokens", 0) or 0)
    details = getattr(usage, "prompt_tokens_details", None)
    cached = int(getattr(details, "cached_tokens", 0) or 0) if details else 0
    bucket["api_calls"] += 1
    bucket["prompt_tokens"] += prompt
    bucket["completion_tokens"] += completion
    bucket["cached_tokens"] += cached
    bucket["total_tokens"] += prompt + completion


def build_debug(
    *,
    model: str,
    tool_calls: list[dict[str, Any]],
    usage: dict[str, int],
) -> dict[str, Any]:
    cost = estimate_cost_usd(
        model,
        usage.get("prompt_tokens", 0),
        usage.get("completion_tokens", 0),
        usage.get("cached_tokens", 0),
    )
    return {
        "model": model,
        "tool_calls": tool_calls,
        "api_calls": usage.get("api_calls", 0),
        "usage": {
            "prompt_tokens": usage.get("prompt_tokens", 0),
            "completion_tokens": usage.get("completion_tokens", 0),
            "cached_tokens": usage.get("cached_tokens", 0),
            "total_tokens": usage.get("total_tokens", 0),
        },
        "cost_usd": round(cost, 6),
    }
