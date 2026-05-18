import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    bot_token: str = os.environ["BOT_TOKEN"]
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    db_path: str = os.getenv("DB_PATH", "tgbot.db")
    owner_user_id: int | None = int(v) if (v := os.getenv("OWNER_USER_ID")) else None


config = Config()
