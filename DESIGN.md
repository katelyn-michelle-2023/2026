Aura — Phase 2 Design Doc
# Aura — Design Doc (Phases 1–3)

The Core Loop



What Is Aura?

Aura is an AI-powered personal stylist. A user opens the Aura website, takes a photo of themselves (or a garment) with the in-browser camera, and records a voice note describing what they need. Aura responds like a bestie — fast, opinionated, Gen-Z energy — with curated outfit recommendations delivered as a voice note that plays back in the browser, alongside a grid of the picks.

Phase 2 adds Knot integration: Aura now pulls the user's real purchase history via TransactionLink to personalize recommendations, autonomously purchases the selected items via AgenticShopping, and can surface and cancel irrelevant clothing subscriptions via SubManager.

Persona: Aura is a D1 Yapper. She doesn't just find clothes — she narrates an arc. She uses Gen-Z slang naturally but is secretly a genius at fabric composition and silhouette theory. Her ElevenLabs voice should sound like a hype bestie, not a customer service rep.

---

## Goal

One working end-to-end flow. User records a voice note and captures a photo in the browser. The backend transcribes the audio, parses the image, reasons over a hardcoded catalog, and returns a voice note with 3 recommendations in Aura's persona that the browser plays back.

---

## Tech Stack

| Layer                  | Tool                                         |
| ---------------------- | -------------------------------------------- |
| Frontend               | Plain HTML + JS (camera + MediaRecorder)     |
| Backend                | FastAPI (Python)                             |
| Speech-to-text         | ElevenLabs STT                               |
| Image & vision parsing | Gemini multimodal (`gemini-3-flash-preview`) |
| Reasoning engine       | K2 Think V2                                  |
| Voice output           | ElevenLabs TTS                               |
| Product discovery      | Firecrawl search + scrape                    |
| Review crawling        | Firecrawl interact (browser sessions)        |

---

## File Structure

```
├── main.py                      # FastAPI app — /chat endpoint + orchestration
├── config.py                    # API keys + feature flags (TO_REVIEW, TRUSTED_SITES)
├── logger.py                    # Shared NDJSON logger → logs/aura.log
├── static/
│   └── index.html               # Camera + mic capture + audio playback
├── stt/
│   └── transcribe.py            # ElevenLabs STT
├── vision/
│   └── gemini_parser.py         # Gemini multimodal image parser
├── reasoning/
│   └── k2_stylist.py            # Phase 1: get_picks() / Phase 3: get_final_picks()
├── tts/
│   └── elevenlabs_tts.py        # ElevenLabs TTS
├── catalog/
│   └── hardcoded.py             # Legacy static catalog (not used in live flow)
├── search/
│   └── web_search.py            # Phase 2: Firecrawl search + scrape + K2 extraction
├── reviews/
│   ├── review_crawler.py        # Phase 3: Firecrawl interact review crawler
│   └── sizing_analyzer.py      # Phase 3: K2 sizing verdict engine
└── logs/
    └── aura.log                 # NDJSON audit log of all API calls
```

---

## Module Specs

### config.py

Stores all API keys and constants loaded from environment variables. Keys needed: ElevenLabs API key, ElevenLabs Voice ID, Gemini API key, K2 API key and base URL, Knot API key.
Stores all API keys and constants loaded from environment variables.

| Variable              | Description                                                                                      |
| --------------------- | ------------------------------------------------------------------------------------------------ |
| `ELEVENLABS_API_KEY`  | ElevenLabs API key                                                                               |
| `ELEVENLABS_VOICE_ID` | ElevenLabs voice ID for Aura                                                                     |
| `GEMINI_API_KEY`      | Google Gemini API key (vision + K2 JSON fallback)                                                |
| `K2_API_KEY`          | K2 Think V2 API key                                                                              |
| `K2_BASE_URL`         | K2 base URL (default: `https://api.k2think.ai/v1`)                                               |
| `FIRECRAWL_API_KEY`   | Firecrawl API key (search, scrape, interact)                                                     |
| `TRUSTED_SITES`       | Comma-separated e-commerce domains to search (default: ssense, therealreal, farfetch, nordstrom) |
| `TO_REVIEW`           | `true` to enable Phase 3 review pipeline; `false`/missing to skip (default off)                  |
| `AUDIO_OUTPUT_DIR`    | Directory for generated TTS audio files                                                          |



catalog/hardcoded.py

