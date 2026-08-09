"""Regenerate the README banner (assets/banner.png).

Run it after changing the palette: every colour is read from theme.py, so the
banner tracks the app instead of drifting from it, which is exactly the kind of
thing nobody notices for six months.

    python tools/make_banner.py

Drawn at 3x and downsampled so the type and the hairlines survive on the
displays people actually read GitHub on. Geometry is written in final pixels
and scaled once, which is the only way the margins stay checkable by eye
against a 1280x360 canvas.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from PIL import Image, ImageDraw, ImageFont
import theme

S = 3
W, H = 1280, 360
FONTS = Path(r"C:\Windows\Fonts")

F_SEMIBOLD = "seguisb.ttf"
F_REGULAR = "segoeui.ttf"
F_SEMILIGHT = "segoeuisl.ttf"


def font(name, size):
    return ImageFont.truetype(str(FONTS / name), size * S)


def rect(d, x0, y0, x1, y1, **kw):
    d.rectangle([min(x0, x1) * S, min(y0, y1) * S,
                 max(x0, x1) * S, max(y0, y1) * S], **kw)


def rrect(d, x0, y0, x1, y1, radius, **kw):
    d.rounded_rectangle([x0 * S, y0 * S, x1 * S, y1 * S],
                        radius=radius * S, **kw)


def line(d, x0, y0, x1, y1, **kw):
    d.line([x0 * S, y0 * S, x1 * S, y1 * S], **kw)


img = Image.new("RGB", (W * S, H * S), theme.BG)
d = ImageDraw.Draw(img)

# --------------------------------------------------------------- the sheet
# A page panel carrying a card grid: the thing the app produces, kept small
# enough to read as a mark rather than a screenshot. At the ~880 px GitHub
# actually renders a README image, a screenshot would be illegible.
CARD_W, CARD_H, GAP = 74, 103, 9
COLS, ROWS = 3, 2
PAD = 26                                   # page margin around the grid

grid_w = COLS * CARD_W + (COLS - 1) * GAP
grid_h = ROWS * CARD_H + (ROWS - 1) * GAP
page_w, page_h = grid_w + 2 * PAD, grid_h + 2 * PAD
page_x = W - 92 - page_w
page_y = (H - page_h) // 2
gx, gy = page_x + PAD, page_y + PAD

rrect(d, page_x, page_y, page_x + page_w, page_y + page_h, 10,
      fill=theme.SURFACE, outline=theme.BORDER, width=1 * S)

for r in range(ROWS):
    for c in range(COLS):
        x, y = gx + c * (CARD_W + GAP), gy + r * (CARD_H + GAP)
        # surface, not black: it should read as a card, not as a hole
        rrect(d, x, y, x + CARD_W, y + CARD_H, 5,
              fill=theme.SURFACE_ALT, outline=theme.BORDER, width=1 * S)
        rrect(d, x + 7, y + 7, x + CARD_W - 7, y + int(CARD_H * 0.55), 3,
              fill=theme.SURFACE_HOVER)

# Cut guides at every card boundary, in the app's gold - the detail that says
# what the tool is actually for. One pixel wide, so it stays a whisper.
TICK = 8
xs = [gx - GAP // 2] + [gx + c * (CARD_W + GAP) + CARD_W + GAP // 2
                        for c in range(COLS)]
ys = [gy - GAP // 2] + [gy + r * (CARD_H + GAP) + CARD_H + GAP // 2
                        for r in range(ROWS)]
for x in xs:
    for y in ys:
        line(d, x - TICK, y, x + TICK, y, fill=theme.ACCENT, width=1 * S)
        line(d, x, y - TICK, x, y + TICK, fill=theme.ACCENT, width=1 * S)

# Registration marks: the corner brackets a cutting machine hunts for. They
# sit on the page, inside its edge, exactly as the real ones do.
ARM, THICK, INSET = 17, 3, 10
for cx, cy, sx, sy in ((page_x + INSET, page_y + INSET, 1, 1),
                       (page_x + page_w - INSET, page_y + INSET, -1, 1),
                       (page_x + INSET, page_y + page_h - INSET, 1, -1),
                       (page_x + page_w - INSET, page_y + page_h - INSET,
                        -1, -1)):
    rect(d, cx, cy, cx + sx * ARM, cy + sy * THICK, fill=theme.TEXT_DIM)
    rect(d, cx, cy, cx + sx * THICK, cy + sy * ARM, fill=theme.TEXT_DIM)

# ------------------------------------------------------------------- type
# Measured, then centred as a block. Eyeballing the baseline is what put the
# first draft's text low and left the middle of the canvas empty.
LEFT = 96
name_f = font(F_SEMIBOLD, 58)
tag_f = font(F_SEMILIGHT, 24)
meta_f = font(F_REGULAR, 15)

NAME = "Cardwright"
TAG = "Print-ready TCG proxies at true 1200 DPI"
META = ("GPU AI upscaling   ·   Magic, Pokémon, Yu-Gi-Oh   ·   "
        "cutting-machine registration marks   ·   free")

name_h = d.textbbox((0, 0), NAME, font=name_f)[3] / S
tag_h = d.textbbox((0, 0), TAG, font=tag_f)[3] / S
meta_h = d.textbbox((0, 0), META, font=meta_f)[3] / S
RULE_GAP, RULE_H, TAG_GAP, META_GAP = 20, 3, 24, 26

block_h = name_h + RULE_GAP + RULE_H + TAG_GAP + tag_h + META_GAP + meta_h
top = (H - block_h) / 2

d.text((LEFT * S, top * S), NAME, font=name_f, fill=theme.TEXT)
# the gold rule: the accent used once more, at the width of a cut guide
rule_y = top + name_h + RULE_GAP
rect(d, LEFT, rule_y, LEFT + 50, rule_y + RULE_H, fill=theme.ACCENT)
tag_y = rule_y + RULE_H + TAG_GAP
d.text((LEFT * S, tag_y * S), TAG, font=tag_f, fill=theme.TEXT_DIM)
d.text((LEFT * S, (tag_y + tag_h + META_GAP) * S), META,
       font=meta_f, fill=theme.TEXT_MUTED)

# ----------------------------------------------------------------- finish
img = img.resize((W, H), Image.LANCZOS)
out = REPO / "assets" / "banner.png"
out.parent.mkdir(parents=True, exist_ok=True)
img.save(out, "PNG")
print(f"wrote {out} {img.size} {out.stat().st_size / 1000:.0f} kB")
