"""
Phase 2 — live product discovery via Firecrawl + K2 extraction.

Flow:
  1. Firecrawl Search  → product URLs from trusted e-commerce sites
  2. Firecrawl Scrape  → raw Markdown per URL  (parallel)
  3. K2 Think V2       → structured product JSON per URL  (parallel)
  4. Material auditor  → cotton-percentage flag per product
  5. Dedup + rank      → top n_results clean products
"""

import asyncio
import json
import re
from dataclasses import dataclass, field

import httpx
from firecrawl import Firecrawl

from config import FIRECRAWL_API_KEY, K2_API_KEY, K2_BASE_URL, TRUSTED_SITES
from logger import (
    log_firecrawl_scrape,
    log_firecrawl_scrape_result,
    log_firecrawl_search,
    log_firecrawl_search_results,
    log_search_query,
    log_web_search_k2,
)


def _fc() -> Firecrawl:
    """Return a Firecrawl SDK client."""
    return Firecrawl(api_key=FIRECRAWL_API_KEY)


def _domain(site: str) -> str:
    """Strip scheme and trailing slash from a site entry so site: operators work."""
    return re.sub(r"^https?://", "", site).rstrip("/")


_DOMAIN_BRAND: dict[str, str] = {
    "lewkin.com": "Lewkin",
    "fashionnova.com": "Fashion Nova",
    "gap.com": "Gap",
    "amazon.com": "Amazon",
    "shein.com": "SHEIN",
    "ssense.com": "SSENSE",
    "therealreal.com": "The RealReal",
    "farfetch.com": "Farfetch",
    "nordstrom.com": "Nordstrom",
    "aritzia.com": "Aritzia",
    "revolve.com": "Revolve",
    "shopbop.com": "Shopbop",
    "net-a-porter.com": "Net-a-Porter",
}


def _brand_from_url(url: str) -> str | None:
    """Infer a display brand name from the product URL domain."""
    for domain, brand in _DOMAIN_BRAND.items():
        if domain in url:
            return brand
    return None


# Limit concurrent scrape+extract tasks so we don't hammer rate limits
_SCRAPE_SEMAPHORE = asyncio.Semaphore(15)


# ── Data model ────────────────────────────────────────────────────────────────

@dataclass
class SearchContext:
    vibe: str | None = None
    garment_type: str | None = None
    occasion: str | None = None
    colors: list[str] = field(default_factory=list)
    exclude_owned: list[str] = field(default_factory=list)
    max_price: float | None = None   # USD; None means no limit
    n_results: int = 15
    synthesized_query: str | None = None  # K2-written search query; overrides build_query()


# ── Query builder ─────────────────────────────────────────────────────────────

def build_query(ctx: SearchContext) -> str:
    parts: list[str] = []
    if ctx.garment_type:
        parts.append(ctx.garment_type)
    if ctx.vibe:
        parts.append(ctx.vibe)
    if ctx.occasion:
        parts.append(f"for {ctx.occasion}")
    if ctx.colors:
        parts.append(f"in {', '.join(ctx.colors)}")
    parts.append("women's fashion")
    return " ".join(parts)


# ── Firecrawl helpers ─────────────────────────────────────────────────────────

async def _search_one_site(query: str, site: str, per_site: int) -> list[str]:
    """Run one Firecrawl search scoped to a single site, return URLs."""
    scoped_query = f"{query} site:{_domain(site)}"
    loop = asyncio.get_running_loop()
    try:
        results = await loop.run_in_executor(
            None,
            lambda: _fc().search(scoped_query, limit=per_site),
        )
        web_results = getattr(results, "web", None) or []
        urls = [r.url for r in web_results if getattr(r, "url", None)]
        print(f"[web_search] {_domain(site)}: {len(urls)} URLs")
        return urls
    except Exception as exc:
        print(f"[web_search] search error for {_domain(site)}: {exc}")
        return []


