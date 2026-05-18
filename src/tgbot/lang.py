import re

from langdetect import detect, LangDetectException

_HE_BLOCK = range(0x0590, 0x0600)  # Hebrew Unicode block
_CY_BLOCK = range(0x0400, 0x0500)  # Cyrillic Unicode block


def _has_hebrew(text: str) -> bool:
    return any(ord(c) in _HE_BLOCK for c in text)


def _has_cyrillic(text: str) -> bool:
    return any(ord(c) in _CY_BLOCK for c in text)


def detect_lang(text: str) -> str:
    """Return 'he', 'ru', 'en', or 'other'."""
    if _has_hebrew(text):
        return "he"
    # Cyrillic block check is more reliable than langdetect for short texts.
    # All Cyrillic-script messages are routed to Hebrew — close enough for this bot.
    if _has_cyrillic(text):
        return "ru"
    try:
        lang = detect(text)
    except LangDetectException:
        return "other"
    if lang == "en":
        return "en"
    return "other"


def route(src_lang: str) -> tuple[str, str] | None:
    """Return (src, tgt) pair or None if should not translate."""
    if src_lang == "he":
        return ("he", "ru")
    if src_lang in ("ru", "en"):
        return (src_lang, "he")
    return None


def extract_hebrew_words(text: str) -> list[str]:
    """Tokenize Hebrew words from mixed text. Returns runs of Hebrew chars, length >= 2."""
    tokens = re.split(r'[^֐-׿]+', text)
    return [t for t in tokens if len(t) >= 2]
