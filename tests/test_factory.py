"""
Tests for the translator factory and RoutingTranslator.
"""

import json
import os
import pytest
from unittest.mock import AsyncMock


os.environ.setdefault("BOT_TOKEN", "test-token")
os.environ.setdefault("DB_PATH", "test.db")


def _reload_factory(backend: str, task_backends: str = "") -> object:
    """Force-reload config + factory with fresh env vars."""
    import importlib
    os.environ["TRANSLATOR_BACKEND"] = backend
    os.environ["TRANSLATOR_TASK_BACKENDS"] = task_backends

    import tgbot.config as cfg_mod
    importlib.reload(cfg_mod)

    import tgbot.translators as tr_pkg
    importlib.reload(tr_pkg)

    return tr_pkg.make_translator()


def test_factory_returns_claude_by_default():
    from tgbot.translators.claude_agent import AgentSdkTranslator
    tr = _reload_factory("claude")
    assert isinstance(tr, AgentSdkTranslator)


def test_factory_returns_local():
    from tgbot.translators.local_mlx import LocalLlmTranslator
    os.environ["LOCAL_LLM_URL"] = "http://localhost:8080/v1"
    os.environ["LOCAL_LLM_MODEL"] = "test-model"
    tr = _reload_factory("local")
    assert isinstance(tr, LocalLlmTranslator)


def test_factory_routing_creates_routing_translator():
    import tgbot.translators as tr_pkg
    task_map = json.dumps({"translate_to_hebrew": "local"})
    tr = _reload_factory("claude", task_backends=task_map)
    # Must be the routing wrapper (not a plain backend)
    assert hasattr(tr, "_task_map")
    assert hasattr(tr, "_backends")
    assert "local" in tr._backends
    assert "claude" in tr._backends


@pytest.mark.asyncio
async def test_routing_translator_dispatches_correctly():
    import importlib
    import tgbot.config as cfg_mod
    os.environ["TRANSLATOR_BACKEND"] = "claude"
    os.environ["TRANSLATOR_TASK_BACKENDS"] = json.dumps({"translate_to_hebrew": "local"})
    os.environ["LOCAL_LLM_URL"] = "http://localhost:8080/v1"
    os.environ["LOCAL_LLM_MODEL"] = "test-model"
    importlib.reload(cfg_mod)
    import tgbot.translators as tr_pkg
    importlib.reload(tr_pkg)
    tr = tr_pkg.make_translator()

    # Patch both backend instances
    claude_he = AsyncMock(return_value=("שלום", "шало́м"))
    local_he = AsyncMock(return_value=("שלום_local", "шало́м_local"))
    claude_ru = AsyncMock(return_value="Привет")
    local_ru = AsyncMock(return_value="Привет_local")

    tr._backends["claude"].translate_to_hebrew = claude_he
    tr._backends["local"].translate_to_hebrew = local_he
    tr._backends["claude"].translate_to_russian = claude_ru
    tr._backends["local"].translate_to_russian = local_ru

    he, pron = await tr.translate_to_hebrew("Hello")
    assert he == "שלום_local"  # mapped to local

    ru = await tr.translate_to_russian("שלום")
    assert ru == "Привет"  # default = claude

    # Cleanup
    os.environ["TRANSLATOR_TASK_BACKENDS"] = ""


def test_factory_invalid_task_key_ignored():
    import importlib
    import tgbot.config as cfg_mod
    os.environ["TRANSLATOR_BACKEND"] = "claude"
    os.environ["TRANSLATOR_TASK_BACKENDS"] = json.dumps({"nonexistent_task": "local"})
    importlib.reload(cfg_mod)
    import tgbot.translators as tr_pkg
    importlib.reload(tr_pkg)
    # Should not raise; invalid key is silently dropped → returns plain claude backend
    tr = tr_pkg.make_translator()
    from tgbot.translators.claude_agent import AgentSdkTranslator
    assert isinstance(tr, AgentSdkTranslator)
    os.environ["TRANSLATOR_TASK_BACKENDS"] = ""
