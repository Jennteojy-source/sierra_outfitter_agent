"""
Evaluation Runner for Sierra Outfitter AI Agent.

Executes test cases against the agent and scores tool invocation,
argument correctness, empty-match results, and handoff flags.
Does not score assistant wording.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any
from unittest.mock import patch

from evals.dataset import EVAL_DATASET, EvalTestCase
from server.agent import run_agent


class FixedDateTime(datetime):
    _fixed_now: datetime | None = None

    @classmethod
    def now(cls, tz=None):
        if cls._fixed_now is not None:
            if tz is not None:
                return cls._fixed_now.astimezone(tz)
            return cls._fixed_now
        return datetime.now(tz)


def make_datetime_mock(iso_str: str):
    dt = datetime.fromisoformat(iso_str)

    class CustomFixedDateTime(FixedDateTime):
        _fixed_now = dt

    return CustomFixedDateTime


def extract_tool_calls(history: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Extract all tool calls executed during the agent run, with parsed results."""
    calls: list[dict[str, Any]] = []
    by_id: dict[str, dict[str, Any]] = {}
    for msg in history:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                name = tc.get("function", {}).get("name")
                raw_args = tc.get("function", {}).get("arguments", "{}")
                try:
                    args = json.loads(raw_args)
                except Exception:
                    args = {}
                call = {"name": name, "args": args, "id": tc.get("id"), "result": None}
                calls.append(call)
                if call["id"]:
                    by_id[call["id"]] = call
        elif msg.get("role") == "tool":
            tid = msg.get("tool_call_id")
            if tid in by_id:
                try:
                    by_id[tid]["result"] = json.loads(msg.get("content") or "{}")
                except Exception:
                    by_id[tid]["result"] = {}
    return calls


def _is_no_match_result(result: Any) -> bool:
    """True when a completed lookup/search found nothing (not a missing-field ask)."""
    if not isinstance(result, dict):
        return False
    if result.get("need"):
        return False
    if result.get("found") is False:
        return True
    products = result.get("products")
    return isinstance(products, list) and len(products) == 0 and result.get("count") == 0


def _run_conversation(test_case: EvalTestCase) -> tuple[str, str, list[dict[str, Any]], list[list[str]], dict[str, Any]]:
    """Run all user turns. Returns (first_text, final_text, all_calls, per_turn_names, flags)."""
    prompts = [test_case.user_prompt, *test_case.follow_ups]
    history: list[dict[str, Any]] = []
    all_calls: list[dict[str, Any]] = []
    turn_names: list[list[str]] = []
    first_text = ""
    assistant_text = ""
    flags: dict[str, Any] = {}

    for prompt in prompts:
        before = len(history)
        assistant_text, history, _products, flags = run_agent(
            history,
            {"role": "user", "content": prompt},
        )
        if not first_text:
            first_text = assistant_text
        turn_calls = extract_tool_calls(history[before:])
        all_calls.extend(turn_calls)
        turn_names.append([tc["name"] for tc in turn_calls])

    return first_text, assistant_text, all_calls, turn_names, flags


