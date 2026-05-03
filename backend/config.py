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

    # ── Self-Deployed Gemma 4 (Vertex AI Model Garden) ────────────────────────
    GEMMA_PROJECT: str = os.getenv("GEMMA_PROJECT", "")
    GEMMA_LOCATION: str = os.getenv("GEMMA_LOCATION", "europe-west4")
    GEMMA_ENDPOINT_ID: str = os.getenv("GEMMA_ENDPOINT_ID", "")
    GEMMA_DEDICATED_DNS: str = os.getenv("GEMMA_DEDICATED_DNS", "")
    GEMMA_MODEL_NAME: str = os.getenv("GEMMA_MODEL_NAME", "google/gemma-4-31b-it")

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
        if not self.GOOGLE_API_KEY and not self.GEMMA_ENDPOINT_ID and not self.GROQ_API_KEY:
            missing.append("GOOGLE_API_KEY, GEMMA_ENDPOINT_ID, or GROQ_API_KEY")
        if not self.MONGODB_URI: missing.append("MONGODB_URI")
        if not self.E2B_API_KEY: log.warning("E2B_API_KEY missing — sandboxing disabled.")
        if not self.NOMIC_API_KEY: log.warning("NOMIC_API_KEY missing — vector embeddings will fail.")
        if not self.COHERE_API_KEY: log.warning("COHERE_API_KEY missing — reranking disabled.")
        if not self.SERPER_API_KEY or self.SERPER_API_KEY.startswith("your_"):
            log.warning("SERPER_API_KEY missing or placeholder — web search disabled.")
        if self.GEMMA_ENDPOINT_ID:
            if not self.GEMMA_DEDICATED_DNS:
                log.warning("GEMMA_DEDICATED_DNS missing — Gemma endpoint requires dedicated DNS hostname.")
            else:
                log.info("Gemma 4 (Vertex AI) configured as primary LLM.")
        if missing:
            raise EnvironmentError(f"Missing required environment variables: {', '.join(missing)}")

settings = Settings()
os.makedirs(settings.JOBS_DIR, exist_ok=True)
