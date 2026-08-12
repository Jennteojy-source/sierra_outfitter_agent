"""Structural checks for the eval dataset — no live LLM calls."""

from __future__ import annotations

from evals.dataset import EVAL_DATASET

VALID_CATEGORIES = {"catalog", "order", "promo", "handoff"}
VALID_TOOLS = {
    "search_catalog",
    "lookup_order",
    "early_riser_promo",
    "request_human_handoff",
}


def test_eval_ids_are_unique():
    ids = [case.id for case in EVAL_DATASET]
    assert len(ids) == len(set(ids))


def test_eval_cases_are_well_formed():
    assert len(EVAL_DATASET) >= 12
    for case in EVAL_DATASET:
        assert case.category in VALID_CATEGORIES, case.id
        assert case.user_prompt.strip(), case.id
        for tool in case.expected_tools + case.forbidden_tools:
            assert tool in VALID_TOOLS, f"{case.id}: unknown tool {tool}"
        overlap = set(case.expected_tools) & set(case.forbidden_tools)
        assert not overlap, f"{case.id} expects and forbids {overlap}"
        for follow in case.follow_ups:
            assert follow.strip(), f"{case.id}: empty follow-up"
        for tool in case.forbidden_until_last:
            assert tool in VALID_TOOLS, f"{case.id}: unknown tool {tool}"
        if case.follow_ups:
            assert case.forbidden_until_last, f"{case.id}: multi-turn case should set forbidden_until_last"


def test_eval_covers_multi_turn_order_lookup():
    multi = [c for c in EVAL_DATASET if c.follow_ups]
    assert len(multi) >= 3
    assert all(c.category == "order" for c in multi)
    assert any(c.id == "ord_07_number_then_email" for c in multi)
    assert any(c.id == "ord_08_email_then_number" for c in multi)
    assert any("lookup_order" in c.forbidden_until_last for c in multi)


def test_eval_covers_core_agent_skills():
    by_cat = {cat: [] for cat in VALID_CATEGORIES}
    for case in EVAL_DATASET:
        by_cat[case.category].append(case.id)
    for cat, ids in by_cat.items():
        assert ids, f"missing evals for {cat}"
    assert any("lookup_order" in c.expected_tools for c in EVAL_DATASET)
    assert any("search_catalog" in c.expected_tools for c in EVAL_DATASET)
    assert any("early_riser_promo" in c.expected_tools for c in EVAL_DATASET)
    assert any("request_human_handoff" in c.expected_tools for c in EVAL_DATASET)
    assert any(c.expect_handed_off is True for c in EVAL_DATASET)
    assert any(c.expect_handed_off is False for c in EVAL_DATASET)
