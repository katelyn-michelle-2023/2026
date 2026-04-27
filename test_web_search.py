"""
Manual smoke test for search/web_search.py.
Run with:  python test_web_search.py
Reads .env automatically via config.py.

Sites searched: lewkin.com, fashionnova.com, gap.com, amazon.com, m.shein.com/us
Extraction: K2 Think V2 (no Gemini)
"""
import asyncio
import json

from search.web_search import SearchContext, build_search_context, get_products


async def test_direct_context():
    """Hardcoded SearchContext — fastest way to check the full pipeline."""
    print("\n=== test_direct_context ===")
    ctx = SearchContext(
        garment_type="jeans",
        vibe="Y2K",
        n_results=3,
    )
    products = await get_products(ctx)
    print(f"\nGot {len(products)} products")
    for p in products:
        print(f"  [{p['id']}] {p.get('brand', '?')} — {p.get('name', '?')} — ${p.get('price', '?')}")
        print(f"         url:   {p.get('product_url', '?')}")
        print(f"         image: {p.get('image_url', '?')}")
        desc = (p.get('description') or '')[:120]
        print(f"         desc:  {desc}{'...' if len(p.get('description') or '') > 120 else ''}")
    if products:
        print("\n── Full first product ──")
        print(json.dumps(products[0], indent=2, default=str))


async def test_with_budget():
    """Same as above but with a budget cap."""
    print("\n=== test_with_budget ($40 max) ===")
    ctx = SearchContext(
        garment_type="dress",
        vibe="coquette",
        max_price=40.0,
        n_results=3,
    )
    products = await get_products(ctx)
    print(f"Got {len(products)} products (all should be <= $40)")
    for p in products:
        print(f"  [{p['id']}] {p.get('name', '?')} — ${p.get('price', '?')} — {p.get('product_url', '?')}")


async def test_from_text():
    """Simulates a voice note: K2 extracts intent, then searches."""
    print("\n=== test_from_text ===")
    ctx = await build_search_context(
        user_request="I want something cute for a party, maybe a mini skirt or bodycon dress, under $60",
        parsed_image=None,
    )
    print(f"  garment_type: {ctx.garment_type}")
    print(f"  vibe:         {ctx.vibe}")
    print(f"  occasion:     {ctx.occasion}")
    print(f"  colors:       {ctx.colors}")
    print(f"  max_price:    {ctx.max_price}")
    ctx.n_results = 3
    products = await get_products(ctx)
    print(f"Got {len(products)} products")
    for p in products:
        print(f"  [{p['id']}] {p.get('name', '?')} — ${p.get('price', '?')} — {p.get('image_url', '?')}")


if __name__ == "__main__":
    # ── Pick which test to run ────────────────────────────────────────────────
    asyncio.run(test_direct_context())
    # asyncio.run(test_with_budget())
    # asyncio.run(test_from_text())
