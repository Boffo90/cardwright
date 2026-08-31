"""
A duplex back has to come out the same size as its front.

The back is drawn into a rect `back_bleed_mm` larger on every edge, so cutting
along the front's guides never exposes white paper. The IMAGE has to grow to
match. It did not: the same card was simply scaled into the larger rect, which
at the 1.5 mm default made the back 4.7% too wide and 3.4% too tall - not even
the same aspect ratio, since 1.5 mm is a bigger fraction of 63 than of 88.

Invisible on a plain card back, which is symmetric and has nothing near its
edge to compare. Fatal on a double-faced card, whose back is a real card face
with a frame and a text box that have to line up with the front's.
"""

import numpy as np
import pytest
from PIL import Image, ImageDraw

import print_sheet as ps

DPI = 200
PX_PER_MM = DPI / 25.4


@pytest.fixture
def card(tmp_path):
    """Black card with a red rectangle inset 10% a side, so the printed
    rectangle's size reads back how large the card was drawn."""
    w, h = 744, 1039
    p = tmp_path / "card.png"
    im = Image.new("RGB", (w, h), (0, 0, 0))
    ImageDraw.Draw(im).rectangle(
        [int(w * 0.10), int(h * 0.10), int(w * 0.90) - 1, int(h * 0.90) - 1],
        fill=(220, 20, 20))
    im.save(p)
    return p


def _marker(path):
    """(x0, y0, x1, y1) of the red rectangle, in pixels."""
    a = np.asarray(Image.open(path).convert("RGB")).astype(int)
    m = (a[:, :, 0] > 150) & (a[:, :, 1] < 90) & (a[:, :, 2] < 90)
    ys, xs = np.nonzero(m)
    return xs.min(), ys.min(), xs.max(), ys.max()


def _sheet(card, out, n=1, **kw):
    cards = [card] * n
    args = dict(page_name="Letter", layout="3×3 portrait",
                image_format="PNG", image_dpi=DPI, backs=cards,
                guide_color="None")
    args.update(kw)
    return ps.build_pdf(cards, out, **args)


@pytest.mark.parametrize("bleed", [0.0, 1.5, 3.0])
def test_the_back_is_the_same_size_as_the_front(card, tmp_path, bleed):
    front, back = _sheet(card, tmp_path / "s.png", back_bleed_mm=bleed)
    fx0, fy0, fx1, fy1 = _marker(front)
    bx0, by0, bx1, by1 = _marker(back)
    assert (bx1 - bx0) / (fx1 - fx0) == pytest.approx(1.0, abs=0.004)
    assert (by1 - by0) / (fy1 - fy0) == pytest.approx(1.0, abs=0.004)


def test_the_bleed_still_reaches_past_the_card(card, tmp_path):
    """The ring is the point: it has to actually be there, or duplex drift
    shows white paper at the cut."""
    plain, _ = _sheet(card, tmp_path / "a.png", back_bleed_mm=0.0)
    _, bled = _sheet(card, tmp_path / "b.png", back_bleed_mm=3.0)

    def dark_span(path):
        a = np.asarray(Image.open(path).convert("L"))
        ys, xs = np.nonzero(a < 100)          # the card's black body
        return xs.max() - xs.min() + 1, ys.max() - ys.min() + 1

    w0, h0 = dark_span(plain)
    w1, h1 = dark_span(bled)
    assert (w1 - w0) / PX_PER_MM == pytest.approx(6.0, abs=0.4)   # 3 mm a side
    assert (h1 - h0) / PX_PER_MM == pytest.approx(6.0, abs=0.4)


@pytest.mark.parametrize("layout, n", [
    ("3×3 portrait", 9),
    ("4×2 landscape", 8),
])
def test_flipping_the_sheet_lands_the_back_on_its_front(card, tmp_path,
                                                        layout, n):
    """What duplex physically does: the back page mirrored on the long edge
    has to sit on top of the front page."""
    front, back = _sheet(card, tmp_path / "s.png", n=n, layout=layout)
    fb = _marker(front)
    flipped = tmp_path / "flipped.png"
    Image.open(back).transpose(Image.FLIP_LEFT_RIGHT).save(flipped)
    bb = _marker(flipped)
    for f, b in zip(fb, bb):
        assert abs(b - f) / PX_PER_MM < 0.2      # mm
