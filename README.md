# TGbotMessageToHebrew

Telegram bot that auto-translates chat messages (RU/EN ↔ Hebrew) via a local Ollama LLM, plus a personal Hebrew vocabulary builder with spaced-repetition practice.

## Features

- **Chat translator** — joins any group/chat; translates every message on the fly
  - RU/EN → Hebrew; Hebrew → Russian
  - Default ON; `/off` / `/on` to toggle per chat (group admins only)
- **Vocabulary DM** — send a Hebrew word in DM; bot saves it with Russian translation + transliteration
- **Practice mode** — `/practice` quizzes you with 4-choice inline buttons; tracks correct/wrong per word

## Performance

- Language detection: <1 ms (Unicode block check for Hebrew/Cyrillic; `langdetect` only for EN vs other)
- Translation latency: depends entirely on Ollama model speed (e.g. `qwen2.5:14b` on M2 Mac Studio ≈ 2–5 s/message)
- Storage: SQLite, no external DB; handles thousands of words without issue
- Bot process: single async process, ~30 MB RAM; runs on any machine with Python 3.11+

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| `python-telegram-bot[ext]` | ≥21.0 | Telegram Bot API client + async helpers |
| `httpx` | ≥0.27 | Async HTTP client for Ollama API |
| `aiosqlite` | ≥0.20 | Async SQLite for chat settings + vocabulary |
| `langdetect` | ≥1.0.9 | Language detection fallback (EN vs other) |
| `python-dotenv` | ≥1.0 | Load `.env` config file |

Dev only: `ruff`, `pytest`, `pytest-asyncio`, `respx` (mock HTTP).

## Setup

```bash
# 1. Get a bot token from @BotFather on Telegram
# 2. Have Ollama running with a multilingual model:
ollama pull qwen2.5:14b

# 3. Configure and run
cp .env.example .env        # fill in BOT_TOKEN and OLLAMA_URL
uv sync
uv run python -m tgbot.main
```

## Environment

| Variable | Default | Description |
|---|---|---|
| `BOT_TOKEN` | — | BotFather token **(required)** |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama server base URL |
| `OLLAMA_MODEL` | `qwen2.5:14b` | Model name (any multilingual model works) |
| `DB_PATH` | `tgbot.db` | SQLite database file path |
| `OWNER_USER_ID` | — | Your Telegram numeric user ID (optional) |

## Commands

| Command | Where | Who |
|---|---|---|
| `/on` / `/off` | any chat | admins only |
| `/list` | DM or chat | you |
| `/practice` | DM or chat | you |
| `/stats` | DM or chat | you |
| `/help` | DM or chat | you |

## Requirements

- Python 3.11+
- Ollama running locally or on LAN with a multilingual model (`qwen2.5:14b`, `gemma2:9b`, etc.)
- No cloud APIs — fully local
