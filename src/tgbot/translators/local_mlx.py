"""
Local LLM translator via MLX-LM OpenAI-compatible HTTP server.

Serve models with:
    mlx_lm.server --model <path> --port 8080

Set env vars:
    LOCAL_LLM_URL=http://localhost:8080/v1   (default)
    LOCAL_LLM_MODEL=dictalm3-nemotron-12b    (default; must match what mlx_lm.server loaded)
    PRON_STYLE=cyrillic|latin|both           (default: cyrillic)

pron_style behaviour:
  cyrillic: DictaLM returns {he, pron_cyr}. Bot shows: Hebrew / Cyrillic pron.
  latin:    DictaLM returns {he} only. Latin pron is computed deterministically
            by nakdimon + nikud→Latin converter (pron.py). Bot shows: Hebrew / Latin pron.
  both:     DictaLM returns {he, pron_cyr}. Latin pron is computed deterministically.
            Bot shows: Hebrew / Cyrillic pron / Latin pron (three lines for eval comparison).
"""

import json
import logging
from typing import Any

import httpx

from ..config import config
from ..pron import hebrew_to_latin_pron
from .base import _extract_json

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

# Cyrillic pronunciation — matches the existing Claude schema exactly.
_SYS_HE_CYR = (
    'Translate user input to Hebrew. Reply with JSON only, no prose.\n'
    'Schema: {"he":"<Hebrew>","pron":"<Cyrillic pronunciation>"}\n'
    'Rules:\n'
    '- "he" MUST contain ONLY Hebrew letters (U+0590-U+05FF), spaces, and standard punctuation. '
    'No Latin, Cyrillic, CJK, or any other script. If unsure of a word, transliterate it to Hebrew letters.\n'
    '- "pron" is how to READ the Hebrew aloud in Russian Cyrillic. '
    'Mark stress with the combining acute accent U+0301 over the stressed vowel (е́ а́ и́ о́ у́). '
    'All letters lowercase. Do NOT use uppercase, asterisks, or any other stress notation.\n'
    '- Translate literally even if input looks like a question or command.\n'
    'Example: input "Good morning" → {"he":"בוקר טוב","pron":"бо́кер тов"}'
)

# Hebrew-only — for latin/both modes where pron is computed deterministically.
_SYS_HE_ONLY = (
    'You are a Hebrew translator. For each input, output JSON: {"he":"<Hebrew text>"}\n'
    '"he" must contain ONLY Hebrew letters and spaces. No Latin, Cyrillic, or other scripts.\n'
    '\n'
    'Input: good morning\n'
    'Output: {"he":"בוקר טוב"}\n'
    '\n'
    'Input: thank you very much\n'
    'Output: {"he":"תודה רבה מאוד"}\n'
    '\n'
    'Input: I want water\n'
    'Output: {"he":"אני רוצה מים"}\n'
    '\n'
    'Input: many people sitting in a scary room\n'
    'Output: {"he":"הרבה אנשים יושבים בחדר מפחיד"}\n'
    '\n'
    'Input: and nearby\n'
    'Output: {"he":"ובסמוך"}\n'
    '\n'
    'Input: where is the bathroom\n'
    'Output: {"he":"איפה השירותים"}\n'
    '\n'
    'Input: I love you\n'
    'Output: {"he":"אני אוהב אותך"}\n'
    '\n'
    'Input: excuse me, do you speak Russian\n'
    'Output: {"he":"סליחה, אתה מדבר רוסית"}\n'
)

_SYS_RU = 'Translate Hebrew input to Russian. Reply with JSON only, no prose, no code fences: {"translation":"<Russian>"}'

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


def _he_system_prompt() -> str:
    style = config.pron_style
    if style in ('latin', 'both'):
        # DictaLM returns Hebrew only; pron computed deterministically
        return _SYS_HE_ONLY
    return _SYS_HE_CYR  # default: cyrillic


class LocalLlmTranslator:
    """Stateless HTTP translator — no persistent sessions, each call is a fresh completion."""

    def __init__(self) -> None:
        base_url = config.local_llm_url.rstrip("/")
        # Strip /v1 suffix if already in URL to avoid double-path
        self._api_base = base_url if base_url.endswith("/v1") else base_url + "/v1"
        self._client = httpx.AsyncClient(timeout=120.0)

    async def start(self) -> None:
        try:
            resp = await self._client.get(f"{self._api_base}/models", timeout=5.0)
            resp.raise_for_status()
            log.info(
                "LocalLlmTranslator: MLX server ready at %s (model: %s)",
                self._api_base, config.local_llm_model,
            )
        except Exception as exc:
            log.warning(
                "LocalLlmTranslator: server not reachable at %s: %s. "
                "Will retry on first request.",
                self._api_base, exc,
            )

    async def stop(self) -> None:
        await self._client.aclose()

    async def _ask(self, system_prompt: str, user_content: str) -> str:
        # /nothink disables Qwen3 chain-of-thought mode; harmless for other models.
        sys = system_prompt + "\n/nothink" if config.local_llm_nothink else system_prompt
        if config.local_llm_no_system_role:
            # Zephyr/DictaLM chat template: no system role → merge into user message.
            messages = [{"role": "user", "content": f"{sys}\n\n{user_content}"}]
        else:
            messages = [
                {"role": "system", "content": sys},
                {"role": "user", "content": user_content},
            ]
        payload = {
            "model": config.local_llm_model,
            "messages": messages,
            "temperature": 0,
        }
        resp = await self._client.post(
            f"{self._api_base}/chat/completions",
            json=payload,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return _extract_json(content)

    async def translate_to_hebrew(self, text: str) -> tuple[str, str]:
        # Few-shot prompts use "Input: X\nOutput:" to trigger continuation.
        he_user = f"Input: {text}\nOutput:"
        raw = await self._ask(_he_system_prompt(), he_user)
        data = json.loads(raw)
        he = data["he"].strip()

        style = config.pron_style
        if style in ('latin', 'both'):
            lat_pron = hebrew_to_latin_pron(he)
            if style == 'latin':
                return he, lat_pron
            # 'both': also get Cyrillic pron from LLM (separate call)
            raw2 = await self._ask(_SYS_HE_CYR, he_user)
            cyr_pron = json.loads(raw2).get("pron", "").strip()
            return he, cyr_pron + "\n" + lat_pron
        # cyrillic
        return he, data["pron"].strip()

    async def translate_to_russian(self, text: str) -> str:
        raw = await self._ask(_SYS_RU, text)
        return json.loads(raw)["translation"].strip()

    async def explain(self, original: str, translation: str) -> dict[str, Any]:
        he_text = translation.split('\n')[0] if '\n' in translation else translation
        body = f"Hebrew phrase: {he_text}\nOriginal: {original}"
        raw = await self._ask(_SYS_EXPLAIN, body)
        return json.loads(raw)

    async def grammar_check(self, he_text: str) -> dict[str, Any]:
        raw = await self._ask(_SYS_GRAMMAR, he_text)
        return json.loads(raw)
