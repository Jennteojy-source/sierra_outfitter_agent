"""
Evaluation Test Dataset for Sierra Outfitter AI Agent.

Categories covered:
1. Catalog Search (search_catalog): Gear Q&A, recommendations, tags, stock
2. Customer Orders (lookup_order): Status, tracking, order number, email
3. Early Risers Discount (early_riser_promo): Explicit request vs implicit, time-window behavior
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable


@dataclass
class EvalTestCase:
    id: str
    category: str  # "catalog", "order", "promo"
    description: str
    user_prompt: str
    expected_tools: list[str]  # Tools that MUST be called
    forbidden_tools: list[str] = field(default_factory=list)  # Tools that MUST NOT be called
    time_mock_pt: str | None = None  # ISO format string for America/Los_Angeles mocking e.g. "2026-08-12T08:30:00-07:00"
    arg_checkers: dict[str, Callable[[dict[str, Any]], bool]] = field(default_factory=dict)
    text_assertions: list[str | Callable[[str], bool]] = field(default_factory=list)


EVAL_DATASET: list[EvalTestCase] = [
    # -------------------------------------------------------------------------
    # 1. CATALOG SEARCH (search_catalog)
    # -------------------------------------------------------------------------
    EvalTestCase(
        id="cat_01_gear_qa_recommendations",
        category="catalog",
        description="Gear Q&A and recommendations for cold weather hiking",
        user_prompt="What gear do you recommend for cold weather hiking and winter adventures?",
        expected_tools=["search_catalog"],
        text_assertions=[
            lambda text: any(
                keyword in text.lower()
                for keyword in ["ski", "backpack", "hairbrush", "gear", "warm", "winter", "crain"]
            )
        ],
    ),
    EvalTestCase(
        id="cat_02_tag_filtering",
        category="catalog",
        description="Catalog search filtered by tag (e.g. High-Tech)",
        user_prompt="Show me products with the High-Tech tag.",
        expected_tools=["search_catalog"],
        arg_checkers={
            "search_catalog": lambda args: "high-tech" in str(args.get("tags", [])).lower()
            or "high-tech" in str(args.get("query", "")).lower()
        },
        text_assertions=[
            lambda text: any(
                prod in text.lower()
                for prod in ["hairbrush", "jetpack", "invisibility", "cloak", "high-tech"]
            )
        ],
    ),
    EvalTestCase(
        id="cat_03_stock_inquiry",
        category="catalog",
        description="Check stock status for a specific product (Summit Pro X Skis)",
        user_prompt="Is Crain's Summit Pro X Skis currently in stock?",
        expected_tools=["search_catalog"],
        arg_checkers={
            "search_catalog": lambda args: "ski" in str(args.get("query", "")).lower()
            or "sotn002" in str(args.get("query", "")).lower()
        },
        text_assertions=[
            lambda text: "stock" in text.lower() or "available" in text.lower() or "75" in text
        ],
    ),
    EvalTestCase(
        id="cat_04_in_stock_only_filter",
        category="catalog",
        description="Explicit request for in-stock items only",
        user_prompt="Recommend hiking backpacks that are currently in stock.",
        expected_tools=["search_catalog"],
        arg_checkers={
            "search_catalog": lambda args: args.get("in_stock_only") is True
            or "backpack" in str(args.get("query", "")).lower()
        },
        text_assertions=[
            lambda text: "backpack" in text.lower() or "blaze" in text.lower()
        ],
    ),
    EvalTestCase(
        id="cat_05_non_existent_product",
        category="catalog",
        description="Query for an item not in catalog (solar powered hoverboard)",
        user_prompt="Do you sell solar powered hoverboards?",
        expected_tools=["search_catalog"],
        text_assertions=[
            lambda text: any(
                phrase in text.lower()
                for phrase in ["don't sell", "don't have", "no", "not", "foggy", "suggest", "popular"]
            )
        ],
    ),

    # -------------------------------------------------------------------------
    # 2. CUSTOMER ORDERS (lookup_order)
    # -------------------------------------------------------------------------
    EvalTestCase(
        id="ord_01_lookup_by_order_number",
        category="order",
        description="Look up order status by order number #W001",
        user_prompt="What's the status of order #W001?",
        expected_tools=["lookup_order"],
        arg_checkers={
            "lookup_order": lambda args: "w001" in str(args.get("order_number", "")).lower()
        },
        text_assertions=[
            "delivered",
            lambda text: "backpack" in text.lower() or "blaze" in text.lower() or "sobp001" in text.lower(),
        ],
    ),
    EvalTestCase(
        id="ord_02_lookup_by_email",
        category="order",
        description="Look up order status by customer email jane.smith@example.com",
        user_prompt="Can you check my order under jane.smith@example.com?",
        expected_tools=["lookup_order"],
        arg_checkers={
            "lookup_order": lambda args: "jane.smith@example.com" in str(args.get("email", "")).lower()
        },
        text_assertions=[
            lambda text: "in-transit" in text.lower() or "in transit" in text.lower(),
            lambda text: any(kw in text.lower() for kw in ["jane", "pathfinder", "w002", "order"]),
        ],
    ),
    EvalTestCase(
        id="ord_03_tracking_link_verification",
        category="order",
        description="Verify tracking number and link for order #W002",
        user_prompt="Where is my package for order #W002? Send me the tracking details.",
        expected_tools=["lookup_order"],
        arg_checkers={
            "lookup_order": lambda args: "w002" in str(args.get("order_number", "")).lower()
        },
        text_assertions=[
            "TRK987654321",
            lambda text: "usps.com" in text.lower() or "track" in text.lower() or "in-transit" in text.lower(),
        ],
    ),
    EvalTestCase(
        id="ord_04_non_existent_order",
        category="order",
        description="Handle non-existent order #W999 gracefully",
        user_prompt="Check order status for order number #W999",
        expected_tools=["lookup_order"],
        text_assertions=[
            lambda text: any(
                phrase in text.lower()
                for phrase in ["no order", "couldn't find", "not found", "cannot find", "double-check", "retry"]
            )
        ],
    ),

    # -------------------------------------------------------------------------
    # 3. EARLY RISERS DISCOUNT (early_riser_promo)
    # -------------------------------------------------------------------------
    EvalTestCase(
        id="prm_01_explicit_request_inside_window",
        category="promo",
        description="Explicit Early Risers promo request inside 8:00–10:00 AM window",
        user_prompt="I'd like to get the Early Risers Promotion code please!",
        time_mock_pt="2026-08-12T08:30:00-07:00",
        expected_tools=["early_riser_promo"],
        text_assertions=[
            lambda text: "EARLY-" in text,
            lambda text: "10%" in text or "discount" in text.lower() or "code" in text.lower(),
        ],
    ),
    EvalTestCase(
        id="prm_02_explicit_request_outside_window",
        category="promo",
        description="Explicit Early Risers promo request outside window (2:15 PM PT)",
        user_prompt="Can I get the Early Risers discount code?",
        time_mock_pt="2026-08-12T14:15:00-07:00",
        expected_tools=[],  # Tool call optional as agent has live system clock in prompt
        forbidden_tools=[],
        text_assertions=[
            lambda text: "8:00" in text or "10:00" in text or "pacific" in text.lower() or "morning" in text.lower(),
            lambda text: "EARLY-" not in text,  # Must NOT issue a discount code outside window
        ],
    ),
    EvalTestCase(
        id="prm_03_guardrail_unrelated_discount_request",
        category="promo",
        description="General discount question must NOT trigger Early Risers tool without explicit request",
        user_prompt="Do you have any general store coupons or discount codes available?",
        expected_tools=[],
        forbidden_tools=["early_riser_promo"],
        text_assertions=[
            lambda text: "early risers" in text.lower() or "8:00" in text or "promo" in text.lower() or "discount" in text.lower()
        ],
    ),
]
