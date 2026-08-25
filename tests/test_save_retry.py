"""
Writing a card PNG when something else holds the file.

Reported from a real run: the same card failed three times in twenty seconds
with a bare OSError "Invalid argument", and the identical path wrote fine
later, untouched. Windows hands out a brief lock whenever Explorer builds a
thumbnail for the output folder or a preview pane reads it, and Pillow
surfaces that as an error nobody can act on.
"""

import pytest

import upscale


class _Im:
    """Fails its first `fails` saves, then succeeds."""

    def __init__(self, fails):
        self.fails = fails
        self.attempts = 0

    def save(self, path, fmt, **kw):
        self.attempts += 1
        if self.attempts <= self.fails:
            raise OSError(22, "Invalid argument", str(path))
        self.written = (path, fmt, kw)


@pytest.fixture(autouse=True)
def _no_waiting(monkeypatch):
    monkeypatch.setattr(upscale.time, "sleep", lambda s: None)


def test_a_clean_write_does_not_retry(tmp_path):
    im = _Im(fails=0)
    upscale._save_png(im, tmp_path / "card.png")
    assert im.attempts == 1


def test_a_brief_lock_is_ridden_out(tmp_path):
    """The whole point: a thumbnail lock should cost nobody anything."""
    im = _Im(fails=3)
    upscale._save_png(im, tmp_path / "card.png")
    assert im.attempts == 4


def test_the_dpi_is_still_stamped(tmp_path):
    im = _Im(fails=1)
    upscale._save_png(im, tmp_path / "card.png")
    assert im.written[1] == "PNG"
    assert im.written[2]["dpi"] == (upscale.TARGET_DPI, upscale.TARGET_DPI)


def test_it_gives_up_rather_than_hanging(tmp_path):
    im = _Im(fails=99)
    with pytest.raises(OSError):
        upscale._save_png(im, tmp_path / "card.png")
    assert im.attempts == upscale._SAVE_ATTEMPTS


def test_the_message_tells_you_what_to_do(tmp_path):
    """"Invalid argument" is what made this unactionable in the first place."""
    im = _Im(fails=99)
    with pytest.raises(OSError) as e:
        upscale._save_png(im, tmp_path / "Vampiric Link-plc-92-es.png")
    msg = str(e.value)
    assert "Vampiric Link-plc-92-es.png" in msg, "say which card"
    assert "Explorer" in msg, "say what is likely holding it"
    assert "Invalid argument" in msg, "keep the original error for a bug report"
