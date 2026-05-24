import pytest
from tgbot.format import build_explain_table


_SAMPLE = {
    "rows": [
        {"he": "הולך", "base": "ללכת", "pron": "холе́х", "ru": "идёт"},
        {"he": "הביתה", "base": "", "pron": "хабайта́", "ru": "домой"},
    ],
    "context": "Фраза означает «идёт домой».",
}


def test_output_wrapped_in_pre():
    out = build_explain_table(_SAMPLE)
    assert out.startswith("<pre>")
    assert "</pre>" in out


def test_context_appended_after_pre():
    out = build_explain_table(_SAMPLE)
    pre_end = out.index("</pre>")
    assert "идёт домой" in out[pre_end:]


def test_headers_present():
    out = build_explain_table(_SAMPLE)
    for header in ("Слово", "База", "Произн.", "Перевод"):
        assert header in out


def test_all_rows_present():
    out = build_explain_table(_SAMPLE)
    assert "הולך" in out
    assert "ללכת" in out
    assert "холе́х" in out
    assert "идёт" in out
    assert "הביתה" in out
    assert "хабайта́" in out


def test_html_escaped():
    payload = {
        "rows": [{"he": "א", "base": "", "pron": "а́леф", "ru": "буква & <знак>"}],
        "context": "Контекст с <тегом>.",
    }
    out = build_explain_table(payload)
    assert "&amp;" in out or "<тегом>" not in out
    assert "&lt;" in out


def test_empty_rows():
    out = build_explain_table({"rows": [], "context": "Нет слов."})
    assert "<pre>" in out
    assert "Нет слов." in out


def test_no_context():
    payload = {
        "rows": [{"he": "שלום", "base": "", "pron": "шало́м", "ru": "мир"}],
        "context": "",
    }
    out = build_explain_table(payload)
    assert out.endswith("</pre>")


# --- Trigger filter logic (pure string, no async needed) ---

def _trigger(text: str) -> str:
    return text.strip().rstrip('!.?…').strip().lower()


@pytest.mark.parametrize("text,expected", [
    ("объясни", "объясни"),
    ("Объясни", "объясни"),
    ("ОБЪЯСНИ", "объясни"),
    ("Объясни!", "объясни"),
    ("объясни.", "объясни"),
    ("объясни?", "объясни"),
    ("объясни…", "объясни"),
    ("объясни это", "объясни это"),
    ("привет", "привет"),
])
def test_trigger_normalization(text, expected):
    assert _trigger(text) == expected


def test_trigger_passes_only_exact():
    passing = ["объясни", "Объясни!", "объясни.", "объясни?", "ОБЪЯСНИ"]
    failing = ["объясни пожалуйста", "привет", "объясни это", " "]
    for t in passing:
        assert _trigger(t) == "объясни", f"Should pass: {t!r}"
    for t in failing:
        assert _trigger(t) != "объясни", f"Should fail: {t!r}"
