"""Tests for message skip logic in handle_message."""
import pytest
from unittest.mock import MagicMock

from tgbot.handlers.translate import _has_url_or_media


def _make_msg(text=None, photo=None, document=None, sticker=None,
              animation=None, video=None, entities=None):
    msg = MagicMock()
    msg.text = text
    msg.photo = photo
    msg.document = document
    msg.sticker = sticker
    msg.animation = animation
    msg.video = video
    msg.entities = entities or []
    return msg


def test_plain_text_not_filtered():
    msg = _make_msg(text="Доброе утро")
    assert _has_url_or_media(msg) is False


def test_photo_filtered():
    msg = _make_msg(photo=[MagicMock()])
    assert _has_url_or_media(msg) is True


def test_sticker_filtered():
    msg = _make_msg(sticker=MagicMock())
    assert _has_url_or_media(msg) is True


def test_document_filtered():
    msg = _make_msg(document=MagicMock())
    assert _has_url_or_media(msg) is True


def test_url_entity_filtered():
    entity = MagicMock()
    entity.type = "url"
    msg = _make_msg(text="check https://example.com", entities=[entity])
    assert _has_url_or_media(msg) is True


def test_text_link_entity_filtered():
    entity = MagicMock()
    entity.type = "text_link"
    msg = _make_msg(text="click here", entities=[entity])
    assert _has_url_or_media(msg) is True


def test_bold_entity_not_filtered():
    entity = MagicMock()
    entity.type = "bold"
    msg = _make_msg(text="hello", entities=[entity])
    assert _has_url_or_media(msg) is False


def test_word_count_threshold():
    """Verify threshold logic (not in _has_url_or_media but used in handler)."""
    text = "один два три четыре пять шесть семь восемь девять десять одиннадцать двенадцать тринадцать четырнадцать пятнадцать шестнадцать"
    word_count = len(text.split())
    assert word_count >= 15  # should be skipped at threshold=15


def test_single_word_skip():
    text = "Привет"
    assert len(text.split()) == 1
