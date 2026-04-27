"""
Shared structured logger for Aura.
Appends NDJSON entries to logs/aura.log so every API call is auditable.
"""

import json
import os
from datetime import datetime, timezone
from pathlib import Path

LOG_DIR = Path(__file__).parent / "logs"
LOG_FILE = LOG_DIR / "aura.log"


def _write(entry: dict) -> None:
    LOG_DIR.mkdir(exist_ok=True)
    entry["ts"] = datetime.now(timezone.utc).isoformat()
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def log_chat_start(session_id: str) -> None:
    _write({
        "event": "chat_start",
        "session_id": session_id,
    })


def log_gemini_request(image_size_bytes: int, prompt: str) -> None:
    _write({
        "event": "gemini_request",
        "image_bytes": image_size_bytes,
        "prompt": prompt,
    })


def log_gemini_response(raw_text: str, parsed: dict) -> None:
    _write({
        "event": "gemini_response",
        "raw_text": raw_text,
        "parsed": parsed,
    })


def log_k2_request(user_message: str, system_prompt: str) -> None:
    _write({
        "event": "k2_request",
        "system_prompt": system_prompt,
        "user_message": user_message,
    })


def log_k2_thinking(think_content: str) -> None:
    _write({
        "event": "k2_thinking",
        "content": think_content,
    })


def log_k2_response(raw_text: str, result: dict) -> None:
    _write({
        "event": "k2_response",
        "raw_text": raw_text,
        "result": result,
    })


def log_firecrawl_search(query: str, trusted_sites: list[str]) -> None:
    _write({
        "event": "firecrawl_search_request",
        "query": query,
        "trusted_sites": trusted_sites,
    })


def log_firecrawl_search_results(query: str, urls: list[str]) -> None:
    _write({
        "event": "firecrawl_search_results",
        "query": query,
        "n_urls": len(urls),
        "urls": urls,
    })


def log_firecrawl_scrape(url: str) -> None:
    _write({
        "event": "firecrawl_scrape_request",
        "url": url,
    })


def log_firecrawl_scrape_result(url: str, success: bool, markdown_len: int | None = None) -> None:
    _write({
        "event": "firecrawl_scrape_result",
        "url": url,
        "success": success,
        "markdown_len": markdown_len,
    })


def log_search_query(query: str, sources: list[str]) -> None:
    _write({
        "event": "search_query_synthesized",
        "query": query,
        "sources": sources,
    })


def log_web_search_k2(label: str, prompt: str, raw_output: str | None, parsed: dict | None, error: str | None = None) -> None:
    _write({
        "event": "web_search_k2",
        "label": label,
        "prompt": prompt,
        "raw_output": raw_output,
        "parsed": parsed,
        "error": error,
    })


# ── Review crawler ─────────────────────────────────────────────────────────────

def log_review_crawl_start(product_url: str) -> None:
    _write({
        "event": "review_crawl_start",
        "product_url": product_url,
    })


def log_review_crawl_scrape(product_url: str, scrape_id: str | None, markdown_len: int) -> None:
    _write({
        "event": "review_crawl_scrape",
        "product_url": product_url,
        "scrape_id": scrape_id,
        "markdown_len": markdown_len,
    })


def log_review_crawl_interact(
    product_url: str,
    call_num: int,
    raw_output: str | None = None,
    note: str | None = None,
) -> None:
    _write({
        "event": "review_crawl_interact",
        "product_url": product_url,
        "call_num": call_num,
        "raw_output_len": len(raw_output) if raw_output else 0,
        "raw_output": raw_output,
        "note": note,
    })


def log_review_crawl_result(product_url: str, result: dict) -> None:
    _write({
        "event": "review_crawl_result",
        "product_url": product_url,
        "crawl_status": result.get("crawl_status"),
        "aggregate_rating": result.get("aggregate_rating"),
        "total_review_count": result.get("total_review_count"),
        "total_reviews_found": result.get("total_reviews_found"),
        "sizing_sentiment": result.get("sizing_sentiment"),
        "top_sizing_complaints": result.get("top_sizing_complaints"),
        "garment_measurements": result.get("garment_measurements"),
        "material_composition": result.get("material_composition"),
        "review_summary": result.get("review_summary"),
        "reviews": result.get("reviews"),
    })


def log_review_crawl_error(product_url: str, error_type: str, detail: str) -> None:
    _write({
        "event": "review_crawl_error",
        "product_url": product_url,
        "error_type": error_type,
        "detail": detail,
    })


# ── Sizing analyzer ────────────────────────────────────────────────────────────

def log_sizing_analyzer_skip(product_url: str, reason: str) -> None:
    _write({
        "event": "sizing_analyzer_skip",
        "product_url": product_url,
        "reason": reason,
    })


def log_sizing_analyzer_request(product_url: str, user_message: str) -> None:
    _write({
        "event": "sizing_analyzer_request",
        "product_url": product_url,
        "user_message": user_message,
    })


def log_sizing_analyzer_result(
    product_url: str,
    raw: str | None,
    verdict: dict | None,
    error: str | None = None,
) -> None:
    _write({
        "event": "sizing_analyzer_result",
        "product_url": product_url,
        "raw": raw,
        "verdict": verdict,
        "error": error,
    })


# ── Final stylist ──────────────────────────────────────────────────────────────

def log_final_picks_request(user_message: str, system_prompt: str) -> None:
    _write({
        "event": "final_picks_request",
        "system_prompt": system_prompt,
        "user_message": user_message,
    })


def log_final_picks_response(raw_text: str, result: dict) -> None:
    _write({
        "event": "final_picks_response",
        "raw_text": raw_text,
        "result": result,
    })
