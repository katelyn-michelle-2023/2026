"""
Phase 3 — sizing verdict engine for Aura.

Takes a ReviewData dict (from review_crawler.py) + user profile + garment type.
Sends a focused, single-purpose prompt to K2 Think V2 and returns a sizing verdict.

Skip entirely if:
  - review_data is None
  - crawl_status is "blocked" or "failed"

If crawl_status is "no_reviews" or "partial", still run — K2 returns a low-confidence verdict.
"""

import asyncio
import json
import re

import httpx

from config import K2_API_KEY, K2_BASE_URL
from logger import (
    log_sizing_analyzer_request,
    log_sizing_analyzer_result,
    log_sizing_analyzer_skip,
)

_SKIP_STATUSES = {"blocked", "failed"}

_SIZING_SYSTEM_PROMPT = """
You are a sizing and fit expert. Your ONLY job is to determine if a garment will fit a specific person
based on review data and garment measurements. Be direct and concrete.
Return ONLY a JSON object — no prose outside the JSON, no markdown fences, no explanation.
""".strip()


def _clean_json(raw: str) -> str:
    if "</think>" in raw:
        _, raw = raw.split("</think>", 1)
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    raw = re.sub(r",\s*([}\]])", r"\1", raw)
    return raw


def _build_user_message(
    review_data: dict,
    user_profile: dict,
    garment_type: str,
) -> str:
    lines: list[str] = []

    # ── User profile ──────────────────────────────────────────────────────────
    profile_parts: list[str] = []
    if user_profile.get("top_size"):
        profile_parts.append(f"US top size {user_profile['top_size']}")
    if user_profile.get("bottom_size"):
        profile_parts.append(f"US bottom size {user_profile['bottom_size']}")
    if user_profile.get("shoe_size"):
        profile_parts.append(f"US shoe size {user_profile['shoe_size']}")
    if user_profile.get("height"):
        profile_parts.append(f"height {user_profile['height']}")
    if user_profile.get("build"):
        profile_parts.append(f"{user_profile['build']} build")
    lines.append(f"USER: {', '.join(profile_parts) if profile_parts else 'no measurements provided'}")

    # ── Garment info ──────────────────────────────────────────────────────────
    lines.append(f"GARMENT TYPE: {garment_type}")
    if review_data.get("garment_measurements"):
        lines.append(f"LISTED MEASUREMENTS: {json.dumps(review_data['garment_measurements'])}")
    if review_data.get("material_composition"):
        lines.append(f"MATERIAL: {review_data['material_composition']}")

    # ── Trust signal ──────────────────────────────────────────────────────────
    rating = review_data.get("aggregate_rating")
    count = review_data.get("total_review_count")
    if rating is not None or count is not None:
        trust_parts: list[str] = []
        if rating is not None:
            trust_parts.append(f"{rating} stars")
        if count is not None:
            trust_parts.append(f"{count} total reviews")
        lines.append(f"PRODUCT TRUST SIGNAL: {', '.join(trust_parts)}")

    # ── Review analysis ───────────────────────────────────────────────────────
    crawl_status = review_data.get("crawl_status", "success")
    sizing_sentiment = review_data.get("sizing_sentiment", "insufficient_data")
    lines.append(f"CRAWL STATUS: {crawl_status}")
    lines.append(f"SIZING SENTIMENT: {sizing_sentiment}")
    if review_data.get("top_sizing_complaints"):
        lines.append(f"TOP SIZING COMPLAINTS: {', '.join(review_data['top_sizing_complaints'])}")

    # ── Sizing review excerpts (capped at 15) ─────────────────────────────────
    sizing_reviews = [
        r for r in review_data.get("reviews", []) if r.get("mentions_sizing")
    ][:15]
    if sizing_reviews:
        lines.append("SIZING REVIEW EXCERPTS:")
        for r in sizing_reviews:
            star = f" [{r['star_rating']}★]" if r.get("star_rating") else ""
            excerpt = (r.get("text") or "")[:200]
            lines.append(f"  -{star} {excerpt}")

    # ── Confidence ceiling for zero-data scenarios ───────────────────────────
    no_data = (
        sizing_sentiment == "insufficient_data"
        and crawl_status in ("no_reviews", "partial")
    )
    if no_data:
        lines.append(
            "\nNOTE: No sizing reviews found at all. "
            "You MUST set size_adjustment to 'none' and confidence to 'low'. "
            "Base confidence_reason on material and garment type only if available."
        )
    elif sizing_sentiment == "insufficient_data" or crawl_status in ("no_reviews", "partial"):
        lines.append(
            "\nNOTE: Limited sizing data (fewer than 5 sizing reviews or partial crawl). "
            "Set confidence to 'low'. Still reason from the reviews you have and explain what they suggest. "
            "Do not refuse to give a recommendation — make your best inference and be transparent about the uncertainty."
        )

    # ── Confidence rules ──────────────────────────────────────────────────────
    lines.append(
        "\nCONFIDENCE RULES: "
        "'high' = 10+ reviews mention sizing and mostly agree. "
        "'medium' = 5-9 reviews mention sizing OR significant disagreement. "
        "'low' = <5 reviews mention sizing, no garment measurements, or crawl_status was partial/no_reviews."
    )

    # ── Output spec ───────────────────────────────────────────────────────────
    lines.append(
        "\nReturn ONLY this JSON object:\n"
        '{ "recommended_size": string, "size_adjustment": "up"|"down"|"none", '
        '"fit_flags": [string], "confidence": "high"|"medium"|"low", '
        '"confidence_reason": string }'
    )

    return "\n".join(lines)


