"""
Deterministic Hebrew → Latin phonetics pipeline.

  unvocalized Hebrew  →  nakdimon (add nikud)  →  nikud_to_latin  →  Latin phonetics

Usage:
    from tgbot.pron import hebrew_to_latin_pron
    pron = hebrew_to_latin_pron("שלום")  # → "shalom"
"""

import re
import unicodedata

import nakdimon

# ---------------------------------------------------------------------------
# Character constants (explicit Unicode to avoid editor encoding issues)
# ---------------------------------------------------------------------------
_DAGESH   = 'ּ'  # dagesh / mapiq — also used as shuruk mark on vav
_SHIN_DOT = 'ׁ'  # shin dot (שׁ = sh)
_SIN_DOT  = 'ׂ'  # sin dot (שׂ = s)
_SHVA     = 'ְ'  # shva — silent at mid-word, vocal (= 'e') at word start
_HOLAM    = 'ֹ'  # holam khaser / holam male (on vav)

# Hebrew consonant → Latin phoneme (default, without dagesh)
_CONS: dict[str, str] = {
    'א': '',   'ב': 'v',  'ג': 'g',  'ד': 'd',  'ה': 'h',  'ו': 'v',
    'ז': 'z',  'ח': 'kh', 'ט': 't',  'י': 'y',  'כ': 'kh', 'ל': 'l',
    'מ': 'm',  'נ': 'n',  'ס': 's',  'ע': '',   'פ': 'f',  'צ': 'ts',
    'ק': 'k',  'ר': 'r',  'ש': 'sh', 'ת': 't',
    # Final forms
    'ך': 'kh', 'ם': 'm',  'ן': 'n',  'ף': 'f',  'ץ': 'ts',
}

# Nikud diacritic → vowel phoneme (U+05B0..U+05BB)
_VOWEL: dict[str, str] = {
    'ְ': '',   # shva — handled separately
    'ֱ': 'e',  # hataf segol
    'ֲ': 'a',  # hataf patakh
    'ֳ': 'o',  # hataf holam
    'ִ': 'i',  # khirik
    'ֵ': 'e',  # tsere
    'ֶ': 'e',  # segol
    'ַ': 'a',  # patakh
    'ָ': 'a',  # kamatz
    'ֹ': 'o',  # holam (khaser or male on vav)
    'ֺ': 'o',  # holam male
    'ֻ': 'u',  # kubuts
}

_HEBREW_CHARS = set(_CONS)
_DIAC_CATS = {'Mn', 'Mc', 'Me'}
_WORD_SPLIT = re.compile(r'([\s,.\-!?;:()\[\]«»"\']+)')


# ---------------------------------------------------------------------------
# Core word parser
# ---------------------------------------------------------------------------

def _word_to_latin(word: str, word_pos: int = 0) -> str:
    """
    Convert one vocalized Hebrew word to stressed Latin phonetics.

    Rules applied:
    - ו with holam (ֹ) or dagesh-as-shuruk (ּ) → mater lectionis (suppress 'v', emit 'o'/'u')
    - י with no own vowel, following a voweled letter → mater lectionis (suppress 'y')
    - ה with no vowel at word end → silent
    - shva at word-start (first consonant) → vocal 'e'
    - shva elsewhere → silent
    """
    chars = list(word)
    n = len(chars)
    syllables: list[str] = []  # completed syllables
    buf = ''                   # consonant phonemes waiting for a vowel
    prev_had_vowel = False     # True after a syllable with a real vowel was closed
    first_cons = True          # for vocal-shva rule at word start

    i = 0
    while i < n:
        c = chars[i]

        if c not in _HEBREW_CHARS:
            i += 1
            continue

        # Collect all diacritics immediately after this letter
        j = i + 1
        diacs: list[str] = []
        while j < n and unicodedata.category(chars[j]) in _DIAC_CATS:
            diacs.append(chars[j])
            j += 1
        i = j

        has_dagesh   = _DAGESH   in diacs
        has_shin_dot = _SHIN_DOT in diacs
        has_sin_dot  = _SIN_DOT  in diacs
        has_shva     = _SHVA     in diacs

        # ------------------------------------------------------------------
        # Determine if this letter is acting as a mater lectionis (silent
        # vowel carrier) rather than a consonant.
        # ------------------------------------------------------------------
        is_mater = False
        mater_vowel = ''

        if c == 'ו':
            if _HOLAM in diacs or 'ֺ' in diacs:   # holam / holam male
                is_mater, mater_vowel = True, 'o'
            elif has_dagesh:                            # dagesh inside vav = shuruk
                is_mater, mater_vowel = True, 'u'

        elif c == 'י' and prev_had_vowel:
            # Yod with no own vowel after a voweled syllable = mater for 'i'
            has_own_vowel = any(_VOWEL.get(d, '') for d in diacs if d != _DAGESH)
            if not has_own_vowel:
                is_mater = True   # silent yod; don't add vowel (it's already in prev syl)

        elif c == 'ה' and not first_cons and not any(_VOWEL.get(d, '') for d in diacs):
            # He with no vowel at non-initial position = silent (word-final ה is almost always mute)
            is_mater = True

        # ------------------------------------------------------------------
        # Consonant phoneme
        # ------------------------------------------------------------------
        if is_mater:
            cons = ''
        elif c == 'ש':
            cons = 's' if has_sin_dot else 'sh'
        elif has_dagesh and c in ('ב', 'כ', 'פ'):
            cons = {'ב': 'b', 'כ': 'k', 'פ': 'p'}[c]
        else:
            cons = _CONS.get(c, '')

        buf += cons

        # ------------------------------------------------------------------
        # Vowel for this syllable
        # ------------------------------------------------------------------
        if is_mater:
            vowel = mater_vowel
        elif has_shva:
            # Vocal shva only at very first consonant of the word
            vowel = 'e' if first_cons else ''
        else:
            vowel = ''
            for d in diacs:
                v = _VOWEL.get(d, None)
                if v is not None and v != '':
                    vowel = v
                    break

        first_cons = False

        if vowel:
            syllables.append(buf + vowel)
            buf = ''
            prev_had_vowel = True
        else:
            prev_had_vowel = False

    # Trailing consonants (word-final, no following vowel)
    if buf:
        if syllables:
            syllables[-1] += buf
        else:
            syllables.append(buf)

    if not syllables:
        return ''

    return ''.join(syllables)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def nikud_to_latin(vocalized_text: str) -> str:
    """Convert fully-vocalized Hebrew text to stressed Latin. Non-Hebrew tokens pass through."""
    parts = _WORD_SPLIT.split(vocalized_text)
    out: list[str] = []
    pos = 0
    for part in parts:
        if _WORD_SPLIT.match(part):
            out.append(part)
        elif any(c in _HEBREW_CHARS for c in part):
            out.append(_word_to_latin(part, pos))
        else:
            out.append(part)
        pos += len(part)
    return ''.join(out)


def hebrew_to_latin_pron(he_text: str) -> str:
    """Full pipeline: unvocalized Hebrew → nakdimon nikud → stressed Latin phonetics."""
    try:
        vocalized = nakdimon.diacritize(he_text)
    except Exception:
        return ''
    return nikud_to_latin(vocalized)
