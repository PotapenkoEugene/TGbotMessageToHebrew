from tgbot.lang import extract_hebrew_words


def test_pure_hebrew():
    assert extract_hebrew_words("שלום עולם") == ["שלום", "עולם"]


def test_mixed_with_english():
    assert extract_hebrew_words("hello שלום world") == ["שלום"]


def test_mixed_with_russian():
    assert extract_hebrew_words("привет שלום мир") == ["שלום"]


def test_single_char_filtered():
    # Single-char Hebrew should be filtered (len < 2)
    result = extract_hebrew_words("א")
    assert result == []


def test_short_word_filtered():
    result = extract_hebrew_words("hi א there")
    assert result == []


def test_multi_word_phrase():
    words = extract_hebrew_words("מה שלומך היום")
    assert words == ["מה", "שלומך", "היום"]


def test_empty_string():
    assert extract_hebrew_words("") == []


def test_no_hebrew():
    assert extract_hebrew_words("hello world") == []


def test_punctuation_split():
    words = extract_hebrew_words("שלום, עולם!")
    assert "שלום" in words
    assert "עולם" in words
