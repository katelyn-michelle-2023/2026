"""
Image parsing via Gemini multimodal.
Accepts raw image bytes (JPEG).
Returns a structured dict describing the garment or the person.
"""

import json
import re

from google import genai
from google.genai import types

from config import GEMINI_API_KEY
from logger import log_gemini_request, log_gemini_response

SYSTEM_PROMPT = """
You are a fashion vision AI. Analyze the provided image and return a JSON object.

Determine whether the photo shows:
  (A) A garment or outfit (clothing item, flat-lay, outfit photo), OR
  (B) A person (selfie, full-body, mirror photo).

For (A) — garment/outfit — return exactly this JSON shape:
{
  "subject_type": "garment",
  "garment_type": "<e.g. oversized blazer>",
  "colors": ["<color1>", "<color2>"],
  "material_inference": "<likely fabric based on texture/drape>",
  "styling_cues": "<accessories, silhouette, how it's worn>",
  "vibe": "<inferred aesthetic, e.g. quiet luxury, Y2K, coquette>"
}

For (B) — person — return exactly this JSON shape:
{
  "subject_type": "self",
  "build": "<general body proportions>",
  "coloring": "<skin tone, hair color, visible undertones>",
  "current_style_cues": "<what they're wearing, visible accessories>",
  "vibe": "<aesthetic they seem to be going for>"
}

Return ONLY valid JSON. No markdown fences, no explanation.
""".strip()


async def parse_image(image_bytes: bytes) -> dict:
    """
    Send image bytes to Gemini multimodal and return parsed JSON.
    """
    log_gemini_request(len(image_bytes), SYSTEM_PROMPT)
    client = genai.Client(api_key=GEMINI_API_KEY)

    response = client.models.generate_content(
        model="gemini-3-flash-preview",
        contents=[
            SYSTEM_PROMPT,
            types.Part.from_bytes(data=image_bytes, mime_type="image/jpeg"),
        ],
        config=types.GenerateContentConfig(
            temperature=0.2,
            max_output_tokens=512,
        ),
    )

    raw_text: str = response.text.strip()
    print("[gemini_parser] raw response:", raw_text)

    # Strip markdown code fences if Gemini adds them despite instructions
    if raw_text.startswith("```"):
        raw_text = raw_text.split("```")[1]
        if raw_text.startswith("json"):
            raw_text = raw_text[4:]
        raw_text = raw_text.strip()

    # Remove trailing commas before } or ] (common Gemini quirk)
    raw_text = re.sub(r",\s*([}\]])", r"\1", raw_text)

    parsed: dict = json.loads(raw_text)
    log_gemini_response(raw_text, parsed)
    return parsed
