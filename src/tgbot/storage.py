import aiosqlite
from dataclasses import dataclass
from datetime import datetime, UTC

from .config import config


@dataclass
class VocabWord:
    id: int
    user_id: int
    hebrew: str
    translation: str
    transliteration: str
    added_at: str
    last_practiced: str | None
    correct_count: int
    wrong_count: int


async def init_db(db_path: str = config.db_path) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS chat_settings (
                chat_id INTEGER PRIMARY KEY,
                enabled INTEGER NOT NULL DEFAULT 1
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS vocab (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                hebrew TEXT NOT NULL,
                translation TEXT NOT NULL,
                transliteration TEXT NOT NULL DEFAULT '',
                added_at TEXT NOT NULL,
                last_practiced TEXT,
                correct_count INTEGER NOT NULL DEFAULT 0,
                wrong_count INTEGER NOT NULL DEFAULT 0,
                UNIQUE(user_id, hebrew)
            )
        """)
        await db.commit()


async def is_chat_enabled(chat_id: int, db_path: str = config.db_path) -> bool:
    async with aiosqlite.connect(db_path) as db:
        async with db.execute(
            "SELECT enabled FROM chat_settings WHERE chat_id = ?", (chat_id,)
        ) as cur:
            row = await cur.fetchone()
            return row[0] == 1 if row else True  # default ON


async def set_chat_enabled(chat_id: int, enabled: bool, db_path: str = config.db_path) -> None:
    async with aiosqlite.connect(db_path) as db:
        await db.execute(
            "INSERT INTO chat_settings(chat_id, enabled) VALUES(?, ?) "
            "ON CONFLICT(chat_id) DO UPDATE SET enabled=excluded.enabled",
            (chat_id, int(enabled)),
        )
        await db.commit()


async def add_vocab_word(
    user_id: int,
    hebrew: str,
    translation: str,
    transliteration: str = "",
    db_path: str = config.db_path,
) -> bool:
    """Insert word. Returns True if inserted, False if already exists."""
    now = datetime.now(UTC).isoformat()
    async with aiosqlite.connect(db_path) as db:
        try:
            await db.execute(
                "INSERT INTO vocab(user_id, hebrew, translation, transliteration, added_at) "
                "VALUES(?, ?, ?, ?, ?)",
                (user_id, hebrew, translation, transliteration, now),
            )
            await db.commit()
            return True
        except aiosqlite.IntegrityError:
            return False


async def get_vocab_words(user_id: int, db_path: str = config.db_path) -> list[VocabWord]:
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM vocab WHERE user_id = ? ORDER BY added_at DESC", (user_id,)
        ) as cur:
            rows = await cur.fetchall()
            return [VocabWord(**dict(row)) for row in rows]


async def get_practice_word(user_id: int, db_path: str = config.db_path) -> VocabWord | None:
    """Pick word most in need of practice (highest wrong - correct, oldest last_practiced)."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM vocab
            WHERE user_id = ?
            ORDER BY (wrong_count - correct_count) DESC,
                     COALESCE(last_practiced, '0') ASC
            LIMIT 1
            """,
            (user_id,),
        ) as cur:
            row = await cur.fetchone()
            return VocabWord(**dict(row)) if row else None


async def get_distractors(
    user_id: int, exclude_id: int, count: int = 3, db_path: str = config.db_path
) -> list[VocabWord]:
    """Random words from user's vocab excluding the given id."""
    async with aiosqlite.connect(db_path) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM vocab WHERE user_id = ? AND id != ? ORDER BY RANDOM() LIMIT ?",
            (user_id, exclude_id, count),
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
