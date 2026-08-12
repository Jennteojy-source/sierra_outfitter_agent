"""
Evaluation Runner for Sierra Outfitter AI Agent.

Executes test cases against the agent, evaluates tool invocation accuracy,
argument correctness, and text response assertions.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any
from unittest.mock import patch
from zoneinfo import ZoneInfo

from evals.dataset import EVAL_DATASET, EvalTestCase
from server.agent import run_agent

PT = ZoneInfo("America/Los_Angeles")


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
    """Extract all tool calls executed during the agent run."""
    calls = []
    for msg in history:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            for tc in msg["tool_calls"]:
                name = tc.get("function", {}).get("name")
                raw_args = tc.get("function", {}).get("arguments", "{}")
                try:
                    args = json.loads(raw_args)
                except Exception:
                    args = {}
                calls.append({"name": name, "args": args})
    return calls


def run_single_test(test_case: EvalTestCase) -> dict[str, Any]:
    """Runs a single test case and returns evaluation results."""
    user_msg = {"role": "user", "content": test_case.user_prompt}

    def _invoke():
        return run_agent(history=[], user_message=user_msg)

    if test_case.time_mock_pt:
        mock_dt = make_datetime_mock(test_case.time_mock_pt)
        with patch("server.tools.datetime", mock_dt), patch("server.prompts.datetime", mock_dt):
            assistant_text, history, products, flags = _invoke()
    else:
        assistant_text, history, products, flags = _invoke()

    tool_calls = extract_tool_calls(history)
    executed_tool_names = [tc["name"] for tc in tool_calls]

    failures: list[str] = []

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

    for i, assertion in enumerate(test_case.text_assertions, 1):
        if isinstance(assertion, str):
            if assertion.lower() not in assistant_text.lower():
                failures.append(f"Response missing expected text substring: '{assertion}'")
        elif callable(assertion):
            label = getattr(assertion, "__name__", f"assertion_{i}")
            try:
                if not assertion(assistant_text):
                    failures.append(f"Text assertion '{label}' returned False.")
            except Exception as e:
                failures.append(f"Text assertion '{label}' error: {e}")

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
        "assistant_text": assistant_text,
        "executed_tools": executed_tool_names,
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
