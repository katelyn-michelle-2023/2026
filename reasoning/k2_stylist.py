"""
Aura's reasoning engine — powered by K2 Think V2.
Combines user context + parsed image + catalog, and returns 3 curated picks
alongside a TTS-ready aura_script in Aura's D1 Yapper voice.
"""

import json
import re

import httpx

from config import K2_API_KEY, K2_BASE_URL
from logger import log_k2_request, log_k2_response, log_k2_thinking, log_final_picks_request, log_final_picks_response

SYSTEM_PROMPT = """
You are Aura — a D1 Yapper AI personal stylist. You don't just find clothes, you narrate an arc.
You use Gen-Z slang naturally (periodt, slay, no cap, it's giving, understood the assignment, main character)
but you're secretly a genius at fabric composition and silhouette theory. You sound like a hype bestie,
not a customer service rep. You're opinionated, fast, and you never hedge. If something is mid, you say so.

## Vibe Dictionary
Use these definitions when matching items to aesthetics:

- **Coquette**: Soft, feminine, romantic. Think bows, lace, ribbons, pastel pinks, ballet flats, satin,
  tulle. Silhouettes are delicate — babydoll, A-line, corset. Influenced by Lana Del Rey and Sofia Coppola.

- **Clean Girl**: Minimal, effortless, healthy glow. Ribbed neutrals, gold jewelry, slicked buns.
  Fabrics are elevated basics — cashmere, linen, seamless knit. No loud logos, no clutter.

- **Dark Academia**: Moody, intellectual, literary. Tartan, wool, oxfords, tweed, turtlenecks, blazers.
  Color palette: forest green, burgundy, camel, navy, brown. Silhouettes are layered and structured.

- **Quiet Luxury**: Old money, no logos, exceptional fabric. Cashmere, leather, fine wool.
  Colors: camel, cream, navy, chocolate, grey. Every piece looks expensive without announcing it.

- **Y2K**: Early 2000s chaos energy. Low-rise, butterfly clips, micro minis, cargo pants,
  platform sneakers, juicy tracksuits, metallic fabrics. Maximalist, fun, unserious.

- **Streetwear**: Hype, urban, layered. Oversized hoodies, cargo pants, Jordan 1s, puffer vests,
  graphic tees, beanies. Gender-neutral silhouettes. Confidence is the accessory.

## Task
Given the user's request, their image analysis (if provided), their purchase history (if provided),
and the catalog below, pick exactly 4 items that best match their vibe and need.

If purchase history is provided, use it to:
- Infer the user's sizing from past purchases
- Understand their budget range and avoid recommending far outside it
- Note brand preferences and lean into or deliberately expand them
- Ground your justifications in concrete references to their past taste

Reason carefully — consider occasion, body proportions, color harmony, and aesthetic coherence.

## Output Format
Return a single JSON object with this exact shape:
{
  "picks": [
    { "id": "<catalog_item_id>", "justification": "<1-2 sentences in Aura's voice>" },
    { "id": "<catalog_item_id>", "justification": "<1-2 sentences in Aura's voice>" },
    { "id": "<catalog_item_id>", "justification": "<1-2 sentences in Aura's voice>" },
    { "id": "<catalog_item_id>", "justification": "<1-2 sentences in Aura's voice>" }
  ],
  "aura_script": "<A 3-5 sentence spoken monologue in Aura's voice describing the 4 picks and WHY. This is piped directly to TTS — write it as natural speech, no bullet points, no markdown.>"
}

Return ONLY valid JSON. No markdown fences, no preamble.
""".strip()


