"""
Phase 3 — Firecrawl interact-based review crawler for Aura.

For a given product URL:
  1. Scrape the page → get scrape_id + parse aggregate rating/count for free
  2. Interact call #1 → expand reviews section, extract reviews as JSON
  3. Interact call #2 → extract garment measurements + material composition
  4. Always close the session in a finally block

Returns a ReviewData dict on success, or None on unrecoverable failure.
A failed crawl for one product never blocks or crashes the pipeline.
"""

import asyncio
import json
import re
import traceback
from typing import Any

import httpx

from firecrawl import Firecrawl

from config import FIRECRAWL_API_KEY, K2_API_KEY, K2_BASE_URL
from logger import (
    log_review_crawl_error,
    log_review_crawl_interact,
    log_review_crawl_result,
    log_review_crawl_scrape,
    log_review_crawl_start,
)

# ── Constants ─────────────────────────────────────────────────────────────────

_AMAZON_BLOCK_PHRASES = [
    "robot check",
    "captcha",
    "enter the characters you see below",
    "sorry, we just need to make sure you're not a robot",
]

_SIZING_KEYWORDS = [
    "runs small", "runs large", "size up", "size down", "true to size",
    "fits small", "boxy", "short", "long", "tight", "loose", "narrow", "wide",
]

_SIZING_POSITIVE_PHRASES = [
    "true to size", "fits perfectly", "perfect fit", "fits well",
    "size as expected", "fits great", "fits nicely", "accurate sizing", "fits correctly",
]

_SIZING_NEGATIVE_PHRASES = [
    "runs small", "runs large", "size up", "size down", "fits small", "boxy",
    "too short", "too long", "too tight", "too loose", "too narrow", "too wide",
]

# ── Interact prompts (one task each) ─────────────────────────────────────────

# Call A: click the reviews tab
_INTERACT_A_CLICK_REVIEWS_TAB = (
    "Click any tab, button, or link whose text contains the word 'Reviews' or 'Ratings'. "
    "After clicking, wait for the page content to finish updating before returning. "
    "Just click and wait, don't extract anything."
)

# Call B: load more reviews
_INTERACT_B_LOAD_MORE_REVIEWS = (
    "Click any 'Load More', 'Show more', or 'See all reviews' button in the reviews section. "
    "Just click it, don't extract anything."
)

# Call C: extract reviews as JSON
_INTERACT_C_EXTRACT_REVIEWS = (
    "Extract all visible customer reviews as a JSON array. "
    "Each item: text (string), star_rating (1-5 or null), "
    "mentions_sizing (true if it mentions fit/size/sizing/runs small/runs large/true to size). "
    "Return ONLY the JSON array."
)

# Call D: click the details/size tab
_INTERACT_D_CLICK_DETAILS_TAB = (
    "Click any tab, accordion, or button whose text contains "
    "'Details', 'Size & Fit', 'Size Guide', 'Fabric', 'Material', or 'Description'. "
    "Just click it, don't extract anything."
)

# Call E: extract measurements and material as JSON
_INTERACT_E_EXTRACT_SPECS = (
    "Extract garment measurements (chest, length, waist, inseam, sleeve in inches or cm) "
    "and material composition from the page. "
    "Return ONLY a JSON object: {\"measurements\": {...} or null, \"material\": \"...\" or null}."
)

