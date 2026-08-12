"""
Pytest integration for Sierra Outfitter Agent Evals.

Allows running `pytest evals/` to execute all agent evaluation test cases.
"""

from __future__ import annotations

import pytest

from evals.dataset import EVAL_DATASET, EvalTestCase
from evals.eval_runner import run_single_test


@pytest.mark.parametrize("test_case", EVAL_DATASET, ids=lambda tc: tc.id)
def test_agent_eval_case(test_case: EvalTestCase):
    result = run_single_test(test_case)
    if not result["passed"]:
        failure_msg = "\n".join(result["failures"])
        pytest.fail(f"Eval Test Failed [{test_case.id}]:\n{failure_msg}\nResponse:\n{result['assistant_text']}")
