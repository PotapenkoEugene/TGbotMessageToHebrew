import pytest
import tempfile
import os

from tgbot.storage import (
    init_db, is_chat_enabled, set_chat_enabled,
    add_vocab_word, get_vocab_words, get_practice_word,
    update_practice_result, upsert_vocab_seen,
    save_bot_message, get_bot_message, save_problem,
)


@pytest.fixture
async def db():
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    await init_db(path)
    yield path
    os.unlink(path)


async def test_chat_default_enabled(db):
    assert await is_chat_enabled(999, db) is True


async def test_chat_toggle(db):
    await set_chat_enabled(42, False, db)
    assert await is_chat_enabled(42, db) is False
    await set_chat_enabled(42, True, db)
    assert await is_chat_enabled(42, db) is True


async def test_add_vocab_insert(db):
    ok = await add_vocab_word("שלום", "привет", "shalom", db)
    assert ok is True
    words = await get_vocab_words(db)
    assert len(words) == 1
    assert words[0].hebrew == "שלום"
    assert words[0].translation == "привет"


async def test_add_vocab_duplicate_returns_false(db):
    await add_vocab_word("שלום", "привет", "shalom", db)
    ok = await add_vocab_word("שלום", "привет", "shalom", db)
    assert ok is False


async def test_upsert_vocab_seen_increments_frequency(db):
    await upsert_vocab_seen("שלום", db)
    await upsert_vocab_seen("שלום", db)
    await upsert_vocab_seen("שלום", db)
    words = await get_vocab_words(db)
    assert words[0].frequency == 3


async def test_upsert_vocab_seen_new_word(db):
    await upsert_vocab_seen("עולם", db)
    words = await get_vocab_words(db)
    assert len(words) == 1
    assert words[0].hebrew == "עולם"
    assert words[0].frequency == 1


async def test_practice_picks_worst(db):
    await add_vocab_word("שלום", "привет", "shalom", db)
    await add_vocab_word("עולם", "мир", "olam", db)
    words = await get_vocab_words(db)
    # Mark one word as wrong twice, another correct once
    await update_practice_result(words[0].id, False, db)
    await update_practice_result(words[0].id, False, db)
    await update_practice_result(words[1].id, True, db)
    pick = await get_practice_word(db)
    assert pick is not None
    assert pick.id == words[0].id


async def test_bot_message_round_trip(db):
    await save_bot_message(100, 200, "Доброе утро", "בוקר טוב\nбо́кер тов", db)
    result = await get_bot_message(100, 200, db)
    assert result == ("Доброе утро", "בוקר טוב\nбо́кер тов")


async def test_bot_message_missing_returns_none(db):
    result = await get_bot_message(999, 888, db)
    assert result is None


async def test_save_problem(db):
    await save_problem(100, 1, "Доброе утро", "בוקר טוב", "что значит בוקר?", "Утро.", db)
    import aiosqlite
    async with aiosqlite.connect(db) as conn:
        async with conn.execute("SELECT COUNT(*) FROM problems") as cur:
            row = await cur.fetchone()
    assert row[0] == 1


async def test_migration_from_old_schema(tmp_path):
    """Old schema with user_id should be silently migrated on init_db."""
    import aiosqlite
    db_path = str(tmp_path / "old.db")
    async with aiosqlite.connect(db_path) as conn:
        await conn.execute("""
            CREATE TABLE vocab (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                hebrew TEXT NOT NULL,
                translation TEXT NOT NULL,
                UNIQUE(user_id, hebrew)
            )
        """)
        await conn.execute("INSERT INTO vocab(user_id, hebrew, translation) VALUES(1,'שלום','привет')")
        await conn.commit()

    await init_db(db_path)

    async with aiosqlite.connect(db_path) as conn:
        async with conn.execute("PRAGMA table_info(vocab)") as cur:
            cols = {row[1] async for row in cur}
    assert "user_id" not in cols
    assert "frequency" in cols
