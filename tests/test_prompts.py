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
    assert "Always call before naming products" in prompt
    assert "Assortment overview" not in prompt


def test_prompt_does_not_leak_catalog_facts():
    prompt = build_system_prompt()
    assert "SOBP001" not in prompt
    assert "SOTN002" not in prompt
    assert "Bhavish's Backcountry Blaze Backpack" not in prompt
    assert "hiking / outdoor gear" not in prompt
    assert "winter sports" not in prompt
    assert "Useful tags:" not in prompt
    assert "tents, hiking boots, or jackets" not in prompt
    assert "#W001" not in prompt


def test_prompt_has_no_duplicate_skill_headers():
    prompt = build_system_prompt()
    assert prompt.count("# search_catalog") == 1
    assert prompt.count("# lookup_order") == 1
    assert prompt.count("Never invent orders") == 1
    assert "HubSpot" not in prompt


def test_order_lookup_lets_the_tool_gate_identifiers():
    prompt = build_system_prompt()
    assert "Always — the tool decides if identifiers are enough" in prompt
    assert "Always call for order status" in prompt
    assert "Do not guess a missing field" in prompt
    assert "Call immediately when BOTH" not in prompt
    assert "partial key" not in prompt


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
    assert "the tool decides eligibility" in prompt.lower() or "Do not decide eligibility yourself" in prompt


def test_prompt_does_not_leak_early_risers_eligibility():
    prompt = build_system_prompt()
    assert "8:00–10:00" not in prompt
    assert "8:00-10:00" not in prompt
    assert "must ask for Early Risers by name" not in prompt.lower()


def test_nudge_prompt_is_check_in_not_full_manual():
    nudge = build_nudge_prompt()
    assert "idle check-in" in nudge.lower()
    assert "Do not call tools" in nudge
    assert "search_catalog" not in nudge
    assert len(nudge) < len(build_system_prompt())


def test_prompt_tells_agent_to_look_at_photos():
    idle = build_system_prompt()
    assert "You CAN see customer photos" in idle
    assert "cannot see images" in idle.lower() or "Do not say you cannot see" in idle
    attached = build_system_prompt(photo_attached=True)
    assert "photo is attached" in attached.lower()
    assert "Do not ask them to describe the photo" in attached
