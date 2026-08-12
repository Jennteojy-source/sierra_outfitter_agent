"""
Unit Tests for Sierra Outfitter Local Tools (server/tools.py).
All test assertions strictly validate against real data in customer_order.json and product_catalog.json.
"""

from __future__ import annotations

from datetime import datetime
from unittest.mock import patch

from server.tools import (
    early_riser_promo,
    lookup_order,
    request_human_handoff,
    run_tool,
    search_catalog,
)


class FixedDateTime(datetime):
    _fixed_now: datetime | None = None

    @classmethod
    def now(cls, tz=None):
        if cls._fixed_now is not None:
            if tz is not None:
                return cls._fixed_now.astimezone(tz)
            return cls._fixed_now
        return datetime.now(tz)


def make_dt_mock(iso_str: str):
    dt = datetime.fromisoformat(iso_str)

    class CustomFixedDateTime(FixedDateTime):
        _fixed_now = dt

    return CustomFixedDateTime


# =============================================================================
# 1. CUSTOMER ORDERS (lookup_order) — Validated against customer_order.json
# =============================================================================

def test_lookup_order_w001_delivered():
    """Real Order #W001: John Doe, status 'delivered', tracking 'TRK123456789'."""
    res = lookup_order(order_number="#W001", email="john.doe@example.com")
    assert res["found"] is True
    assert len(res["orders"]) == 1
    order = res["orders"][0]
    assert order["order_number"] == "#W001"
    assert order["customer_name"] == "John Doe"
    assert order["email"] == "john.doe@example.com"
    assert order["status"] == "delivered"
    assert order["tracking_number"] == "TRK123456789"
    assert order["tracking_url"] == "https://tools.usps.com/go/TrackConfirmAction?tLabels=TRK123456789"
    skus = [p["sku"] for p in order["products"]]
    assert "SOBP001" in skus
    assert "SOWB004" in skus


def test_lookup_order_requires_both_identifiers():
    by_number = lookup_order(order_number="#W001")
    assert by_number["found"] is False
    assert by_number["need"] == ["email"]

    by_email = lookup_order(email="jane.smith@example.com")
    assert by_email["found"] is False
    assert by_email["need"] == ["order_number"]

    neither = lookup_order()
    assert neither["found"] is False
    assert set(neither["need"]) == {"order_number", "email"}


def test_lookup_order_by_email_and_number_jane_smith():
    """Real Order #W002: Jane Smith, jane.smith@example.com, status 'in-transit'."""
    res = lookup_order(order_number="#W002", email="jane.smith@example.com")
    assert res["found"] is True
    order = res["orders"][0]
    assert order["order_number"] == "#W002"
    assert order["customer_name"] == "Jane Smith"
    assert order["status"] == "in-transit"
    assert order["tracking_number"] == "TRK987654321"


def test_lookup_order_w004_error_status():
    """Real Order #W004: Bob Brown, status 'error', null tracking."""
    res = lookup_order(order_number="#W004", email="bob.brown@example.com")
    assert res["found"] is True
    order = res["orders"][0]
    assert order["status"] == "error"
    assert order["tracking_number"] is None
    assert order["tracking_url"] is None


def test_lookup_order_case_insensitive_and_normalized():
    """Test order lookup with lowercase and stripped symbols 'w005'."""
    res = lookup_order(order_number="w005", email="charlie.davis@example.com")
    assert res["found"] is True
    order = res["orders"][0]
    assert order["order_number"] == "#W005"
    assert order["customer_name"] == "Charlie Davis"
    assert order["status"] == "delivered"


def test_lookup_order_not_found():
    res = lookup_order(order_number="#W999999", email="nobody@example.com")
    assert res["found"] is False
    assert "No order found" in res["message"]


def test_lookup_order_both_identifiers_must_match():
    res = lookup_order(order_number="#W001", email="jane.smith@example.com")
    assert res["found"] is False


def test_lookup_order_both_identifiers_matching():
    res = lookup_order(order_number="#W001", email="john.doe@example.com")
    assert res["found"] is True
    assert res["orders"][0]["order_number"] == "#W001"


# =============================================================================
# 2. CATALOG SEARCH (search_catalog) — Validated against product_catalog.json
# =============================================================================

def test_search_catalog_blaze_backpack():
    """SOBP001: Bhavish's Backcountry Blaze Backpack (Inventory: 120)."""
    res = search_catalog(query="Backcountry Blaze Backpack")
    assert res["count"] > 0
    top = res["products"][0]
    assert top["sku"] == "SOBP001"
    assert top["name"] == "Bhavish's Backcountry Blaze Backpack"
    assert top["inventory"] == 120
    assert top["in_stock"] is True


