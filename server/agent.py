"""Simple OpenAI tool-calling agent loop (no orchestration framework)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from server.prompts import build_system_prompt
from server.tools import TOOL_DEFINITIONS, run_tool

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

MAX_HISTORY_MESSAGES = 25
MAX_TOOL_ITERS = 5
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")


def _client() -> OpenAI:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set. Please check your .env file.")
    return OpenAI(api_key=api_key)


def _trim_history(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the last N messages, but never orphan a tool message without its assistant call."""
    if len(history) <= MAX_HISTORY_MESSAGES:
        return list(history)

    trimmed = history[-MAX_HISTORY_MESSAGES:]
    # Drop leading tool messages that lack their preceding assistant tool_calls
    while trimmed and trimmed[0].get("role") == "tool":
        trimmed = trimmed[1:]
    # If we start mid tool-call assistant, skip until a clean user/assistant boundary
    while trimmed and trimmed[0].get("role") == "assistant" and trimmed[0].get("tool_calls"):
        # drop assistant + following tools
        trimmed = trimmed[1:]
        while trimmed and trimmed[0].get("role") == "tool":
            trimmed = trimmed[1:]
    return trimmed


def run_agent(
    history: list[dict[str, Any]],
    user_message: dict[str, Any],
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]] | None]:
    """
    Append user_message, run tool loop, update history.
    Returns (assistant_text, updated_history, products_for_ui).
    """
    client = _client()
    working = list(history)
    working.append(user_message)

    products_for_ui: list[dict[str, Any]] | None = None
    assistant_text = ""

    for _ in range(MAX_TOOL_ITERS):
        messages = [{"role": "system", "content": build_system_prompt()}]
        messages.extend(_trim_history(working))

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
        )
        choice = response.choices[0].message

        assistant_entry: dict[str, Any] = {
            "role": "assistant",
            "content": choice.content or "",
        }
        if choice.tool_calls:
            assistant_entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments or "{}",
                    },
                }
                for tc in choice.tool_calls
            ]
        working.append(assistant_entry)

        if not choice.tool_calls:
            assistant_text = choice.content or ""
            break

        for tc in choice.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result, products = run_tool(tc.function.name, args)
            if products:
                products_for_ui = products
            working.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                }
            )
    else:
        # Hit max iters without a final text reply
        if not assistant_text:
            assistant_text = (
                "Trail's a bit foggy on my end ⛰️ — mind sending that again? "
                "Onward into the unknown!"
            )
            working.append({"role": "assistant", "content": assistant_text})

    return assistant_text, working, products_for_ui
