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
    assert "Onward into the unknown!" in prompt
    assert "Assortment overview" in prompt
    assert "orientation only" in prompt
    assert "Always call search_catalog" in prompt or "Always — overview is not enough" in prompt


def test_prompt_has_high_level_assortment_not_sku_dump():
    prompt = build_system_prompt()
    assert "hiking / outdoor gear" in prompt
    assert "winter sports" in prompt
    # Full SKU list should not be in the prompt — tools own product truth.
    assert "SOBP001" not in prompt
    assert "Bhavish's Backcountry Blaze Backpack" not in prompt


def test_prompt_has_no_duplicate_skill_headers():
    prompt = build_system_prompt()
    assert prompt.count("# search_catalog") == 1
    assert prompt.count("# lookup_order") == 1
    assert prompt.count("Never invent orders") == 1
    assert "HubSpot" not in prompt


def test_order_lookup_requires_both_identifiers():
    prompt = build_system_prompt()
    assert "BOTH" in prompt
    assert "order_number AND email" in prompt
    assert "Do NOT ask for email first" not in prompt


def test_handoff_queued_block_only_when_pending():
    idle = build_system_prompt()
    assert "# Handoff queued" not in idle
    queued = build_system_prompt(handoff_queued=True, handoff_reason="out_of_scope")
    assert "# Handoff queued" in queued
    assert "out_of_scope" in queued
    assert "does not mute" in queued.lower() or "not a mute" in queued.lower()


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
