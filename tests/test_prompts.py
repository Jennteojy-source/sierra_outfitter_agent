"""Unit tests for system prompt builder (server/prompts.py)."""

from __future__ import annotations

from server.prompts import build_nudge_prompt, build_system_prompt


def test_build_system_prompt_contains_brand_and_skills():
    prompt = build_system_prompt()
    assert "Sierra Outfitters" in prompt
    assert "search_catalog" in prompt
    assert "lookup_order" in prompt
    assert "early_riser_promo" in prompt
    assert "request_human_handoff" in prompt
    assert "America/Los_Angeles" in prompt
    assert "SOBP001" in prompt
    assert "Onward into the unknown!" in prompt


def test_prompt_has_no_duplicate_skill_headers():
    prompt = build_system_prompt()
    assert prompt.count("# search_catalog") == 1
    assert prompt.count("# lookup_order") == 1
    assert prompt.count("Never invent orders") == 1
    assert "HubSpot" not in prompt


def test_order_lookup_allows_either_identifier():
    prompt = build_system_prompt()
    assert "either" in prompt.lower()
    assert "Do NOT ask for email first" in prompt
    assert "Do NOT ask for an order number first" in prompt


def test_handoff_skill_in_prompt():
    prompt = build_system_prompt()
    assert "request_human_handoff" in prompt
    assert "Last resort" in prompt


def test_nudge_prompt_is_check_in_not_full_manual():
    nudge = build_nudge_prompt()
    assert "idle check-in" in nudge.lower()
    assert "Do not call tools" in nudge
    assert "search_catalog" not in nudge
    assert len(nudge) < len(build_system_prompt())
