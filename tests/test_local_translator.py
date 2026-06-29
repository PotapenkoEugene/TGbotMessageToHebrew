"""
Tests for LocalLlmTranslator — HTTP layer mocked with respx.

These tests verify the payload structure sent to the MLX server
and that JSON responses are parsed into the correct return types.
Also covers the echo-detection + retry logic added in the few-shot-echo fix.
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

from tgbot.translators.local_mlx import (  # noqa: E402
    LocalLlmTranslator,
    _HE_ECHO_OUTPUTS,
    _HE_FEWSHOT_PAIRS,
    _HE_CYR_ECHO_OUTPUTS,
)
from tgbot.translators.base import he_problem, is_hebrew_script  # noqa: E402


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


# ---------------------------------------------------------------------------
# Echo-detection unit tests (no HTTP mocking needed)
# ---------------------------------------------------------------------------

def test_he_problem_echo():
    """Known few-shot example Hebrew → 'echo' when input is unrelated."""
    # The attractor: סליחה, אתה מדבר רוסית
    result = he_problem(
        "סליחה, אתה מדבר רוסית",
        "Ой очные пары?",
        echo_outputs=_HE_ECHO_OUTPUTS,
        fewshot_pairs=_HE_FEWSHOT_PAIRS,
    )
    assert result == "echo"


def test_he_problem_clean():
    """Hebrew not in echo set → None."""
    result = he_problem(
        "שלום",
        "Hello",
        echo_outputs=_HE_ECHO_OUTPUTS,
        fewshot_pairs=_HE_FEWSHOT_PAIRS,
    )
    assert result is None


def test_he_problem_latin_leakage():
    """Latin letters in he → 'non_hebrew'."""
    result = he_problem(
        "hello world",
        "Hello",
        echo_outputs=_HE_ECHO_OUTPUTS,
        fewshot_pairs=_HE_FEWSHOT_PAIRS,
    )
    assert result == "non_hebrew"


def test_he_problem_cyrillic_leakage():
    """Cyrillic letters mixed in → 'non_hebrew'."""
    result = he_problem(
        "שלום привет",
        "Hello",
        echo_outputs=_HE_ECHO_OUTPUTS,
        fewshot_pairs=_HE_FEWSHOT_PAIRS,
    )
    assert result == "non_hebrew"


def test_he_problem_fewshot_exemption():
    """User literally typed the fewshot source phrase → genuine, return None."""
    result = he_problem(
        "סליחה, אתה מדבר רוסית",
        "excuse me, do you speak Russian",
        echo_outputs=_HE_ECHO_OUTPUTS,
        fewshot_pairs=_HE_FEWSHOT_PAIRS,
    )
    assert result is None


def test_he_problem_cyr_echo_set():
    """Cyrillic-mode echo set: only the single inline example triggers echo."""
    # בוקר טוב is the single example in _SYS_HE_CYR → should trigger in cyr set
    result_cyr = he_problem(
        "בוקר טוב",
        "Ой очные пары?",
        echo_outputs=_HE_CYR_ECHO_OUTPUTS,
        fewshot_pairs=_HE_FEWSHOT_PAIRS,
    )
    assert result_cyr == "echo"
    # שלום is not in cyrillic echo set
    result_clean = he_problem(
        "שלום",
        "Ой очные пары?",
        echo_outputs=_HE_CYR_ECHO_OUTPUTS,
        fewshot_pairs=_HE_FEWSHOT_PAIRS,
    )
    assert result_clean is None


def test_is_hebrew_script_valid():
    assert is_hebrew_script("שלום") is True
    assert is_hebrew_script("בוקר טוב") is True


def test_is_hebrew_script_invalid():
    assert is_hebrew_script("hello") is False
    assert is_hebrew_script("") is False
    assert is_hebrew_script("שלום hello") is False


# ---------------------------------------------------------------------------
# Retry logic integration tests (latin mode, HTTP mocked via respx)
# ---------------------------------------------------------------------------

def _latin_translator():
    """Reload config+module for latin pron_style and return a fresh translator instance."""
    import importlib
    import tgbot.config as cfg_mod
    importlib.reload(cfg_mod)
    from tgbot.translators import local_mlx as lm_mod
    importlib.reload(lm_mod)
    from tgbot.translators.local_mlx import LocalLlmTranslator as LLT
    return LLT()


@respx.mock
@pytest.mark.asyncio
async def test_no_retry_on_good_first():
    """Clean output on attempt 0 → exactly 1 HTTP call, correct result."""
    os.environ["PRON_STYLE"] = "latin"
    tr = _latin_translator()

    call_count = 0

    def capture(request):
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json=_make_chat_response({"he": "שלום"}))

    respx.post("http://localhost:8080/v1/chat/completions").mock(side_effect=capture)
    he, _pron = await tr.translate_to_hebrew("Hello")
    assert he == "שלום"
    assert call_count == 1
    await tr.stop()
    os.environ["PRON_STYLE"] = "cyrillic"


@respx.mock
@pytest.mark.asyncio
async def test_retry_on_echo_then_good():
    """Echo on attempt 0, good translation on attempt 1 → 2 HTTP calls, returns good."""
    os.environ["PRON_STYLE"] = "latin"
    tr = _latin_translator()

    captured_payloads: list[dict] = []

    def capture(request):
        body = json.loads(request.content)
        captured_payloads.append(body)
        # Attempt 0: return the attractor echo; attempt 1: return clean translation
        if len(captured_payloads) == 1:
            return httpx.Response(200, json=_make_chat_response({"he": "סליחה, אתה מדבר רוסית"}))
        return httpx.Response(200, json=_make_chat_response({"he": "שלום"}))

    respx.post("http://localhost:8080/v1/chat/completions").mock(side_effect=capture)
    he, _pron = await tr.translate_to_hebrew("Ой очные пары?")

    assert he == "שלום"
    assert len(captured_payloads) == 2

    # Attempt 0: temperature 0, full prompt (with attractor)
    assert captured_payloads[0]["temperature"] == 0.0
    sys_msg_0 = captured_payloads[0]["messages"][0]["content"]
    assert "do you speak Russian" in sys_msg_0

    # Attempt 1: temperature 0.3, attractor stripped
    assert captured_payloads[1]["temperature"] == 0.3
    sys_msg_1 = captured_payloads[1]["messages"][0]["content"]
    assert "do you speak Russian" not in sys_msg_1

    await tr.stop()
    os.environ["PRON_STYLE"] = "cyrillic"


@respx.mock
@pytest.mark.asyncio
async def test_temperature_schedule():
    """All 3 attempts return echoes → temperatures are 0.0, 0.3, 0.7 in order."""
    os.environ["PRON_STYLE"] = "latin"
    tr = _latin_translator()

    # Three different echo outputs so seen_he changes (→ ERROR log, not WARNING)
    echo_responses = [
        {"he": "סליחה, אתה מדבר רוסית"},   # attempt 0
        {"he": "בוקר טוב"},                  # attempt 1
        {"he": "אני רוצה מים"},              # attempt 2
    ]
    captured_temps: list[float] = []

    def capture(request):
        body = json.loads(request.content)
        captured_temps.append(body["temperature"])
        return httpx.Response(200, json=_make_chat_response(echo_responses[len(captured_temps) - 1]))

    respx.post("http://localhost:8080/v1/chat/completions").mock(side_effect=capture)
    # All 3 fail detection; exhausted → still returns the last result
    he, _pron = await tr.translate_to_hebrew("Ой очные пары?")

    assert len(captured_temps) == 3
    assert captured_temps == [0.0, 0.3, 0.7]
    assert he == "אני רוצה מים"  # last attempt's Hebrew returned

    await tr.stop()
    os.environ["PRON_STYLE"] = "cyrillic"


@respx.mock
@pytest.mark.asyncio
async def test_exhausted_changed_logs_error(caplog):
    """All 3 return different echoes → exhausted, ERROR level logged."""
    import logging
    os.environ["PRON_STYLE"] = "latin"
    tr = _latin_translator()

    echo_responses = [
        {"he": "סליחה, אתה מדבר רוסית"},
        {"he": "בוקר טוב"},
        {"he": "אני רוצה מים"},
    ]
    call_idx = [0]

    def capture(request):
        resp = echo_responses[call_idx[0]]
        call_idx[0] += 1
        return httpx.Response(200, json=_make_chat_response(resp))

    respx.post("http://localhost:8080/v1/chat/completions").mock(side_effect=capture)

    with caplog.at_level(logging.ERROR, logger="tgbot.translators.local_mlx"):
        he, _pron = await tr.translate_to_hebrew("Ой очные пары?")

    assert he == "אני רוצה מים"
    assert any("he_exhausted" in r.message for r in caplog.records if r.levelno == logging.ERROR)

    await tr.stop()
    os.environ["PRON_STYLE"] = "cyrillic"


@respx.mock
@pytest.mark.asyncio
async def test_exhausted_stable_logs_warning(caplog):
    """All 3 return the SAME echo → WARNING (stable greeting), not ERROR."""
    import logging
    os.environ["PRON_STYLE"] = "latin"
    tr = _latin_translator()

    # Same echo every time → stable
    respx.post("http://localhost:8080/v1/chat/completions").mock(
        return_value=httpx.Response(200, json=_make_chat_response({"he": "בוקר טוב"}))
    )

    with caplog.at_level(logging.WARNING, logger="tgbot.translators.local_mlx"):
        he, _pron = await tr.translate_to_hebrew("Ой очные пары?")

    assert he == "בוקר טוב"
    # Should see a WARNING but no ERROR
    he_exhausted_records = [r for r in caplog.records if "he_exhausted" in r.message]
    assert he_exhausted_records, "expected at least one he_exhausted log record"
    assert any(r.levelno == logging.WARNING for r in he_exhausted_records)
    assert not any(r.levelno == logging.ERROR for r in he_exhausted_records)

    await tr.stop()
    os.environ["PRON_STYLE"] = "cyrillic"


@respx.mock
@pytest.mark.asyncio
async def test_all_parse_errors_reraise():
    """All 3 attempts return unparseable content → exception propagates."""
    os.environ["PRON_STYLE"] = "latin"
    tr = _latin_translator()

    respx.post("http://localhost:8080/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "choices": [{"message": {"content": "not valid json at all"}}]
        })
    )

    with pytest.raises(Exception):
        await tr.translate_to_hebrew("Ой очные пары?")

    await tr.stop()
    os.environ["PRON_STYLE"] = "cyrillic"


@respx.mock
@pytest.mark.asyncio
async def test_parse_error_then_good():
    """Parse error on attempt 0 → retry fires, attempt 1 succeeds."""
    os.environ["PRON_STYLE"] = "latin"
    tr = _latin_translator()

    call_count = [0]

    def capture(request):
        call_count[0] += 1
        if call_count[0] == 1:
            return httpx.Response(200, json={
                "choices": [{"message": {"content": "not valid json"}}]
            })
        return httpx.Response(200, json=_make_chat_response({"he": "שלום"}))

    respx.post("http://localhost:8080/v1/chat/completions").mock(side_effect=capture)
    he, _pron = await tr.translate_to_hebrew("Hello")

    assert he == "שלום"
    assert call_count[0] == 2

    await tr.stop()
    os.environ["PRON_STYLE"] = "cyrillic"
