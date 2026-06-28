"""
Translator factory.

Reads TRANSLATOR_BACKEND (default: claude) and optional TRANSLATOR_TASK_BACKENDS
(JSON map of task→backend) from config and returns the appropriate implementation.

Backends:
    claude  — AgentSdkTranslator (persistent claude-agent-sdk sessions)
    local   — LocalLlmTranslator (stateless httpx calls to mlx_lm.server)

Per-task routing example (post-eval hybrid):
    TRANSLATOR_BACKEND=claude
    TRANSLATOR_TASK_BACKENDS={"translate_to_hebrew": "local"}

This would route HE translation to the local model while keeping
Russian-output tasks (translate_to_russian, explain, grammar_check) on Claude.
"""

import logging
from typing import Any

from ..config import config
from .base import Translator, _extract_json
from .claude_agent import AgentSdkTranslator
from .local_mlx import LocalLlmTranslator

log = logging.getLogger(__name__)

__all__ = [
    "Translator",
    "_extract_json",
    "AgentSdkTranslator",
    "LocalLlmTranslator",
    "make_translator",
]

_TASK_METHODS = (
    "translate_to_hebrew",
    "translate_to_russian",
    "explain",
    "grammar_check",
)


def _make_single(backend: str) -> AgentSdkTranslator | LocalLlmTranslator:
    if backend == "local":
        return LocalLlmTranslator()
    return AgentSdkTranslator()


class _RoutingTranslator:
    """
    Dispatches each method to the backend specified in task_map.
    Falls back to the default backend for unmapped tasks.
    """

    def __init__(
        self,
        task_map: dict[str, str],
        default_backend: str,
    ) -> None:
        self._default_backend = default_backend
        self._task_map = task_map
        # Build only the backends actually needed
        needed = set(task_map.values()) | {default_backend}
        self._backends: dict[str, Any] = {b: _make_single(b) for b in needed}
        log.info(
            "RoutingTranslator: default=%s task_overrides=%s",
            default_backend, task_map,
        )

    def _backend_for(self, task: str) -> Any:
        return self._backends[self._task_map.get(task, self._default_backend)]

    async def start(self) -> None:
        for b in self._backends.values():
            await b.start()

    async def stop(self) -> None:
        for b in self._backends.values():
            await b.stop()

    async def translate_to_hebrew(self, text: str) -> tuple[str, str]:
        return await self._backend_for("translate_to_hebrew").translate_to_hebrew(text)

    async def translate_to_russian(self, text: str) -> str:
        return await self._backend_for("translate_to_russian").translate_to_russian(text)

    async def explain(self, original: str, translation: str) -> dict[str, Any]:
        return await self._backend_for("explain").explain(original, translation)

    async def grammar_check(self, he_text: str) -> dict[str, Any]:
        return await self._backend_for("grammar_check").grammar_check(he_text)


def make_translator() -> Any:
    """
    Factory: return the translator selected by config.

    If TRANSLATOR_TASK_BACKENDS is set (non-empty JSON object), returns a
    _RoutingTranslator that dispatches per task. Otherwise returns a single backend.
    """
    task_map: dict[str, str] = {}
    if config.translator_task_backends:
        import json
        raw = config.translator_task_backends
        try:
            task_map = json.loads(raw)
        except Exception:
            log.warning("TRANSLATOR_TASK_BACKENDS is not valid JSON, ignoring: %r", raw)

    # Validate keys
    invalid = set(task_map) - set(_TASK_METHODS)
    if invalid:
        log.warning("Unknown task keys in TRANSLATOR_TASK_BACKENDS (ignored): %s", invalid)
        for k in invalid:
            del task_map[k]

    if task_map:
        return _RoutingTranslator(task_map, config.translator_backend)

    backend = config.translator_backend
    log.info("Translator backend: %s", backend)
    return _make_single(backend)
