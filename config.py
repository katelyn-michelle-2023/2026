import os
from dotenv import load_dotenv

load_dotenv()

# ElevenLabs
ELEVENLABS_API_KEY: str = os.environ["ELEVENLABS_API_KEY"]
ELEVENLABS_VOICE_ID: str = os.environ["ELEVENLABS_VOICE_ID"]

# Google Gemini (used by vision/gemini_parser.py)
GEMINI_API_KEY: str = os.environ["GEMINI_API_KEY"]

# K2 (Think V2)
K2_API_KEY: str = os.environ["K2_API_KEY"]
K2_BASE_URL: str = os.environ.get("K2_BASE_URL", "https://api.k2think.ai/v1")

# Knot
KNOT_CLIENT_ID: str = os.environ.get("KNOT_CLIENT_ID", "")
KNOT_SECRET: str = os.environ.get("KNOT_SECRET", "")
KNOT_ENV: str = os.environ.get("KNOT_ENV", "development")
KNOT_BASE_URL: str = f"https://{KNOT_ENV}.knotapi.com"
# Amazon merchant ID in Knot — verify in dashboard; 46 is the Knot example value
KNOT_AMAZON_MERCHANT_ID: int = int(os.environ.get("KNOT_AMAZON_MERCHANT_ID", "46"))
# Firecrawl
FIRECRAWL_API_KEY: str = os.environ["FIRECRAWL_API_KEY"]

# Trusted e-commerce sites for product search.
# Override via comma-separated TRUSTED_SITES env var; keep to 3-4 for demo speed.
TRUSTED_SITES: list[str] = os.environ.get(
    "TRUSTED_SITES",
    "ssense.com,therealreal.com,farfetch.com,nordstrom.com",
).split(",")

# Phase 3 review pipeline toggle.
# Set TO_REVIEW=true to enable review crawling + sizing analysis.
# Defaults to disabled (false / missing) because it adds significant latency.
TO_REVIEW: bool = os.environ.get("TO_REVIEW", "false").strip().lower() == "true"

# Misc
AUDIO_OUTPUT_DIR: str = os.environ.get("AUDIO_OUTPUT_DIR", "/tmp/aura_audio")
