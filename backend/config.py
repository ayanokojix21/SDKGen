import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

class Settings:
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
    
    # Other potential settings
    DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "t")
    PORT = int(os.getenv("PORT", 8000))

settings = Settings()

if not settings.GOOGLE_API_KEY:
    import logging
    logging.warning("GOOGLE_API_KEY is not set in the environment. LangGraph nodes using Gemini will fail.")
