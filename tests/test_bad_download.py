"""
A download that is not an image.

Reported in the log attached to issue #8: ten MPC cards failed in one evening
with Pillow's "cannot identify image file", pointing at `_orient_to_card` -
the Riftbound orientation probe, which was simply the first thing to open the
downloaded file. The same cards downloaded fine later, so Google Drive had
refused them for a while and answered with something that was not the image.

Two faults, and the message was the worse one. A source refusing a file is
ordinary and recoverable; a card dying on "cannot identify image file" names
neither the cause nor the cure.
"""

import io

import pytest
from PIL import Image

import config
import mpcfill
import scryfall
import upscale


def _png_bytes(size=(40, 56)):
    buf = io.BytesIO()
    Image.new("RGB", size, (20, 30, 40)).save(buf, "PNG")
    return buf.getvalue()


DRIVE_PAGE = (b"<!DOCTYPE html><html><head><title>Google Drive - Quota "
              b"exceeded</title></head><body>" + b"x" * 4000 + b"</body></html>")


# ------------------------------------------------------- what arrived

def test_a_web_page_is_recognised_as_one():
    """The specific thing Drive sends when it will not serve the file. It is
    far past any size floor, which is why a length check never caught it."""
    assert len(DRIVE_PAGE) > 2000
    assert config.image_kind(DRIVE_PAGE) == "a web page"


def test_a_real_image_passes():
    assert config.image_kind(_png_bytes()) == "image"


@pytest.mark.parametrize("data, expected", [
    (b"", "an empty file"),
    (b"\x00\x01garbage" * 500, "not an image"),
    (b"   <html>hello</html>", "a web page"),
])
def test_the_other_shapes_are_named(data, expected):
    assert config.image_kind(data) == expected


def test_the_check_does_not_decode_the_pixels():
    """A card is ~12 MB. Parsing the header is enough to know it is an image,
    and this runs on every download."""
    big = _png_bytes((2976, 4160))
    assert config.image_kind(big) == "image"


# ------------------------------------------- caught where it arrives

class _Resp:
    def __init__(self, content, status=200):
        self.content = content
        self.status_code = status


def test_scryfall_refuses_to_save_a_web_page(monkeypatch, tmp_path):
    monkeypatch.setattr(scryfall, "TEMP_FOLDER", tmp_path)
    monkeypatch.setattr(scryfall.time, "sleep", lambda *a: None)
    monkeypatch.setattr(scryfall.requests, "get",
                        lambda *a, **kw: _Resp(DRIVE_PAGE))
    with pytest.raises(scryfall.ScryfallError) as e:
        scryfall.download_to_temp("Kappa Cannoneer", "https://drive.google.com/uc?id=x")
    msg = str(e.value)
    assert "a web page" in msg and "Kappa Cannoneer" in msg
    assert "Upscale all again" in msg          # what to actually do
    assert not list(tmp_path.iterdir())        # nothing written


def test_the_message_names_drive_only_when_it_was_drive(monkeypatch, tmp_path):
    monkeypatch.setattr(scryfall, "TEMP_FOLDER", tmp_path)
    monkeypatch.setattr(scryfall.time, "sleep", lambda *a: None)
    monkeypatch.setattr(scryfall.requests, "get",
                        lambda *a, **kw: _Resp(DRIVE_PAGE))
    with pytest.raises(scryfall.ScryfallError) as e:
        scryfall.download_to_temp("Sol Ring", "https://cards.scryfall.io/png/x.png")
    assert "Google Drive" not in str(e.value)


def test_a_good_download_is_still_saved(monkeypatch, tmp_path):
    monkeypatch.setattr(scryfall, "TEMP_FOLDER", tmp_path)
    monkeypatch.setattr(scryfall.time, "sleep", lambda *a: None)
    monkeypatch.setattr(scryfall.requests, "get",
                        lambda *a, **kw: _Resp(_png_bytes((744, 1039))))
    out = scryfall.download_to_temp("Sol Ring", "https://cards.scryfall.io/x.png")
    assert out.exists() and out.stat().st_size > 2000


def test_mpc_refuses_it_too(monkeypatch, tmp_path):
    monkeypatch.setattr(mpcfill, "_throttle", lambda: None)
    monkeypatch.setattr(mpcfill.requests, "get",
                        lambda *a, **kw: _Resp(DRIVE_PAGE))
    target = tmp_path / "card.png"
    with pytest.raises(mpcfill.MPCError) as e:
        mpcfill.download({"name": "Kappa Cannoneer", "identifier": "x",
                          "download": "https://drive.google.com/uc?id=x"}, target)
    assert "a web page" in str(e.value)
    assert not target.exists()


# --------------------------------- and survivable further down the line

def test_the_orientation_probe_no_longer_brings_the_card_down(tmp_path):
    """It only decides which way up to turn a card. An unreadable file is a
    real problem, but not this function's to report."""
    bad = tmp_path / "bad.png"
    bad.write_bytes(DRIVE_PAGE)
    assert upscale._orient_to_card(bad, (2976, 4160)) is None


def test_an_unreadable_input_fails_in_words(tmp_path):
    bad = tmp_path / "Kappa Cannoneer.png"
    bad.write_bytes(DRIVE_PAGE)
    with pytest.raises(RuntimeError) as e:
        upscale._normalize_input(bad, False, None, (2976, 4160), [])
    msg = str(e.value)
    assert "Kappa Cannoneer.png" in msg
    assert "Upscale all" in msg                 # the recoverable case
    assert "image viewer" in msg                # the user's-own-file case


def test_a_readable_input_is_untouched(tmp_path):
    good = tmp_path / "card.png"
    good.write_bytes(_png_bytes((744, 1039)))
    made = []
    assert upscale._normalize_input(good, False, None, (2976, 4160), made) == good
    assert made == []
