"""
Shared utilities and Translator protocol.

Both AgentSdkTranslator and LocalLlmTranslator implement Translator.
_extract_json is a shared fence-stripping / brace-matching helper.
"""

import re
from typing import Any, Protocol, runtime_checkable


def _extract_json(text: str) -> str:
    """Strip markdown fences and extract the first complete JSON object."""
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


@runtime_checkable
class Translator(Protocol):
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    async def translate_to_hebrew(self, text: str) -> tuple[str, str]: ...
    async def translate_to_russian(self, text: str) -> str: ...
    async def explain(self, original: str, translation: str) -> dict[str, Any]: ...
    async def grammar_check(self, he_text: str) -> dict[str, Any]: ...
