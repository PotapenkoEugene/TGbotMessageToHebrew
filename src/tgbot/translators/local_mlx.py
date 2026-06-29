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

Echo-detection + retry:
  On short or ambiguous input, the small local model may collapse and copy a few-shot
  example verbatim.  translate_to_hebrew detects this and retries up to 3 attempts,
  each with a higher temperature and (on retry 2+) with the trailing attractor example
  stripped from the prompt.
"""

import json
import logging
from typing import Any

import httpx

from ..config import config
from ..pron import hebrew_to_latin_pron
from .base import _extract_json, _normalize_en, _normalize_he, he_problem

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

# ---------------------------------------------------------------------------
# Few-shot prompt for latin/both modes — single source of truth.
# The echo-detection set (_HE_ECHO_OUTPUTS) is derived from _HE_EXAMPLES so
# adding/removing/reordering examples automatically keeps detection in sync.
#
# IMPORTANT: keep the trailing "attractor" example (the one whose Hebrew is most
# likely to be echoed by a weak model) LAST — it is stripped on retry attempts 2+
# via _he_system_prompt(strip_attractor=True).
# ---------------------------------------------------------------------------

_HE_HEADER = (
    'You are a Hebrew translator. For each input, output JSON: {"he":"<Hebrew text>"}\n'
    '"he" must contain ONLY Hebrew letters and spaces. No Latin, Cyrillic, or other scripts.\n'
)

_HE_TASK_LINE = 'Translate the next input the same way. Output JSON only.\n'

# (English input, Hebrew output) — order matters; attractor stays last.
_HE_EXAMPLES: list[tuple[str, str]] = [
    ("good morning", "בוקר טוב"),
    ("thank you very much", "תודה רבה מאוד"),
    ("I want water", "אני רוצה מים"),
    ("where is the bathroom", "איפה השירותים"),
    ("I love you", "אני אוהב אותך"),
    # trailing attractor: stripped on retry to reduce verbatim-copy risk
    ("excuse me, do you speak Russian", "סליחה, אתה מדבר רוסית"),
]

# Pre-computed sets for echo detection (module-level, computed once).
_HE_ECHO_OUTPUTS: frozenset[str] = frozenset(_normalize_he(o) for _, o in _HE_EXAMPLES)
_HE_FEWSHOT_PAIRS: dict[str, str] = {
    _normalize_en(i): _normalize_he(o) for i, o in _HE_EXAMPLES
}

# Cyrillic-prompt echo set (single inline example in _SYS_HE_CYR).
_HE_CYR_ECHO_OUTPUTS: frozenset[str] = frozenset({_normalize_he("בוקר טוב")})


def _build_he_prompt(examples: list[tuple[str, str]]) -> str:
    blocks = "\n".join(f'Input: {inp}\nOutput: {{"he":"{out}"}}\n' for inp, out in examples)
    return f"{_HE_HEADER}\n{blocks}\n{_HE_TASK_LINE}"


def _he_system_prompt(strip_attractor: bool = False) -> str:
    """Return the appropriate HE system prompt for the current pron_style."""
    style = config.pron_style
    if style in ('latin', 'both'):
        examples = _HE_EXAMPLES[:-1] if strip_attractor else _HE_EXAMPLES
        return _build_he_prompt(examples)
    return _SYS_HE_CYR  # default: cyrillic


# ---------------------------------------------------------------------------
# Retry schedule: (temperature, strip_attractor).
# Attempt 0 = baseline (temp=0, full prompt).
# Attempts 1+ raise temperature and strip the trailing attractor.
# Each attempt therefore produces different output even on a deterministic model.
# ---------------------------------------------------------------------------

_HE_RETRY_SCHEDULE: list[tuple[float, bool]] = [
    (0.0, False),
    (0.3, True),
    (0.7, True),
]

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


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

def _log_attempt(
    input_text: str,
    attempt: int,
    temperature: float,
    strip_attractor: bool,
    *,
    raw: str | None,
    he: str | None,
    reason: str | None,
    ok: bool,
) -> None:
    fields = dict(
        event="he_attempt",
        backend="local",
        model=config.local_llm_model,
        pron_style=config.pron_style,
        attempt=attempt,
        total=len(_HE_RETRY_SCHEDULE),
        temperature=temperature,
        strip_attractor=strip_attractor,
        input=input_text,
        raw=raw,
        he=he,
        reason=reason,
        ok=ok,
    )
    if ok:
        log.debug("he_attempt ok: %s", fields)
    else:
        log.warning("he_attempt problem detected: %s", fields)


def _log_exhausted(
    input_text: str,
    *,
    parsed_any: bool,
    stable: bool,
    reason: str | None = None,
    final_he: str | None = None,
    final_pron: str | None = None,
) -> None:
    fields = dict(
        event="he_exhausted",
        backend="local",
        model=config.local_llm_model,
        pron_style=config.pron_style,
        input=input_text,
        parsed_any=parsed_any,
        stable=stable,
        final_reason=reason,
        final_he=final_he,
        final_pron=final_pron,
    )
    if stable:
        # Stable = same output every retry (likely a genuine common greeting); log as warning.
        log.warning("he_exhausted (stable, returning last): %s", fields)
    else:
        log.error("he_exhausted (changed every retry, returning last): %s", fields)


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

    async def _ask(
        self,
        system_prompt: str,
        user_content: str,
        *,
        temperature: float | None = None,
    ) -> str:
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
            "temperature": 0 if temperature is None else temperature,
        }
        resp = await self._client.post(
            f"{self._api_base}/chat/completions",
            json=payload,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        return _extract_json(content)

    async def _finish_he_async(
        self,
        data: dict,
        he: str,
        style: str,
        he_user: str,
    ) -> tuple[str, str]:
        """Build final (he, pron) from a parsed dict + computed pron for latin/both."""
        if style in ('latin', 'both'):
            lat_pron = hebrew_to_latin_pron(he)
            if style == 'latin':
                return he, lat_pron
            # 'both': also get Cyrillic pron from LLM
            raw2 = await self._ask(_SYS_HE_CYR, he_user)
            cyr_pron = json.loads(raw2).get("pron", "").strip()
            return he, cyr_pron + "\n" + lat_pron
        # cyrillic
        return he, data.get("pron", "").strip()

    async def translate_to_hebrew(self, text: str) -> tuple[str, str]:
        he_user = f"Input: {text}\nOutput:"
        style = config.pron_style
        cyr = style not in ('latin', 'both')
        echo_outputs = _HE_CYR_ECHO_OUTPUTS if cyr else _HE_ECHO_OUTPUTS

        last_valid: dict | None = None
        last_reason: str | None = None
        last_exc: Exception | None = None
        last_he: str | None = None
        seen_he: list[str] = []

        for attempt, (temp, strip) in enumerate(_HE_RETRY_SCHEDULE):
            prompt = _SYS_HE_CYR if cyr else _he_system_prompt(strip_attractor=strip)
            raw: str | None = None
            he: str | None = None
            try:
                raw = await self._ask(prompt, he_user, temperature=temp)
                data = json.loads(raw)
                he = data["he"].strip()
            except Exception as exc:
                last_exc = exc
                _log_attempt(text, attempt, temp, strip, raw=raw, he=None,
                             reason="parse_error", ok=False)
                continue

            reason = he_problem(
                he, text,
                echo_outputs=echo_outputs,
                fewshot_pairs=_HE_FEWSHOT_PAIRS,
            )
            _log_attempt(text, attempt, temp, strip, raw=raw, he=he,
                         reason=reason, ok=(reason is None))

            last_valid = data
            last_reason = reason
            last_he = he
            seen_he.append(_normalize_he(he))

            if reason is None:
                return await self._finish_he_async(data, he, style, he_user)

        # --- Exhausted all attempts ---
        if last_valid is None:
            # Never got a parseable response; re-raise so handler sends no reply
            # (better than emitting garbage).
            _log_exhausted(text, parsed_any=False, stable=False, reason="parse_error")
            raise last_exc or RuntimeError("all HE translation attempts failed to parse")

        stable = len(set(seen_he)) == 1
        assert last_he is not None  # invariant: set whenever last_valid is set
        _log_exhausted(
            text,
            parsed_any=True,
            stable=stable,
            reason=last_reason,
            final_he=last_he,
        )
        # Return the last parseable Hebrew anyway — user gets something usable.
        return await self._finish_he_async(last_valid, last_he, style, he_user)

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
