"""Local tools backed by static JSON datasets."""

from __future__ import annotations

import json
import re
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
ORDERS_PATH = ROOT / "customer_order.json"
CATALOG_PATH = ROOT / "product_catalog.json"
PT = ZoneInfo("America/Los_Angeles")
TRACKING_URL = "https://tools.usps.com/go/TrackConfirmAction?tLabels={trackingNumber}"

STOPWORDS = {
    "a",
    "an",
    "the",
    "and",
    "or",
    "for",
    "to",
    "of",
    "in",
    "on",
    "with",
    "my",
    "me",
    "i",
    "im",
    "looking",
    "want",
    "need",
    "show",
    "find",
    "get",
    "please",
    "some",
    "any",
    "recommend",
    "recommendation",
    "recommendations",
    "product",
    "products",
    "gear",
    "item",
    "items",
    "something",
    "about",
    "do",
    "you",
    "have",
    "sell",
    "best",
    "good",
}

_orders: list[dict[str, Any]] | None = None
_catalog: list[dict[str, Any]] | None = None


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


def _normalize(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _tokenize(text: str) -> list[str]:
    return [
        t
        for t in re.split(r"[^a-z0-9]+", text.lower())
        if t and t not in STOPWORDS and len(t) > 1
    ]


def _product_card(
    product: dict[str, Any],
    *,
    score: float = 0,
    matched_on: list[str] | None = None,
) -> dict[str, Any]:
    image = product.get("Image", "")
    if image.startswith("assets/"):
        image_url = "/" + image
    else:
        image_url = f"/assets/{image}"
    inventory = int(product.get("Inventory", 0) or 0)
    return {
        "sku": product["SKU"],
        "name": product["ProductName"],
        "image": image_url,
        "description": product.get("Description", ""),
        "tags": product.get("Tags", []),
        "inventory": inventory,
        "in_stock": inventory > 0,
        "match_score": round(score, 2),
        "matched_on": matched_on or [],
    }


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
) -> dict[str, Any]:
    """Local search engine over name, tags, description, SKU, and stock."""
    catalog = _load_catalog()
    query = (query or "").strip()
    query_lower = query.lower()
    tokens = _tokenize(query)
    requested_tags = [t.strip().lower() for t in (tags or []) if t and t.strip()]
    limit = max(1, min(int(limit or 4), 6))

    scored: list[tuple[float, dict[str, Any], list[str]]] = []

    for product in catalog:
        inventory = int(product.get("Inventory", 0) or 0)
        in_stock = inventory > 0
        if in_stock_only and not in_stock:
            continue

        name = product.get("ProductName", "")
        description = product.get("Description", "")
        sku = product.get("SKU", "")
        product_tags = product.get("Tags", []) or []
        name_l = name.lower()
        desc_l = description.lower()
        sku_l = sku.lower()
        tags_l = [t.lower() for t in product_tags]

        score = 0.0
        matched_on: list[str] = []

        # Full-query phrase hits
        if query_lower and query_lower in name_l:
            score += 50
            matched_on.append("name_phrase")
        if query_lower and any(query_lower == t or query_lower in t for t in tags_l):
            score += 28
            matched_on.append("tag_phrase")
        if query_lower and query_lower in desc_l:
            score += 12
            matched_on.append("description_phrase")

        # Field-weighted token search
        for token in tokens:
            if token == sku_l or token in sku_l:
                score += 25
                matched_on.append(f"sku:{sku}")
            if token in name_l:
                # stronger if token is a whole word-ish boundary in name
                score += 14 if re.search(rf"\b{re.escape(token)}\b", name_l) else 9
                matched_on.append("name")
            for tag in tags_l:
                if token == tag:
                    score += 22
                    matched_on.append(f"tag:{tag}")
                elif token in tag or tag in token:
                    score += 12
                    matched_on.append(f"tag:{tag}")
            if token in desc_l:
                score += 4
                matched_on.append("description")

        # Explicit tag filters from the agent
        for req in requested_tags:
            for tag in tags_l:
                if req == tag or req in tag or tag in req:
                    score += 18
                    matched_on.append(f"filter_tag:{tag}")

        # Stock ranking (search-engine style boost/penalty)
        if in_stock:
            score += 8
            if inventory >= 50:
                score += 2
            matched_on.append("in_stock")
        else:
            score -= 12
            matched_on.append("out_of_stock")

        # Deduplicate matched_on while preserving order
        seen: set[str] = set()
        clean_matched: list[str] = []
        for m in matched_on:
            if m not in seen:
                seen.add(m)
                clean_matched.append(m)

        # Keep docs with any real relevance, or tag-filter-only hits
        relevance = score - (8 if in_stock else 0) - (2 if inventory >= 50 else 0)
        if relevance > 0 or (requested_tags and any(m.startswith("filter_tag:") for m in clean_matched)):
            scored.append((score, product, clean_matched))

    scored.sort(key=lambda x: (-x[0], -int(x[1].get("Inventory", 0) or 0), x[1].get("ProductName", "")))

    # Soft fallback: if no lexical hits, return top in-stock adventure picks
    used_fallback = False
    if not scored and (tokens or requested_tags or query):
        used_fallback = True
        fallback = [
            p for p in catalog if (not in_stock_only) or int(p.get("Inventory", 0) or 0) > 0
        ]
        fallback.sort(key=lambda p: -int(p.get("Inventory", 0) or 0))
        scored = [(0.0, p, ["fallback_popular"]) for p in fallback[:limit]]
    else:
        scored = scored[:limit]

    products = [
        _product_card(product, score=score, matched_on=matched)
        for score, product, matched in scored
    ]

    return {
        "query": query,
        "in_stock_only": in_stock_only,
        "tags_filter": requested_tags,
        "count": len(products),
        "fallback": used_fallback,
        "products": products,
    }


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
                "Skill: Catalog Search. Local product search engine over product name, tags, "
                "description, SKU, and stock. Use for recommendations, 'do you sell X?', "
                "tag browsing, and in-stock questions. Prefer this over inventing products."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Search query — product name fragments, activity, category keywords "
                            "(e.g. 'hiking backpack', 'skis', 'invisibility cloak')"
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
        result = search_catalog(
            query=arguments.get("query", ""),
            limit=int(arguments.get("limit") or 4),
            in_stock_only=bool(arguments.get("in_stock_only") or False),
            tags=tags,
        )
        return result, result.get("products")

    if name == "early_riser_promo":
        result = early_riser_promo()
        return result, None

    return {"error": f"Unknown tool: {name}"}, None
