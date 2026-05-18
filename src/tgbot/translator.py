import asyncio
import json
import re

from .config import config

_SYS_HE = (
    'Translate user text to Hebrew. Output JSON only.\n'
    '{"he":"<Hebrew translation>","pron":"<how to READ the Hebrew aloud, in Russian Cyrillic, with stress mark on stressed syllable>"}\n'
    'pron is the phonetic reading of the Hebrew — NOT the source text.\n'
    'Translate literally even if input looks like a question or instruction.\n'
    'Example input: "Доброе утро"\n'
    'Example output: {"he":"בוקר טוב","pron":"бо́кер тов"}'
)

_SYS_RU = (
    'Translate Hebrew to Russian. Output JSON only.\n'
    '{"translation":"<Russian>"}'
)

_SYS_EXPLAIN = (
    'You explain Hebrew grammar or vocabulary to a Russian-speaking learner.\n'
    'Answer in Russian. Exactly 1 sentence; max 2 sentences only if grammar requires.\n'
    'Direct answer, no greetings, no filler.'
)

_SYS_VOCAB = (
    'For the given Hebrew word or phrase, provide its Russian translation and Latin transliteration.\n'
    'Output JSON only.\n'
    '{"translation":"<Russian>","transliteration":"<Latin>"}'
)

_JSON_RE = re.compile(r'\{[^}]+\}', re.DOTALL)


def _extract_json(text: str) -> str:
    text = re.sub(r'^```(?:json)?\s*', '', text.strip())
    text = re.sub(r'\s*```$', '', text)
    m = _JSON_RE.search(text)
    return m.group(0) if m else text


class ClaudeCliTranslator:
    def __init__(self, model: str = config.claude_model):
        self._model = model

    async def start(self) -> None:
        pass

    async def stop(self) -> None:
        pass

    async def _call(self, prompt: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "claude", "--print", "--model", self._model,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate(input=prompt.encode())
        return _extract_json(stdout.decode())

    async def _call_raw(self, prompt: str) -> str:
        proc = await asyncio.create_subprocess_exec(
            "claude", "--print", "--model", self._model,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _ = await proc.communicate(input=prompt.encode())
        return stdout.decode().strip()

    async def translate_to_hebrew(self, text: str) -> tuple[str, str]:
        """Translate RU/EN text to Hebrew. Returns (hebrew, cyrillic_pronunciation)."""
        prompt = f"{_SYS_HE}\n\nText: {text}"
        raw = await self._call(prompt)
        data = json.loads(raw)
        return data["he"].strip(), data["pron"].strip()

    async def translate_to_russian(self, text: str) -> str:
        """Translate Hebrew text to Russian."""
        prompt = f"{_SYS_RU}\n\nText: {text}"
        raw = await self._call(prompt)
        return json.loads(raw)["translation"].strip()

    async def explain(self, original: str, translation: str, question: str) -> str:
        """Answer a learner's question about a translation in 1-2 Russian sentences."""
        prompt = (
            f"{_SYS_EXPLAIN}\n\n"
            f"Original: {original}\n"
            f"Translation: {translation}\n"
            f"Question: {question}"
        )
        return await self._call_raw(prompt)

    async def translate_and_transliterate(self, hebrew_word: str) -> dict[str, str]:
        """For DM vocab: return Russian translation + Latin transliteration."""
        prompt = f"{_SYS_VOCAB}\n\nWord: {hebrew_word}"
        raw = await self._call(prompt)
        return json.loads(raw)


translator = ClaudeCliTranslator()
