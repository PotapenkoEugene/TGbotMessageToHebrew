"""
Shared utilities and Translator protocol.

Both AgentSdkTranslator and LocalLlmTranslator implement Translator.
_extract_json is a shared fence-stripping / brace-matching helper.
Detection helpers (is_hebrew_script, _normalize_he, _normalize_en, he_problem)
validate parsed Hebrew output and detect few-shot echo / script leakage.
"""

import re
import unicodedata
from typing import Any, Protocol, runtime_checkable

# Hebrew script block: U+0590–U+05FF (letters, nikud, cantillation, punctuation)
_HE_BLOCK_START = 0x0590
_HE_BLOCK_END = 0x05FF


def _normalize_he(s: str) -> str:
    """NFC, strip, drop Unicode punctuation, collapse internal whitespace."""
    s = unicodedata.normalize("NFC", s).strip()
    s = "".join(c for c in s if not unicodedata.category(c).startswith("P"))
    return " ".join(s.split())


def _normalize_en(s: str) -> str:
    """Lowercase, strip, drop punctuation, collapse whitespace. For fewshot-pair lookup."""
    s = s.lower().strip()
    s = "".join(c for c in s if not unicodedata.category(c).startswith("P"))
    return " ".join(s.split())


def is_hebrew_script(he: str) -> bool:
    """True if he has >=1 Hebrew letter and NO Latin/Cyrillic/CJK alphabetic characters.

    Digits, spaces, and punctuation are ignored — only alphabetic characters matter.
    """
    has_he = False
    for c in he:
        cp = ord(c)
        if _HE_BLOCK_START <= cp <= _HE_BLOCK_END:
            has_he = True
        elif c.isalpha():
            # Any alphabetic character outside the Hebrew block = script leakage
            return False
    return has_he


def he_problem(
    he: str,
    input_text: str,
    *,
    echo_outputs: "frozenset[str]",
    fewshot_pairs: "dict[str, str]",
    length_check: bool = False,
) -> "str | None":
    """Return a reason code or None if he looks like a valid translation.

    Reason codes:
      'non_hebrew'   — he contains Latin/Cyrillic/CJK letters or has no Hebrew at all
      'echo'         — he exactly matches a known few-shot example output
      'length_ratio' — suspiciously long output for a very short input (only when length_check=True)

    Edge-case exemption: if the user literally typed the source phrase of a fewshot pair,
    the matching output is genuine — return None rather than 'echo'.
    """
    if not is_hebrew_script(he):
        return "non_hebrew"
    norm = _normalize_he(he)
    if norm in echo_outputs:
        # Genuine input? Check if input maps to this exact Hebrew in the fewshot pairs.
        if fewshot_pairs.get(_normalize_en(input_text)) == norm:
            return None
        return "echo"
    if length_check:
        in_words = len(input_text.split())
        out_words = len(he.split())
        if in_words <= 2 and out_words >= 4:
            return "length_ratio"
    return None


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