async def analyze_sizing(
    review_data: dict | None,
    user_profile: dict,
    garment_type: str,
    product_url: str = "",
) -> dict | None:
    """
    Run a K2 sizing analysis for one product.

    Returns a SizingVerdict dict, or None if skipped or K2 fails.
    """
    if review_data is None:
        log_sizing_analyzer_skip(product_url, reason="review_data_null")
        return None

    crawl_status = review_data.get("crawl_status", "")
    if crawl_status in _SKIP_STATUSES:
        log_sizing_analyzer_skip(product_url, reason=f"crawl_status_{crawl_status}")
        print(f"[sizing_analyzer] skipping {product_url[:60]} — crawl_status={crawl_status}")
        return None

    user_message = _build_user_message(review_data, user_profile, garment_type)
    log_sizing_analyzer_request(product_url, user_message)
    print(f"[sizing_analyzer] running K2 for {product_url[:60]}")

    payload = {
        "model": "MBZUAI-IFM/K2-Think-v2",
        "messages": [
            {"role": "system", "content": _SIZING_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.0,
        "max_tokens": 400,
    }
    headers = {
        "Authorization": f"Bearer {K2_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{K2_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        cleaned = _clean_json(raw)
        verdict = json.loads(cleaned)
        log_sizing_analyzer_result(product_url, raw, verdict)
        print(f"[sizing_analyzer] {product_url[:60]} — verdict: {verdict.get('size_adjustment')} / {verdict.get('confidence')}")
        return verdict
    except Exception as exc:
        log_sizing_analyzer_result(product_url, None, None, error=str(exc))
        print(f"[sizing_analyzer] {product_url[:60]} — K2 failed: {exc}")
        return None


async def analyze_sizing_parallel(
    products: list[dict],
    review_data_list: list[dict | None],
    user_profile: dict,
) -> list[dict | None]:
    """
    Run analyze_sizing on all products in parallel.
    Returns a list aligned with the input — None for skipped or failed products.
    """
    tasks = [
        analyze_sizing(
            review_data=rd,
            user_profile=user_profile,
            garment_type=p.get("garment_type") or p.get("name") or "garment",
            product_url=p.get("product_url") or p.get("url") or "",
        )
        for p, rd in zip(products, review_data_list)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    out: list[dict | None] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            url = products[i].get("product_url") or products[i].get("url", "?")
            print(f"[sizing_analyzer] gather exception for {url}: {r}")
            out.append(None)
        else:
            out.append(r)  # type: ignore[arg-type]
    return out
