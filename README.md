# TGbotMessageToHebrew

Telegram bot that auto-translates messages in any chat (RU/EN ↔ Hebrew) via a local Ollama LLM, plus a personal Hebrew vocabulary builder with practice mode.

## Features

- **Chat translator**: joins any group/chat, translates every message on the fly
  - RU/EN → Hebrew; Hebrew → Russian
  - Default ON; `/off` and `/on` to toggle per chat (admins only in groups)
- **Vocabulary DM**: send a Hebrew word you don't know in a DM, bot saves it with translation + transliteration
- **Practice mode**: `/practice` quizzes you with 4-choice inline buttons, tracks correct/wrong counts

## Setup

```bash
cp .env.example .env
# fill in BOT_TOKEN, OLLAMA_URL, OLLAMA_MODEL
uv sync
uv run python -m tgbot.main
```

## Environment

| Variable | Default | Description |
|---|---|---|
| `BOT_TOKEN` | — | BotFather token (required) |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_MODEL` | `qwen2.5:14b` | Model name |
| `DB_PATH` | `tgbot.db` | SQLite database path |
| `OWNER_USER_ID` | — | Your Telegram user ID (optional, for owner-only commands) |

## Requirements

- Python 3.11+
- Ollama with a multilingual model (qwen2.5, gemma2, etc.)
