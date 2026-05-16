import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    bot_token: str = os.environ["BOT_TOKEN"]
    ollama_url: str = os.getenv("OLLAMA_URL", "http://localhost:11434")
    ollama_model: str = os.getenv("OLLAMA_MODEL", "qwen2.5:14b")
    db_path: str = os.getenv("DB_PATH", "tgbot.db")
    owner_user_id: int | None = int(v) if (v := os.getenv("OWNER_USER_ID")) else None


config = Config()
