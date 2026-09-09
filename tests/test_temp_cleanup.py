"""
Working files get deleted.

Nothing ever did. Measured on a six-week-old install: `_temp` held 3049 files
and 6.6 GB against 1.2 GB of actual output - every card ever downloaded plus
two or three intermediates each. `print_sheet` cleaned up after itself, which
is why only two of its sheet flattens survived; `upscale` and `scryfall` never
deleted anything.

They have no use once the card is upscaled. A project and "Add cards…" both
read from the output folder, and `download_to_temp` re-fetches rather than
looking for a local copy, so a kept download is not even a cache.
"""

import time

import pytest
from PIL import Image

import upscale


@pytest.fixture
def temp(tmp_path, monkeypatch):
    monkeypatch.setattr(upscale, "TEMP_FOLDER", tmp_path)
    return tmp_path


def _png(path, size=(40, 56)):
    Image.new("RGB", size, (10, 20, 30)).save(path)
    return path


def _age(path, days):
    old = time.time() - days * 86400
    import os
    os.utime(path, (old, old))


# ------------------------------------------------------------- the sweep

def test_a_stale_working_file_is_swept(temp):
    f = _png(temp / "card.png")
    _age(f, 30)
    removed, freed = upscale.sweep_temp()
    assert removed == 1 and freed > 0
    assert not f.exists()


def test_a_recent_one_is_left_alone(temp):
    """A run may still be going. Cleanup as each card finishes is what keeps
    the folder small; this only catches the backlog."""
    f = _png(temp / "card.png")
    upscale.sweep_temp()
    assert f.exists()


def test_the_thumbnail_caches_survive(temp):
    """ygo_thumbs and riftbound_thumbs are deliberate: both catalogues ask in
    their terms not to keep re-fetching the same images. They are folders, and
    the sweep only touches files at the top level."""
    for name in ("ygo_thumbs", "riftbound_thumbs"):
        d = temp / name
        d.mkdir()
        t = _png(d / "thumb.png")
        _age(t, 400)
        _age(d, 400)
    _age(_png(temp / "junk.png"), 400)

    removed, _ = upscale.sweep_temp()
    assert removed == 1
    for name in ("ygo_thumbs", "riftbound_thumbs"):
        assert (temp / name / "thumb.png").exists()


def test_a_missing_temp_folder_is_not_an_error(tmp_path, monkeypatch):
    monkeypatch.setattr(upscale, "TEMP_FOLDER", tmp_path / "gone")
    assert upscale.sweep_temp() == (0, 0)


def test_the_age_is_configurable(temp):
    f = _png(temp / "card.png")
    _age(f, 3)
    assert upscale.sweep_temp(older_than_days=7)[0] == 0
    assert upscale.sweep_temp(older_than_days=1)[0] == 1


# ------------------------------------------------------------- discard

def test_discard_removes_what_it_is_given(temp):
    a, b = _png(temp / "a.png"), _png(temp / "b.png")
    upscale.discard([a, b])
    assert not a.exists() and not b.exists()


def test_discard_survives_a_file_that_will_not_go(temp):
    """A temp that cannot be deleted gets swept later. Failing an upscale that
    already succeeded, over a leftover, would be absurd."""
    upscale.discard([temp / "never-existed.png"])      # must not raise


# ------------------------------------------- what normalize leaves behind

def test_normalize_reports_the_files_it_creates(temp, monkeypatch):
    """The caller deletes them, so it has to be told which they are - the
    rotated copy is not the same file as the trimmed one."""
    src = _png(temp / "sideways.png", (1039, 744))
    made = []
    out = upscale._normalize_input(src, False, None, (2976, 4160), made)
    assert made == [out]
    assert out != src and out.exists()


def test_a_file_that_needs_nothing_creates_nothing(temp):
    src = _png(temp / "upright.png", (744, 1039))
    made = []
    out = upscale._normalize_input(src, False, None, (2976, 4160), made)
    assert made == []
    assert out == src
