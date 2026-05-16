import pytest
import respx
import httpx

from tgbot.translator import OllamaTranslator

BASE = "http://test-ollama:11434"


@pytest.fixture
async def tr():
    t = OllamaTranslator(base_url=BASE, model="test-model")
    await t.start()
    yield t
    await t.stop()


@respx.mock
async def test_translate_ru_to_he(tr):
    respx.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={"message": {"content": "  שלום  "}},
        )
    )
    result = await tr.translate("Привет", "ru", "he")
    assert result == "שלום"


@respx.mock
async def test_translate_he_to_ru(tr):
    respx.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={"message": {"content": "Привет"}},
        )
    )
    result = await tr.translate("שלום", "he", "ru")
    assert result == "Привет"


@respx.mock
async def test_transliterate(tr):
    respx.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={"message": {"content": '{"translation": "привет", "transliteration": "shalom"}'}},
        )
    )
    result = await tr.translate_and_transliterate("שלום")
    assert result["translation"] == "привет"
    assert result["transliteration"] == "shalom"


@respx.mock
async def test_transliterate_strips_code_fence(tr):
    respx.post(f"{BASE}/api/chat").mock(
        return_value=httpx.Response(
            200,
            json={"message": {"content": '```json\n{"translation": "мир", "transliteration": "olam"}\n```'}},
        )
    )
    result = await tr.translate_and_transliterate("עולם")
    assert result["translation"] == "мир"
    assert result["transliteration"] == "olam"