_K2_FALLBACK_PROMPT = (
    "Extract valid JSON from the text below. "
    "Return ONLY the JSON object or array, no explanation, no markdown fences.\n\nTEXT:\n"
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fc() -> Firecrawl:
    return Firecrawl(api_key=FIRECRAWL_API_KEY)


def _clean_json(raw: str) -> str:
    """Strip think blocks, markdown fences, trailing commas."""
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


async def _summarize_reviews(reviews: list[dict], product_url: str) -> str | None:
    """Ask K2 to write a 2-3 sentence plain-English summary of overall review sentiment."""
    excerpts = "\n".join(
        f"- [{r.get('star_rating', '?')}★] {(r.get('text') or '')[:200]}"
        for r in reviews[:20]
    )
    prompt = (
        "Read these customer reviews and write a 2-3 sentence summary of what people generally think "
        "about this product. Be specific — mention what they liked, what they didn't, and any patterns. "
        "Write in plain conversational English. Return ONLY the summary text, no labels or preamble.\n\n"
        f"REVIEWS:\n{excerpts}"
    )
    payload = {
        "model": "MBZUAI-IFM/K2-Think-v2",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.3,
        "max_tokens": 150,
    }
    headers = {"Authorization": f"Bearer {K2_API_KEY}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(f"{K2_BASE_URL}/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        # Strip thinking block if present
        if "</think>" in raw:
            _, raw = raw.split("</think>", 1)
        return raw.strip()
    except Exception as exc:
        log_review_crawl_error(product_url, "review_summary_failed", str(exc))
        traceback.print_exc()
        return None


async def _k2_json_fallback(text: str) -> Any:
    """Pass malformed interact output to K2 Think V2 and extract JSON (thinking block stripped)."""
    payload = {
        "model": "MBZUAI-IFM/K2-Think-v2",
        "messages": [{"role": "user", "content": _K2_FALLBACK_PROMPT + text[:4000]}],
        "temperature": 0.0,
        "max_tokens": 1024,
    }
    headers = {
        "Authorization": f"Bearer {K2_API_KEY}",
        "Content-Type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(f"{K2_BASE_URL}/chat/completions", headers=headers, json=payload)
    resp.raise_for_status()
    raw = resp.json()["choices"][0]["message"]["content"].strip()
    return json.loads(_clean_json(raw))


def _parse_rating_and_count(markdown: str) -> tuple[float | None, int | None]:
    """
    Extract aggregate star rating and total review count from page Markdown.
    These are in the initial scrape payload for free (no extra credits).
    """
    rating: float | None = None
    count: int | None = None

    for pattern in [
        r"(\d\.\d)\s*out\s*of\s*5",
        r"★\s*(\d\.\d)",
        r"[Rr]ated\s+(\d\.\d)",
        r"(\d\.\d)\s*/\s*5",
        r'"ratingValue"\s*:\s*"?(\d\.\d)"?',
    ]:
        m = re.search(pattern, markdown)
        if m:
            try:
                rating = float(m.group(1))
                break
            except ValueError:
                pass

    for pattern in [
        r"(\d[\d,]+)\s+(?:customer\s+)?reviews",
        r"(\d[\d,]+)\s+ratings?",
        r"\((\d[\d,]+)\s+reviews?\)",
        r'"reviewCount"\s*:\s*"?(\d[\d,]+)"?',
    ]:
        m = re.search(pattern, markdown, re.IGNORECASE)
        if m:
            try:
                count = int(m.group(1).replace(",", ""))
                break
            except ValueError:
                pass

    return rating, count


def _is_amazon_blocked(markdown: str) -> bool:
    lower = markdown.lower()
    return any(phrase in lower for phrase in _AMAZON_BLOCK_PHRASES)


def _compute_sizing_sentiment(reviews: list[dict]) -> str:
    sizing_reviews = [r for r in reviews if r.get("mentions_sizing")]
    if not sizing_reviews:
        return "insufficient_data"

    positive = 0
    negative = 0
    for r in sizing_reviews:
        text_lower = (r.get("text") or "").lower()
        is_pos = any(p in text_lower for p in _SIZING_POSITIVE_PHRASES)
        is_neg = any(p in text_lower for p in _SIZING_NEGATIVE_PHRASES)
        if is_pos and not is_neg:
            positive += 1
        elif is_neg:
            negative += 1

    total = len(sizing_reviews)
    if negative / total > 0.4:
        return "negative"
    if positive / total > 0.7:
        return "positive"
    return "mixed"


def _extract_top_complaints(reviews: list[dict]) -> list[str]:
    counts: dict[str, int] = {}
    for r in reviews:
        text_lower = (r.get("text") or "").lower()
        for kw in _SIZING_KEYWORDS:
            if kw in text_lower:
                counts[kw] = counts.get(kw, 0) + 1
    sorted_complaints = sorted(counts.items(), key=lambda x: -x[1])
    return [kw for kw, _ in sorted_complaints[:5]]


async def _parse_interact_output(
    raw_output: str,
    product_url: str,
    call_num: int,
    expected_type: type,
) -> Any:
    """
    Parse interact output to expected_type (list or dict).
    Falls back to Gemini Flash if direct JSON parse fails.
    Returns None on complete failure.
    """
    # Direct parse attempt
    try:
        parsed = json.loads(_clean_json(raw_output))
        if isinstance(parsed, expected_type):
            return parsed
        # Unwrap if nested (some sites return {"reviews": [...]})
        if isinstance(parsed, dict) and expected_type is list:
            for v in parsed.values():
                if isinstance(v, list):
                    return v
    except (json.JSONDecodeError, ValueError):
        pass

    # K2 Think V2 fallback
    try:
        parsed = await _k2_json_fallback(raw_output)
        if isinstance(parsed, expected_type):
            return parsed
        if isinstance(parsed, dict) and expected_type is list:
            for v in parsed.values():
                if isinstance(v, list):
                    return v
    except Exception as exc:
        log_review_crawl_error(
            product_url,
            f"interact{call_num}_k2_fallback_failed",
            str(exc),
        )
        traceback.print_exc()

    return None


# ── Public API ────────────────────────────────────────────────────────────────

async def crawl_product(product_url: str) -> dict | None:
    """
    Open a Firecrawl interact session for a product URL and extract review data.

    Returns a ReviewData dict on success, or None on unrecoverable failure.
    Session is always closed in a finally block.
    """
    log_review_crawl_start(product_url)
    loop = asyncio.get_running_loop()
    fc = _fc()
    scrape_id: str | None = None

    try:
        # ── Step 1: Scrape → scrape_id + free aggregate data ─────────────────
        try:
            scrape_result = await loop.run_in_executor(
                None,
                lambda: fc.scrape(product_url, formats=["markdown"]),
            )
        except Exception as exc:
            log_review_crawl_error(product_url, "scrape_failed", str(exc))
            traceback.print_exc()
            return None

        scrape_id = getattr(getattr(scrape_result, "metadata", None), "scrape_id", None)
        markdown = getattr(scrape_result, "markdown", "") or ""

        log_review_crawl_scrape(product_url, scrape_id=scrape_id, markdown_len=len(markdown))

        # Amazon CAPTCHA check — bail out before any interact credits are spent
        if "amazon.com" in product_url and _is_amazon_blocked(markdown):
            log_review_crawl_error(product_url, "blocked", "Amazon CAPTCHA/robot-check detected in Markdown")
            # scrape_id may exist but no interact session started yet; stop_interaction is safe to skip
            scrape_id = None
            return None

        aggregate_rating, total_review_count = _parse_rating_and_count(markdown)
        print(
            f"[review_crawler] {product_url[:60]} — "
            f"rating={aggregate_rating} count={total_review_count} scrape_id={scrape_id}"
        )

        if scrape_id is None:
            log_review_crawl_error(product_url, "no_scrape_id", "Firecrawl scrape did not return a scrape_id")
            return None

        reviews: list[dict] = []
        garment_measurements: dict | None = None
        material_composition: str | None = None
        crawl_status = "success"

        # ── Call A: click reviews tab ─────────────────────────────────────────
        try:
            r = await loop.run_in_executor(
                None,
                lambda: fc.interact(scrape_id, prompt=_INTERACT_A_CLICK_REVIEWS_TAB),
            )
            raw = getattr(r, "output", "") or ""
            log_review_crawl_interact(product_url, call_num=1, raw_output=raw, note="click_reviews_tab")
            print(f"[review_crawler] {product_url[:60]} — A: click reviews tab → {raw[:80]}")
        except Exception as exc:
            log_review_crawl_error(product_url, "interactA_failed", str(exc))
            print(f"[review_crawler] {product_url[:60]} — A: click reviews tab failed (continuing): {exc}")
            traceback.print_exc()

        # ── Call B: extract reviews ───────────────────────────────────────────
        try:
            r = await loop.run_in_executor(
                None,
                lambda: fc.interact(scrape_id, prompt=_INTERACT_C_EXTRACT_REVIEWS),
            )
            raw = getattr(r, "output", "") or ""
            log_review_crawl_interact(product_url, call_num=2, raw_output=raw, note="extract_reviews")

            parsed_reviews = await _parse_interact_output(raw, product_url, 2, list)
            if parsed_reviews is not None:
                reviews = parsed_reviews
            else:
                crawl_status = "partial"

            print(f"[review_crawler] {product_url[:60]} — B: {len(reviews)} reviews extracted")
        except Exception as exc:
            log_review_crawl_error(product_url, "interactB_failed", str(exc))
            crawl_status = "partial"
            print(f"[review_crawler] {product_url[:60]} — B: extract reviews failed: {exc}")
            traceback.print_exc()

        # ── Call C: load more + re-extract only if we got nothing ─────────────
        if not reviews:
            try:
                r = await loop.run_in_executor(
                    None,
                    lambda: fc.interact(scrape_id, prompt=_INTERACT_B_LOAD_MORE_REVIEWS),
                )
                raw = getattr(r, "output", "") or ""
                log_review_crawl_interact(product_url, call_num=3, raw_output=raw, note="load_more_reviews")
                print(f"[review_crawler] {product_url[:60]} — C: load more → {raw[:80]}")

                r2 = await loop.run_in_executor(
                    None,
                    lambda: fc.interact(scrape_id, prompt=_INTERACT_C_EXTRACT_REVIEWS),
                )
                raw2 = getattr(r2, "output", "") or ""
                log_review_crawl_interact(product_url, call_num=4, raw_output=raw2, note="extract_reviews_after_load_more")

                parsed_reviews = await _parse_interact_output(raw2, product_url, 4, list)
                if parsed_reviews is not None:
                    reviews = parsed_reviews
                print(f"[review_crawler] {product_url[:60]} — C: {len(reviews)} reviews after load more")
            except Exception as exc:
                log_review_crawl_error(product_url, "interactC_failed", str(exc))
                print(f"[review_crawler] {product_url[:60]} — C: load more/re-extract failed (continuing): {exc}")
                traceback.print_exc()

        if not reviews:
            crawl_status = "no_reviews"
            log_review_crawl_interact(product_url, call_num=4, note="empty_reviews_array")

        # ── Call D: click details/size tab ────────────────────────────────────
        try:
            r = await loop.run_in_executor(
                None,
                lambda: fc.interact(scrape_id, prompt=_INTERACT_D_CLICK_DETAILS_TAB),
            )
            raw = getattr(r, "output", "") or ""
            log_review_crawl_interact(product_url, call_num=4, raw_output=raw, note="click_details_tab")
            print(f"[review_crawler] {product_url[:60]} — D: click details tab → {raw[:80]}")
        except Exception as exc:
            log_review_crawl_error(product_url, "interactD_failed", str(exc))
            print(f"[review_crawler] {product_url[:60]} — D: click details tab failed (continuing): {exc}")
            traceback.print_exc()

        # ── Call E: extract measurements + material ───────────────────────────
        try:
            r = await loop.run_in_executor(
                None,
                lambda: fc.interact(scrape_id, prompt=_INTERACT_E_EXTRACT_SPECS),
            )
            raw = getattr(r, "output", "") or ""
            log_review_crawl_interact(product_url, call_num=5, raw_output=raw, note="extract_specs")

            parsed_specs = await _parse_interact_output(raw, product_url, 5, dict)
            if isinstance(parsed_specs, dict):
                

                garment_measurements = parsed_specs.get("measurements") or None
                material_composition = parsed_specs.get("material") or None

            print(
                f"[review_crawler] {product_url[:60]} — E: "
                f"measurements={garment_measurements is not None} material={material_composition is not None}"
            )
        except Exception as exc:
            log_review_crawl_error(product_url, "interactE_failed", str(exc))
            print(f"[review_crawler] {product_url[:60]} — E: extract specs failed: {exc}")
            traceback.print_exc()
            # garment_measurements and material_composition stay None

        # ── Derive computed fields ─────────────────────────────────────────────
        sizing_sentiment = _compute_sizing_sentiment(reviews)
        top_sizing_complaints = _extract_top_complaints(reviews)

        # Promote to "success" if we got reviews and status wasn't already degraded
        if reviews and crawl_status == "no_reviews":
            crawl_status = "success"

        # ── K2 review summary ────────────────────────────────────────────
        review_summary: str | None = None
        if reviews:
            review_summary = await _summarize_reviews(reviews, product_url)
            print(f"[review_crawler] {product_url[:60]} — summary: {(review_summary or '')[:80]}")

        result: dict = {
            "product_url": product_url,
            "aggregate_rating": aggregate_rating,
            "total_review_count": total_review_count,
            "reviews": reviews,
            "total_reviews_found": len(reviews),
            "review_summary": review_summary,
            "sizing_sentiment": sizing_sentiment,
            "top_sizing_complaints": top_sizing_complaints,
            "garment_measurements": garment_measurements,
            "material_composition": material_composition,
            "crawl_status": crawl_status,
        }

        log_review_crawl_result(product_url, result)
        print(f"[review_crawler] {product_url[:60]} — done: status={crawl_status} sentiment={sizing_sentiment}")
        return result

    except Exception as exc:
        log_review_crawl_error(product_url, "unhandled_exception", str(exc))
        print(f"[review_crawler] {product_url[:60]} — unhandled exception: {exc}")
        traceback.print_exc()
        return None

    finally:
        # Always close the session — logged if DELETE fails, never re-thrown
        if scrape_id:
            try:
                await loop.run_in_executor(None, lambda: fc.stop_interaction(scrape_id))
                print(f"[review_crawler] session closed: {scrape_id}")
            except Exception as exc:
                log_review_crawl_error(product_url, "delete_session_failed", str(exc))
                print(f"[review_crawler] WARNING: failed to close session {scrape_id}: {exc}")
                traceback.print_exc()


async def crawl_products_parallel(products: list[dict]) -> list[dict | None]:
    """
    Run crawl_product on all products in parallel.
    Returns a list aligned with the input — None for any product whose crawl failed.
    A failure on one never delays the others.
    """
    tasks = [crawl_product(p["product_url"]) for p in products]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    out: list[dict | None] = []
    for i, r in enumerate(results):
        if isinstance(r, Exception):
            url = products[i].get("product_url", "?")
            log_review_crawl_error(url, "gather_exception", str(r))
            print(f"[review_crawler] gather exception for {url}: {r}")
            out.append(None)
        else:
            out.append(r)  # type: ignore[arg-type]
    return out
