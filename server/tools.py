"""Local tools backed by static JSON datasets."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from server.catalog_index import CatalogIndex

ROOT = Path(__file__).resolve().parent.parent
ORDERS_PATH = ROOT / "customer_order.json"
CATALOG_PATH = ROOT / "product_catalog.json"
PT = ZoneInfo("America/Los_Angeles")
TRACKING_URL = "https://tools.usps.com/go/TrackConfirmAction?tLabels={trackingNumber}"

_orders: list[dict[str, Any]] | None = None
_catalog: list[dict[str, Any]] | None = None
_catalog_index: CatalogIndex | None = None


def _load_orders() -> list[dict[str, Any]]:
    global _orders
    if _orders is None:
        _orders = json.loads(ORDERS_PATH.read_text())
    return _orders


def _load_catalog() -> list[dict[str, Any]]:
    global _catalog
    if _catalog is None:
        _catalog = json.loads(CATALOG_PATH.read_text())
    return _catalog


def _get_catalog_index() -> CatalogIndex:
    global _catalog_index
    if _catalog_index is None:
        _catalog_index = CatalogIndex(_load_catalog())
    return _catalog_index


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def lookup_order(order_number: str | None = None, email: str | None = None) -> dict[str, Any]:
    orders = _load_orders()
    matches: list[dict[str, Any]] = []

    for order in orders:
        ok = True
        if order_number:
            if _normalize(order["OrderNumber"]) != _normalize(order_number):
                ok = False
        if email:
            if order["Email"].lower().strip() != email.lower().strip():
                ok = False
        if ok and (order_number or email):
            matches.append(order)

    if not matches:
        return {
            "found": False,
            "message": "No order found for the provided order number and/or email.",
        }

    results = []
    catalog_by_sku = {p["SKU"]: p for p in _load_catalog()}
    for order in matches:
        tracking = order.get("TrackingNumber")
        product_names = []
        for sku in order.get("ProductsOrdered", []):
            product = catalog_by_sku.get(sku)
            product_names.append(
                {
                    "sku": sku,
                    "name": product["ProductName"] if product else sku,
                }
            )
        results.append(
            {
                "customer_name": order["CustomerName"],
                "email": order["Email"],
                "order_number": order["OrderNumber"],
                "status": order["Status"],
                "products": product_names,
                "tracking_number": tracking,
                "tracking_url": TRACKING_URL.format(trackingNumber=tracking) if tracking else None,
            }
        )

    return {"found": True, "orders": results}


def search_catalog(
    query: str,
    limit: int = 4,
    in_stock_only: bool = False,
    tags: list[str] | None = None,
    exclude_skus: list[str] | None = None,
) -> dict[str, Any]:
    """Local inverted-index search over name, tags, description, SKU, and stock."""
    return _get_catalog_index().search(
        query,
        limit=limit,
        in_stock_only=in_stock_only,
        tags=tags,
        exclude_skus=exclude_skus,
    )


# Back-compat alias
def recommend_products(query: str, limit: int = 4, in_stock_only: bool = False) -> dict[str, Any]:
    return search_catalog(query=query, limit=limit, in_stock_only=in_stock_only)


def early_riser_promo() -> dict[str, Any]:
    now = datetime.now(PT)
    in_window = now.hour in (8, 9)  # 8:00 inclusive through 9:59

    if not in_window:
        return {
            "valid": False,
            "code": None,
            "timezone": "America/Los_Angeles",
            "current_time": now.isoformat(),
            "window": "08:00–10:00 America/Los_Angeles",
            "reason": "Early Risers Promotion is only available between 8:00 and 10:00 AM Pacific Time.",
        }

    code = f"EARLY-{uuid.uuid4().hex[:8].upper()}"
    return {
        "valid": True,
        "code": code,
        "discount": "10%",
        "timezone": "America/Los_Angeles",
        "current_time": now.isoformat(),
        "window": "08:00–10:00 America/Los_Angeles",
        "reason": "Customer is within the Early Risers window; unique code generated.",
    }


def request_human_handoff(reason: str, summary: str | None = None) -> dict[str, Any]:
    allowed = {"explicit_request", "out_of_scope", "unresolved_after_retries"}
    clean_reason = reason if reason in allowed else "explicit_request"
    return {
        "handed_off": True,
        "reason": clean_reason,
        "summary": (summary or "").strip() or None,
        "queue": "human_trail_guides",
        "ai_muted": True,
        "message": (
            "Handoff recorded. Confirm briefly that a human will take over, then stop. "
            "Do not keep answering as the AI."
        ),
    }


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": (
                "Skill: Customer Orders. Look up order status and tracking. "
                "Call with EITHER order_number OR email alone — both are not required. "
                "If the customer already gave an order number, call immediately with that "
                "order_number; do not wait for email. Same for email-only requests. "
                "Use for shipment, delivery, or tracking questions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_number": {
                        "type": "string",
                        "description": (
                            "Order number such as #W001 or W001. Sufficient by itself — "
                            "do not require email when this is provided."
                        ),
                    },
                    "email": {
                        "type": "string",
                        "description": (
                            "Customer email associated with the order. Sufficient by itself — "
                            "do not require order number when this is provided."
                        ),
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_catalog",
            "description": (
                "Skill: Catalog Search. Local inverted-index search over product name, tags, "
                "description, SKU, and stock. Use for recommendations, 'do you sell X?', "
                "tag browsing, and in-stock questions. Prefer this over inventing products. "
                "If found=false, say we don't carry that item — do not invent alternatives "
                "as if they matched the query. For 'what do you sell' / 'I want to buy "
                "something', call with query 'browse' and only mention returned products."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Search query — product name fragments, activity, category keywords "
                            "(e.g. 'hiking backpack', 'skis', 'jackets')"
                        ),
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max products to return (1-6). Default 4.",
                    },
                    "in_stock_only": {
                        "type": "boolean",
                        "description": (
                            "If true, only return products with inventory > 0. "
                            "Default false (out-of-stock items ranked lower but may appear)."
                        ),
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "Optional tag filters to boost (e.g. Hiking, Snow, Adventure, "
                            "Food & Beverage)."
                        ),
                    },
                    "exclude_skus": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": (
                            "SKUs to skip — use when the customer says 'show me more', "
                            "'any other', or 'something else' so you don't re-show the same item."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "early_riser_promo",
            "description": (
                "Skill: Early Risers Discount. Generate a unique 10% Early Risers code. "
                "ONLY call when the customer explicitly asks for Early Risers. "
                "Tool enforces 8:00–10:00 AM Pacific. Do not invent codes."
            ),
            "parameters": {
                "type": "object",
                "properties": {},
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "request_human_handoff",
            "description": (
                "Escalate to a human trail guide and mute this AI. "
                "Try Skills 1–3 first. Call only for an explicit human request you cannot "
                "fulfill, out-of-scope issues (returns, billing, claims), or after a real "
                "failed attempt where the customer is still stuck."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "reason": {
                        "type": "string",
                        "enum": [
                            "explicit_request",
                            "out_of_scope",
                            "unresolved_after_retries",
                        ],
                        "description": "Why a human is needed.",
                    },
                    "summary": {
                        "type": "string",
                        "description": "One-sentence brief for the human teammate.",
                    },
                },
                "required": ["reason"],
            },
        },
    },
]


def run_tool(name: str, arguments: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]] | None]:
    """Run a tool. Returns (result_json, optional product cards for UI)."""
    if name == "lookup_order":
        result = lookup_order(
            order_number=arguments.get("order_number"),
            email=arguments.get("email"),
        )
        return result, None

    if name in ("search_catalog", "recommend_products"):
        tags = arguments.get("tags")
        if isinstance(tags, str):
            tags = [tags]
        exclude = arguments.get("exclude_skus")
        if isinstance(exclude, str):
            exclude = [exclude]
        result = search_catalog(
            query=arguments.get("query", ""),
            limit=int(arguments.get("limit") or 4),
            in_stock_only=bool(arguments.get("in_stock_only") or False),
            tags=tags,
            exclude_skus=exclude,
        )
        products = result.get("products") or None
        return result, products if products else None

    if name == "early_riser_promo":
        result = early_riser_promo()
        return result, None

    if name == "request_human_handoff":
        result = request_human_handoff(
            reason=str(arguments.get("reason") or "explicit_request"),
            summary=arguments.get("summary"),
        )
        return result, None

    return {"error": f"Unknown tool: {name}"}, None
