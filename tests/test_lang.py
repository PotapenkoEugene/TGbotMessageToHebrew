from tgbot.lang import detect_lang, route


def test_hebrew_detected():
    assert detect_lang("שלום עולם") == "he"


def test_russian_detected():
    assert detect_lang("Привет мир, как дела") == "ru"


def test_english_detected():
    assert detect_lang("Hello world, how are you doing today") == "en"


def test_route_he_to_ru():
    assert route("he") == ("he", "ru")


def test_route_ru_to_he():
    assert route("ru") == ("ru", "he")


def test_route_en_to_he():
    assert route("en") == ("en", "he")


def test_route_other_none():
    assert route("other") is None


def test_mixed_hebrew_detected_as_he():
    # Hebrew chars dominate detection
    assert detect_lang("שלום hello") == "he"
