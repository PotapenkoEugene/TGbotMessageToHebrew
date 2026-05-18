import os
import pytest

# Patch required env vars before any tgbot module is imported
os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("CLAUDE_MODEL", "claude-haiku-4-5")
os.environ.setdefault("DB_PATH", "test.db")
