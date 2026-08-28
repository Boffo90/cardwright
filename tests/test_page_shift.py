"""
Moving the whole card block on the paper, both axes, both directions.

It used to shift down only, for heavy cardstock that feeds late and clips the
top of the page. An Epson ET-8500 owner reported the opposite problem: the
rear top loader eats 0.8 in at the far end and leaves roller marks, and no
amount of downward shift reaches that. Which edge is unusable depends on the
tray, so the control has to reach all four - and it has to stop at the paper
edge rather than walking cards off it.
"""

import pytest
from reportlab.lib.units import mm

import print_sheet as ps

# 4x2 landscape on Letter: 252x176 mm of cards on 279.4x215.9 mm of paper, so
# there is real margin to move around in on both axes.
PAGE = "Letter"
LAYOUT = "4×2 landscape"


def _origin(down=0.0, right=0.0, layout=LAYOUT, page=PAGE):
    cols, rows, landscape = ps.LAYOUTS[layout]
    pw, ph = ps.PAGES[page]
    if landscape:
        pw, ph = ph, pw
    return ps._block_origin(pw, ph, cols * ps.CARD_W, rows * ps.CARD_H,
                            down, right)


def test_no_shift_centres_the_block():
    ox, oy = _origin()
    pw, ph = ps.PAGES[PAGE][1], ps.PAGES[PAGE][0]
    assert ox == pytest.approx((pw - 4 * ps.CARD_W) / 2)
    assert oy == pytest.approx((ph - 2 * ps.CARD_H) / 2)


def test_a_positive_shift_moves_down_and_right():
    ox, oy = _origin(down=5.0, right=4.0)
    cx, cy = _origin()
    assert ox - cx == pytest.approx(4.0 * mm)
    assert cy - oy == pytest.approx(5.0 * mm)


def test_a_negative_shift_moves_up_and_left():
    """The whole point of the report: down-only could not reach the edge the
    rear feed mangles."""
    ox, oy = _origin(down=-5.0, right=-4.0)
    cx, cy = _origin()
    assert cx - ox == pytest.approx(4.0 * mm)
    assert oy - cy == pytest.approx(5.0 * mm)


@pytest.mark.parametrize("down, right", [
    (500, 0), (-500, 0), (0, 500), (0, -500),
])
def test_an_over_large_shift_stops_at_the_printable_edge(down, right):
    ox, oy = _origin(down=down, right=right)
    pw, ph = ps.PAGES[PAGE][1], ps.PAGES[PAGE][0]
    assert ps.MIN_BOTTOM <= ox <= pw - 4 * ps.CARD_W - ps.MIN_BOTTOM
    assert ps.MIN_BOTTOM <= oy <= ph - 2 * ps.CARD_H - ps.MIN_BOTTOM


@pytest.mark.parametrize("want", [0, 200, -200])
def test_a_block_that_cannot_fit_is_centred_rather_than_pinned(want):
    """When the block is wider than the printable area there is no position
    that honours the 3 mm margin on both sides, so the overflow is shared
    between the two edges instead of all going to one."""
    page, size = 400.0, 400.0
    assert ps._on_page(want, size, page) == pytest.approx(0.0)


def test_the_margin_is_kept_when_the_block_does_fit():
    assert ps._on_page(0.0, 300.0, 400.0) == pytest.approx(ps.MIN_BOTTOM)
    assert ps._on_page(1e6, 300.0, 400.0) == pytest.approx(
        400.0 - 300.0 - ps.MIN_BOTTOM)


# ------------------------------------------------- what the preview shares

def test_the_preview_helper_agrees_with_the_export():
    """The preview used to recompute placement, which is how it could show a
    shift the export then clamped away."""
    pw, ph = 279.4, 215.9                     # Letter, landscape, in mm
    bw, bh = 4 * 63.0, 2 * 88.0
    left, top = ps.block_origin_mm(pw, ph, bw, bh, 4.0, 5.0)
    ox, oy = _origin(down=5.0, right=4.0)
    assert left == pytest.approx(ox / mm)
    assert top == pytest.approx(ph - oy / mm - bh)


def test_the_preview_helper_clamps_too():
    pw, ph = 279.4, 215.9
    bw, bh = 4 * 63.0, 2 * 88.0
    left, top = ps.block_origin_mm(pw, ph, bw, bh, -500.0, -500.0)
    assert left == pytest.approx(3.0)
    assert top == pytest.approx(3.0)


# ------------------------------------------------------- through build_pdf

def test_the_shift_reaches_the_sheet(tmp_path):
    """End to end, in pixels: shifting right moves the cards right."""
    from PIL import Image
    import numpy as np

    card = tmp_path / "c.png"
    Image.new("RGB", (744, 1039), (200, 40, 40)).save(card)

    n = [0]

    def left_edge(**kw):
        n[0] += 1
        f = ps.build_pdf([card], tmp_path / f"s{n[0]}.png", page_name=PAGE,
                         layout=LAYOUT, image_format="PNG", image_dpi=100,
                         **kw)[0]
        a = np.asarray(Image.open(f).convert("RGB"))
        red = (a[:, :, 0] > 150) & (a[:, :, 1] < 80)
        return np.nonzero(red.any(axis=0))[0].min()

    base = left_edge()
    assert left_edge(shift_right_mm=10.0) - base == pytest.approx(
        10.0 / 25.4 * 100, abs=1)
    assert base - left_edge(shift_right_mm=-10.0) == pytest.approx(
        10.0 / 25.4 * 100, abs=1)


def test_registration_marks_still_ignore_the_shift(tmp_path):
    """The cutter finds the marks wherever the paper fed and cuts relative to
    them, so it self-compensates; moving only the cards would break that."""
    from PIL import Image
    import numpy as np

    card = tmp_path / "c.png"
    Image.new("RGB", (744, 1039), (200, 40, 40)).save(card)

    n = [0]

    def left_edge(**kw):
        n[0] += 1
        f = ps.build_pdf([card], tmp_path / f"r{n[0]}.png", page_name=PAGE,
                         layout=LAYOUT, image_format="PNG", image_dpi=100,
                         reg_marks=True, **kw)[0]
        a = np.asarray(Image.open(f).convert("RGB"))
        red = (a[:, :, 0] > 150) & (a[:, :, 1] < 80)
        return np.nonzero(red.any(axis=0))[0].min()

    assert left_edge() == left_edge(shift_right_mm=10.0, shift_down_mm=10.0)
