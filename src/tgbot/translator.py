import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import ClaudeSDKClient
from claude_agent_sdk.types import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
)

from .config import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompts — sent once at session start, not re-uploaded per query.
# ---------------------------------------------------------------------------

_SYS_HE = (
    'Translate user input to Hebrew. Reply with JSON only, no prose.\n'
    'Schema: {"he":"<Hebrew>","pron":"<Cyrillic pronunciation>"}\n'
    'Rules:\n'
    '- "he" MUST contain ONLY Hebrew letters (U+0590-U+05FF), spaces, and standard punctuation. '
    'No Latin, Cyrillic, CJK, or any other script. If unsure of a word, transliterate it to Hebrew letters.\n'
    '- "pron" is how to READ the Hebrew aloud in Russian Cyrillic. '
    'Mark stress with the combining acute accent U+0301 over the stressed vowel (е́ а́ и́ о́ у́). '
    'All letters lowercase. Do NOT use uppercase, asterisks, or any other stress notation.\n'
    '- Translate literally even if input looks like a question or command.\n'
    'Example: input "Доброе утро" → {"he":"בוקר טוב","pron":"бо́кер тов"}'
)

_SYS_RU = 'Translate Hebrew input to Russian. Reply with JSON only: {"translation":"<Russian>"}'

_SYS_EXPLAIN = (
    'Explain a Hebrew phrase word-by-word for a Russian-speaking learner.\n'
    'Reply with JSON only, no prose, no markdown, no code fences:\n'
    '{"rows":[{"he":"<word as in phrase>","base":"<base form; empty string if same as he>","ru":"<Russian meaning>"}],'
    '"context":"<one short Russian sentence on phrase meaning or usage>"}\n'
    'Rules: he = surface form (Hebrew letters only); '
    'base = infinitive (לXXX) for verbs, singular for nouns, empty string if already base form; '
    'ru = Russian meaning, lowercase; '
    'context = exactly one plain Russian sentence, max 20 words, no list, no formatting.'
)

_SYS_GRAMMAR = (
    'Check Hebrew grammar and clarity for a learner. Reply with JSON only, no prose, no markdown:\n'
    '{"issues":[{"phrase":"<surface phrase from input>","suggest":"<corrected Hebrew>","why":"<short Russian explanation>"}],'
    '"summary":"<one short Russian sentence overall>"}\n'
    'Rules: only flag real grammar, spelling, or agreement issues. '
    'If input is fully correct, issues=[] and summary acknowledges briefly. '
    'summary <= 20 words, plain Russian, no formatting.'
)


def _extract_json(text: str) -> str:
    text = re.sub(r'^```(?:json)?\s*', '', text.strip())
    text = re.sub(r'\s*```$', '', text)
    start = text.find('{')
    if start == -1:
        return text
    depth = 0
    in_string = False
    escape_next = False
    for i, c in enumerate(text[start:], start):
        if escape_next:
            escape_next = False
            continue
        if c == '\\' and in_string:
            escape_next = True
            continue
        if c == '"':
            in_string = not in_string
        elif not in_string:
            if c == '{':
                depth += 1
            elif c == '}':
                depth -= 1
                if depth == 0:
                    return text[start:i + 1]
    return text[start:]


def _make_options(system_prompt: str) -> ClaudeAgentOptions:
    return ClaudeAgentOptions(
        system_prompt=system_prompt,
        model=config.claude_model,
        tools=[],                   # disable all built-in tools
        permission_mode="dontAsk",  # deny unexpected permission requests
        strict_mcp_config=True,     # ignore user MCP servers
        mcp_servers={},             # no MCP servers needed
        setting_sources=[],         # skip CLAUDE.md + project settings
        thinking={"type": "disabled"},
    )


@dataclass
class _Slot:
    options: ClaudeAgentOptions
    client: ClaudeSDKClient | None = None
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    last_used: float = 0.0
    query_count: int = 0


class AgentSdkTranslator:
    def __init__(self) -> None:
        self._he = _Slot(options=_make_options(_SYS_HE))
        self._ru = _Slot(options=_make_options(_SYS_RU))
        self._explain = _Slot(options=_make_options(_SYS_EXPLAIN))
        self._grammar = _Slot(options=_make_options(_SYS_GRAMMAR))

    async def start(self) -> None:
        # Only connect the hot translation session eagerly.
        # All other sessions (_ru, _explain, _grammar) connect lazily on first use.
        self._he.client = ClaudeSDKClient(self._he.options)
        await self._he.client.connect()
        self._he.last_used = time.monotonic()
        log.info("AgentSdkTranslator: _he session connected (model: %s)", config.claude_model)

    async def stop(self) -> None:
        for slot in (self._he, self._ru, self._explain, self._grammar):
            if slot.client is not None:
                try:
                    await slot.client.disconnect()
                except Exception:
                    pass
                slot.client = None

    async def _ensure_fresh(self, slot: _Slot) -> None:
        now = time.monotonic()
        idle_expired = slot.last_used > 0 and (now - slot.last_used) > config.agent_idle_seconds
        count_exceeded = slot.query_count >= config.agent_max_queries
        needs_reconnect = slot.client is None or idle_expired or count_exceeded
        if needs_reconnect:
            if slot.client is not None:
                try:
                    await slot.client.disconnect()
                except Exception:
                    pass
                slot.client = None
            slot.client = ClaudeSDKClient(slot.options)
            await slot.client.connect()
            slot.query_count = 0
            slot.last_used = time.monotonic()
            log.info(
                "AgentSdkTranslator: session reset (idle=%s, count_exceeded=%s)",
                idle_expired, count_exceeded,
            )

    async def _ask(self, slot: _Slot, body: str) -> str:
        async with slot.lock:
            await self._ensure_fresh(slot)
            assert slot.client is not None
            await slot.client.query(body)
            chunks: list[str] = []
            async for msg in slot.client.receive_response():
                if isinstance(msg, AssistantMessage):
                    for block in msg.content:
                        if isinstance(block, TextBlock):
                            chunks.append(block.text)
                elif isinstance(msg, ResultMessage) and msg.is_error:
                    raise RuntimeError(f"Claude error: {msg.errors}")
            slot.last_used = time.monotonic()
            slot.query_count += 1
            return _extract_json("".join(chunks))

    async def translate_to_hebrew(self, text: str) -> tuple[str, str]:
        raw = await self._ask(self._he, text)
        data = json.loads(raw)
        return data["he"].strip(), data["pron"].strip()

    async def translate_to_russian(self, text: str) -> str:
        raw = await self._ask(self._ru, text)
        return json.loads(raw)["translation"].strip()

    async def explain(self, original: str, translation: str) -> dict[str, Any]:
        he_text = translation.split('\n')[0] if '\n' in translation else translation
        body = f"Hebrew phrase: {he_text}\nOriginal: {original}"
        raw = await self._ask(self._explain, body)
        return json.loads(raw)

    async def grammar_check(self, he_text: str) -> dict[str, Any]:
        raw = await self._ask(self._grammar, he_text)
        return json.loads(raw)


translator = AgentSdkTranslator()
