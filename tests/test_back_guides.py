"""
Cut guides on the back pages, which you can now turn off.

Duplex drift means the back's guides never land exactly where the front's do,
so a second set that disagrees with the one you are cutting to is worse than
none. Reported by someone printing duplex, who could not find the setting
because it did not exist.
"""

import re
import zlib
from pathlib import Path

import pytest
from PIL import Image

import print_sheet as ps


@pytest.fixture
def cards(tmp_path):
    front, back = tmp_path / "f.png", tmp_path / "b.png"
    Image.new("RGB", (300, 420), (200, 60, 60)).save(front)
    Image.new("RGB", (300, 420), (40, 60, 200)).save(back)
    return front, back


def _guide_segments_per_page(pdf):
    """Guide strokes on each page that carries cards, front first."""
    raw = Path(pdf).read_bytes()
    streams = []
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        try:
            streams.append(zlib.decompress(m.group(1)).decode("latin-1"))
        except Exception:
            pass
    return [s.count(" l S") for s in streams if " Do" in s]


def _build(tmp_path, cards, **kw):
    front, back = cards
    out = tmp_path / "sheet.pdf"
    args = dict(page_name="A4", layout="3x3", backs=[back],
                guide_color="Black", quality="Fast")
    args.update(kw)
    ps.build_pdf([front], out, **args)
    return out


def test_backs_carry_guides_by_default(tmp_path, cards):
    """The behaviour every existing user already has."""
    front_n, back_n = _guide_segments_per_page(_build(tmp_path, cards))
    assert front_n > 0 and back_n == front_n


def test_turning_it_off_clears_the_back_only(tmp_path, cards):
    front_n, back_n = _guide_segments_per_page(
        _build(tmp_path, cards, back_guides=False))
    assert back_n == 0, "the back still has guides"
    assert front_n > 0, "the front lost its guides too, which is not the ask"


def test_guides_off_entirely_still_means_off_on_both(tmp_path, cards):
    pages = _guide_segments_per_page(
        _build(tmp_path, cards, guide_color="None", back_guides=True))
    assert pages == [0, 0]


def test_registration_marks_are_a_separate_decision(tmp_path, cards):
    """A cutting machine still needs its marks on the back even when the human
    guides are gone, so the switch must not take them with it."""
    front, back = cards
    out = tmp_path / "reg.pdf"
    ps.build_pdf([front], out, page_name="A4", layout="3x3", backs=[back],
                 guide_color="Black", quality="Fast", back_guides=False,
                 reg_marks=True)
    raw = out.read_bytes()
    marks = 0
    for m in re.finditer(rb"stream\r?\n(.*?)endstream", raw, re.S):
        try:
            marks += zlib.decompress(m.group(1)).decode("latin-1").count(" re f*")
        except Exception:
            pass
    assert marks > 0, "registration marks vanished with the cut guides"