async def _firecrawl_search(query: str, limit: int = 20) -> list[str]:
    """Search each trusted site separately and interleave results so every site is represented."""
    n_sites = len(TRUSTED_SITES)
    per_site = max(2, -(-limit // n_sites))  # ceiling division
    log_firecrawl_search(query, TRUSTED_SITES)

    tasks = [_search_one_site(query, site, per_site) for site in TRUSTED_SITES]
    per_site_results: list[list[str]] = await asyncio.gather(*tasks)

    # Interleave: take one URL from each site in round-robin order
    # so the final list alternates sites rather than being all-Amazon first
    seen: set[str] = set()
    interleaved: list[str] = []
    max_len = max((len(r) for r in per_site_results), default=0)
    for i in range(max_len):
        for site_urls in per_site_results:
            if i < len(site_urls):
                url = site_urls[i]
                if url not in seen:
                    seen.add(url)
                    interleaved.append(url)

    log_firecrawl_search_results(query, interleaved)
    return interleaved


async def _firecrawl_scrape(url: str) -> str | None:
    """Call Firecrawl scrape via SDK on a single URL, return Markdown text or None."""
    log_firecrawl_scrape(url)
    try:
        loop = asyncio.get_running_loop()
        result = await loop.run_in_executor(
            None,
            lambda: _fc().scrape(url, formats=["markdown"]),
        )
        markdown = getattr(result, "markdown", None)
        log_firecrawl_scrape_result(url, success=markdown is not None, markdown_len=len(markdown) if markdown else 0)
        return markdown
    except Exception as exc:
        print(f"[web_search] scrape error for {url}: {exc}")
        log_firecrawl_scrape_result(url, success=False)
        return None


# ── K2 extraction helpers ─────────────────────────────────────────────────────

_EXTRACTION_PROMPT = """\
Extract product details from the product page text below.
Return ONLY a JSON object with these exact fields (null if not found):
{
  "name": string or null,
  "brand": string or null,
  "price": number (USD, numeric only) or null,
  "description": string or null,
  "material_composition": string or null,
  "available_sizes": [string] or null,
  "image_url": string or null
}
image_url must be a full absolute URL to the main product image (starting with http).
description must be the actual product description text from the page, not a summary you invent.
Do not guess or hallucinate values. Return ONLY the JSON object, no markdown fences.

PAGE TEXT:
"""

_AUDIT_PROMPT = """\
Parse the material composition text for a garment and evaluate cotton content.
Return ONLY a JSON object (no markdown fences):
{
  "materials": [{"type": string, "percentage": number}],
  "meets_50pct_cotton": boolean,
  "reasoning": string
}

MATERIAL TEXT:
"""

_QUERY_SYNTHESIS_PROMPT = """\
You are a search query writer for a fashion e-commerce search engine.
Given signals about what the user wants, write a short, effective product search query (10 words max).
The query must be concrete and specific — it will be sent directly to a site search.
Do NOT include site names, URLs, or markdown. Return ONLY the query string, nothing else.

SIGNALS:
"""

_INTENT_PROMPT = """\
Extract fashion search intent from the user request below.
Return ONLY a JSON object (no markdown fences):
{
  "garment_type": string or null,
  "occasion": string or null,
  "colors": [string] or null,
  "vibe": string or null,
  "max_price": number or null
}
For max_price: extract a numeric USD budget limit if the user mentions one (e.g. "under $200", "less than 150", "budget of $300"). Return null if no budget is mentioned.

USER REQUEST:
"""


def _clean_json(raw: str) -> str:
    """Strip <think> blocks, markdown fences, and trailing commas from K2 output."""
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


async def _k2_json(prompt: str, max_tokens: int = 512, label: str = "k2") -> dict | None:
    """Call K2 Think V2 with a prompt, return parsed JSON dict or None."""
    payload = {
        "model": "MBZUAI-IFM/K2-Think-v2",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": max_tokens,
    }
    headers = {
        "Authorization": f"Bearer {K2_API_KEY}",
        "Content-Type": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=45.0) as client:
            resp = await client.post(
                f"{K2_BASE_URL}/chat/completions",
                headers=headers,
                json=payload,
            )
        resp.raise_for_status()
        raw = resp.json()["choices"][0]["message"]["content"].strip()
        cleaned = _clean_json(raw)
        parsed = json.loads(cleaned)
        log_web_search_k2(label, prompt, raw, parsed)
        return parsed
    except Exception as exc:
        print(f"[web_search] k2_json error ({label}): {exc}")
        log_web_search_k2(label, prompt, None, None, error=str(exc))
        return None


async def _extract_product_fields(markdown: str, url: str) -> dict | None:
    """Use K2 to extract structured product fields from scraped Markdown."""
    result = await _k2_json(
        _EXTRACTION_PROMPT + markdown[:8000],
        max_tokens=512,
        label=f"extract:{url}",
    )
    if result is None:
        return None
    result["product_url"] = url
    return result


async def _audit_material(material_text: str | None, url: str = "") -> dict | None:
    """Evaluate cotton percentage in a material composition string."""
    if not material_text:
        return None
    return await _k2_json(_AUDIT_PROMPT + material_text, max_tokens=256, label=f"audit:{url}")


# ── Per-URL pipeline ──────────────────────────────────────────────────────────

async def _process_url(url: str, idx: int) -> dict | None:
    """Scrape → extract → audit a single product URL. Returns product dict or None."""
    async with _SCRAPE_SEMAPHORE:
        markdown = await _firecrawl_scrape(url)
    if not markdown:
        return None

    product = await _extract_product_fields(markdown, url)
    if not product:
        return None

    product["material_audit"] = await _audit_material(product.get("material_composition"), url=url)
    product["id"] = f"p{idx:03d}"

    # Fall back to domain name when K2 couldn't find a brand on the page
    if not product.get("brand"):
        product["brand"] = _brand_from_url(url)

    # Aliases for frontend backward-compatibility
    if product.get("price") is not None:
        product["price_usd"] = product["price"]
    if product.get("product_url"):
        product["url"] = product["product_url"]

    return product


# ── Deduplication & ranking ───────────────────────────────────────────────────

def _deduplicate_rank(
    products: list[dict],
    exclude_owned: list[str],
    n_results: int,
    max_price: float | None = None,
) -> list[dict]:
    seen_urls: set[str] = set()
    seen_name_brand: set[tuple[str, str]] = set()
    result: list[dict] = []

    exclude_lower = [ex.lower() for ex in exclude_owned if ex]

    # Sort: complete products first, then by site trust
    def _sort_key(p: dict) -> tuple:
        has_nulls = any(p.get(f) is None for f in ("name", "price", "image_url"))
        return (int(has_nulls),)

    for p in sorted(products, key=_sort_key):
        url = p.get("product_url", "")
        name = (p.get("name") or "").lower().strip()
        brand = (p.get("brand") or "").lower().strip()
        nb_key = (name, brand)

        if url in seen_urls:
            continue
        if nb_key != ("", "") and nb_key in seen_name_brand:
            continue
        if any(ex in name for ex in exclude_lower):
            continue
        if max_price is not None and p.get("price") is not None:
            try:
                if float(p["price"]) > max_price:
                    continue
            except (TypeError, ValueError):
                pass

        seen_urls.add(url)
        seen_name_brand.add(nb_key)
        result.append(p)

        if len(result) >= n_results:
            break

    return result


# ── Public API ────────────────────────────────────────────────────────────────

async def get_products(ctx: SearchContext) -> list[dict]:
    """
    Main entry point. Returns up to ctx.n_results live product dicts.
    """
    query = ctx.synthesized_query or build_query(ctx)
    print(f"[web_search] query: {query!r}")

    # Step 1 — search
    urls = await _firecrawl_search(query, limit=ctx.n_results * 2)

    if not urls:
        # Retry with simplified query (drop color + occasion modifiers)
        print("[web_search] 0 results — retrying with simplified query")
        simple = SearchContext(vibe=ctx.vibe, garment_type=ctx.garment_type)
        simple_query = build_query(simple)
        urls = await _firecrawl_search(simple_query, limit=ctx.n_results * 2)

    if not urls:
        print("[web_search] still 0 results after retry — returning empty catalog")
        return []

    print(f"[web_search] {len(urls)} URLs from search")

    # Step 2–4 — scrape + extract + audit in parallel
    tasks = [_process_url(url, idx + 1) for idx, url in enumerate(urls)]
    raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    products: list[dict] = []
    for r in raw_results:
        if isinstance(r, dict):
            products.append(r)
        elif isinstance(r, Exception):
            print(f"[web_search] task error: {r}")

    print(f"[web_search] {len(products)} products extracted")
    if ctx.max_price is not None:
        print(f"[web_search] budget filter: max ${ctx.max_price}")

    # Step 5 — dedup + rank
    ranked = _deduplicate_rank(products, ctx.exclude_owned, ctx.n_results, ctx.max_price)
    print(f"[web_search] returning {len(ranked)} products")
    return ranked


async def build_search_context(
    user_request: str | None,
    parsed_image: dict | None,
    max_budget: float | None = None,
) -> SearchContext:
    """
    Build a SearchContext from available signals (image parse + STT transcript).
    K2 Think V2 is used for both structured intent extraction and final query synthesis.
    """
    ctx = SearchContext(max_price=max_budget)

    # ── Structured signals from image parse ───────────────────────────────────
    if parsed_image:
        ctx.vibe = parsed_image.get("vibe")
        if parsed_image.get("subject_type") == "garment":
            ctx.garment_type = parsed_image.get("garment_type")
            colors = parsed_image.get("colors")
            if isinstance(colors, list):
                ctx.colors = colors
            elif colors:
                ctx.colors = [colors]

    # ── Structured intent extraction from free text ───────────────────────────
    if user_request:
        extracted = await _k2_json(_INTENT_PROMPT + user_request, max_tokens=128, label="intent")
        if extracted:
            if not ctx.garment_type and extracted.get("garment_type"):
                ctx.garment_type = extracted["garment_type"]
            if not ctx.occasion and extracted.get("occasion"):
                ctx.occasion = extracted["occasion"]
            if not ctx.colors and extracted.get("colors"):
                ctx.colors = extracted["colors"]
            if not ctx.vibe and extracted.get("vibe"):
                ctx.vibe = extracted["vibe"]
            if ctx.max_price is None and extracted.get("max_price"):
                try:
                    ctx.max_price = float(extracted["max_price"])
                except (TypeError, ValueError):
                    pass

    # ── K2 query synthesis — combines both signals into one search string ─────
    signals: list[str] = []
    if user_request:
        signals.append(f"User request: {user_request}")
    if parsed_image:
        signals.append(f"Image analysis: {json.dumps(parsed_image)}")
    if ctx.max_price is not None:
        signals.append(f"Budget: under ${ctx.max_price}")

    if signals:
        synthesis_prompt = _QUERY_SYNTHESIS_PROMPT + "\n".join(signals)
        raw_query = await _k2_raw(synthesis_prompt, max_tokens=40, label="query_synthesis")
        if raw_query:
            ctx.synthesized_query = raw_query.strip().strip('"')
            print(f"[web_search] synthesized query: {ctx.synthesized_query!r}")
            sources = [s.split(":")[0] for s in signals]
            log_search_query(ctx.synthesized_query, sources)

    return ctx


async def _k2_raw(prompt: str, max_tokens: int = 64, label: str = "k2_raw") -> str | None:
    """Call K2 and return the raw text response (not JSON), with <think> stripped."""
    payload = {
        "model": "MBZUAI-IFM/K2-Think-v2",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.0,
        "max_tokens": max_tokens,
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
        # Strip <think> block if present
        if "</think>" in raw:
            _, raw = raw.split("</think>", 1)
        raw = raw.strip()
        log_web_search_k2(label, prompt, raw, None)
        return raw
    except Exception as exc:
        print(f"[web_search] k2_raw error ({label}): {exc}")
        log_web_search_k2(label, prompt, None, None, error=str(exc))
        return None
