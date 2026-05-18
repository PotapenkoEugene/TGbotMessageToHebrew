import aiosqlite
from dataclasses import dataclass
from datetime import datetime, UTC

from .config import config


@dataclass
class VocabWord:
    id: int
    hebrew: str
    translation: str
    transliteration: str
    frequency: int
    first_seen_at: str
    last_seen_at: str
    last_practiced: str | None
    correct_count: int
    wrong_count: int


async def _needs_vocab_migration(db: aiosqlite.Connection) -> bool:
    """Detect old schema (has user_id column)."""
    async with db.execute("PRAGMA table_info(vocab)") as cur:
        cols = {row[1] async for row in cur}
    return "user_id" in cols


async def init_db(db_path: str = config.db_path) -> None:
    async with aiosqlite.connect(db_path) as db:
        if await _needs_vocab_migration(db):
            await db.execute("DROP TABLE vocab")

        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS vocab (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                hebrew TEXT NOT NULL UNIQUE,
                translation TEXT NOT NULL DEFAULT '',
                transliteration TEXT NOT NULL DEFAULT '',
                frequency INTEGER NOT NULL DEFAULT 1,
                first_seen_at TEXT NOT NULL,
                last_seen_at TEXT NOT NULL,
                last_practiced TEXT,
                correct_count INTEGER NOT NULL DEFAULT 0,
                wrong_count INTEGER NOT NULL DEFAULT 0
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS bot_messages (
                chat_id INTEGER NOT NULL,
                message_id INTEGER NOT NULL,
                original_text TEXT NOT NULL,
                translation TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(chat_id, message_id)
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS problems (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                original_text TEXT NOT NULL,
                translation TEXT NOT NULL,
                question TEXT NOT NULL,
                explanation TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        await db.commit()


async def is_chat_enabled(chat_id: int, db_path: str = config.db_path) -> bool:
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT enabled FROM chat_settings WHERE chat_id = ?", (chat_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] == 1 if row else True


async def set_chat_enabled(chat_id: int, enabled: bool, db_path: str = config.db_path) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO chat_settings(chat_id, enabled) VALUES(?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET enabled=excluded.enabled",
            (chat_id, int(enabled)),
        )
        await db.commit()


async def upsert_vocab_seen(hebrew: str, db_path: str = config.db_path) -> None:
    """Increment frequency for a Hebrew word; insert with freq=1 if new."""
    now = datetime.now(UTC).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO vocab(hebrew, first_seen_at, last_seen_at)
            VALUES(?, ?, ?)
            ON CONFLICT(hebrew) DO UPDATE SET
                frequency = frequency + 1,
                last_seen_at = excluded.last_seen_at
            """,
            (hebrew, now, now),
        )
        await db.commit()


async def add_vocab_word(
    hebrew: str,
    translation: str,
    transliteration: str = "",
    db_path: str = config.db_path,
) -> bool:
    """Full insert from DM vocab. Returns True if inserted, False if already exists."""
    now = datetime.now(UTC).isoformat()
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT id FROM vocab WHERE hebrew = ?", (hebrew,)
        ) as cur:
            existing = await cur.fetchone()

        if existing:
            await db.execute(
                "UPDATE vocab SET translation=?, transliteration=?, last_seen_at=? WHERE hebrew=?",
                (translation, transliteration, now, hebrew),
            )
            await db.commit()
            return False

        await db.execute(
            """
            INSERT INTO vocab(hebrew, translation, transliteration, first_seen_at, last_seen_at)
            VALUES(?, ?, ?, ?, ?)
            """,
            (hebrew, translation, transliteration, now, now),
        )
        await db.commit()
        return True


async def get_vocab_words(db_path: str = config.db_path) -> list[VocabWord]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM vocab ORDER BY frequency DESC, first_seen_at DESC"
        ) as cur:
            rows = await cur.fetchall()
            return [VocabWord(**dict(row)) for row in rows]


async def get_practice_word(db_path: str = config.db_path) -> VocabWord | None:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM vocab
            WHERE translation != ''
            ORDER BY (wrong_count - correct_count) DESC,
                     COALESCE(last_practiced, '0') ASC
            LIMIT 1
            """
        ) as cur:
            row = await cur.fetchone()
            return VocabWord(**dict(row)) if row else None


async def get_distractors(
    exclude_id: int, count: int = 3, db_path: str = config.db_path
) -> list[VocabWord]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM vocab WHERE id != ? AND translation != '' ORDER BY RANDOM() LIMIT ?",
            (exclude_id, count),
        ) as cur:
            rows = await cur.fetchall()
            return [VocabWord(**dict(row)) for row in rows]


async def update_practice_result(
    word_id: int, correct: bool, db_path: str = config.db_path
) -> None:
    now = datetime.now(UTC).isoformat()
    col = "correct_count" if correct else "wrong_count"
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            f"UPDATE vocab SET {col} = {col} + 1, last_practiced = ? WHERE id = ?",
            (now, word_id),
        )
        await db.commit()


async def save_bot_message(
    chat_id: int,
    message_id: int,
    original_text: str,
    translation: str,
    db_path: str = config.db_path,
) -> None:
    now = datetime.now(UTC).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO bot_messages(chat_id, message_id, original_text, translation, created_at)
            VALUES(?, ?, ?, ?, ?)
            """,
            (chat_id, message_id, original_text, translation, now),
        )
        await db.commit()


async def get_bot_message(
    chat_id: int, message_id: int, db_path: str = config.db_path
) -> tuple[str, str] | None:
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT original_text, translation FROM bot_messages WHERE chat_id=? AND message_id=?",
            (chat_id, message_id),
        ) as cur:
            row = await cur.fetchone()
            return (row[0], row[1]) if row else None


async def save_problem(
    chat_id: int,
    user_id: int,
    original_text: str,
    translation: str,
    question: str,
    explanation: str,
    db_path: str = config.db_path,
) -> None:
    now = datetime.now(UTC).isoformat()
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            """
            INSERT INTO problems(chat_id, user_id, original_text, translation, question, explanation, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?)
            """,
            (chat_id, user_id, original_text, translation, question, explanation, now),
        )
        await db.commit()
