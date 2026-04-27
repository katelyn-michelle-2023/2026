"""
Text-to-speech via ElevenLabs TTS API.
Accepts the aura_script string, returns a Path to the generated .mp3 file.
"""

import uuid
from pathlib import Path

import httpx

from config import ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID

ELEVENLABS_TTS_URL = (
    f"https://api.elevenlabs.io/v1/text-to-speech/{{voice_id}}"
)


async def generate_speech(script: str, output_dir: Path) -> Path:
    """
    Send script to ElevenLabs TTS and write the mp3 to output_dir.
    Returns the Path of the written file.
    """
    url = ELEVENLABS_TTS_URL.format(voice_id=ELEVENLABS_VOICE_ID)

    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }

    payload = {
        "text": script,
        "model_id": "eleven_turbo_v2_5",  # fast, high quality
        "voice_settings": {
            "stability": 0.4,         # slightly unstable = more expressive
            "similarity_boost": 0.75,
            "style": 0.5,             # lean into Aura's persona
            "use_speaker_boost": True,
        },
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(url, headers=headers, json=payload)

    response.raise_for_status()

    filename = f"aura_{uuid.uuid4().hex[:8]}.mp3"
    output_path = output_dir / filename
    output_path.write_bytes(response.content)

    return output_path
