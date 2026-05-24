import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    bot_token: str = os.environ["BOT_TOKEN"]
    claude_model: str = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")
    db_path: str = os.getenv("DB_PATH", "tgbot.db")
    owner_user_id: int | None = int(v) if (v := os.getenv("OWNER_USER_ID")) else None
    word_threshold: int = int(os.getenv("WORD_THRESHOLD", "15"))
    agent_idle_seconds: int = int(os.getenv("AGENT_IDLE_SECONDS", "600"))
    agent_max_queries: int = int(os.getenv("AGENT_MAX_QUERIES", "50"))


config = Config()
