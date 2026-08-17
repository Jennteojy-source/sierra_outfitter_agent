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
    order_number = (order_number or "").strip() or None
    email = (email or "").strip() or None
    missing: list[str] = []
    if not order_number:
        missing.append("order_number")
    if not email:
        missing.append("email")
    if missing:
        return {
            "found": False,
            "need": missing,
            "message": (
                "Both order_number and email are required before looking up an order. "
                "Ask the customer for the missing field(s); do not guess."
            ),
        }

    orders = _load_orders()
    matches: list[dict[str, Any]] = []

    for order in orders:
        if _normalize(order["OrderNumber"]) != _normalize(order_number):
            continue
        if order["Email"].lower().strip() != email.lower().strip():
            continue
        matches.append(order)

    if not matches:
        return {
            "found": False,
            "message": "No order found for that order number and email together.",
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


_EARLY_RISERS_RE = re.compile(r"early[\s-]*risers?", re.IGNORECASE)


def _explicit_early_risers(customer_text: str | None) -> bool:
    return bool(_EARLY_RISERS_RE.search(customer_text or ""))


def early_riser_promo(customer_text: str | None = None) -> dict[str, Any]:
    """Mint a code only for an explicit Early Risers ask inside the PT window.

    Eligibility is enforced here, not by the model. `customer_text` must be the
    actual customer utterance (injected by the agent loop), not an LLM argument.
    """
    now = datetime.now(PT)
    base = {
        "code": None,
        "timezone": "America/Los_Angeles",
        "current_time": now.isoformat(),
        "window": "08:00–10:00 America/Los_Angeles",
    }

    if not _explicit_early_risers(customer_text):
        return {
            **base,
            "valid": False,
            "reason": (
                "Customer did not explicitly request the Early Risers Promotion by name. "
                "Do not mint a code for a generic coupon or discount ask. You may mention "
                "that Early Risers exists and is available 8:00–10:00 AM Pacific."
            ),
        }

    in_window = now.hour in (8, 9)  # 8:00 inclusive through 9:59
    if not in_window:
        return {
            **base,
            "valid": False,
            "reason": "Early Risers Promotion is only available between 8:00 and 10:00 AM Pacific Time.",
        }

    return {
        **base,
        "valid": True,
        "code": f"EARLY-{uuid.uuid4().hex[:8].upper()}",
        "discount": "10%",
        "reason": "Customer explicitly requested Early Risers inside the window; unique code generated.",
    }


def request_human_handoff(reason: str, summary: str | None = None) -> dict[str, Any]:
    allowed = {"explicit_request", "out_of_scope", "unresolved_after_retries"}
    clean_reason = reason if reason in allowed else "explicit_request"
    return {
        "handed_off": True,
        "reason": clean_reason,
        "summary": (summary or "").strip() or None,
        "queue": "human_trail_guides",
        "queued": True,
        "message": (
            "Handoff queued — a human will join. Confirm that, and say you can still "
            "help with catalog, orders, and Early Risers while they wait. Do not try "
            "to finish the escalated issue."
        ),
    }


TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "lookup_order",
            "description": (
                "Skill: Customer Orders. Call for any order status, shipment, or tracking "
                "question. Pass any order number and/or email the customer typed; omit a "
                "field they have not given. Do not guess. The tool decides if identifiers "
                "are enough and whether they match. Never invent a format or tracking number."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "order_number": {
                        "type": "string",
                        "description": "Order number as the customer typed it, if they gave one.",
                    },
                    "email": {
                        "type": "string",
                        "description": "Email as the customer typed it, if they gave one.",
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
                "as if they matched the query. For 'what do you sell' / 'show me some "
                "products' / 'I want to buy something', call with query 'browse' and only "
                "mention returned products."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": (
                            "Search query — nouns from the customer's message or photo. "
                            "Use 'browse' for open-ended shopping."
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
                            "Optional tag filters matching words the customer used."
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
                "Skill: Early Risers Discount. Call for any coupon, discount, or Early "
                "Risers request. Eligibility and codes come only from this tool. "
                "Never invent a code; report the tool result."
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
                "Queue a human trail guide. Does not mute this AI — you may still help "
                "with catalog, orders, and Early Risers while they wait. Try Skills 1–3 "
                "first. Call only for an explicit human request you cannot fulfill, "
                "out-of-scope issues (returns, billing, claims), or after a real failed "
                "attempt where the customer is still stuck."
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


def run_tool(
    name: str,
    arguments: dict[str, Any],
    *,
    customer_text: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]] | None]:
    """Run a tool. Returns (result_json, optional product cards for UI)."""
    if name == "lookup_order":
        result = lookup_order(
            order_number=arguments.get("order_number"),
            email=arguments.get("email"),
        )
        return result, None

    if name == "search_catalog":
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
        result = early_riser_promo(customer_text=customer_text)
        return result, None

    if name == "request_human_handoff":
        result = request_human_handoff(
            reason=str(arguments.get("reason") or "explicit_request"),
            summary=arguments.get("summary"),
        )
        return result, None

    return {"error": f"Unknown tool: {name}"}, None
