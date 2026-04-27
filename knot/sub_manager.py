"""
Knot SubManager — surface and cancel fashion-related subscriptions.

SubscriptionManager surfaces subscription IDs via the CARD_UPDATED webhook
after a CardSwitcher flow. For this app, we:

1. GET /accounts to find connected accounts that include subscription scope.
2. For any subscription IDs we have stored (passed in from webhook storage),
   call GET /subscriptions/{id} to retrieve details.
3. Filter for fashion-relevant services and return them.
4. Cancel endpoint: POST /subscriptions/{id}/cancel.

Because webhook storage is outside this module's scope, the caller may pass
known subscription IDs directly. If none are available, we return an empty
list gracefully.
"""

from __future__ import annotations

import httpx

from knot._client import knot_client

FASHION_SUBSCRIPTION_KEYWORDS = {
    "stitch fix", "stitchfix", "fabfitfun", "rent the runway", "nuuly",
    "le tote", "gwynnie bee", "fashion", "style", "clothing", "apparel",
    "thred up", "thredup", "poshmark",
}

FASHION_SUBSCRIPTION_MERCHANTS = {
    "stitch fix", "rent the runway", "nuuly", "fabfitfun",
}


def _is_fashion_subscription(name: str) -> bool:
    name_lower = name.lower()
    return any(kw in name_lower for kw in FASHION_SUBSCRIPTION_KEYWORDS)


async def get_active_subscriptions(
    external_user_id: str,
    known_subscription_ids: list[str] | None = None,
) -> list[dict]:
    """
    Return fashion-relevant active subscriptions for this user.
    Pass known_subscription_ids from the CARD_UPDATED webhook payload if available.
    """
    from config import KNOT_CLIENT_ID

    if not KNOT_CLIENT_ID:
        return []

    try:
        async with knot_client() as client:
            return await _fetch_subscriptions(client, external_user_id, known_subscription_ids or [])
    except Exception as exc:
        print(f"[sub_manager] Error fetching subscriptions: {exc}")
        return []


async def _fetch_subscriptions(
    client: httpx.AsyncClient,
    external_user_id: str,
    known_ids: list[str],
) -> list[dict]:
    subscriptions: list[dict] = []

    # If we have subscription IDs from a webhook, retrieve each one
    for sub_id in known_ids:
        try:
            resp = await client.get(f"/subscriptions/{sub_id}")
            if resp.status_code == 200:
                sub = resp.json()
                if _is_fashion_subscription(sub.get("name", "") or sub.get("merchant_name", "")):
                    subscriptions.append(_format_subscription(sub))
        except Exception as exc:
            print(f"[sub_manager] Could not retrieve subscription {sub_id}: {exc}")

    return subscriptions


def _format_subscription(raw: dict) -> dict:
    return {
        "id": raw.get("id", ""),
        "name": raw.get("name") or raw.get("merchant_name", "Unknown"),
        "monthly_cost_usd": _extract_monthly_cost(raw),
        "status": raw.get("status", "active"),
        "is_cancellable": raw.get("is_cancellable", False),
        "next_charge_date": raw.get("next_charge_date"),
    }


def _extract_monthly_cost(raw: dict) -> float | None:
    amount = raw.get("amount") or raw.get("price")
    if amount is None:
        return None
    try:
        return float(amount)
    except (ValueError, TypeError):
        return None


async def cancel_subscription(subscription_id: str) -> dict:
    """
    Cancel a subscription by ID.
    Returns { success: bool, message: str }.
    """
    from config import KNOT_CLIENT_ID

    if not KNOT_CLIENT_ID:
        return {"success": False, "message": "Knot not configured"}

    try:
        async with knot_client() as client:
            resp = await client.post(f"/subscriptions/{subscription_id}/cancel")
            if resp.status_code in (200, 202):
                return {"success": True, "message": "Cancellation request submitted"}
            return {
                "success": False,
                "message": f"Cancellation failed: {resp.status_code} {resp.text[:200]}",
            }
    except Exception as exc:
        return {"success": False, "message": str(exc)}
