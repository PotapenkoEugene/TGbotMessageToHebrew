# TGbotMessageToHebrew

Telegram bot that auto-translates Russian/English ↔ Hebrew in group chats. Replies with a two-line output: Hebrew translation + Cyrillic pronunciation with stress marks. Maintains a shared vocabulary, supports word-by-word breakdown on demand, and includes a weighted quiz mode.

## Features

- **Auto-translate** in group chats: RU/EN → Hebrew (2 lines: translation + Cyrillic pronunciation), Hebrew → Russian (1 line)
- **Reply with "объясни"** to any bot translation for a word-by-word breakdown table
- **Shared vocabulary** — every Hebrew word the bot translates is saved globally with frequency tracking
- **DM vocab save** — send any Hebrew word directly to the bot to look it up and add it to the shared vocab
- **Quiz mode** — 4-choice inline keyboard quiz with weighted word selection (more wrong answers = seen more often)
- **Per-chat on/off** — admins control whether translation is active in their group

---

## Using the bot

### Auto-translation in group chats

1. Add the bot to a group.
2. An admin runs `/on` to enable translation.
3. The bot will quietly reply to messages it can translate.

**What gets translated:** plain text messages in Russian, English, or Hebrew (2–14 words).

**What gets skipped:**
- Commands (starting with `/`)
- Replies to other messages
- Single-word messages and messages with 15 or more words
- Messages containing URLs or media (photos, videos, stickers, documents)
- Messages from other bots

**Output format:**

For Russian or English input:
```
בּוֹקֶר טוֹב
бо́кер тов
```

For Hebrew input:
```
Доброе утро
```

### Reply with "объясни" for word-by-word breakdown

Reply to any bot translation with exactly `объясни` (trailing punctuation is fine: `объясни!`, `объясни?`).

The bot replies with a table showing each word, its base form, Cyrillic pronunciation, and Russian translation — plus a one-sentence usage note.

```
Слово   | База    | Произн. | Перевод
--------+---------+---------+---------
בּוֹקֶר  | בּוֹקֶר  | бо́кер   | утро
טוֹב    | טוֹב    | тов     | хороший

Фраза используется как приветствие в утреннее время.
```

### Automatic vocabulary collection

Every Hebrew word the bot encounters in an enabled group chat is automatically added to the shared vocabulary with a frequency counter. You do not need to do anything — just chat.

Use `/list` to browse the vocabulary by frequency, `/practice` to quiz yourself.

### Direct messages — save words manually

Send any Hebrew word or phrase directly to the bot in a private chat. The bot will translate and transliterate it and save it to the shared vocabulary.

If the word is already saved, the bot will confirm it is already in the vocabulary without creating a duplicate.

```
You: שָׁלוֹם
Bot: Saved!
     שָׁלוֹם — мир, покой (shalom)
```

Non-Hebrew DMs get a usage hint instead.

### Commands

| Command     | Where        | Who                                       | What it does                                             |
|-------------|--------------|-------------------------------------------|----------------------------------------------------------|
| `/start`    | DM or group  | anyone                                    | Shows welcome text with command list                     |
| `/help`     | DM or group  | anyone                                    | Same as `/start`                                         |
| `/on`       | DM or group  | group admin/owner; always allowed in DMs  | Enables auto-translation for this chat                   |
| `/off`      | DM or group  | group admin/owner; always allowed in DMs  | Disables auto-translation for this chat                  |
| `/list`     | DM or group  | anyone                                    | Shows all saved words sorted by frequency                |
| `/practice` | DM or group  | anyone (needs ≥2 words)                  | Starts a 4-choice quiz on a weighted word                |
| `/stats`    | DM or group  | anyone                                    | Shows total words, practiced count, correct/wrong totals |

> **Note:** The vocabulary is shared across all users — `/list` and `/practice` reflect the same global word list regardless of who calls them.

---

## Self-hosting

### Requirements

- Python 3.11+
- [`uv`](https://github.com/astral-sh/uv) for dependency management
- A Telegram bot token from [BotFather](https://t.me/BotFather)
- A Claude Code subscription with `CLAUDE_CODE_OAUTH_TOKEN` set in your environment (the bot uses `claude-agent-sdk` for translation — no Anthropic API key billing)

### Install

```bash
git clone https://github.com/youruser/TGbotMessageToHebrew
cd TGbotMessageToHebrew
uv venv && uv sync
cp .env.example .env   # edit with your values
export CLAUDE_CODE_OAUTH_TOKEN=your_token_here
uv run python -m tgbot.main
```

### Environment variables

| Variable                  | Default            | Required  | Purpose                                                        |
|---------------------------|--------------------|-----------|----------------------------------------------------------------|
| `BOT_TOKEN`               | —                  | yes       | Telegram bot token from BotFather                              |
| `CLAUDE_CODE_OAUTH_TOKEN` | —                  | yes (env) | Claude Code subscription auth — set in shell env, not `.env`   |
| `CLAUDE_MODEL`            | `claude-haiku-4-5` | no        | Claude model used for all 4 translation sessions               |
| `DB_PATH`                 | `tgbot.db`         | no        | Path to the SQLite database file                               |
| `WORD_THRESHOLD`          | `15`               | no        | Messages with this many words or more are not translated       |
| `AGENT_IDLE_SECONDS`      | `600`              | no        | Reconnect a translation session after this many idle seconds   |
| `AGENT_MAX_QUERIES`       | `50`               | no        | Reconnect a translation session after this many queries        |
| `OWNER_USER_ID`           | —                  | no        | Reserved for future admin features                             |

### Deployment (Mac Studio / launchd)

This repo includes a home-manager module (`tgbot.nix`) that registers the bot as a launchd user agent (`com.ortho.tgbot`) on macOS. Deploy updates with:

```bash
ssh ortho@mac-studio 'tgbot-update'
```

---

## Architecture

- **Translation backend:** `claude-agent-sdk` with 4 persistent sessions (`he`, `ru`, `explain`, `vocab`). Each session holds an `asyncio.Lock` and reconnects automatically after idle timeout or query count. Startup cost (~5–6 s) is paid once, not per message.
- **Storage:** SQLite via `aiosqlite`. Tables: `chat_settings`, `vocab` (global, no user ID), `bot_messages` (for explain lookup), `problems` (explain interaction log).
- **Language detection:** Hebrew via Unicode block U+0590–U+05FF, Cyrillic via U+0400–U+04FF, English via `langdetect`.

---

## Roadmap

- `/add` command — explicit vocab add as an alternative to sending Hebrew words in DM
- Webhook vs polling decision (currently using polling)
