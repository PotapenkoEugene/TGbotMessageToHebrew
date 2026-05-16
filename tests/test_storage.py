import pytest
import tempfile
import os

from tgbot.storage import (
    init_db, is_chat_enabled, set_chat_enabled,
    add_vocab_word, get_vocab_words, get_practice_word,
    update_practice_result,
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


async def test_add_vocab(db):
    ok = await add_vocab_word(1, "שלום", "привет", "shalom", db)
    assert ok is True
    words = await get_vocab_words(1, db)
    assert len(words) == 1
    assert words[0].hebrew == "שלום"


async def test_add_vocab_duplicate(db):
    await add_vocab_word(1, "שלום", "привет", "shalom", db)
    ok = await add_vocab_word(1, "שלום", "привет", "shalom", db)
    assert ok is False


async def test_practice_picks_worst(db):
    await add_vocab_word(1, "שלום", "привет", "shalom", db)
    await add_vocab_word(1, "עולם", "мир", "olam", db)
    words = await get_vocab_words(1, db)
    # words[0]="עולם" (added last, DESC order), words[1]="שלום"
    await update_practice_result(words[0].id, False, db)
    await update_practice_result(words[0].id, False, db)
    await update_practice_result(words[1].id, True, db)
    pick = await get_practice_word(1, db)
    assert pick is not None
    assert pick.hebrew == "עולם"