A static list of 15–20 clothing items. Each item must have: a unique ID, name, brand, price in USD, product URL, a list of vibe tags (e.g. "clean girl," "dark academia," "Y2K," "coquette," "streetwear"), garment type, color list, material description, and an image URL. Cover a wide range of vibes and garment types so K2 has real variety to reason over.

For Phase 2, prioritize items available on Amazon, as Knot's AgenticShopping and TransactionLink have confirmed Amazon support. Include the Amazon ASIN or product URL for any catalog items that map to Amazon listings so AgenticShopping can execute the purchase directly.



static/index.html (frontend)

A single-page browser UI that handles capture, playback, and purchase confirmation. Key responsibilities:

Camera capture. Uses navigator.mediaDevices.getUserMedia({ video: true }) to stream the camera into a <video> element. A "Take Photo" button draws the current video frame onto a hidden <canvas> and exports it as a JPEG blob.

Voice recording. Uses navigator.mediaDevices.getUserMedia({ audio: true }) + MediaRecorder to capture the user's voice note. Start/stop buttons control the recording; the resulting audio is stored as a webm/opus blob.

Knot auth flow. On first load, renders a "Connect your accounts" step that initializes the Knot Link UI (CardSwitcher/TransactionLink auth). Once connected, the user's Knot access token is stored in memory for the session.

Submission. "Send to Aura" button POSTs a single multipart/form-data request to /chat with the photo blob, the audio blob, and the Knot access token.

Response playback. Receives a JSON body with picks metadata, an audio URL (or base64 .mp3), and a purchase_status field from the backend. Pipes the audio into an <audio> element and autoplays, renders the 3 picks as a product grid (image, name, price, product link), and shows a purchase confirmation card per pick if AgenticShopping executed ("Aura already copped this for you ✓").

Purchase confirmation gate. Before calling /chat, render a "Aura is about to cop these for you — confirm?" modal showing the 3 picks and total cost. User must explicitly confirm before AgenticShopping executes. This prevents accidental purchases during demos.

SubManager prompt. If the backend returns active_subscriptions, render a dismissable banner listing them with a one-tap cancel button per subscription.

No framework required — keep it one HTML file so deploy is trivial.



main.py (FastAPI server)

Serves the static frontend at / and exposes a /chat endpoint and a /cancel-subscription endpoint. Key responsibilities:

