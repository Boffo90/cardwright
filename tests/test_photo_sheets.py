"""
4x6 photo prints, and the raster output that makes them usable.

Two cards on a 4x6 photo print is several times cheaper than nine on A4 or
Letter in some countries, and the labs that price it that way generally refuse
PDF outright. So this covers both halves: that the page and grid put two cards
on the print at the measured size, and that the same layout code can draw
itself into pixels instead of a PDF.
"""

import numpy as np
import pytest
from PIL import Image

import print_sheet as ps

PAGE = "4x6 photo"
GRID = "2×1 landscape"


@pytest.fixture
def cards(tmp_path):
    """Three flat, distinctly coloured cards - enough to fill two sheets."""
    out = []
    for i, rgb in enumerate(((200, 40, 40), (40, 120, 200), (230, 200, 60))):
        p = tmp_path / f"card{i}.png"
        Image.new("RGB", (744, 1039), rgb).save(p)
        out.append(p)
    return out


def _sheet(paths, out, **kw):
    kw.setdefault("page_name", PAGE)
    kw.setdefault("layout", GRID)
    kw.setdefault("image_format", "PNG")
    kw.setdefault("image_dpi", 300)
    return ps.build_pdf(paths, out, **kw)


# ------------------------------------------------------------- the geometry

def test_the_photo_print_holds_exactly_two_cards():
    cols, rows, landscape = ps.LAYOUTS[GRID]
    assert (cols * rows, landscape) == (2, True)


def test_the_page_is_four_by_six_inches():
    w, h = ps.PAGES[PAGE]
    assert (round(w / 72, 3), round(h / 72, 3)) == (4.0, 6.0)


def test_two_cards_fit_the_print_with_the_measured_margins(cards, tmp_path):
    """1.04 in across the long edge and 0.54 in across the short one. If a
    change ever squeezes these, the cards no longer fit a real 4x6."""
    f = _sheet(cards[:2], tmp_path / "s.png")[0]
    a = np.asarray(Image.open(f).convert("RGB"))

    # the cards are the only saturated colour on the sheet
    coloured = (a.max(axis=2).astype(int) - a.min(axis=2)) > 40
    ys, xs = np.nonzero(coloured)
    assert a.shape[:2] == (1200, 1800)
    assert round((1800 - (xs.max() - xs.min() + 1)) / 300, 2) == 1.04
    assert round((1200 - (ys.max() - ys.min() + 1)) / 300, 2) == 0.54


def test_the_cards_touch_so_one_cut_separates_them(cards, tmp_path):
    f = _sheet(cards[:2], tmp_path / "s.png")[0]
    a = np.asarray(Image.open(f).convert("RGB"))
    row = a[600]
    red = np.nonzero((row[:, 0] > 150) & (row[:, 1] < 80))[0]
    blue = np.nonzero((row[:, 2] > 150) & (row[:, 0] < 80))[0]
    assert blue.min() == red.max() + 1


# ------------------------------------------------------------ raster output

@pytest.mark.parametrize("dpi, sheet, card", [
    (300, (1800, 1200), 744),
    (600, (3600, 2400), 1488),
    (1200, (7200, 4800), 2976),
])
def test_the_dpi_choice_drives_the_pixel_size(cards, tmp_path, dpi, sheet, card):
    """The lab decides what it accepts, so the resolution is a choice rather
    than 300 hard-coded and the upscaler's work quietly thrown away."""
    f = _sheet(cards[:1], tmp_path / "s.png", image_dpi=dpi)[0]
    a = np.asarray(Image.open(f).convert("RGB"))
    assert (a.shape[1], a.shape[0]) == sheet
    xs = np.nonzero(((a.max(axis=2).astype(int) - a.min(axis=2)) > 40).any(0))[0]
    assert xs.max() - xs.min() + 1 == card


def test_each_sheet_is_its_own_numbered_file(cards, tmp_path):
    """A bitmap has no pages, so three cards across two sheets is two files."""
    files = _sheet(cards, tmp_path / "print-sheet.png")
    assert [f.name for f in files] == ["print-sheet-01.png",
                                       "print-sheet-02.png"]


def test_a_single_sheet_keeps_the_name_it_was_given(cards, tmp_path):
    files = _sheet(cards[:2], tmp_path / "print-sheet.png")
    assert [f.name for f in files] == ["print-sheet.png"]


def test_jpeg_lands_as_jpg(cards, tmp_path):
    files = _sheet(cards[:1], tmp_path / "print-sheet.png", image_format="JPEG")
    assert [f.name for f in files] == ["print-sheet.jpg"]
    with Image.open(files[0]) as im:
        assert im.format == "JPEG"


def test_the_file_split_setting_does_not_apply_to_bitmaps(cards, tmp_path):
    """It splits PDF pages into files; a bitmap is already one page per file,
    so asking for two pages per file must not merge or drop a sheet."""
    files = _sheet(cards, tmp_path / "s.png", pages_per_file=2)
    assert len(files) == 2


def test_the_resolution_is_recorded_in_the_file(cards, tmp_path):
    """A lab that reads DPI from the file must not print a 4x6 at some other
    size because the header said nothing."""
    f = _sheet(cards[:1], tmp_path / "s.png", image_dpi=600)[0]
    with Image.open(f) as im:
        assert round(im.info["dpi"][0]) == 600


# --------------------------------------------------- the rest of the sheet

def test_backs_come_out_as_their_own_files(cards, tmp_path):
    back = tmp_path / "back.png"
    Image.new("RGB", (744, 1039), (30, 30, 30)).save(back)
    files = _sheet(cards[:2], tmp_path / "s.png", backs=[back, back])
    assert [f.name for f in files] == ["s-01.png", "s-02.png"]


def test_cut_guides_are_drawn(cards, tmp_path):
    """The guides go through the same code as the PDF's, so what this checks
    is that the raster canvas draws lines at all, in the margin where only a
    guide or a margin tick can be."""
    f = _sheet(cards[:2], tmp_path / "s.png", guide_color="Black")[0]
    a = np.asarray(Image.open(f).convert("L"))
    margin = a[:, :140]                      # left of the card block
    assert (margin < 200).any()

    plain = _sheet(cards[:2], tmp_path / "n.png", guide_color="None")[0]
    b = np.asarray(Image.open(plain).convert("L"))
    assert not (b[:, :140] < 200).any()


def test_registration_marks_reach_the_bitmap(cards, tmp_path):
    """Marks are filled rectangles rather than lines, a separate canvas call,
    and a cutter that cannot see them makes the whole export useless."""
    f = _sheet(cards, tmp_path / "s.png", page_name="Letter",
               layout="3×3 portrait", reg_marks=True)[0]
    a = np.asarray(Image.open(f).convert("L"))
    corner = a[:200, :200]                   # the 5 mm filled square
    assert (corner < 60).sum() > 500


def test_a_pdf_is_still_a_pdf(cards, tmp_path):
    """The raster path is an addition, not a replacement."""
    files = ps.build_pdf(cards[:2], tmp_path / "s.pdf", page_name=PAGE,
                         layout=GRID)
    assert [f.name for f in files] == ["s.pdf"]
    assert files[0].read_bytes()[:5] == b"%PDF-"