def test_search_catalog_summit_skis():
    """SOTN002: Crain's Summit Pro X Skis (Inventory: 75)."""
    res = search_catalog(query="Summit Pro X Skis")
    assert res["count"] > 0
    top = res["products"][0]
    assert top["sku"] == "SOTN002"
    assert top["inventory"] == 75
    assert "Snow" in top["tags"]


def test_search_catalog_tag_filter_high_tech():
    """Products with tag 'High-Tech': Nat's Hairbrush (SOBT003), Ishmeet's Jetpack (SOSB006), Nishita's Cloak (SOSV007)."""
    res = search_catalog(query="gear", tags=["High-Tech"])
    assert res["count"] > 0
    found_skus = {p["sku"] for p in res["products"]}
    assert found_skus.intersection({"SOBT003", "SOSB006", "SOSV007"})


def test_search_catalog_in_stock_only():
    res = search_catalog(query="adventure", in_stock_only=True)
    for prod in res["products"]:
        assert prod["in_stock"] is True
        assert prod["inventory"] > 0


def test_search_catalog_no_matches_is_honest():
    """No soft popular fallback — empty result with available tags for the agent."""
    res = search_catalog(query="jackets")
    assert res["found"] is False
    assert res["fallback"] is False
    assert res["count"] == 0
    assert res["products"] == []
    assert res["message"]
    assert "available_tags" in res


def test_search_catalog_hiking_backpacks():
    res = search_catalog(query="hiking backpacks")
    assert res["found"] is True
    assert res["products"][0]["sku"] == "SOBP001"


def test_search_catalog_hiking_boots_is_honest_miss():
    res = search_catalog(query="hiking boots")
    assert res["found"] is False
    assert res["products"] == []


def test_search_catalog_browse():
    res = search_catalog(query="browse")
    assert res["browse"] is True
    assert res["found"] is True
    assert res["count"] > 0


def test_search_catalog_exclude_skus():
    res = search_catalog(query="hiking backpack", exclude_skus=["SOBP001"])
    assert res["found"] is False or all(p["sku"] != "SOBP001" for p in res["products"])


# =============================================================================
# 3. EARLY RISERS DISCOUNT (early_riser_promo)
# =============================================================================

def test_early_riser_promo_inside_window():
    # 8:30 AM Pacific Time
    mock_dt = make_dt_mock("2026-08-12T08:30:00-07:00")
    with patch("server.tools.datetime", mock_dt):
        res = early_riser_promo()
        assert res["valid"] is True
        assert res["code"].startswith("EARLY-")
        assert res["discount"] == "10%"


def test_early_riser_promo_outside_window():
    # 2:30 PM Pacific Time
    mock_dt = make_dt_mock("2026-08-12T14:30:00-07:00")
    with patch("server.tools.datetime", mock_dt):
        res = early_riser_promo()
        assert res["valid"] is False
        assert res["code"] is None
        assert "8:00 and 10:00 AM" in res["reason"]


def test_early_riser_promo_at_window_edges():
    with patch("server.tools.datetime", make_dt_mock("2026-08-12T08:00:00-07:00")):
        assert early_riser_promo()["valid"] is True
    with patch("server.tools.datetime", make_dt_mock("2026-08-12T09:59:00-07:00")):
        assert early_riser_promo()["valid"] is True
    with patch("server.tools.datetime", make_dt_mock("2026-08-12T10:00:00-07:00")):
        assert early_riser_promo()["valid"] is False


# =============================================================================
# 4. RUN_TOOL DISPATCHER
# =============================================================================

def test_run_tool_lookup_order():
    res, products = run_tool(
        "lookup_order",
        {"order_number": "#W001", "email": "john.doe@example.com"},
    )
    assert res["found"] is True
    assert products is None


def test_run_tool_search_catalog():
    res, products = run_tool("search_catalog", {"query": "jetpack"})
    assert res["count"] > 0
    assert products is not None
    assert any(p["sku"] == "SOSB006" for p in products)


def test_run_tool_unknown():
    res, products = run_tool("unknown_tool", {})
    assert "error" in res
    assert products is None


def test_request_human_handoff():
    res = request_human_handoff(reason="explicit_request", summary="Wants a refund")
    assert res["handed_off"] is True
    assert res["queued"] is True
    assert res["reason"] == "explicit_request"


def test_request_human_handoff_unknown_reason_defaults():
    res = request_human_handoff(reason="whatever")
    assert res["handed_off"] is True
    assert res["reason"] == "explicit_request"


def test_run_tool_handoff():
    res, products = run_tool(
        "request_human_handoff",
        {"reason": "out_of_scope", "summary": "Billing dispute"},
    )
    assert res["handed_off"] is True
    assert res["reason"] == "out_of_scope"
    assert products is None
