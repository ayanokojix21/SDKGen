import os
import logging
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

class Settings:
    # ── LLMs ──────────────────────────────────────────────────────────────────
    GOOGLE_API_KEY: str = os.getenv("GOOGLE_API_KEY", "")
    GEMINI_MODEL: str = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "")

    # ── Research & RAG ────────────────────────────────────────────────────────
    MONGODB_URI: str = os.getenv("MONGODB_URI", "")
    NOMIC_API_KEY: str = os.getenv("NOMIC_API_KEY", "")
    COHERE_API_KEY: str = os.getenv("COHERE_API_KEY", "")
    SERPER_API_KEY: str = os.getenv("SERPER_API_KEY", "")

    # ── Sandbox ───────────────────────────────────────────────────────────────
    E2B_API_KEY: str = os.getenv("E2B_API_KEY", "")
    
    # ── External Services ─────────────────────────────────────────────────────
    ELEVENLABS_API_KEY: str = os.getenv("ELEVENLABS_API_KEY", "")

    # ── Persistence ───────────────────────────────────────────────────────────
    MONGODB_DB_NAME: str = os.getenv("MONGODB_DB_NAME", "sdkgen")
    CHECKPOINT_COLLECTION: str = "lg_checkpoints"

    # ── Runtime ───────────────────────────────────────────────────────────────
    DEBUG: bool = os.getenv("DEBUG", "false").lower() in ("true", "1", "t")
    PORT: int = int(os.getenv("PORT", "8000"))
    JOBS_DIR: str = os.path.join(os.path.dirname(__file__), "jobs")

    MAX_ITERATIONS: int = 15
    MAX_QA_ROUNDS: int = 4
    WRITES_COLLECTION: str = "lg_writes"

    def validate(self) -> None:
        missing = []
        if not self.GOOGLE_API_KEY: missing.append("GOOGLE_API_KEY")
        if not self.MONGODB_URI: missing.append("MONGODB_URI")
        if not self.E2B_API_KEY: log.warning("E2B_API_KEY missing — sandboxing disabled.")
        if missing:
            raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

settings = Settings()
os.makedirs(settings.JOBS_DIR, exist_ok=True)
