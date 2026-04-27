"""
Manual smoke test for the Phase 3 review pipeline.

Usage:
    python test_review_pipeline.py
    python test_review_pipeline.py https://www.gap.com/products/some-item
    python test_review_pipeline.py https://www.gap.com/products/some-item --height "5'6" --top S --bottom 28 --build slim

Reads .env automatically via config.py.
"""

import argparse
import asyncio
import json
import sys

from reviews.review_crawler import crawl_product
from reviews.sizing_analyzer import analyze_sizing

# ── Default test URLs (one per site) ─────────────────────────────────────────

DEFAULT_URLS = [
    "https://www.gap.com/products/womens-high-rise-vintage-slim-jeans/7050490000",
    "https://www.fashionnova.com/products/high-waisted-distressed-jeans",
    "https://lewkin.com/products/long-sleeve-crop-top",
]

# ── Default user profile for sizing test ──────────────────────────────────────

DEFAULT_PROFILE = {
    "height": "5'6\"",
    "top_size": "M",
    "bottom_size": "28",
    "shoe_size": "8",
    "build": "slim",
}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print(f"{'─' * 60}")


def _print_review_data(rd: dict | None, url: str) -> None:
    if rd is None:
        print(f"  [CRAWLER] returned None for {url}")
        return

    print(f"  crawl_status:        {rd['crawl_status']}")
    print(f"  aggregate_rating:    {rd['aggregate_rating']}")
    print(f"  total_review_count:  {rd['total_review_count']}")
    print(f"  total_reviews_found: {rd['total_reviews_found']}")
    print(f"  sizing_sentiment:    {rd['sizing_sentiment']}")
    print(f"  top_sizing_complaints: {rd['top_sizing_complaints']}")
    print(f"  garment_measurements:  {rd['garment_measurements']}")
    print(f"  material_composition:  {rd['material_composition']}")

    sizing_reviews = [r for r in rd["reviews"] if r.get("mentions_sizing")]
    print(f"\n  Reviews mentioning sizing ({len(sizing_reviews)} / {rd['total_reviews_found']}):")
    for r in sizing_reviews[:5]:
        star = f"[{r['star_rating']}★] " if r.get("star_rating") else ""
        excerpt = (r.get("text") or "")[:120].replace("\n", " ")
        print(f"    {star}{excerpt}")

    if rd["total_reviews_found"] > 0:
        print(f"\n  First 3 reviews (raw):")
        for r in rd["reviews"][:3]:
            star = f"[{r['star_rating']}★] " if r.get("star_rating") else ""
            excerpt = (r.get("text") or "")[:150].replace("\n", " ")
            print(f"    {star}{excerpt}")


def _print_verdict(verdict: dict | None) -> None:
    if verdict is None:
        print("  [SIZING] skipped or failed — no verdict")
        return
    print(f"  recommended_size:  {verdict.get('recommended_size')}")
    print(f"  size_adjustment:   {verdict.get('size_adjustment')}")
    print(f"  fit_flags:         {verdict.get('fit_flags')}")
    print(f"  confidence:        {verdict.get('confidence')}")
    print(f"  confidence_reason: {verdict.get('confidence_reason')}")


# ── Main test runner ──────────────────────────────────────────────────────────

async def run_test(url: str, user_profile: dict, garment_type: str) -> None:
    _section(f"CRAWLING: {url}")
    print(f"  (this opens a Firecrawl interact session — ~11 credits)")

    review_data = await crawl_product(url)
    _print_review_data(review_data, url)

    _section(f"SIZING ANALYSIS: {url}")
    has_profile = any(v for v in user_profile.values())
    if not has_profile:
        print("  No user profile provided — skipping sizing analysis.")
        print("  Pass --height / --top / --bottom / --build to test sizing.")
        return

    print(f"  User profile: {user_profile}")
    print(f"  Garment type: {garment_type}")
    verdict = await analyze_sizing(
        review_data=review_data,
        user_profile=user_profile,
        garment_type=garment_type,
        product_url=url,
    )
    _print_verdict(verdict)

    _section("FULL JSON OUTPUT")
    output = {
        "url": url,
        "review_data": review_data,
        "sizing_verdict": verdict,
    }
    print(json.dumps(output, indent=2, default=str))


async def main() -> None:
    parser = argparse.ArgumentParser(description="Test the Phase 3 review pipeline")
    parser.add_argument("url", nargs="?", default=None, help="Product URL to test (default: runs all DEFAULT_URLS)")
    parser.add_argument("--height",  default=DEFAULT_PROFILE["height"],    help='e.g. "5\'6\\"" or "168cm"')
    parser.add_argument("--top",     default=DEFAULT_PROFILE["top_size"],  help='US top size e.g. S, M, L, 8')
    parser.add_argument("--bottom",  default=DEFAULT_PROFILE["bottom_size"], help='US bottom size e.g. 28, M')
    parser.add_argument("--shoe",    default=DEFAULT_PROFILE["shoe_size"], help='US shoe size e.g. 8.5')
    parser.add_argument("--build",   default=DEFAULT_PROFILE["build"],     help='e.g. slim, athletic, curvy')
    parser.add_argument("--garment", default="tops",                      help='Garment type for sizing prompt')
    parser.add_argument("--no-profile", action="store_true",               help="Skip sizing analysis even if defaults are set")
    args = parser.parse_args()

    user_profile = {} if args.no_profile else {
        "height":      args.height,
        "top_size":    args.top,
        "bottom_size": args.bottom,
        "shoe_size":   args.shoe,
        "build":       args.build,
    }

    urls = [args.url] if args.url else DEFAULT_URLS

    for url in urls:
        await run_test(url, user_profile, args.garment)
        if len(urls) > 1:
            print("\n\n")


if __name__ == "__main__":
    asyncio.run(main())
