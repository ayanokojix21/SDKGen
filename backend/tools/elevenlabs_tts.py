"""
backend/tools/elevenlabs_tts.py
────────────────────────────────
ElevenLabs Text-to-Speech narration generator.

Generates a short MP3 narration clip for the SDK generation summary.
Non-critical — returns None gracefully when the API key is missing
or any error occurs.
"""
import logging
import os
from typing import Optional

from backend.config import settings

log = logging.getLogger(__name__)

# ── Configuration ─────────────────────────────────────────────────────────────
_VOICE_ID = "aMSt68OGf4xUZAnLpTU8"  # Matches the ConvAI agent voice
_MODEL_ID = "eleven_flash_v2"         # Fast model — narration is 2–3 sentences


def _is_available() -> bool:
    """Check if ElevenLabs TTS is configured."""
    return bool(settings.ELEVENLABS_API_KEY)


def _get_client():
    """Lazy-initialize the ElevenLabs client."""
    from elevenlabs.client import ElevenLabs
    return ElevenLabs(api_key=settings.ELEVENLABS_API_KEY)


async def generate_narration_audio(text: str, job_id: str) -> Optional[str]:
    """
    Generate a narration audio clip via ElevenLabs TTS.

    Args:
        text:   The narration text (2–3 sentences).
        job_id: Current job ID — used to determine the output file path.

    Returns:
        The absolute file path of the generated MP3, or None on failure.
    """
    if not _is_available():
        log.info("[elevenlabs_tts] API key not set — skipping TTS generation")
        return None

    if not text or not text.strip():
        log.info("[elevenlabs_tts] Empty narration text — skipping")
        return None

    import asyncio

    try:
        audio_bytes = await asyncio.to_thread(_sync_generate, text)

        # Save to the job directory
        job_dir = os.path.join(settings.JOBS_DIR, job_id)
        os.makedirs(job_dir, exist_ok=True)
        output_path = os.path.join(job_dir, "narration.mp3")

        with open(output_path, "wb") as f:
            f.write(audio_bytes)

        log.info(
            "[elevenlabs_tts] Generated narration audio (%d bytes) → %s",
            len(audio_bytes), output_path,
        )
        return output_path

    except Exception as exc:
        log.warning("[elevenlabs_tts] TTS generation failed (non-critical): %s", exc)
        return None


def _sync_generate(text: str) -> bytes:
    """Synchronous call to the ElevenLabs TTS API. Returns raw MP3 bytes."""
    client = _get_client()

    # generate() returns an iterator of audio chunks
    audio_iterator = client.text_to_speech.convert(
        text=text,
        voice_id=_VOICE_ID,
        model_id=_MODEL_ID,
        output_format="mp3_44100_128",
    )

    # Collect all chunks into a single bytes object
    chunks = []
    for chunk in audio_iterator:
        chunks.append(chunk)

    return b"".join(chunks)
