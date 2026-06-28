"""
Tests for LocalLlmTranslator — HTTP layer mocked with respx.

These tests verify the payload structure sent to the MLX server
and that JSON responses are parsed into the correct return types.
"""

import json
import os
import pytest
import respx
import httpx

# Ensure local backend config is set before importing tgbot modules
os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ["TRANSLATOR_BACKEND"] = "local"
os.environ["LOCAL_LLM_URL"] = "http://localhost:8080/v1"
os.environ["LOCAL_LLM_MODEL"] = "test-model"
os.environ["PRON_STYLE"] = "cyrillic"

from tgbot.translators.local_mlx import LocalLlmTranslator  # noqa: E402


def _make_chat_response(content: dict) -> dict:
    """Minimal OpenAI-compatible chat completion response."""
    return {
        "choices": [
            {"message": {"content": json.dumps(content)}}
        ]
    }


@respx.mock
@pytest.mark.asyncio
async def test_translate_to_hebrew_cyrillic():
    os.environ["PRON_STYLE"] = "cyrillic"
    # Re-import config to pick up env change
    import importlib
    import tgbot.config as cfg_mod
    importlib.reload(cfg_mod)
    from tgbot.translators import local_mlx as lm_mod
    importlib.reload(lm_mod)
    from tgbot.translators.local_mlx import LocalLlmTranslator as LLT

    tr = LLT()
    respx.post("http://localhost:8080/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_make_chat_response(
            {"he": "שלום", "pron": "шало́м"}
        ))
    )
    he, pron = await tr.translate_to_hebrew("Hello")
    assert he == "שלום"
    assert pron == "шало́м"
    await tr.stop()


@respx.mock
@pytest.mark.asyncio
async def test_translate_to_hebrew_both():
    """both mode: call 1 returns {he}, call 2 returns {he,pron}; Latin pron is deterministic."""
    os.environ["PRON_STYLE"] = "both"
    import importlib
    import tgbot.config as cfg_mod
    importlib.reload(cfg_mod)
    from tgbot.translators import local_mlx as lm_mod
    importlib.reload(lm_mod)
    from tgbot.translators.local_mlx import LocalLlmTranslator as LLT

    tr = LLT()
    respx.post("http://localhost:8080/v1/chat/completions").mock(side_effect=[
        httpx.Response(200, json=_make_chat_response({"he": "שלום"})),
        httpx.Response(200, json=_make_chat_response({"he": "שלום", "pron": "шало́м"})),
    ])
    he, pron = await tr.translate_to_hebrew("Hello")
    assert he == "שלום"
    assert "шало́м" in pron           # Cyrillic from LLM
    assert "sheLOM" in pron           # Latin from deterministic converter
    assert "\n" in pron               # two-line
    await tr.stop()
    os.environ["PRON_STYLE"] = "cyrillic"


@respx.mock
@pytest.mark.asyncio
async def test_translate_to_hebrew_latin():
    """latin mode: LLM returns {he} only; Latin pron computed deterministically via nakdimon."""
    os.environ["PRON_STYLE"] = "latin"
    import importlib
    import tgbot.config as cfg_mod
    importlib.reload(cfg_mod)
    from tgbot.translators import local_mlx as lm_mod
    importlib.reload(lm_mod)
    from tgbot.translators.local_mlx import LocalLlmTranslator as LLT

    tr = LLT()
    respx.post("http://localhost:8080/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_make_chat_response({"he": "שלום"}))
    )
    he, pron = await tr.translate_to_hebrew("Hello")
    assert he == "שלום"
    assert pron == "sheLOM"   # deterministic: nakdimon gives שְׁלוֹם → sheLOM
    assert "\n" not in pron   # single line
    await tr.stop()
    os.environ["PRON_STYLE"] = "cyrillic"


@respx.mock
@pytest.mark.asyncio
async def test_translate_to_russian():
    tr = LocalLlmTranslator()
    respx.post("http://localhost:8080/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_make_chat_response(
            {"translation": "Привет"}
        ))
    )
    result = await tr.translate_to_russian("שלום")
    assert result == "Привет"
    await tr.stop()


@respx.mock
@pytest.mark.asyncio
async def test_explain_returns_dict():
    tr = LocalLlmTranslator()
    payload = {
        "rows": [{"he": "בּוֹקֶר", "base": "", "ru": "утро"}],
        "context": "Фраза означает «доброе утро».",
    }
    respx.post("http://localhost:8080/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_make_chat_response(payload))
    )
    result = await tr.explain("Good morning", "בוקר טוב\nбо́кер тов")
    assert isinstance(result, dict)
    assert result["rows"][0]["he"] == "בּוֹקֶר"
    assert "context" in result
    await tr.stop()


@respx.mock
@pytest.mark.asyncio
async def test_grammar_check_no_issues():
    tr = LocalLlmTranslator()
    payload = {"issues": [], "summary": "Грамматика верна."}
    respx.post("http://localhost:8080/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_make_chat_response(payload))
    )
    result = await tr.grammar_check("שלום")
    assert result["issues"] == []
    assert "summary" in result
    await tr.stop()


@respx.mock
@pytest.mark.asyncio
async def test_request_payload_structure():
    """Verify the exact payload sent to the MLX server."""
    tr = LocalLlmTranslator()
    captured = {}

    def capture(request):
        captured["body"] = json.loads(request.content)
        return httpx.Response(200, json=_make_chat_response(
            {"translation": "Доброе утро"}
        ))

    respx.post("http://localhost:8080/v1/chat/completions").mock(side_effect=capture)
    await tr.translate_to_russian("בוקר טוב")

    body = captured["body"]
    assert body["model"] == "test-model"
    assert body["temperature"] == 0
    msgs = body["messages"]
    assert msgs[0]["role"] == "system"
    assert msgs[1]["role"] == "user"
    assert msgs[1]["content"] == "בוקר טוב"
    await tr.stop()


@respx.mock
@pytest.mark.asyncio
async def test_json_fence_stripping():
    """Local model may wrap JSON in markdown fences — _extract_json must strip them."""
    tr = LocalLlmTranslator()
    fenced_json = '```json\n{"translation": "Привет"}\n```'
    respx.post("http://localhost:8080/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"content": fenced_json}}]
        })
    )
    result = await tr.translate_to_russian("שלום")
    assert result == "Привет"
    await tr.stop()
