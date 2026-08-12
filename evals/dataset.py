"""
Evaluation dataset for the Sierra Outfitters agent.

Cases check tool choice, arguments, and reply content against the live
catalog, orders, promo window, and handoff rules. Order lookup also has
multi-turn cases (`follow_ups`) that collect email and order number
across messages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class EvalTestCase:
    id: str
    category: str  # catalog | order | promo | handoff
    description: str
    user_prompt: str
    expected_tools: list[str]
    forbidden_tools: list[str] = field(default_factory=list)
    follow_ups: list[str] = field(default_factory=list)
    forbidden_until_last: list[str] = field(default_factory=list)
    time_mock_pt: str | None = None
    arg_checkers: dict[str, Callable[[dict[str, Any]], bool]] = field(default_factory=dict)
    text_assertions: list[str | Callable[[str], bool]] = field(default_factory=list)
    first_turn_assertions: list[str | Callable[[str], bool]] = field(default_factory=list)
    expect_handed_off: bool | None = None


def _mentions_any(text: str, *needles: str) -> bool:
    lower = text.lower()
    return any(n.lower() in lower for n in needles)


def _avoids_unrelated_catalog_filler(text: str) -> bool:
    """Hoverboards/jackets should not be answered with random in-stock SKUs."""
    lower = text.lower()
    bait = ["energy drink", "hairbrush", "jetpack", "lampshade", "protein bar"]
    return not any(b in lower for b in bait)


EVAL_DATASET: list[EvalTestCase] = [
    # -------------------------------------------------------------------------
    # Catalog
    # -------------------------------------------------------------------------
    EvalTestCase(
        id="cat_01_winter_hiking_recs",
        category="catalog",
        description="Recommend gear for cold-weather hiking / winter",
        user_prompt="What gear do you recommend for cold weather hiking and winter adventures?",
        expected_tools=["search_catalog"],
        forbidden_tools=["request_human_handoff", "early_riser_promo", "lookup_order"],
        text_assertions=[
            lambda text: _mentions_any(text, "ski", "backpack", "blaze", "winter", "hiking", "crain"),
        ],
    ),
    EvalTestCase(
        id="cat_02_tag_filtering",
        category="catalog",
        description="Browse High-Tech tagged products",
        user_prompt="Show me products with the High-Tech tag.",
        expected_tools=["search_catalog"],
        arg_checkers={
            "search_catalog": lambda args: "high-tech" in str(args.get("tags", [])).lower()
            or "high-tech" in str(args.get("query", "")).lower()
            or "high tech" in str(args.get("query", "")).lower()
        },
        text_assertions=[
            lambda text: _mentions_any(text, "hairbrush", "jetpack", "invisibility", "cloak", "high-tech"),
        ],
    ),
    EvalTestCase(
        id="cat_03_stock_inquiry",
        category="catalog",
        description="Stock check for Summit Pro X Skis",
        user_prompt="Is Crain's Summit Pro X Skis currently in stock?",
        expected_tools=["search_catalog"],
        arg_checkers={
            "search_catalog": lambda args: "ski" in str(args.get("query", "")).lower()
            or "sotn002" in str(args.get("query", "")).lower()
            or "crain" in str(args.get("query", "")).lower()
        },
        text_assertions=[
            lambda text: _mentions_any(text, "stock", "available", "75", "in stock"),
        ],
    ),
    EvalTestCase(
        id="cat_04_hiking_backpacks",
        category="catalog",
        description="Hiking backpacks currently in stock — only one exists",
        user_prompt="Recommend hiking backpacks that are currently in stock.",
        expected_tools=["search_catalog"],
        arg_checkers={
            "search_catalog": lambda args: "backpack" in str(args.get("query", "")).lower()
            or "hiking" in str(args.get("query", "")).lower()
        },
        text_assertions=[
            lambda text: _mentions_any(text, "backpack", "blaze", "sobp001"),
        ],
    ),
    EvalTestCase(
        id="cat_05_non_existent_product",
        category="catalog",
        description="Honest miss for an item not in the catalog",
        user_prompt="Do you sell solar powered hoverboards?",
        expected_tools=["search_catalog"],
        forbidden_tools=["request_human_handoff"],
        text_assertions=[
            lambda text: _mentions_any(
                text,
                "don't sell",
                "do not sell",
                "don't carry",
                "do not carry",
                "don't have",
                "not in",
                "no hoverboard",
                "couldn't find",
                "don't currently",
            ),
            _avoids_unrelated_catalog_filler,
        ],
    ),
    EvalTestCase(
        id="cat_07_hiking_boots_honest_miss",
        category="catalog",
        description="Hiking boots are not in the catalog — do not pitch shoes or backpacks as boots",
        user_prompt="Do you have hiking boots?",
        expected_tools=["search_catalog"],
        forbidden_tools=["request_human_handoff"],
        text_assertions=[
            lambda text: _mentions_any(
                text,
                "don't sell",
                "do not sell",
                "don't carry",
                "don't have",
                "no hiking boot",
                "not in",
                "couldn't find",
                "don't currently",
            ),
            lambda text: "boot" in text.lower() or "don't" in text.lower() or "do not" in text.lower(),
            _avoids_unrelated_catalog_filler,
        ],
    ),
    EvalTestCase(
        id="cat_06_jackets_honest_miss",
        category="catalog",
        description="Jackets are not in the catalog — do not invent alternatives as matches",
        user_prompt="Do you have any jackets in stock?",
        expected_tools=["search_catalog"],
        forbidden_tools=["request_human_handoff"],
        text_assertions=[
            lambda text: _mentions_any(
                text,
                "don't sell",
                "do not sell",
                "don't carry",
                "don't have",
                "no jacket",
                "not in",
                "couldn't find",
                "don't currently",
            ),
            _avoids_unrelated_catalog_filler,
        ],
    ),

    # -------------------------------------------------------------------------
    # Orders — both order number AND email are required
    # -------------------------------------------------------------------------
    EvalTestCase(
        id="ord_01_order_number_asks_email",
        category="order",
        description="Order number alone is not enough — ask for email",
        user_prompt="What's the status of order #W001?",
        expected_tools=[],
        forbidden_tools=["request_human_handoff", "early_riser_promo"],
        text_assertions=[
            lambda text: "email" in text.lower(),
            lambda text: "delivered" not in text.lower(),
        ],
    ),
    EvalTestCase(
        id="ord_02_email_asks_order_number",
        category="order",
        description="Email alone is not enough — ask for order number",
        user_prompt="Can you check my order under jane.smith@example.com?",
        expected_tools=[],
        forbidden_tools=["early_riser_promo"],
        text_assertions=[
            lambda text: _mentions_any(text, "order number", "order #"),
            lambda text: "in-transit" not in text.lower() and "in transit" not in text.lower(),
        ],
    ),
    EvalTestCase(
        id="ord_03_tracking_with_both",
        category="order",
        description="Tracking URL when both identifiers are given",
        user_prompt=(
            "Where is my package for order #W002? "
            "My email is jane.smith@example.com. Send me the tracking details."
        ),
        expected_tools=["lookup_order"],
        arg_checkers={
            "lookup_order": lambda args: (
                "w002" in str(args.get("order_number", "")).lower()
                and "jane.smith@example.com" in str(args.get("email", "")).lower()
            )
        },
        text_assertions=[
            "TRK987654321",
            lambda text: "usps.com" in text.lower() or "track" in text.lower(),
        ],
    ),
    EvalTestCase(
        id="ord_04_not_found",
        category="order",
        description="Unknown order + email — honest miss, no invented tracking",
        user_prompt="Look up order number #W999 with email nobody@example.com",
        expected_tools=["lookup_order"],
        forbidden_tools=["request_human_handoff"],
        text_assertions=[
            lambda text: _mentions_any(
                text,
                "no order",
                "couldn't find",
                "could not find",
                "not found",
                "cannot find",
                "can't find",
                "don't see",
                "unable to find",
                "double-check",
                "doesn't match",
                "do not match",
                "no match",
            ),
            lambda text: "TRK" not in text,
        ],
    ),
    EvalTestCase(
        id="ord_05_error_status_no_tracking",
        category="order",
        description="#W004 is error with no tracking — do not invent a number",
        user_prompt="What's going on with order #W004 for bob.brown@example.com?",
        expected_tools=["lookup_order"],
        forbidden_tools=["request_human_handoff"],
        arg_checkers={
            "lookup_order": lambda args: (
                "w004" in str(args.get("order_number", "")).lower()
                and "bob.brown@example.com" in str(args.get("email", "")).lower()
            )
        },
        text_assertions=[
            lambda text: _mentions_any(text, "error", "issue", "problem", "couldn't", "unable"),
            lambda text: "TRK" not in text,
        ],
    ),
    EvalTestCase(
        id="ord_06_ask_for_identifier",
        category="order",
        description="No order number or email yet — ask for both, do not guess",
        user_prompt="Track my order please",
        expected_tools=[],
        forbidden_tools=["search_catalog", "early_riser_promo"],
        text_assertions=[
            lambda text: _mentions_any(text, "order number", "order #"),
            lambda text: "email" in text.lower(),
        ],
    ),
    EvalTestCase(
        id="ord_07_number_then_email",
        category="order",
        description="Multi-turn: order number first, email second, then lookup",
        user_prompt="What's the status of order #W001?",
        follow_ups=["john.doe@example.com"],
        expected_tools=["lookup_order"],
        forbidden_tools=["request_human_handoff", "early_riser_promo"],
        forbidden_until_last=["lookup_order"],
        arg_checkers={
            "lookup_order": lambda args: (
                "w001" in str(args.get("order_number", "")).lower()
                and "john.doe@example.com" in str(args.get("email", "")).lower()
            )
        },
        first_turn_assertions=[
            lambda text: "email" in text.lower(),
            lambda text: "delivered" not in text.lower(),
        ],
        text_assertions=[
            "delivered",
            "TRK123456789",
            lambda text: "usps.com" in text.lower() or "track" in text.lower(),
        ],
    ),
    EvalTestCase(
        id="ord_08_email_then_number",
        category="order",
        description="Multi-turn: email first, order number second, then lookup",
        user_prompt="Can you check my order under jane.smith@example.com?",
        follow_ups=["It's #W002"],
        expected_tools=["lookup_order"],
        forbidden_tools=["early_riser_promo"],
        forbidden_until_last=["lookup_order"],
        arg_checkers={
            "lookup_order": lambda args: (
                "w002" in str(args.get("order_number", "")).lower()
                and "jane.smith@example.com" in str(args.get("email", "")).lower()
            )
        },
        first_turn_assertions=[
            lambda text: _mentions_any(text, "order number", "order #"),
            lambda text: "in-transit" not in text.lower() and "in transit" not in text.lower(),
        ],
        text_assertions=[
            lambda text: _mentions_any(text, "in-transit", "in transit", "transit"),
            "TRK987654321",
        ],
    ),
    EvalTestCase(
        id="ord_09_mismatch_after_collecting",
        category="order",
        description="Multi-turn: both identifiers collected, but they do not match",
        user_prompt="Track order #W001 please",
        follow_ups=["jane.smith@example.com"],
        expected_tools=["lookup_order"],
        forbidden_tools=["request_human_handoff"],
        forbidden_until_last=["lookup_order"],
        arg_checkers={
            "lookup_order": lambda args: (
                "w001" in str(args.get("order_number", "")).lower()
                and "jane.smith@example.com" in str(args.get("email", "")).lower()
            )
        },
        first_turn_assertions=[
            lambda text: "email" in text.lower(),
            lambda text: "delivered" not in text.lower(),
        ],
        text_assertions=[
            lambda text: _mentions_any(
                text,
                "no order",
                "couldn't find",
                "could not find",
                "not found",
                "cannot find",
                "can't find",
                "don't see",
                "unable to find",
                "doesn't match",
                "do not match",
                "no match",
                "don't match",
            ),
            lambda text: "TRK" not in text,
        ],
    ),

    # -------------------------------------------------------------------------
    # Early Risers
    # -------------------------------------------------------------------------
    EvalTestCase(
        id="prm_01_inside_window",
        category="promo",
        description="Explicit Early Risers request inside 8–10 AM PT",
        user_prompt="I'd like to get the Early Risers Promotion code please!",
        time_mock_pt="2026-08-12T08:30:00-07:00",
        expected_tools=["early_riser_promo"],
        forbidden_tools=["request_human_handoff"],
        text_assertions=[
            lambda text: "EARLY-" in text,
            lambda text: _mentions_any(text, "10%", "discount", "code"),
        ],
    ),
    EvalTestCase(
        id="prm_02_outside_window",
        category="promo",
        description="Explicit request outside the window — tool enforces, no invented code",
        user_prompt="Can I get the Early Risers discount code?",
        time_mock_pt="2026-08-12T14:15:00-07:00",
        expected_tools=["early_riser_promo"],  # Tool enforces the window
        forbidden_tools=["request_human_handoff"],
        text_assertions=[
            lambda text: _mentions_any(text, "8:00", "8 am", "10:00", "10 am", "pacific", "morning"),
            lambda text: "EARLY-" not in text,
        ],
    ),
    EvalTestCase(
        id="prm_03_no_implicit_promo",
        category="promo",
        description="Generic coupon ask must not mint an Early Risers code",
        user_prompt="Do you have any general store coupons or discount codes available?",
        expected_tools=["early_riser_promo"],
        forbidden_tools=["request_human_handoff"],
        text_assertions=[
            lambda text: "EARLY-" not in text,
            lambda text: _mentions_any(text, "early riser", "8:00", "10:00", "promo", "discount"),
        ],
    ),

    # -------------------------------------------------------------------------
    # Human handoff — try skills first; escalate only when truly stuck
    # -------------------------------------------------------------------------
    EvalTestCase(
        id="hnd_01_explicit_refund",
        category="handoff",
        description="Refund + human request is out of scope — queue a human, do not mute",
        user_prompt="I want to talk to a human. I need a refund for a damaged shipment.",
        expected_tools=["request_human_handoff"],
        forbidden_tools=["early_riser_promo"],
        expect_handed_off=True,
        text_assertions=[
            lambda text: _mentions_any(text, "human", "teammate", "team", "person", "specialist", "soon"),
        ],
    ),
    EvalTestCase(
        id="hnd_02_catalog_miss_no_handoff",
        category="handoff",
        description="A catalog miss is still the agent's job — do not escalate",
        user_prompt="Do you sell tents?",
        expected_tools=["search_catalog"],
        forbidden_tools=["request_human_handoff"],
        expect_handed_off=False,
    ),
    EvalTestCase(
        id="hnd_03_order_lookup_no_handoff",
        category="handoff",
        description="A normal order question should not escalate",
        user_prompt="What's the status of order #W001 for john.doe@example.com?",
        expected_tools=["lookup_order"],
        forbidden_tools=["request_human_handoff"],
        expect_handed_off=False,
        text_assertions=["delivered"],
    ),
]
