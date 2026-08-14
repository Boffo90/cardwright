"""
Bleed that continues the card's own art instead of a flat colour frame.

Two modes, picked from the card itself. A framed card gets its frame carried
outward; mirroring there would fold the frame's inner detail back out and read
as a reflection. Full art gets mirrored, because there is no frame to protect
and the picture should just keep going.
"""

import numpy as np
from PIL import Image, ImageDraw

import print_sheet as ps


def _framed(w=120, h=168, border=14):
    im = Image.new("RGB", (w, h), (0, 0, 0))
    ImageDraw.Draw(im).rectangle(
        [border, border, w - border - 1, h - border - 1], fill=(210, 70, 70))
    return im


def _full_art(w=120, h=168):
    im = Image.new("RGB", (w, h))
    px = im.load()
    for y in range(h):
        for x in range(w):
            px[x, y] = (20 + x, 40 + y % 200, 90)
    return im


# ------------------------------------------------------------ which mode

def test_a_black_bordered_card_is_recognised_as_framed():
    assert ps._edge_is_framed(np.asarray(_framed()))


def test_full_art_is_not():
    assert not ps._edge_is_framed(np.asarray(_full_art()))


def test_a_mostly_dark_but_not_black_edge_is_not_framed():
    """The threshold is about black, not about dark: a dim night-time
    illustration running to the edge is still full art."""
    im = Image.new("RGB", (120, 168), (55, 58, 70))
    assert not ps._edge_is_framed(np.asarray(im))


# ------------------------------------------------------------- the growth

def test_the_card_grows_by_the_bleed_on_every_side():
    im = _full_art()
    out = ps.extend_bleed(im, 10)
    assert out.size == (im.width + 20, im.height + 20)


def test_zero_bleed_leaves_the_image_alone():
    im = _full_art()
    assert ps.extend_bleed(im, 0) is im


def test_the_card_itself_is_untouched_in_the_middle():
    im = _full_art()
    out = ps.extend_bleed(im, 10)
    assert out.crop((10, 10, 10 + im.width, 10 + im.height)).tobytes() \
        == im.tobytes()


def test_a_framed_card_keeps_a_black_bleed():
    """Carrying a black frame outward should look exactly like the old solid
    frame, which is why that case needed no visual change."""
    out = ps.extend_bleed(_framed(), 12)
    ring = np.asarray(out)[0]
    assert ring.max() < ps.BLEED_BLACK_THRESHOLD


def test_full_art_bleed_is_not_flat_colour():
    """The whole point: the band carries the picture, not one colour."""
    out = np.asarray(ps.extend_bleed(_full_art(), 12))
    top_band = out[:12]
    assert top_band.std() > 5, "the bleed is flat, so nothing was mirrored"


def test_the_mirrored_edge_continues_the_art():
    """The pixel just outside the card should match the one just inside it,
    which is what makes the seam invisible."""
    im = _full_art()
    b = 8
    out = ps.extend_bleed(im, b)
    inside = out.getpixel((b, b + 40))          # first column of the card
    outside = out.getpixel((b - 1, b + 40))     # last column of the bleed
    assert max(abs(a - c) for a, c in zip(inside, outside)) <= 2


def test_a_bleed_wider_than_the_card_does_not_crash():
    im = _full_art(40, 56)
    out = ps.extend_bleed(im, 60)
    assert out.size == (160, 176)
