"""
Speech-to-text via ElevenLabs STT API.
Accepts raw audio bytes (webm/opus from MediaRecorder).
Returns a plain-text transcript string.
"""

import httpx

from config import ELEVENLABS_API_KEY

ELEVENLABS_STT_URL = "https://api.elevenlabs.io/v1/speech-to-text"


async def transcribe_audio(audio_bytes: bytes) -> str:
    """
    Send audio bytes to ElevenLabs STT.
    Returns the transcribed text.

    Note: ElevenLabs STT accepts webm, mp3, wav, m4a, ogg, flac.
    MediaRecorder in Chrome defaults to webm/opus — should work directly.
    If not, add server-side transcoding with ffmpeg.
    """
    headers = {
        "xi-api-key": ELEVENLABS_API_KEY,
    }

    # ElevenLabs STT expects multipart/form-data with the audio file
    files = {
        "file": ("audio.webm", audio_bytes, "audio/webm"),
    }
    data = {
        "model_id": "scribe_v1",  # ElevenLabs Scribe STT model
    }

    async with httpx.AsyncClient(timeout=60.0) as client:
        response = await client.post(
            ELEVENLABS_STT_URL,
            headers=headers,
            files=files,
            data=data,
        )

    response.raise_for_status()
    result = response.json()

    # ElevenLabs STT response schema: { "text": "...", "words": [...], ... }
    transcript: str = result.get("text", "").strip()
    return transcript