async def get_picks(
    user_request: str | None,
    parsed_image: dict | None,
    catalog: list[dict],
    purchase_history: dict | None = None,
) -> dict:
    """
    Call K2 Think V2 with user context + catalog + optional purchase history.
    Returns { picks: [...], aura_script: "..." }
    """
    user_message_parts: list[str] = []

    if user_request:
        user_message_parts.append(f"USER REQUEST:\n{user_request}")

    if parsed_image:
        user_message_parts.append(
            f"IMAGE ANALYSIS:\n{json.dumps(parsed_image, indent=2)}"
        )

    if purchase_history and "note" not in purchase_history:
        user_message_parts.append(
            f"PURCHASE HISTORY (use to personalise picks):\n{json.dumps(purchase_history, indent=2)}"
        )

    user_message_parts.append(
        f"CATALOG:\n{json.dumps(catalog, indent=2)}"
    )

    user_message = "\n\n".join(user_message_parts)
    log_k2_request(user_message, SYSTEM_PROMPT)

    payload = {
        "model": "MBZUAI-IFM/K2-Think-v2",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.7,
        "max_tokens": 1024,
    }

    headers = {
        "Authorization": f"Bearer {K2_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{K2_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )

    response.raise_for_status()
    data = response.json()
    print("[k2_stylist] status:", response.status_code)
    print("[k2_stylist] raw response json:", data)

    raw_text: str = data["choices"][0]["message"]["content"].strip()
    print("[k2_stylist] raw_text before json.loads:", repr(raw_text))

    # K2-Think-v2 wraps its chain-of-thought in <think>…</think> before the answer
    if "</think>" in raw_text:
        think_block, raw_text = raw_text.split("</think>", 1)
        think_content = think_block.replace("<think>", "").strip()
        print("[k2_stylist] 🧠 thinking:\n" + think_content)
        log_k2_thinking(think_content)
        raw_text = raw_text.strip()

    # Strip markdown fences if present
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    # Remove trailing commas before } or ] 
    raw_text = re.sub(r",\s*([}\]])", r"\1", raw_text)

    print("[k2_stylist] raw_text after stripping think block:", repr(raw_text[:200]))
    result: dict = json.loads(raw_text)
    log_k2_response(raw_text, result)
    return result

# ── Final picks (Phase 3) ──────────────────────────────────────────────────────

_FINAL_PICKS_SYSTEM_PROMPT = """
You are Aura — a D1 Yapper AI personal stylist. You don't just find clothes, you narrate an arc.
You use Gen-Z slang naturally (periodt, slay, no cap, it's giving, understood the assignment, main character)
but you're secretly a genius at fabric composition and silhouette theory. You sound like a hype bestie,
not a customer service rep. You're opinionated, fast, and you never hedge. If something is mid, you say so.

## Sizing Verdict Rules
Each product below may have a sizing_verdict attached. Use these rules strictly:

- If size_adjustment is "up" or "down", OR fit_flags is non-empty → mention it in Aura's voice,
  referencing the user's actual build specifically.
- recommended_size is what Aura tells the user to order — not their usual size.
- If confidence is "low" → Aura hedges: "reviews weren't super conclusive on sizing but I'd probably..."
- If size_adjustment is "none" AND fit_flags is empty → skip sizing mention entirely for that item.
- If a product has no sizing_verdict at all → recommend normally, no sizing commentary.
- If aggregate_rating and total_review_count are both available → Aura may use as a trust signal
  (e.g. "4.6 stars across 400+ reviews, this one has receipts bestie").

## Output Format
Return a single JSON object with this exact shape:
{
  "picks": [
    { "id": "<product_id>", "justification": "<1-2 sentences in Aura's voice, sizing info if relevant>" },
    ...
  ],
  "aura_script": "<A 3-5 sentence spoken monologue in Aura's voice covering all picks, sizing callouts woven in naturally. This is piped directly to TTS — write it as natural speech, no bullet points, no markdown.>"
}

Return ONLY valid JSON. No markdown fences, no preamble.
""".strip()


def _format_sizing_verdict(verdict: dict | None) -> str:
    """Render a sizing verdict as a compact string for K2 context."""
    if verdict is None:
        return "no_verdict"
    parts = [
        f"recommended_size={verdict.get('recommended_size', '?')}",
        f"size_adjustment={verdict.get('size_adjustment', 'none')}",
        f"confidence={verdict.get('confidence', 'low')}",
    ]
    flags = verdict.get("fit_flags") or []
    if flags:
        parts.append(f"fit_flags=[{', '.join(flags)}]")
    reason = verdict.get("confidence_reason", "")
    if reason:
        parts.append(f"reason={reason!r}")
    return " | ".join(parts)


async def get_final_picks(
    pre_picks: list[dict],
    sizing_verdicts: list[dict | None],
    user_request: str | None,
    parsed_image: dict | None,
    user_profile: dict | None,
) -> dict:
    """
    Second K2 call (Phase 3). Takes the 6 pre-picked products + their sizing verdicts
    and generates the final Aura output with sizing commentary baked into justifications
    and aura_script.

    pre_picks: list of full product dicts (already enriched with catalog metadata)
    sizing_verdicts: parallel list — None means no verdict for that product
    """
    # Build a compact product catalog section with sizing verdicts inline
    catalog_lines: list[str] = []
    for product, verdict in zip(pre_picks, sizing_verdicts):
        pid = product.get("id", "?")
        name = product.get("name") or "?"
        brand = product.get("brand") or "?"
        price = product.get("price_usd") or product.get("price") or "?"
        url = product.get("product_url") or product.get("url") or "?"
        rating = product.get("aggregate_rating") or product.get("review_aggregate_rating")
        review_count = product.get("total_review_count") or product.get("review_total_count")

        entry: list[str] = [
            f"ID: {pid}",
            f"Name: {name}",
            f"Brand: {brand}",
            f"Price: ${price}",
            f"URL: {url}",
        ]
        if rating is not None:
            entry.append(f"Rating: {rating}/5 ({review_count or '?'} reviews)")
        entry.append(f"Sizing Verdict: {_format_sizing_verdict(verdict)}")
        catalog_lines.append("\n".join(entry))

    user_message_parts: list[str] = []

    if user_request:
        user_message_parts.append(f"USER REQUEST:\n{user_request}")

    if parsed_image:
        user_message_parts.append(f"IMAGE ANALYSIS:\n{json.dumps(parsed_image, indent=2)}")

    if user_profile and any(user_profile.values()):
        profile_summary = ", ".join(
            f"{k}={v}" for k, v in user_profile.items() if v
        )
        user_message_parts.append(f"USER MEASUREMENTS: {profile_summary}")

    user_message_parts.append("PRODUCTS (with sizing verdicts):\n\n" + "\n\n---\n\n".join(catalog_lines))

    user_message = "\n\n".join(user_message_parts)
    log_final_picks_request(user_message, _FINAL_PICKS_SYSTEM_PROMPT)

    payload = {
        "model": "MBZUAI-IFM/K2-Think-v2",
        "messages": [
            {"role": "system", "content": _FINAL_PICKS_SYSTEM_PROMPT},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.7,
        "max_tokens": 1200,
    }
    headers = {
        "Authorization": f"Bearer {K2_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            f"{K2_BASE_URL}/chat/completions",
            headers=headers,
            json=payload,
        )

    response.raise_for_status()
    data = response.json()
    print("[k2_stylist] final_picks status:", response.status_code)

    raw_text: str = data["choices"][0]["message"]["content"].strip()

    if "</think>" in raw_text:
        think_block, raw_text = raw_text.split("</think>", 1)
        think_content = think_block.replace("<think>", "").strip()
        print("[k2_stylist] final_picks thinking:\n" + think_content)
        log_k2_thinking(think_content)
        raw_text = raw_text.strip()

    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    raw_text = re.sub(r",\s*([}\]])", r"\1", raw_text)

    print("[k2_stylist] final_picks raw_text:", repr(raw_text[:200]))
    result: dict = json.loads(raw_text)
    log_final_picks_response(raw_text, result)
    return result