def run_single_test(test_case: EvalTestCase) -> dict[str, Any]:
    """Runs a single test case (one or more turns) and returns evaluation results."""

    def _invoke():
        return _run_conversation(test_case)

    if test_case.time_mock_pt:
        mock_dt = make_datetime_mock(test_case.time_mock_pt)
        with patch("server.tools.datetime", mock_dt), patch("server.prompts.datetime", mock_dt):
            first_text, assistant_text, tool_calls, turn_names, flags = _invoke()
    else:
        first_text, assistant_text, tool_calls, turn_names, flags = _invoke()

    executed_tool_names = [tc["name"] for tc in tool_calls]
    failures: list[str] = []

    if test_case.forbidden_until_last:
        for turn_i, names in enumerate(turn_names[:-1], 1):
            for tool in test_case.forbidden_until_last:
                if tool in names:
                    failures.append(
                        f"Turn {turn_i}: '{tool}' was called before the last user message. "
                        f"Tools that turn: {names}"
                    )

    for exp_tool in test_case.expected_tools:
        if exp_tool not in executed_tool_names:
            failures.append(
                f"Expected tool '{exp_tool}' was NOT called. Executed tools: {executed_tool_names}"
            )

    for forb_tool in test_case.forbidden_tools:
        if forb_tool in executed_tool_names:
            failures.append(f"Forbidden tool '{forb_tool}' WAS called!")

    for tool_name, checker in test_case.arg_checkers.items():
        matching_args = [tc["args"] for tc in tool_calls if tc["name"] == tool_name]
        if not matching_args:
            failures.append(f"No call to tool '{tool_name}' to check arguments for.")
        else:
            arg_passed = any(checker(args) for args in matching_args)
            if not arg_passed:
                failures.append(
                    f"Tool '{tool_name}' argument check failed for args: {matching_args}"
                )

    if test_case.expect_no_match:
        matching = [tc for tc in tool_calls if tc["name"] == test_case.expect_no_match]
        if not matching:
            failures.append(
                f"Expected '{test_case.expect_no_match}' to return no match, but it was never called."
            )
        elif not _is_no_match_result(matching[-1].get("result")):
            failures.append(
                f"Expected '{test_case.expect_no_match}' to return no match; "
                f"last result was: {matching[-1].get('result')}"
            )

    handed_off = bool(flags.get("handed_off"))
    if test_case.expect_handed_off is True and not handed_off:
        failures.append("Expected handed_off=True but agent stayed in AI mode.")
    if test_case.expect_handed_off is False and handed_off:
        failures.append("Expected handed_off=False but agent escalated to a human.")

    passed = len(failures) == 0
    return {
        "id": test_case.id,
        "category": test_case.category,
        "description": test_case.description,
        "passed": passed,
        "user_prompt": test_case.user_prompt,
        "follow_ups": list(test_case.follow_ups),
        "assistant_text": assistant_text,
        "first_turn_text": first_text,
        "executed_tools": executed_tool_names,
        "turn_tools": turn_names,
        "tool_calls": tool_calls,
        "handed_off": handed_off,
        "failures": failures,
    }


def run_evals(category_filter: str | None = None, test_id_filter: str | None = None) -> list[dict[str, Any]]:
    """Runs evaluation dataset and outputs results report."""
    filtered_cases = EVAL_DATASET

    if category_filter:
        filtered_cases = [c for c in filtered_cases if c.category.lower() == category_filter.lower()]

    if test_id_filter:
        filtered_cases = [c for c in filtered_cases if test_id_filter.lower() in c.id.lower()]

    print("\n" + "=" * 80)
    print(f"🚀 SIERRA OUTFITTER AGENT EVALUATION RUNNER")
    print(f"Total Test Cases: {len(filtered_cases)}")
    print("=" * 80 + "\n")

    results = []
    category_scores: dict[str, dict[str, int]] = {}

    for idx, test_case in enumerate(filtered_cases, 1):
        print(f"[{idx}/{len(filtered_cases)}] Running: {test_case.id} ({test_case.category.upper()})")
        print(f"    Prompt: \"{test_case.user_prompt}\"")
        for follow_i, follow in enumerate(test_case.follow_ups, 2):
            print(f"    Turn {follow_i}: \"{follow}\"")

        res = run_single_test(test_case)
        results.append(res)

        cat = test_case.category
        if cat not in category_scores:
            category_scores[cat] = {"pass": 0, "total": 0}
        category_scores[cat]["total"] += 1

        if res["passed"]:
            category_scores[cat]["pass"] += 1
            print(f"    Status: ✅ PASS")
            print(f"    Tools Called: {res['executed_tools']}")
        else:
            print(f"    Status: ❌ FAIL")
            print(f"    Tools Called: {res['executed_tools']}")
            for f in res["failures"]:
                print(f"      - Failure: {f}")
        print(f"    Response snippet: \"{res['assistant_text'][:120]}...\"\n")

    # Summary
    total_passed = sum(1 for r in results if r["passed"])
    total_tests = len(results)
    pass_rate = (total_passed / total_tests * 100) if total_tests > 0 else 0

    print("=" * 80)
    print("📊 EVALUATION SUMMARY")
    print("=" * 80)
    print(f"Overall Score: {total_passed}/{total_tests} ({pass_rate:.1f}% Pass Rate)\n")

    print("Category Breakdown:")
    for cat, score in category_scores.items():
        cat_rate = (score["pass"] / score["total"] * 100) if score["total"] > 0 else 0
        print(f"  - {cat.upper():<10}: {score['pass']}/{score['total']} ({cat_rate:.1f}%)")
    print("=" * 80 + "\n")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Sierra Outfitter Agent Evaluation Runner")
    parser.add_argument(
        "--category",
        choices=["catalog", "order", "promo", "handoff"],
        help="Filter by category",
    )
    parser.add_argument("--case-id", help="Filter by test case ID")

    args = parser.parse_args()
    results = run_evals(category_filter=args.category, test_id_filter=args.case_id)
    all_passed = all(r["passed"] for r in results)
    sys.exit(0 if all_passed else 1)
