"""Simple inverted search index over the static product catalog.

Built once at load time for the demo — O(tokens) lookup instead of rescanning
every product field on each query. Tiny catalog, but the structure is what you'd
grow into a real search service later.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

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
    "other",
    "others",
    "else",
    "more",
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
    "like",
}

# Expand user vocabulary → catalog vocabulary for the quirky demo assortment.
SYNONYMS: dict[str, list[str]] = {
    "backpack": ["pack", "rucksack", "bag"],
    "backpacks": ["backpack", "pack", "rucksack", "bag"],
    "pack": ["backpack", "rucksack"],
    "jacket": ["coat", "shell", "outerwear", "parka"],
    "jackets": ["jacket", "coat", "shell", "outerwear", "parka"],
    "coat": ["jacket", "outerwear"],
    "ski": ["skis", "snow", "winter"],
    "skis": ["ski", "snow", "winter"],
    "drink": ["beverage", "energy"],
    "beverage": ["drink"],
    "protein": ["bars", "food"],
    "shoes": ["footwear", "boots"],
    "boots": ["shoes", "footwear"],
    "cloak": ["invisibility", "stealth"],
    "jetpack": ["flight", "flying"],
    "plane": ["aircraft", "flight", "aviation"],
    "lamp": ["lampshade", "lighting", "light"],
    "lampshade": ["lamp", "lighting"],
    "hairbrush": ["brush", "hair"],
    "hiking": ["hike", "outdoor"],
    "hike": ["hiking", "outdoor"],
    "winter": ["snow", "ski", "skis"],
    "snow": ["winter", "ski", "skis"],
}

FIELD_WEIGHTS = {
    "sku": 25.0,
    "name": 14.0,
    "tag": 22.0,
    "description": 4.0,
}


def tokenize(text: str) -> list[str]:
    return [
        t
        for t in re.split(r"[^a-z0-9]+", (text or "").lower())
        if t and t not in STOPWORDS and len(t) > 1
    ]


def _stem_variants(token: str) -> list[str]:
    """Tiny plural/stem helpers — enough for backpacks/jackets/skis."""
    variants = [token]
    if token.endswith("ies") and len(token) > 4:
        variants.append(token[:-3] + "y")
    if token.endswith("es") and len(token) > 3:
        variants.append(token[:-2])
    if token.endswith("s") and not token.endswith("ss") and len(token) > 3:
        variants.append(token[:-1])
    return variants


def expand_query_tokens(tokens: list[str]) -> list[str]:
    expanded: list[str] = []
    seen: set[str] = set()
    for token in tokens:
        for variant in _stem_variants(token):
            for candidate in [variant, *SYNONYMS.get(variant, [])]:
                if candidate not in seen:
                    seen.add(candidate)
                    expanded.append(candidate)
    return expanded


@dataclass
class IndexedProduct:
    product: dict[str, Any]
    sku: str
    name: str
    description: str
    tags: list[str]
    inventory: int
    name_l: str
    desc_l: str
    sku_l: str
    tags_l: list[str]
    # term -> best field weight for this doc
    terms: dict[str, float] = field(default_factory=dict)


class CatalogIndex:
    """Inverted index: term → list of (sku, field_weight)."""

    def __init__(self, catalog: list[dict[str, Any]]):
        self.docs: dict[str, IndexedProduct] = {}
        self.inverted: dict[str, list[tuple[str, float]]] = defaultdict(list)
        self.all_tags: list[str] = []
        tag_seen: set[str] = set()

        for product in catalog:
            sku = product["SKU"]
            tags = product.get("Tags", []) or []
            doc = IndexedProduct(
                product=product,
                sku=sku,
                name=product.get("ProductName", ""),
                description=product.get("Description", ""),
                tags=tags,
                inventory=int(product.get("Inventory", 0) or 0),
                name_l=product.get("ProductName", "").lower(),
                desc_l=product.get("Description", "").lower(),
                sku_l=sku.lower(),
                tags_l=[t.lower() for t in tags],
            )
            self._index_doc(doc)
            self.docs[sku] = doc
            for tag in tags:
                if tag not in tag_seen:
                    tag_seen.add(tag)
                    self.all_tags.append(tag)

    def _add_term(self, doc: IndexedProduct, term: str, weight: float) -> None:
        term = term.lower().strip()
        if not term or term in STOPWORDS or len(term) < 2:
            return
        prev = doc.terms.get(term, 0.0)
        if weight > prev:
            doc.terms[term] = weight
            # keep inverted list in sync with best weight
            posting = self.inverted[term]
            for i, (sku, _) in enumerate(posting):
                if sku == doc.sku:
                    posting[i] = (doc.sku, weight)
                    break
            else:
                posting.append((doc.sku, weight))

    def _index_doc(self, doc: IndexedProduct) -> None:
        self._add_term(doc, doc.sku_l, FIELD_WEIGHTS["sku"])
        for token in tokenize(doc.name):
            self._add_term(doc, token, FIELD_WEIGHTS["name"])
            for variant in _stem_variants(token):
                self._add_term(doc, variant, FIELD_WEIGHTS["name"] * 0.9)
        for tag in doc.tags_l:
            self._add_term(doc, tag, FIELD_WEIGHTS["tag"])
            for token in tokenize(tag):
                self._add_term(doc, token, FIELD_WEIGHTS["tag"] * 0.85)
                for variant in _stem_variants(token):
                    self._add_term(doc, variant, FIELD_WEIGHTS["tag"] * 0.8)
        for token in tokenize(doc.description):
            self._add_term(doc, token, FIELD_WEIGHTS["description"])

    def search(
        self,
        query: str,
        *,
        limit: int = 4,
        in_stock_only: bool = False,
        tags: list[str] | None = None,
        exclude_skus: list[str] | None = None,
    ) -> dict[str, Any]:
        query = (query or "").strip()
        query_lower = query.lower()
        tokens = tokenize(query)
        expanded = expand_query_tokens(tokens)
        requested_tags = [t.strip().lower() for t in (tags or []) if t and t.strip()]
        excluded = {s.strip().upper() for s in (exclude_skus or []) if s and s.strip()}
        limit = max(1, min(int(limit or 4), 6))

        scores: dict[str, float] = defaultdict(float)
        matched: dict[str, list[str]] = defaultdict(list)

        # Phrase hits (name / tag / description) — still cheap on 10 docs
        for sku, doc in self.docs.items():
            if sku in excluded:
                continue
            if in_stock_only and doc.inventory <= 0:
                continue
            if query_lower and query_lower in doc.name_l:
                scores[sku] += 50
                matched[sku].append("name_phrase")
            if query_lower and any(query_lower == t or query_lower in t for t in doc.tags_l):
                scores[sku] += 28
                matched[sku].append("tag_phrase")
            if query_lower and query_lower in doc.desc_l:
                scores[sku] += 12
                matched[sku].append("description_phrase")

        # Inverted-index term lookup
        for term in expanded:
            for sku, weight in self.inverted.get(term, []):
                if sku in excluded:
                    continue
                doc = self.docs[sku]
                if in_stock_only and doc.inventory <= 0:
                    continue
                scores[sku] += weight
                matched[sku].append(f"term:{term}")

        # Explicit tag filters from the agent
        for req in requested_tags:
            for sku, doc in self.docs.items():
                if sku in excluded:
                    continue
                if in_stock_only and doc.inventory <= 0:
                    continue
                for tag in doc.tags_l:
                    if req == tag or req in tag or tag in req:
                        scores[sku] += 18
                        matched[sku].append(f"filter_tag:{tag}")

        ranked: list[tuple[float, IndexedProduct, list[str]]] = []
        for sku, score in scores.items():
            doc = self.docs[sku]
            # stock boost
            if doc.inventory > 0:
                score += 8
                if doc.inventory >= 50:
                    score += 2
                matched[sku].append("in_stock")
            else:
                score -= 12
                matched[sku].append("out_of_stock")

            # Drop pure stock-boost noise: need real lexical / tag signal
            clean = _dedupe(matched[sku])
            relevance = score - (8 if doc.inventory > 0 else 0) - (2 if doc.inventory >= 50 else 0)
            has_filter = any(m.startswith("filter_tag:") for m in clean)
            if relevance > 0 or has_filter:
                ranked.append((score, doc, clean))

        ranked.sort(key=lambda x: (-x[0], -x[1].inventory, x[1].name))
        top = ranked[:limit]

        products = [
            {
                "sku": doc.sku,
                "name": doc.name,
                "image": _image_url(doc.product),
                "description": doc.description,
                "tags": doc.tags,
                "inventory": doc.inventory,
                "in_stock": doc.inventory > 0,
                "match_score": round(score, 2),
                "matched_on": matched_on,
            }
            for score, doc, matched_on in top
        ]

        found = len(products) > 0
        return {
            "query": query,
            "expanded_terms": expanded,
            "in_stock_only": in_stock_only,
            "tags_filter": requested_tags,
            "excluded_skus": sorted(excluded),
            "count": len(products),
            "found": found,
            "fallback": False,
            "message": None
            if found
            else (
                "No catalog matches for that query. Be honest — we don't sell that item. "
                f"Available category tags: {', '.join(self.all_tags[:12])}."
            ),
            "available_tags": self.all_tags,
            "products": products,
        }


def _image_url(product: dict[str, Any]) -> str:
    image = product.get("Image", "")
    if image.startswith("assets/"):
        return "/" + image
    return f"/assets/{image}"


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out
