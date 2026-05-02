"""
backend/config.py
─────────────────
Central settings module.  All environment variables are loaded once at import
time and validated so the server refuses to start without required keys.
"""

import os
import logging
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)


class Settings:
    # ── Gemini & Groq ────────────────────────────────────────────────────────
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

    # ── MongoDB (LangGraph checkpointer) ─────────────────────────────────────
    MONGODB_URI: str = os.getenv("MONGODB_URI", "")
    MONGODB_DB_NAME: str = os.getenv("MONGODB_DB_NAME", "sdkgen")
    CHECKPOINT_COLLECTION: str = "lg_checkpoints"
    WRITES_COLLECTION: str   = "lg_writes"

    # ── Runtime ───────────────────────────────────────────────────────────────
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "t")
    PORT: int   = int(os.getenv("PORT", "8000"))
    JOBS_DIR: str = os.path.join(os.path.dirname(__file__), "jobs")

    # ── Safety ceilings (mirror of router.py / supervisor prompt) ────────────
    MAX_ITERATIONS: int  = 15
    MAX_QA_ROUNDS: int   = 4
    SUPERVISOR_RETRIES: int = 3

    def validate(self) -> None:
        """Raise ValueError early if required env vars are missing."""
        missing = []
        if not self.GOOGLE_API_KEY:
            missing.append("GOOGLE_API_KEY")
        if not self.MONGODB_URI:
            missing.append("MONGODB_URI")
        if missing:
            raise EnvironmentError(
                f"Missing required environment variables: {', '.join(missing)}\n"
                "Copy .env.example → .env and fill in the values."
            )


settings = Settings()

# Emit warnings (not errors) so the server can still partially start for
# development work without a MongoDB URI.
if not settings.GOOGLE_API_KEY:
    log.warning("GOOGLE_API_KEY not set — Gemini calls will fail.")
if not settings.MONGODB_URI:
    log.warning("MONGODB_URI not set — checkpointing will fall back to InMemorySaver.")

# Ensure local jobs directory exists
os.makedirs(settings.JOBS_DIR, exist_ok=True)
