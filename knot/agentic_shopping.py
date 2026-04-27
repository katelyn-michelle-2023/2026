"""
Knot AgenticShopping — autonomous cart sync + checkout for catalog picks.

Flow per pick:
1. POST /cart  — add the product (by ASIN / external_id) to the user's merchant cart.
2. POST /cart/checkout — trigger checkout using the user's stored payment method.

Both calls are fire-and-forget (202 Accepted); the real outcome arrives via
CHECKOUT_SUCCEEDED / CHECKOUT_FAILED webhooks.  We return an optimistic
"pending" status immediately and let the frontend poll or wait for the webhook.

Requires:
  - pick["amazon_asin"]     — the product's external identifier on Amazon
  - pick["knot_merchant_id"] — Knot's merchant ID (defaults to KNOT_AMAZON_MERCHANT_ID)
  - external_user_id        — the Knot user identifier
"""

from __future__ import annotations

import httpx

from config import KNOT_AMAZON_MERCHANT_ID
from knot._client import knot_client


async def purchase_picks(
    picks: list[dict],
    external_user_id: str,
    delivery_location: dict | None = None,
) -> list[dict]:
    """
    Attempt to purchase each pick via AgenticShopping.

    Returns a list of purchase_status objects:
      { item_id, status: "pending" | "skipped" | "failed", message }
    """
    from config import KNOT_CLIENT_ID

    if not KNOT_CLIENT_ID:
        return [
            {"item_id": p.get("id"), "status": "skipped", "message": "Knot not configured"}
            for p in picks
        ]

    results: list[dict] = []
    async with knot_client(timeout=45.0) as client:
        for pick in picks:
            result = await _purchase_one(client, pick, external_user_id, delivery_location)
            results.append(result)
    return results


async def _purchase_one(
    client: httpx.AsyncClient,
    pick: dict,
    external_user_id: str,
    delivery_location: dict | None,
) -> dict:
    item_id = pick.get("id", "")
    asin = pick.get("amazon_asin")
    merchant_id = pick.get("knot_merchant_id", KNOT_AMAZON_MERCHANT_ID)

    if not asin:
        return {"item_id": item_id, "status": "skipped", "message": "No Amazon ASIN — cannot auto-purchase"}

    try:
        # ── Step 1: Sync cart ──────────────────────────────────────────────────
        cart_payload: dict = {
            "external_user_id": external_user_id,
            "merchant_id": merchant_id,
            "products": [{"external_id": asin}],
        }
        if delivery_location:
            cart_payload["delivery_location"] = delivery_location

        cart_resp = await client.post("/cart", json=cart_payload)
        if cart_resp.status_code not in (200, 202):
            return {
                "item_id": item_id,
                "status": "failed",
                "message": f"Cart sync failed: {cart_resp.status_code} {cart_resp.text[:200]}",
            }

        # ── Step 2: Checkout ───────────────────────────────────────────────────
        checkout_payload = {
            "external_user_id": external_user_id,
            "merchant_id": merchant_id,
        }
        checkout_resp = await client.post("/cart/checkout", json=checkout_payload)
        if checkout_resp.status_code not in (200, 202):
            return {
                "item_id": item_id,
                "status": "failed",
                "message": f"Checkout failed: {checkout_resp.status_code} {checkout_resp.text[:200]}",
            }

        return {
            "item_id": item_id,
            "status": "pending",
            "message": "Purchase submitted — awaiting confirmation from Amazon",
            "asin": asin,
        }

    except httpx.HTTPStatusError as exc:
        return {
            "item_id": item_id,
            "status": "failed",
            "message": f"HTTP {exc.response.status_code}: {exc.response.text[:200]}",
        }
    except Exception as exc:
        return {
            "item_id": item_id,
            "status": "failed",
            "message": str(exc),
        }
