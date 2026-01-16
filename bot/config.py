import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    DB_USER = os.getenv("DB_USER", "postgres")
    DB_PASS = os.getenv("DB_PASS", "postgres")
    DB_HOST = os.getenv("DB_HOST", "localhost")
    DB_PORT = os.getenv("DB_PORT", "5432")
    DB_NAME = os.getenv("DB_NAME", "rent_bot")

    @property
    def DATABASE_URL(self):
        # Prefer DATABASE_URL env var if set (for SQLite support)
        url = os.getenv("DATABASE_URL")
        if url:
            return url
        return f"postgresql+asyncpg://{self.DB_USER}:{self.DB_PASS}@{self.DB_HOST}:{self.DB_PORT}/{self.DB_NAME}"

    # Admin IDs - loaded from .env (static) + DB (dynamic)
    # Store original env values separately for reload_admin_cache()
    _env_admin_ids = [int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip() and x.strip().isdigit()]
    _env_owner_ids = [int(x.strip()) for x in os.getenv("OWNER_IDS", "").split(",") if x.strip() and x.strip().isdigit()]
    
    # Runtime lists (will be updated from DB on startup and after admin changes)
    ADMIN_IDS = _env_admin_ids.copy()
    OWNER_IDS = _env_owner_ids.copy()

    # Ollama Settings
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://192.168.1.220:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2-vision:latest")

    # DaData Settings (Address Normalization)
    DADATA_API_KEY = os.getenv("DADATA_API_KEY")  # Suggestions API
    DADATA_SECRET_KEY = os.getenv("DADATA_SECRET_KEY")  # Clean API (optional, can use API_KEY)

config = Config()
