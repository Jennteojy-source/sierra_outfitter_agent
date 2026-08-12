"""Simple OpenAI tool-calling agent loop (no orchestration framework)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from openai import OpenAI

from server.prompts import build_nudge_prompt, build_system_prompt
from server.tools import TOOL_DEFINITIONS, run_tool
from server.usage import add_response_usage, build_debug, empty_usage

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

MAX_HISTORY_MESSAGES = 25
MAX_TOOL_ITERS = 5
MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")

DEFAULT_HANDOFF = (
    "I've reached the edge of what I can do from basecamp. "
    "A human trail guide is queued for that — hang tight. "
    "While you wait, I can still help with orders, gear, or Early Risers. 🏔️"
)
DEFAULT_NUDGE = (
    "Still with me on the trail? Happy to keep helping whenever you're ready. 🏔️"
)


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
    while trimmed and trimmed[0].get("role") == "tool":
        trimmed = trimmed[1:]
    while trimmed and trimmed[0].get("role") == "assistant" and trimmed[0].get("tool_calls"):
        trimmed = trimmed[1:]
        while trimmed and trimmed[0].get("role") == "tool":
            trimmed = trimmed[1:]
    return trimmed


def run_agent(
    history: list[dict[str, Any]],
    user_message: dict[str, Any],
    *,
    handoff_queued: bool = False,
    handoff_reason: str | None = None,
) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]] | None, dict[str, Any]]:
    """
    Append user_message, run tool loop, update history.
    Returns (assistant_text, updated_history, products_for_ui, flags).
    """
    client = _client()
    working = list(history)
    working.append(user_message)

    products_for_ui: list[dict[str, Any]] | None = None
    assistant_text = ""
    handed_off = False
    new_handoff_reason: str | None = None
    debug_tools: list[dict[str, Any]] = []
    usage = empty_usage()

    for _ in range(MAX_TOOL_ITERS):
        messages = [
            {
                "role": "system",
                "content": build_system_prompt(
                    handoff_queued=handoff_queued or handed_off,
                    handoff_reason=new_handoff_reason or handoff_reason,
                ),
            }
        ]
        messages.extend(_trim_history(working))

        response = client.chat.completions.create(
            model=MODEL,
            messages=messages,
            tools=TOOL_DEFINITIONS,
            tool_choice="auto",
        )
        add_response_usage(usage, response)
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
            debug_tools.append(
                {
                    "name": tc.function.name,
                    "arguments": args,
                    "ok": not (isinstance(result, dict) and result.get("error")),
                }
            )
            if tc.function.name == "request_human_handoff" or (
                isinstance(result, dict) and result.get("handed_off")
            ):
                handed_off = True
                new_handoff_reason = (
                    (args.get("reason") if isinstance(args, dict) else None)
                    or (result.get("reason") if isinstance(result, dict) else None)
                )
            working.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(result),
                }
            )
    else:
        if not assistant_text:
            assistant_text = (
                "Trail's a bit foggy on my end ⛰️ — mind sending that again? "
                "Onward into the unknown!"
            )
            working.append({"role": "assistant", "content": assistant_text})

    if handed_off and not assistant_text.strip():
        assistant_text = DEFAULT_HANDOFF
        working.append({"role": "assistant", "content": assistant_text})

    flags = {
        "handed_off": handed_off,
        "handoff_reason": new_handoff_reason,
        "debug": build_debug(model=MODEL, tool_calls=debug_tools, usage=usage),
    }
    return assistant_text, working, products_for_ui, flags


def run_nudge(history: list[dict[str, Any]]) -> tuple[str, list[dict[str, Any]], dict[str, Any]]:
    """One-shot idle follow-up. Does not call tools. Does not add a fake user turn."""
    client = _client()
    usage = empty_usage()
    messages = [{"role": "system", "content": build_nudge_prompt()}]
    messages.extend(_trim_history(history))
    messages.append(
        {
            "role": "user",
            "content": (
                "[SYSTEM] The customer has been idle. Write the one-time check-in now. "
                "Do not call tools. Do not ask them to rate the conversation."
            ),
        }
    )
    response = client.chat.completions.create(
        model=MODEL,
        messages=messages,
    )
    add_response_usage(usage, response)
    text = (response.choices[0].message.content or "").strip() or DEFAULT_NUDGE
    working = list(history)
    working.append({"role": "assistant", "content": text})
    debug = build_debug(model=MODEL, tool_calls=[], usage=usage)
    return text, working, debug
