import httpx

from .config import config

_LANG_NAME = {"he": "Hebrew", "ru": "Russian", "en": "English"}

_SYSTEM_PROMPT = "You are a translator. Output ONLY the translation, no explanation, no notes, no quotes."


def _user_prompt(text: str, src: str, tgt: str) -> str:
    return f"Translate the following {_LANG_NAME[src]} text to {_LANG_NAME[tgt]}:\n\n{text}"


class OllamaTranslator:
    def __init__(self, base_url: str = config.ollama_url, model: str = config.ollama_model):
        self._url = base_url.rstrip("/") + "/api/chat"
        self._model = model
        self._client: httpx.AsyncClient | None = None

    async def start(self) -> None:
        self._client = httpx.AsyncClient(timeout=60.0)

    async def stop(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def translate(self, text: str, src: str, tgt: str) -> str:
        assert self._client is not None, "call start() first"
        payload = {
            "model": self._model,
            "stream": False,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": _user_prompt(text, src, tgt)},
            ],
        }
        resp = await self._client.post(self._url, json=payload)
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()

    async def translate_and_transliterate(self, hebrew_word: str) -> dict[str, str]:
        """For vocab: return {'translation': ..., 'transliteration': ...}"""
        assert self._client is not None, "call start() first"
        prompt = (
            f"For the Hebrew word or phrase «{hebrew_word}» provide:\n"
            "1. Russian translation\n"
            "2. Transliteration into Latin letters\n"
            "Reply in exactly this JSON format with no other text:\n"
            '{"translation": "...", "transliteration": "..."}'
        )
        payload = {
            "model": self._model,
            "stream": False,
            "messages": [
                {"role": "system", "content": "You are a Hebrew language assistant. Output only valid JSON."},
                {"role": "user", "content": prompt},
            ],
        }
        resp = await self._client.post(self._url, json=payload)
        resp.raise_for_status()
        import json

        raw = resp.json()["message"]["content"].strip()
        # Strip markdown code fences if model adds them
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())


translator = OllamaTranslator()
