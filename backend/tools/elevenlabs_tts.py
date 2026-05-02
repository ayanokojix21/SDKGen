"""
backend/tools/elevenlabs_tts.py
Stub implementation to prevent import errors.
"""
import logging
from typing import Optional

log = logging.getLogger(__name__)

async def generate_narration_audio(text: str, job_id: str) -> Optional[str]:
    """
    Stub for ElevenLabs TTS generation.
    Returns None since we don't have the API key or full implementation here.
    """
    log.info("[elevenlabs_tts] Stub called for job_id=%s. Returning None.", job_id)
    return None
