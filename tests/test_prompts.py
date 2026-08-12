"""
Unit Tests for System Prompt Builder (server/prompts.py).
"""

from __future__ import annotations

from server.prompts import build_system_prompt


def test_build_system_prompt_contains_brand_and_skills():
    prompt = build_system_prompt()
    assert "Sierra Outfitters" in prompt
    assert "Skill 1 — Catalog Search" in prompt
    assert "search_catalog" in prompt
    assert "Skill 2 — Customer Orders" in prompt
    assert "lookup_order" in prompt
    assert "Skill 3 — Early Risers Discount" in prompt
    assert "early_riser_promo" in prompt
    assert "America/Los_Angeles" in prompt


def test_order_lookup_allows_either_identifier():
    prompt = build_system_prompt()
    assert "either" in prompt.lower()
    assert "do NOT ask for email first" in prompt
    assert "do NOT ask for an order number first" in prompt
