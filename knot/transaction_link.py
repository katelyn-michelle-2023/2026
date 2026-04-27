"""
Knot TransactionLink — fetch SKU-level purchase history for a user.

Flow:
1. GET /accounts to find which merchants the user has linked.
2. For each linked merchant (prioritise Amazon), POST /transactions/sync
   to retrieve recent transactions.
3. Summarise into a structured dict that k2_stylist can inject as context.
"""

from __future__ import annotations

import re

import httpx

from config import KNOT_AMAZON_MERCHANT_ID
from knot._client import knot_client

FASHION_KEYWORDS = {
    "shirt", "dress", "pants", "jeans", "jacket", "coat", "sweater", "hoodie",
    "skirt", "blouse", "top", "shoes", "boots", "sneakers", "heels", "sandals",
    "shorts", "leggings", "suit", "blazer", "vest", "cardigan", "tee", "t-shirt",
    "apparel", "clothing", "fashion", "wear", "outfit", "style",
}


def _is_fashion(item_name: str) -> bool:
    name_lower = item_name.lower()
    return any(kw in name_lower for kw in FASHION_KEYWORDS)


async def get_purchase_history(external_user_id: str) -> dict:
    """
    Return a structured purchase-history summary for k2_stylist context.
    Returns an empty summary (with a note) if Knot credentials are not set
    or if the user has no linked accounts.
    """
    from config import KNOT_CLIENT_ID

    # Demo override — pre-seeded fashion history for hackathon demo.
    # Activate by sending knot_token="aura-test-user-001" or "demo".
    if external_user_id in ("aura-test-user-001", "demo"):
        return {
            "recent_items": [
                {"name": "Levi's 501 Original Jeans W26 L30", "brand": "Levi's", "price_usd": 89.0, "category": "bottoms"},
                {"name": "New Balance 574 Sneaker Size 7", "brand": "New Balance", "price_usd": 95.0, "category": "shoes"},
                {"name": "Zara Oversized Blazer XS", "brand": "Zara", "price_usd": 69.0, "category": "outerwear"},
                {"name": "Mango Ribbed Knit Cardigan XS", "brand": "Mango", "price_usd": 49.0, "category": "tops"},
                {"name": "ASOS Satin Slip Dress Size 6", "brand": "ASOS", "price_usd": 52.0, "category": "dresses"},
                {"name": "H&M Cargo Trousers XS", "brand": "H&M", "price_usd": 34.0, "category": "bottoms"},
                {"name": "Uniqlo Ribbed Crew Neck Sweater XS", "brand": "Uniqlo", "price_usd": 39.0, "category": "tops"},
            ],
            "brand_affinities": ["Levi's", "New Balance", "Zara", "Mango", "Uniqlo"],
            "avg_spend_usd": 61.0,
            "price_range_usd": {"min": 34.0, "max": 95.0},
            "size_signals": ["XS", "W26"],
        }

    if not KNOT_CLIENT_ID:
        return {"note": "Knot not configured — purchase history unavailable."}

    try:
        async with knot_client() as client:
            return await _fetch_history(client, external_user_id)
    except httpx.HTTPStatusError as exc:
        print(f"[transaction_link] HTTP error {exc.response.status_code}: {exc.response.text}")
        return {"note": f"TransactionLink error: {exc.response.status_code}"}
    except Exception as exc:
        print(f"[transaction_link] Unexpected error: {exc}")
        return {"note": "TransactionLink unavailable."}


async def _fetch_history(client: httpx.AsyncClient, external_user_id: str) -> dict:
    # ── 1. Get connected merchant accounts ────────────────────────────────────
    accounts_resp = await client.get(
        "/accounts/get",
        params={"external_user_id": external_user_id},
    )
    if accounts_resp.status_code == 404:
        return {"note": "No linked accounts found for this user."}
    accounts_resp.raise_for_status()
    accounts: list[dict] = accounts_resp.json().get("accounts", [])

    if not accounts:
        return {"note": "User has no linked merchant accounts yet."}

    # Prioritise Amazon; fall back to all connected merchants
    amazon_accounts = [
        a for a in accounts
        if a.get("merchant_id") == KNOT_AMAZON_MERCHANT_ID
        and a.get("connection", {}).get("status") == "connected"
    ]
    target_accounts = amazon_accounts or [
        a for a in accounts if a.get("connection", {}).get("status") == "connected"
    ]

    all_items: list[dict] = []
    prices: list[float] = []
    brands: dict[str, int] = {}

    for account in target_accounts:
        merchant_id = account["merchant_id"]
        items, item_prices = await _sync_transactions(client, external_user_id, merchant_id)
        all_items.extend(items)
        prices.extend(item_prices)
        for item in items:
            brand = item.get("brand", "")
            if brand:
                brands[brand] = brands.get(brand, 0) + 1

    if not all_items:
        return {"note": "No transaction history found for linked accounts."}

    # ── 3. Build summary ──────────────────────────────────────────────────────
    avg_price = sum(prices) / len(prices) if prices else 0
    top_brands = sorted(brands.items(), key=lambda x: -x[1])[:5]
    size_signals = _extract_size_signals(all_items)

    return {
        "recent_items": all_items[:20],
        "brand_affinities": [b[0] for b in top_brands],
        "avg_spend_usd": round(avg_price, 2),
        "price_range_usd": {
            "min": round(min(prices), 2) if prices else 0,
            "max": round(max(prices), 2) if prices else 0,
        },
        "size_signals": size_signals,
    }


async def _sync_transactions(
    client: httpx.AsyncClient, external_user_id: str, merchant_id: int
) -> tuple[list[dict], list[float]]:
    """Sync transactions for one merchant account; return (items, prices)."""
    resp = await client.post(
        "/transactions/sync",
        json={"external_user_id": external_user_id, "merchant_id": merchant_id},
    )
    if resp.status_code in (400, 404):
        return [], []
    resp.raise_for_status()

    transactions: list[dict] = resp.json().get("transactions", [])
    items: list[dict] = []
    prices: list[float] = []

    for txn in transactions:
        for line in txn.get("line_items", []):
            name = line.get("name", "")
            price = line.get("price", 0) or 0
            if price:
                prices.append(float(price))
            items.append({
                "name": name,
                "brand": line.get("brand", ""),
                "price_usd": float(price),
                "category": line.get("category", ""),
                "quantity": line.get("quantity", 1),
            })

    return items, prices


_SIZE_RE = re.compile(
    r"\b(XXS|XS|S|M|L|XL|XXL|XXXL|2XL|3XL|"
    r"size\s*\d+|W\d{2}|L\d{2}|US\s*\d+(\.\d+)?)\b",
    re.IGNORECASE,
)


def _extract_size_signals(items: list[dict]) -> list[str]:
    sizes: set[str] = set()
    for item in items:
        matches = _SIZE_RE.findall(item.get("name", ""))
        for match in matches:
            sizes.add(match[0].upper())
    return sorted(sizes)
