import pytest
from unittest.mock import MagicMock
from utils.media_utils import is_media, is_spoiler, has_cw_keyword


def test_is_media():
    msg = MagicMock()
    msg.attachments = []
    msg.content = "No media here"
    assert is_media(msg) is False

    msg.content = "Check out this link: http://example.com"
    assert is_media(msg) is True

    msg.content = "||secret spoiler||"
    assert is_media(msg) is True

    att = MagicMock()
    att.content_type = "image/png"
    msg.attachments = [att]
    msg.content = ""
    assert is_media(msg) is True


def test_is_spoiler():
    msg = MagicMock()
    msg.attachments = []
    msg.content = "Not a spoiler"
    assert is_spoiler(msg) is False

    msg.content = "||spoiler||"
    assert is_spoiler(msg) is True

    att = MagicMock()
    att.is_spoiler.return_value = True
    msg.attachments = [att]
    assert is_spoiler(msg) is True

    att2 = MagicMock()
    att2.is_spoiler.return_value = False
    msg.attachments = [att, att2]
    assert is_spoiler(msg) is False


def test_has_cw_keyword():
    assert has_cw_keyword("No keyword here") is False
    assert has_cw_keyword("This is a [Contentwarning: test]") is True
    assert has_cw_keyword("CW: Spiders") is True
    assert has_cw_keyword("inhaltswarnung: Blut") is True
    assert has_cw_keyword("TW: Violence") is True
    assert has_cw_keyword("Something iw: test") is True
    assert has_cw_keyword("Here are some Triggerwarnungen") is True
    assert has_cw_keyword("CWS: test") is True
