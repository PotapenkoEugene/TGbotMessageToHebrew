import pytest
from tgbot.format import build_explain_table, build_grammar_reply


_SAMPLE = {
    "rows": [
        {"he": "הולך", "base": "ללכת", "ru": "идёт"},
        {"he": "הביתה", "base": "", "ru": "домой"},
    ],
    "context": "Фраза означает «идёт домой».",
}


# --- build_explain_table ---

def test_row_with_base():
    out = build_explain_table(_SAMPLE)
    assert "הולך — идёт — ללכת" in out


def test_row_without_base():
    out = build_explain_table(_SAMPLE)
    assert "הביתה — домой" in out
    assert "הביתה — домой —" not in out


def test_context_appended():
    out = build_explain_table(_SAMPLE)
    assert "идёт домой" in out


def test_no_table_chars():
    out = build_explain_table(_SAMPLE)
    assert "|" not in out
    assert "-+-" not in out
    assert "<pre>" not in out


def test_html_escaped():
    payload = {
        "rows": [{"he": "א", "base": "", "ru": "буква & <знак>"}],
        "context": "Контекст с <тегом>.",
    }
    out = build_explain_table(payload)
    assert "&amp;" in out
    assert "&lt;" in out


def test_empty_rows():
    out = build_explain_table({"rows": [], "context": "Нет слов."})
    assert "Нет слов." in out


def test_no_context():
    payload = {
        "rows": [{"he": "שלום", "base": "", "ru": "мир"}],
        "context": "",
    }
    out = build_explain_table(payload)
    assert "שלום — мир" in out
    assert "\n\n" not in out


def test_pron_field_shown():
    payload = {
        "rows": [{"he": "שלום", "base": "", "pron": "shaLOM", "ru": "мир"}],
        "context": "",
    }
    out = build_explain_table(payload)
    assert "שלום [shaLOM] — мир" in out


def test_pron_with_base():
    payload = {
        "rows": [{"he": "הולך", "base": "ללכת", "pron": "hoLECH", "ru": "идёт"}],
        "context": "",
    }
    out = build_explain_table(payload)
    assert "הולך [hoLECH] — идёт — ללכת" in out


def test_pron_absent_no_brackets():
    payload = {
        "rows": [{"he": "שלום", "base": "", "ru": "мир"}],
        "context": "",
    }
    out = build_explain_table(payload)
    assert "[" not in out
    assert "שלום — мир" in out


# --- build_grammar_reply ---

def test_grammar_no_issues():
    payload = {"issues": [], "summary": "Всё верно."}
    out = build_grammar_reply(payload)
    assert out == "Всё верно."


def test_grammar_empty_issues_no_summary():
    out = build_grammar_reply({"issues": []})
    assert out == "Всё верно."


def test_grammar_with_issues():
    payload = {
        "issues": [{"phrase": "אני הלכ", "suggest": "אני הלך", "why": "Неверное спряжение"}],
        "summary": "Одна ошибка в глаголе.",
    }
    out = build_grammar_reply(payload)
    assert "אני הלכ → אני הלך — Неверное спряжение" in out
    assert "Одна ошибка в глаголе." in out


def test_grammar_html_escaped():
    payload = {
        "issues": [{"phrase": "a & b", "suggest": "a & b", "why": "<причина>"}],
        "summary": "",
    }
    out = build_grammar_reply(payload)
    assert "&amp;" in out
    assert "&lt;" in out


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
