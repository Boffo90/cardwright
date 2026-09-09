"""
Cut guides thin enough to be invisible.

A user reported the lines were "almost non existent" and worked up by trial
until about 0.24 pt was usable. The field is in points and accepted 0.1, which
is 0.035 mm - measured on a rendered sheet at 1200 DPI, that is a line **two
ink dots wide**. The bottom of the range could not print.

Nothing about "pt" tells anyone that, which is the other half of the problem.
"""

import numpy as np
import pytest
from PIL import Image

import print_sheet as ps

DPI = 1200
PX_PER_MM = DPI / 25.4


@pytest.fixture
def card(tmp_path):
    p = tmp_path / "card.png"
    Image.new("RGB", (744, 1039), (255, 255, 255)).save(p)
    return p


def _guide_width_px(card, tmp_path, pt):
    """Width of the drawn guide, in pixels, from a real sheet."""
    out = ps.build_pdf(
        [card], tmp_path / f"g{pt}.png", page_name="Letter",
        layout="3×3 portrait", image_format="PNG", image_dpi=DPI,
        guide_color="Black", guide_thick=pt, guide_len_mm=6.0)[0]
    a = np.asarray(Image.open(out).convert("L"))
    dark = a < 128
    widths = []
    for row in range(0, a.shape[0], 37):
        run = best = 0
        for v in dark[row]:
            run = run + 1 if v else 0
            best = max(best, run)
        if 0 < best <= 60:
            widths.append(best)
    return int(np.median(widths)) if widths else 0


@pytest.mark.parametrize("pt, mm", [
    (0.25, 0.088),
    (0.4, 0.141),
    (1.0, 0.353),
])
def test_the_setting_lands_where_the_arithmetic_says(card, tmp_path, pt, mm):
    """A point is 1/72 inch, and the drawn line has to actually be that wide -
    the hint in the dialog promises the user these millimetres."""
    got = _guide_width_px(card, tmp_path, pt) / PX_PER_MM
    assert got == pytest.approx(mm, abs=0.01)


def test_the_old_floor_really_was_two_dots(card, tmp_path):
    """Why the floor moved. Not a thin line: an absent one."""
    px = _guide_width_px(card, tmp_path, 0.1)
    assert px <= 2


def test_the_new_floor_is_thicker_than_that(card, tmp_path):
    assert _guide_width_px(card, tmp_path, 0.25) > _guide_width_px(
        card, tmp_path, 0.1)


def test_a_guide_can_still_be_turned_off_outright(card, tmp_path):
    """Raising the floor must not take away "no guides" - that is what the
    Cut guides picker is for, and it is the honest way to ask."""
    out = ps.build_pdf(
        [card], tmp_path / "none.png", page_name="Letter",
        layout="3×3 portrait", image_format="PNG", image_dpi=300,
        guide_color="None")[0]
    a = np.asarray(Image.open(out).convert("L"))
    # nothing outside the white cards: no guides, no margin ticks
    assert (a > 200).all()