Routing. POST /chat accepts multipart/form-data with optional fields: audio (a blob — voice note), image (a blob — photo from camera), text (a plain string, used only for debugging/fallback), and knot_token (the user's Knot session token from the frontend).

Orchestration.

If audio is present → pass to stt/transcribe.py → transcript string

If image is present → pass to vision/gemini_parser.py → parsed JSON

If text is present → treat directly as the user request

If knot_token is present → pass to knot/transaction_link.py → purchase history JSON

Combine transcript + parsed image JSON + text + purchase history into one context object

Reasoning + TTS. Pass the enriched context + hardcoded catalog to reasoning/k2_stylist.py. Take the returned aura_script and pass to tts/elevenlabs_tts.py.

AgenticShopping. After picks are returned by K2, pass each pick's product identifier + knot_token to knot/agentic_shopping.py to execute autonomous purchase. Collect purchase_status per item.

SubManager (optional). If knot_token is present, call knot/sub_manager.py to fetch active clothing-related subscriptions and include them in the response.

Response. Return a JSON body containing the picks metadata, a URL (or base64) for the generated .mp3, purchase_status per pick, and optionally active_subscriptions.

DELETE /cancel-subscription accepts a cancellation action token and knot_token, calls sub_manager.py to cancel the subscription, and returns a success/failure status.



stt/transcribe.py

Accepts an audio file. Sends it to the ElevenLabs Speech-to-Text API. Returns a plain text transcript string. This becomes the user's stated request — e.g. "I have a presentation tomorrow and I need something that says powerful but not try-hard."



vision/gemini_parser.py

Accepts an image file. Sends it to Gemini multimodal. Instructs Gemini to return a structured JSON.

If the photo is of a garment or outfit, return:

garment_type — what kind of item it is (e.g. "oversized blazer")

colors — list of detected colors

material_inference — likely fabric based on texture/drape in the image

styling_cues — accessories, silhouette, how it's worn

vibe — inferred aesthetic (e.g. "quiet luxury," "Y2K")

If the photo is of the user themselves, return:

build — general body proportions the user is working with

coloring — skin tone, hair color, visible undertones

current_style_cues — what they're already wearing, visible accessories

vibe — aesthetic they seem to be going for

A subject_type field on the response ("garment" or "self") tells the reasoning module which branch it got.

Return this JSON to the caller.

---

### reasoning/k2_stylist.py

Contains two K2 calls:

**`get_picks()`** — Phase 1 initial pick. Accepts user context (transcript + parsed image) and the full live catalog. K2 selects **6 candidates** with justifications in Aura's voice and an `aura_script` for TTS.

**`get_final_picks()`** — Phase 3 final pick (only runs if `TO_REVIEW=true`). Accepts the same 6 products now enriched with sizing verdicts. K2 rewrites justifications and the `aura_script` to weave in sizing commentary — e.g. "size up", "runs short for your height", star rating callouts. Products with no verdict get normal treatment; products with `size_adjustment: none` and no `fit_flags` skip sizing mention entirely.

Output format for both: `{ picks: [{id, justification}], aura_script: "..." }`

The user's purchase history JSON from TransactionLink if available, formatted as a concise summary of past items, brands, price points, and inferred sizing



tts/elevenlabs_tts.py

Accepts the `aura_script` string returned by K2. Sends it to the ElevenLabs Text-to-Speech API using the configured Voice ID. Returns a path to the generated .mp3 file (or a URL the frontend can GET). This file is played back in the browser via an `<audio>` element.

---

## Data Flow

```
POST /chat (multipart/form-data)
  Fields: audio?, image?, text?, max_budget?,
          height?, top_size?, bottom_size?, shoe_size?, build?

  ├── [audio]  → ElevenLabs STT → transcript
  ├── [image]  → Gemini multimodal → parsed image JSON
  │
  ├── build_search_context()
  │     └── K2 extracts intent: garment_type, vibe, occasion, colors, max_price
  │
  ├── get_products()  [search/web_search.py]
  │     ├── Firecrawl search per trusted site → URLs  (parallel per site)
  │     ├── Firecrawl scrape each URL → Markdown      (parallel, semaphore 15)
  │     ├── K2 extract product fields per URL          (parallel)
  │     ├── K2 material audit per URL                  (parallel)
  │     └── dedup + rank → catalog (~15 products)
  │
  ├── get_picks()  [k2_stylist.py]
  │     └── K2 selects 6 candidates → { picks, aura_script }
  │
  │   ── if TO_REVIEW=true ──────────────────────────────────────────────
  │
  ├── crawl_products_parallel()  [reviews/review_crawler.py]
  │     └── per product (all 6 in parallel):
  │           ├── Firecrawl scrape → scrape_id
  │           │     └── parse aggregate_rating + review_count (free)
  │           │     └── [Amazon] CAPTCHA check → null if blocked
  │           ├── Call A: click reviews tab (wait for load)
  │           ├── Call B: extract reviews → JSON array
  │           │     └── [0 results] → Call C: load more → re-extract
  │           ├── Call D: click details/size tab
  │           ├── Call E: extract measurements + material
  │           ├── K2: synthesize 2-3 sentence review_summary
  │           ├── [K2 fallback] for any non-JSON interact output
  │           ├── compute sizing_sentiment + top_sizing_complaints
  │           └── DELETE session (always, finally block)
  │                 → ReviewData or null
  │
  ├── analyze_sizing_parallel()  [reviews/sizing_analyzer.py]
  │     └── per product (all 6 in parallel):
  │           ├── [null/blocked/failed] → skip
  │           └── K2 Think V2 → { recommended_size, size_adjustment,
  │                                fit_flags, confidence, confidence_reason }
  │
  ├── get_final_picks()  [k2_stylist.py]
  │     └── K2 with products + sizing verdicts inline
  │           → { picks, aura_script } with sizing woven in
  │
  │   ─────────────────────────────────────────────────────────────────
  │
  ├── ElevenLabs TTS → audio.mp3
  │
  └── JSON response:
        picks: [{ id, name, brand, price_usd, url, image_url, justification,
                  recommended_size?, size_adjustment?, fit_flags?, sizing_confidence? }]
        audio_url: "/audio/<file>"
        transcript: "..."
```

---

## Phase 2 — Live Product Discovery (search/web_search.py)

Replaces the hardcoded catalog with real-time Firecrawl-powered product search.

**`build_search_context()`** — K2 extracts structured intent from the user request: `garment_type`, `vibe`, `occasion`, `colors`, `max_price`. Returns a `SearchContext` dataclass.

**`get_products()`** — main entry point:

1. Search each trusted site in parallel using Firecrawl's search API scoped to `site:<domain>`. Results are interleaved (round-robin per site) so every site is represented.
2. Scrape each URL in parallel (semaphore 15) → Markdown.
3. K2 extracts structured product fields from each Markdown: `name`, `brand`, `price`, `description`, `material_composition`, `available_sizes`, `image_url`.
4. K2 audits material composition for cotton percentage.
5. Deduplicate + filter by price cap + rank → top ~15 products passed to `get_picks()`.

Trusted sites are configured via the `TRUSTED_SITES` env var (comma-separated domains).

---

## Phase 3 — Review Intelligence (reviews/)

Gated by `TO_REVIEW=true`. Runs after `get_picks()` selects 6 candidates, before TTS.

### review_crawler.py

Opens a Firecrawl browser session per product and runs up to 5 interact calls:

| Call | Task                                                     | On failure       |
| ---- | -------------------------------------------------------- | ---------------- |
| A    | Click reviews tab, wait for load                         | Continue         |
| B    | Extract reviews as JSON array                            | `partial` status |
| C    | Click load more → re-extract _(only if B got 0 reviews)_ | Continue         |
| D    | Click details/size/fabric tab                            | Continue         |
| E    | Extract measurements + material as JSON                  | Fields stay null |

After interact calls:

- K2 synthesizes a `review_summary` (2-3 sentences, plain English) from extracted reviews
- `sizing_sentiment` computed from reviews mentioning sizing keywords: `"positive"` / `"negative"` / `"mixed"` / `"insufficient_data"` (only if zero sizing reviews)
- `top_sizing_complaints` — up to 5 most-mentioned sizing phrases verbatim
- Session always closed in `finally` block; DELETE failure is logged, never re-thrown

**ReviewData output fields:**

```
product_url, aggregate_rating, total_review_count,
reviews, total_reviews_found, review_summary,
sizing_sentiment, top_sizing_complaints,
garment_measurements, material_composition,
crawl_status: "success" | "partial" | "no_reviews" | "blocked" | "failed"
```

**Non-JSON interact output** → K2 Think V2 fallback (thinking block stripped before parse).

**Amazon**: CAPTCHA detected in initial Markdown → `crawl_status: "blocked"`, return null, no interact calls.

### sizing_analyzer.py

Skips products with `crawl_status: "blocked"` or `"failed"` (or null crawl). Runs K2 Think V2 (max 400 tokens) with:

- User profile: height, top size, bottom size, shoe size, build
- Garment type + listed measurements + material
- Aggregate rating + review count (trust signal)
- Sizing sentiment + top complaints
- Up to 15 sizing review excerpts

**Confidence rules baked into prompt:**

- `"high"` — 10+ reviews mention sizing, mostly agree
- `"medium"` — 5–9 sizing reviews OR significant disagreement
- `"low"` — <5 sizing reviews, no measurements, or partial/no_reviews crawl

**Zero sizing reviews + no_reviews/partial crawl** → forces `size_adjustment: none`, `confidence: low`.
**1–4 sizing reviews** → K2 reasons from what exists, stays `confidence: low`, explains uncertainty.

**SizingVerdict output fields:**

```
recommended_size, size_adjustment: "up"|"down"|"none",
fit_flags, confidence: "high"|"medium"|"low", confidence_reason
```

---

## /chat Endpoint — All Form Fields

| Field         | Type   | Required     | Description                             |
| ------------- | ------ | ------------ | --------------------------------------- |
| `audio`       | file   | one of these | Voice note (webm/opus)                  |
| `image`       | file   | one of these | Photo from camera (JPEG)                |
| `text`        | string | one of these | Plain text fallback                     |
| `max_budget`  | float  | no           | Max price in USD                        |
| `height`      | string | no           | e.g. `"5'6"` or `"168cm"`               |
| `top_size`    | string | no           | US top size e.g. `"S"`, `"M"`, `"8"`    |
| `bottom_size` | string | no           | US bottom/waist size e.g. `"28"`, `"M"` |
| `shoe_size`   | string | no           | US shoe size e.g. `"8.5"`               |
| `build`       | string | no           | e.g. `"slim"`, `"athletic"`, `"curvy"`  |

Sizing fields are all optional. If none are provided, review crawling still runs (for star rating trust signals) but sizing analysis and sizing commentary are skipped.

---

## Logging

All API calls are appended as NDJSON to `logs/aura.log`. Events logged:

| Event                                                   | When                                   |
| ------------------------------------------------------- | -------------------------------------- |
| `gemini_request` / `gemini_response`                    | Vision parse                           |
| `k2_request` / `k2_response` / `k2_thinking`            | Initial picks                          |
| `search_query_synthesized`                              | Intent extraction                      |
| `firecrawl_search_request` / `firecrawl_search_results` | Product search                         |
| `firecrawl_scrape_request` / `firecrawl_scrape_result`  | Product scrape                         |
| `web_search_k2`                                         | Per-URL K2 extraction + material audit |
| `review_crawl_start` / `review_crawl_scrape`            | Per-product crawl                      |
| `review_crawl_interact`                                 | Each interact call (full raw output)   |
| `review_crawl_result`                                   | Full ReviewData including all reviews  |
| `review_crawl_error`                                    | Any failure with type + detail         |
| `sizing_analyzer_skip`                                  | When crawl was null/blocked/failed     |
| `sizing_analyzer_request` / `sizing_analyzer_result`    | K2 sizing verdict                      |
| `final_picks_request` / `final_picks_response`          | Phase 3 final K2 call                  |

---

## Checklist

**Phase 1**

- [ ] Browser captures photo from webcam and displays a preview
- [ ] Browser records a voice note via MediaRecorder with stop/playback controls
- [ ] `POST /chat` accepts audio + image and logs both payloads correctly
- [ ] STT correctly transcribes a voice note into text
- [ ] Gemini correctly parses an image (garment OR self) into the expected JSON structure
- [ ] K2 returns 6 picks with Aura's script in her voice
- [ ] ElevenLabs generates an .mp3 from the script
- [ ] Browser receives the response, plays the .mp3, and renders the picks
- [ ] Full loop tested end-to-end at least 3 times with different types of input

**Phase 2**

- [ ] Firecrawl search returns URLs from each trusted site
- [ ] Scrape + K2 extraction produces valid product dicts (name, price, image_url)
- [ ] Material audit correctly flags cotton percentage
- [ ] Dedup removes duplicate URLs and name/brand combos
- [ ] Price cap filters work correctly
- [ ] `build_search_context()` correctly extracts intent from varied user requests

**Phase 3**

- [ ] `TO_REVIEW=true` enables the pipeline; `false`/missing skips it cleanly
- [ ] Firecrawl scrape returns a `scrape_id` for all 5 trusted sites
- [ ] Call A correctly clicks a reviews tab on Fashion Nova, Gap, Lewkin
- [ ] Call B extracts review JSON with `text`, `star_rating`, `mentions_sizing`
- [ ] Call C (load more) only fires when Call B returns 0 reviews
- [ ] Call E extracts measurements and material (or null) correctly
- [ ] `review_summary` is a coherent 2-3 sentence summary of review sentiment
- [ ] Amazon CAPTCHA detection sets `crawl_status: "blocked"` and returns null
- [ ] K2 fallback correctly extracts JSON from malformed interact output
- [ ] Session DELETE always runs in finally block; failure is logged not thrown
- [ ] `sizing_sentiment` computes correctly from 1+ sizing reviews
- [ ] `sizing_analyzer` skips blocked/failed crawls
- [ ] K2 sizing verdict includes `recommended_size`, `size_adjustment`, `fit_flags`
- [ ] Low-confidence verdict explains uncertainty without refusing to recommend
- [ ] `get_final_picks()` weaves sizing into Aura's script naturally
- [ ] All 6 crawls run in parallel; one failure doesn't delay others

---

## Notes

- **HTTPS requirement.** `getUserMedia` only works over HTTPS (or `localhost`). For a remote demo, deploy behind HTTPS — Render, Fly, or ngrok all work.
- **Audio format.** MediaRecorder defaults to webm/opus in Chrome. Confirm ElevenLabs STT accepts webm; if not, transcode server-side with ffmpeg or record as WAV via a small polyfill.
- **CORS.** Keep the frontend and backend on the same origin (FastAPI serving `static/`) to avoid CORS entirely. If you split them, enable `fastapi.middleware.cors.CORSMiddleware`.
