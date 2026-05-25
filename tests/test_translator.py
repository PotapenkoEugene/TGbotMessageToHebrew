import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, PropertyMock

from tgbot.translator import AgentSdkTranslator, _extract_json


def _make_slot_mock(json_payload: dict):
    """Return a translator with _ask mocked to return json_payload."""
    tr = AgentSdkTranslator.__new__(AgentSdkTranslator)
    # Set dummy slot attrs so method bodies can reference them as arguments.
    dummy = MagicMock()
    tr._he = dummy
    tr._ru = dummy
    tr._explain = dummy
    tr._grammar = dummy
    tr._ask = AsyncMock(return_value=json.dumps(json_payload))
    return tr


@pytest.mark.asyncio
async def test_translate_to_hebrew():
    tr = _make_slot_mock({"he": "שלום", "pron": "шало́м"})
    he, pron = await tr.translate_to_hebrew("Hello")
    assert he == "שלום"
    assert pron == "шало́м"


@pytest.mark.asyncio
async def test_translate_to_russian():
    tr = _make_slot_mock({"translation": "Привет"})
    result = await tr.translate_to_russian("שלום")
    assert result == "Привет"


@pytest.mark.asyncio
async def test_explain_returns_dict():
    payload = {
        "rows": [{"he": "בַּיִת", "base": "", "ru": "дом"}],
        "context": "Слово בַּיִת означает «дом».",
    }
    tr = _make_slot_mock(payload)
    result = await tr.explain("בַּיִת", "дом")
    assert isinstance(result, dict)
    assert result["rows"][0]["he"] == "בַּיִת"
    assert "context" in result


@pytest.mark.asyncio
async def test_grammar_check_returns_dict():
    payload = {
        "issues": [{"phrase": "אני הולך", "suggest": "אני הולך", "why": "Верно"}],
        "summary": "В целом предложение правильное.",
    }
    tr = _make_slot_mock(payload)
    result = await tr.grammar_check("אני הולך")
    assert isinstance(result, dict)
    assert "issues" in result
    assert "summary" in result


@pytest.mark.asyncio
async def test_grammar_check_no_issues():
    payload = {"issues": [], "summary": "Всё верно, грамматика корректна."}
    tr = _make_slot_mock(payload)
    result = await tr.grammar_check("שלום")
    assert result["issues"] == []


def test_extract_json_strips_fence():
    raw = '```json\n{"he":"שלום","pron":"шало́м"}\n```'
    assert _extract_json(raw) == '{"he":"שלום","pron":"шало́м"}'


def test_extract_json_no_fence():
    raw = '{"translation":"Привет"}'
    assert _extract_json(raw) == raw
