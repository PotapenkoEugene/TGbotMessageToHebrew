import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from tgbot.translator import ClaudeCliTranslator, _extract_json


def _make_proc(stdout: bytes) -> MagicMock:
    proc = MagicMock()
    proc.communicate = AsyncMock(return_value=(stdout, b""))
    return proc


@pytest.fixture
def tr():
    return ClaudeCliTranslator(model="claude-haiku-4-5")


async def test_translate_to_hebrew(tr):
    payload = json.dumps({"he": "שלום", "pron": "шало́м"}).encode()
    with patch("asyncio.create_subprocess_exec", return_value=_make_proc(payload)):
        he, pron = await tr.translate_to_hebrew("Hello")
    assert he == "שלום"
    assert pron == "шало́м"


async def test_translate_to_hebrew_strips_fence(tr):
    raw = b"```json\n" + json.dumps({"he": "בוקר טוב", "pron": "бо́кер тов"}).encode() + b"\n```"
    with patch("asyncio.create_subprocess_exec", return_value=_make_proc(raw)):
        he, pron = await tr.translate_to_hebrew("Good morning")
    assert he == "בוקר טוב"
    assert "бо́кер" in pron


async def test_translate_to_russian(tr):
    payload = json.dumps({"translation": "Привет"}).encode()
    with patch("asyncio.create_subprocess_exec", return_value=_make_proc(payload)):
        result = await tr.translate_to_russian("שלום")
    assert result == "Привет"


async def test_explain_returns_plain_text(tr):
    explanation = "  Окончание ת указывает на женский род.  ".encode("utf-8")
    with patch("asyncio.create_subprocess_exec", return_value=_make_proc(explanation)):
        result = await tr.explain("בַּיִת", "дом", "почему ת в конце?")
    assert "Окончание" in result
    assert result == result.strip()


async def test_translate_and_transliterate(tr):
    payload = json.dumps({"translation": "мир", "transliteration": "olam"}).encode()
    with patch("asyncio.create_subprocess_exec", return_value=_make_proc(payload)):
        result = await tr.translate_and_transliterate("עולם")
    assert result["translation"] == "мир"
    assert result["transliteration"] == "olam"


def test_extract_json_strips_fence():
    raw = '```json\n{"he":"שלום","pron":"шало́м"}\n```'
    assert _extract_json(raw) == '{"he":"שלום","pron":"шало́м"}'


def test_extract_json_no_fence():
    raw = '{"translation":"Привет"}'
    assert _extract_json(raw) == raw
