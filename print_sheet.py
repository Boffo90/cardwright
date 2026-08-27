"""
Print-sheet PDF builder.

Lays out upscaled card PNGs on A4 / Letter pages, 3x3 cards of exactly
63 x 88 mm each (no gutters, so a straight guillotine cut between cards),
with short white cross guides at every card intersection plus dark tick
marks in the margins.

Print-time adjustments (masters on disk stay untouched):
  - quality:  lossless PNG/Flate, or JPEG q97/q92
  - profile:  color calibration (brightness / gamma / saturation) chosen
              from a printed calibration sheet
  - sharpen:  output sharpening to compensate inkjet dot gain
  - pages_per_file: split large lossless exports into printable chunks
"""

from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter, ImageDraw
from reportlab import rl_config

# store image streams as raw binary Flate instead of ASCII85 (25% smaller,
# and lossless mode is heavy enough already)
rl_config.useA85 = 0

from reportlab.lib.pagesizes import A3, A4, A5, LEGAL, letter, TABLOID
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

from config import (
    TEMP_FOLDER,
    PDF_QUALITY_MODES,
    PDF_DEFAULT_QUALITY,
    SHARPEN_MODES,
    SHADOW_LIFTS,
    SHADOW_TEST_LEVELS,
    CALIBRATION_PROFILES,
    find_back_image,
)

CARD_W = 63 * mm
CARD_H = 88 * mm

# name -> (cols, rows, landscape)
LAYOUTS = {
    "3×3 portrait": (3, 3, False),
    "4×2 landscape": (4, 2, True),
    "7-card Silhouette": (4, 2, True),
    # For the bigger papers. Without these, choosing A3 buys a larger sheet
    # and still prints 9 cards on it - A3 and Tabloid hold 16.
    # Not Legal: 4 rows come to 352 mm and Legal is 356, which the 3 mm
    # unprintable margin at each edge eats. They fall through the generic
    # grid path, so no special casing is needed.
    "3×4 portrait": (3, 4, False),
    "4×4 portrait": (4, 4, False),
}
DEFAULT_LAYOUT = "3×3 portrait"

# A 4x2 grid whose left column holds a single, vertically centred card:
#
#     [    ] [ 2 ] [ 3 ] [ 4 ]
#     [ 1  ]
#     [    ] [ 5 ] [ 6 ] [ 7 ]
#
# That frees both left corners, where the registration marks a Cameo relies on
# most (lower-left and upper-right) sit - the same trick ProxySheet's
# "SevenCard" template uses to cut down detection failures.
SEVEN_CARD = "7-card Silhouette"

# calibration / shadow test sheets always use the classic grid
COLS = 3
ROWS = 3
PER_PAGE = COLS * ROWS

MARK_LEN = 4 * mm     # margin tick length
MARK_GAP = 1 * mm     # gap between block edge and tick start

# A3 in particular is worth having: it fits far more cards per sheet and
# the extra margin means registration marks stop competing with card slots.
PAGES = {
    "A4": A4, "Letter": letter, "A3": A3, "A5": A5,
    "Legal": LEGAL, "Tabloid": TABLOID,
}

# The card block never gets closer than this to the paper's bottom edge
# (typical inkjet unprintable margin).
MIN_BOTTOM = 3 * mm


def _block_origin(pw, ph, block_w, block_h, shift_down_mm=0.0):
    """Centered block, optionally shifted down (for printers whose heavy
    cardstock feeds late and clips the top of the page)."""
    ox = (pw - block_w) / 2
    oy = (ph - block_h) / 2 - shift_down_mm * mm
    return ox, max(MIN_BOTTOM, oy)


# --------------------------------------------------------------------------
# image preparation
# --------------------------------------------------------------------------

# Shadow lift only affects tones below this level, fading linearly to zero.
# Midtones and highlights are untouched, so the card keeps its overall look.
SHADOW_KNEE = 75

# --- black-border deepening -----------------------------------------------
# Scans carry their black border at ~20/255 instead of true black, and the
# shadow lift pushes it further up (~37 with profile 9 + Medium), so it
# prints as dark grey. This snaps that border to real black.
#
# Three independent guards keep it artifact-free:
#   1. per card: only run when the perimeter is UNIFORMLY dark. Borderless,
#      full-art and white-bordered cards have art (high variance) or light
#      pixels there, so they are skipped entirely - no vignette effect.
#   2. per pixel, spatially: the treated band is measured from the image
#      (how deep the uniform dark border actually goes), then faded out, so
#      the border is covered edge to edge with no gradient inside it.
#   3. per pixel, tonally: only pixels that are already dark are pushed, so
#      anything bright that reaches into the band is left alone.
# Detection uses percentiles, not mean/std: scans carry stray bright specks
# that wreck a standard deviation (one card measured std 22 off four white
# pixels) while the median and p90 stay rock steady.
BORDER_RING_FRAC = 0.03      # perimeter depth sampled for detection
BORDER_MAX_LEVEL = 60        # brighter than this -> not a black frame
BORDER_MAX_SPREAD = 12       # p90-p50 above this -> art in the ring, skip card
# A row of the black band still counts as border while its BACKGROUND sits at
# the border level: the collector line ("U 0117 TDC - EN ...") is white text
# on black, so a mid percentile jumps there and used to cut the scan short.
BORDER_BG_PCT = 30           # percentile that represents a row's background
BORDER_LEVEL_TOL = 8         # a pixel is frame while it stays this close
BORDER_MIN_SHARE = 0.05      # perimeter this dark at least, or there's no frame
BORDER_MIN_DEPTH = 6         # shorter runs are noise, not a frame
BORDER_SMOOTH = 25           # median window along an edge, in pixels
BORDER_ALONG_STEP = 4        # scan every Nth line along an edge
# The gap that ends the frame must be longer than the collector text, whose
# letters are ~40px tall at print resolution: a column crossing a letter
# used to stop there while its neighbour ran on, leaving black streaks up
# into the artwork. Overshooting into bright content is harmless (the tonal
# guard leaves it alone).
BORDER_BREAK_FRAC = 0.02     # gap that ends the frame, fraction of width
# A black frame is neutral; coloured artwork is not. Measured on the bottom
# band: real frames sit at chroma 1-6, the brown wood of a full-art card at
# 43. Without this, a dark uniform artwork forms its own histogram peak and
# gets crushed to black.
BORDER_MAX_CHROMA = 14       # max(RGB)-min(RGB) allowed for frame pixels
BORDER_SIDE_COVERAGE = 0.88  # a side needs this much frame, or it is art


def _smooth_profile(profile: np.ndarray, k: int = BORDER_SMOOTH) -> np.ndarray:
    """Median filter along an edge so single noisy lines can't cut a notch."""
    if profile.size <= k or k < 3:
        return profile
    pad = k // 2
    padded = np.pad(profile, pad, mode="edge")
    windows = np.lib.stride_tricks.sliding_window_view(padded, k)
    return np.median(windows, axis=1).astype(np.float32)
# Each edge is measured on its own: MDFCs and similar carry a much taller
# bottom border (295px vs 116px at the sides on Agadeem's Awakening), and a
# single shared depth leaves a visible step where treated black meets
# untreated black.
BORDER_MAX_DEPTH = 0.13      # per-edge cap, fraction of that dimension
# Short fade: the detected depth already lands on the border/content edge,
# so a long ramp would darken the first millimetre of the card frame. At
# 1200 DPI this is a quarter of a millimetre - enough to avoid a hard cut,
# too small to see.
BORDER_FADE_FRAC = 0.005     # fade-out distance past the detected border
# Inside the frame, pixels below this go black. Kept low on purpose: the
# bottom band carries the copyright/collector microtext in WHITE on black,
# and its anti-aliased edges ramp through ~60-160. Crushing those to black
# ate the letter edges, closing the counters of 'o', 'a' and 'e' in print
# (measured: >half the ramp destroyed at 100). A washed scan border sits
# near 37 after the shadow lift, so 58 still snaps real frames to black.
BORDER_TONE_MAX = 58


# --- contrast edges -------------------------------------------------------
# The other way to fix a washed-out border, ported from the approach Proxxied
# uses (MIT, github.com/acoreyj/proxies-at-home) and reimplemented here.
#
# The difference that matters: this DETECTS NOTHING. `_deepen_black_border`
# has to work out how deep the frame runs, and that judgement is what breaks
# on artwork that reaches the cut edge. Here the band is a fixed fraction of
# the card, so there is no decision to get wrong. Three things keep it from
# mauling artwork that happens to sit in the band:
#
#   quadratic falloff  the effect fades to nothing by the inner edge of the
#                      band, so there is never a seam to see
#   tone weighting     only dark pixels are pushed; bright art in the band is
#                      left alone, which is what makes it safe on full-art
#   contrast curve     a push, not a binary snap - so a near-black frame goes
#                      black without flattening everything around it

CONTRAST_TONE_KNEE = 140     # above this (0-255) a pixel is art, not frame

BORDER_STYLE_CONTRAST = "contrast"   # fixed band, no detection (default)
BORDER_STYLE_AUTO = "auto"           # measure how deep the frame runs

CONTRAST_EDGE_WIDTH = 0.08           # fraction of the card's shorter side
CONTRAST_CONTRAST = 2.0
CONTRAST_BRIGHTNESS = -50 / 255


def _contrast_edges(im: Image.Image, opaque=None, amount: float = 1.0,
                    edge_width: float = 0.08, contrast: float = 2.0,
                    brightness: float = -50 / 255) -> Image.Image:
    """
    Push the dark pixels inside a fixed edge band towards black.

    edge_width  fraction of the card's SHORTER side, so the band is the same
                physical width whatever resolution the scan came in at.
    contrast    multiplier around mid-grey.
    brightness  offset applied after the contrast, in 0-1 units.
    amount      0..1 blend against the untouched pixel.
    """
    arr = np.asarray(im.convert("RGB"), dtype=np.float32) / 255.0
    h, w = arr.shape[:2]

    edge_px = max(1.0, edge_width * min(h, w))

    ys = np.arange(h, dtype=np.float32).reshape(-1, 1)
    xs = np.arange(w, dtype=np.float32).reshape(1, -1)
    dist = np.minimum(np.minimum(ys, h - 1 - ys), np.minimum(xs, w - 1 - xs))

    edge = np.clip(1.0 - dist / edge_px, 0.0, 1.0)
    edge *= edge                                   # quadratic falloff

    # Weight by how dark the pixel already is, so artwork inside the band
    # keeps its brightness instead of being dragged down with the frame.
    lum = arr.max(axis=2)
    tone = np.clip((CONTRAST_TONE_KNEE / 255.0 - lum) /
                   (CONTRAST_TONE_KNEE / 255.0), 0.0, 1.0)

    effect = (edge * tone * float(np.clip(amount, 0.0, 1.0)))[..., None]
    if opaque is not None:
        effect = effect * opaque[..., None].astype(np.float32)

    pushed = np.clip((arr - 0.5) * contrast + 0.5 + brightness, 0.0, 1.0)
    out = arr * (1.0 - effect) + pushed * effect

    return Image.fromarray((out * 255.0 + 0.5).astype(np.uint8), "RGB")


def _apply_profile(im: Image.Image, profile, shadow=0) -> Image.Image:
    """
    profile = (label, brightness, gamma, saturation); shadow = lift at pure
    black (0-255), fading linearly to zero at SHADOW_KNEE. Only the deepest
    tones rise - the rest of the tonal range is untouched.
    """
    _, brightness, gamma, saturation = profile if profile else ("", 1.0, 1.0, 1.0)
    if gamma != 1.0 or shadow > 0:
        lut = []
        for i in range(256):
            base = 255 * ((i / 255) ** gamma)
            lift = shadow * max(0.0, 1.0 - i / SHADOW_KNEE)
            lut.append(min(255, int(base + lift + 0.5)))
        im = im.point(lut * 3)
    if brightness != 1.0:
        im = ImageEnhance.Brightness(im).enhance(brightness)
    if saturation != 1.0:
        im = ImageEnhance.Color(im).enhance(saturation)
    return im


def _deepen_black_border(im: Image.Image, opaque=None, amount: float = 1.0,
                         manual_width: float = 0.0) -> Image.Image:
    """
    Snap a washed-out black border to true black. Returns the image
    unchanged unless the card's perimeter is uniformly dark.

    `opaque` is a bool mask of non-transparent pixels (the PNG's rounded
    corners must be excluded or every card would look black-bordered).

    amount        0..1, how far towards true black the frame is pushed.
    manual_width  >0 skips detection and treats this fraction of the card
                  width on all four edges - for cards where the artwork
                  reaches the cut edge and no measurement can tell frame
                  from art.
    """
    if amount <= 0:
        return im
    w, h = im.size
    arr = np.array(im, dtype=np.uint8)
    lum = np.array([0.299, 0.587, 0.114], dtype=np.float32)
    lim_v = min(int(h * BORDER_MAX_DEPTH), h // 2)
    lim_h = min(int(w * BORDER_MAX_DEPTH), w // 2)

    # Scanning happens at native resolution: on a downscaled copy the white
    # collector text bleeds into the black band and stops the scan there.
    # Only the four edge strips are converted, never the whole card.
    # Depth is measured at full resolution, but only every Nth line ALONG the
    # edge is scanned: the frame's depth changes slowly, and the profile is
    # median-smoothed afterwards anyway. Cuts the work ~4x.
    step = BORDER_ALONG_STEP

    def strip(sl_y, sl_x):
        px = arr[sl_y, sl_x].astype(np.float32)
        g = px @ lum
        c = px.max(axis=2) - px.min(axis=2)      # chroma: 0 = neutral grey
        m = opaque[sl_y, sl_x] if opaque is not None else None
        return g, c, m

    top_s = strip(slice(0, lim_v), slice(None, None, step))
    bot_s = strip(slice(h - lim_v, h), slice(None, None, step))
    left_s = strip(slice(None, None, step), slice(0, lim_h))
    right_s = strip(slice(None, None, step), slice(w - lim_h, w))

    def flip(x):
        return None if x is None else x[::-1]

    def tr(x):
        return None if x is None else x.T

    # lines ordered from the edge inwards, so depth == index
    edges = [
        (top_s[0], top_s[1], top_s[2]),
        (flip(bot_s[0]), flip(bot_s[1]), flip(bot_s[2])),
        (tr(left_s[0]), tr(left_s[1]), tr(left_s[2])),
        (flip(tr(right_s[0])), flip(tr(right_s[1])), flip(tr(right_s[2]))),
    ]

    t = max(2, int(min(w, h) * BORDER_RING_FRAC))

    if manual_width > 0:
        # user-set width: uniform depth on every edge, no detection at all
        depth = manual_width * w
        prof_top = np.full(w, depth, np.float32)
        prof_bot = np.full(w, depth, np.float32)
        prof_left = np.full(h, depth, np.float32)
        prof_right = np.full(h, depth, np.float32)
        ring = []
        for lines, _c, masks in edges:
            band = lines[:t]
            ring.append(band[masks[:t]] if masks is not None else band.ravel())
        vals = np.concatenate(ring)
        black = float(np.percentile(vals, 60)) if vals.size else 0.0
        return _apply_border(im, arr, w, h, lum, black,
                             prof_top, prof_bot, prof_left, prof_right, amount)

    # ---- what level does this card's black frame sit at?
    perim, perim_c = [], []
    for lines, chroma, masks in edges:
        band, cband = lines[:t], chroma[:t]
        if masks is not None:
            perim.append(band[masks[:t]]); perim_c.append(cband[masks[:t]])
        else:
            perim.append(band.ravel()); perim_c.append(cband.ravel())
    perim = np.concatenate(perim)
    perim_c = np.concatenate(perim_c)
    if perim.size == 0:
        return im
    # frame candidates: dark AND neutral
    dark = perim[(perim <= BORDER_MAX_LEVEL) & (perim_c <= BORDER_MAX_CHROMA)]
    if dark.size < perim.size * BORDER_MIN_SHARE:
        return im                        # nothing frame-like around the card
    # The frame is a big area sitting at one exact level, so it shows up as a
    # spike in the histogram. Take that peak, not the median: dark artwork
    # around the edges drags a median away from it (measured on Solitude SPG,
    # frame at 29 but median 33, close enough to the navy sky at 44 to start
    # eating the art).
    hist, bins = np.histogram(dark, bins=np.arange(0, BORDER_MAX_LEVEL + 3, 2))
    peak = int(np.argmax(hist))
    # count the bins next to the peak too: a frame's level straddles a bin
    # boundary often enough that a single bin under-counts it by half
    share = hist[max(0, peak - 1):peak + 2].sum()
    if share < perim.size * BORDER_MIN_SHARE:
        return im                        # no dominant dark level
    near = dark[(dark >= bins[peak] - 2) & (dark <= bins[peak + 1] + 2)]
    black = float(np.median(near))

    # ---- how deep is the black frame along EVERY line of every edge?
    # One depth per edge is still too coarse: on Special Guest printings a
    # side is artwork along its top half and a real black frame beside the
    # text box, so the whole side used to be discarded. A pixel counts as
    # frame while it stays at the card's black level; transparent corner
    # pixels don't break the run (they are already black).
    def edge_profile(lines, chroma, masks):
        ok = (np.abs(lines - black) <= BORDER_LEVEL_TOL) &              (chroma <= BORDER_MAX_CHROMA)
        if masks is not None:
            ok |= ~masks
        # The frame ends where several CONSECUTIVE pixels leave its level.
        # A single stray pixel must not end it: cards carry one or two
        # anti-aliased pixels right at the cut edge (measured 15, 53, 29, 15,
        # 15 ... on Bloodstained Mire), which used to stop the scan at once
        # and leave the rest of the band untreated.
        n = lines.shape[0]
        brk = max(6, int(w * BORDER_BREAK_FRAC))
        if n <= brk:
            return np.zeros(lines.shape[1], dtype=np.float32)
        # rolling count of off-level pixels via a cumulative sum: a sliding
        # window view here costs brk times more work for the same answer
        bad = (~ok).astype(np.int32)
        cs = np.cumsum(bad, axis=0)
        zero = np.zeros((1, bad.shape[1]), np.int32)
        ends = (cs[brk - 1:] - np.concatenate([zero, cs[:n - brk]])) == brk
        depth = np.argmax(ends, axis=0).astype(np.float32)
        depth[~ends.any(axis=0)] = n
        depth[depth < BORDER_MIN_DEPTH] = 0.0
        # A real black frame runs the whole length of its side; dark artwork
        # only looks like a frame in patches. If most of this side is NOT
        # frame, it is art reaching the cut edge (extended-art borders), so
        # drop the whole side rather than blacken those patches. Measured:
        # true frames cover >=96% of the side, art sides 30-71%.
        if (depth > 0).mean() < BORDER_SIDE_COVERAGE:
            depth[:] = 0.0
        return _smooth_profile(depth, max(3, BORDER_SMOOTH // step))

    def expand(profile, size):
        return np.repeat(profile, step)[:size].astype(np.float32)

    prof_top, prof_bot = (expand(edge_profile(*e), w) for e in edges[:2])
    prof_left, prof_right = (expand(edge_profile(*e), h) for e in edges[2:])
    if not any(p.max() > 0 for p in (prof_top, prof_bot, prof_left, prof_right)):
        return im

    return _apply_border(im, arr, w, h, lum, black,
                         prof_top, prof_bot, prof_left, prof_right, amount)


def _apply_border(im, arr, w, h, lum, black,
                  prof_top, prof_bot, prof_left, prof_right, amount):
    """Blend the frame towards true black using the per-line depth profiles."""
    fade = max(2.0, w * BORDER_FADE_FRAC)
    black_point = min(black + BORDER_LEVEL_TOL + 6, BORDER_TONE_MAX - 5)
    k = 255.0 / (255.0 - black_point)
    amount = float(np.clip(amount, 0.0, 1.0))

    # Only the frame band can change (spatial weight is 0 further in), so we
    # touch a fraction of the pixels. Each side spans its own deepest run.
    def band_of(profile, size):
        d = float(profile.max())
        return 0 if d <= 0 else min(int(d + fade) + 2, size // 2)

    tb = band_of(prof_top, h)
    bb = band_of(prof_bot, h)
    lb = band_of(prof_left, w)
    rb = band_of(prof_right, w)

    def treat(y0, y1, x0, x1):
        sub = arr[y0:y1, x0:x1].astype(np.float32)
        yy = np.arange(y0, y1, dtype=np.float32)[:, None]
        xx = np.arange(x0, x1, dtype=np.float32)[None, :]
        # ---- guard 2: spatial weight, per line, so a side that is artwork
        # along part of its length and frame along the rest works out.
        # `* (p > 0)` matters: without it a line with no frame at all would
        # still get full weight at the very edge.
        def term(p, dist):
            return np.clip((p + fade - dist) / fade, 0.0, 1.0) * (p > 0)

        terms = [
            term(prof_top[None, x0:x1], yy),
            term(prof_bot[None, x0:x1], h - 1 - yy),
            term(prof_left[y0:y1, None], xx),
            term(prof_right[y0:y1, None], w - 1 - xx),
        ]
        spatial = np.maximum.reduce(np.broadcast_arrays(*terms))
        # ---- guard 3: a frame pixel goes fully to black, it is never left at
        # a fraction. A proportional weight turned the grey transition between
        # the black frame and the text box (and the halo around the credit
        # line) into an uneven mid-grey that prints as mottling. So the
        # decision is binary per pixel: inside the frame AND dark -> solid
        # black; anything else keeps its value. `amount` scales the black we
        # blend to, so the effect can still be softened globally.
        gray = sub @ lum
        treat = (spatial > 0.5) & (gray < BORDER_TONE_MAX)
        black_to = (1.0 - amount)          # 0 at full strength
        out = sub.copy()
        out[treat] = out[treat] * black_to
        arr[y0:y1, x0:x1] = out.astype(np.uint8)

    if tb:
        treat(0, tb, 0, w)
    if bb:
        treat(h - bb, h, 0, w)
    if (lb or rb) and h - bb > tb:
        if lb:
            treat(tb, h - bb, 0, lb)
        if rb:
            treat(tb, h - bb, w - rb, w)
    return Image.fromarray(arr, "RGB")


def _round_corners(im: Image.Image, radius_mm: float) -> Image.Image:
    """Return an RGBA copy with the card's corners rounded to transparency,
    so the paper (or bleed frame) shows through when drawn with mask='auto'."""
    r = int(radius_mm * im.width / 63.0)     # 63 mm = card width
    if r <= 0:
        return im.convert("RGBA")
    im = im.convert("RGBA")
    mask = Image.new("L", im.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, im.width - 1, im.height - 1], radius=r, fill=255)
    im.putalpha(mask)
    return im


# Deciding whether a card is bordered or full-art. A near-black edge means a
# framed card, where the honest extension is to carry the frame outward; a
# mirror there would fold the frame's INNER detail back out and read as a
# reflection. Full art has no frame to protect, so mirroring continues the
# picture. Thresholds follow proxy-print's add-bleed, which solves the same
# problem and is worth agreeing with rather than diverging from by accident.
BLEED_BLACK_THRESHOLD = 30      # per-channel value still counted as black
BLEED_BLACK_RATIO = 0.7         # fraction of the edge that has to be black
BLEED_STRETCH_SLICE = 8         # px of edge stretched outward on framed cards
BLEED_MIRROR_BLEND = 4          # px of overlap, so the seam is not a hard line


def _edge_is_framed(arr) -> bool:
    """True when the card's outer pixels are mostly black, i.e. it has a frame."""
    edges = np.concatenate([arr[0], arr[-1], arr[:, 0], arr[:, -1]])
    dark = (edges < BLEED_BLACK_THRESHOLD).all(axis=1)
    return float(dark.mean()) > BLEED_BLACK_RATIO


def extend_bleed(im: Image.Image, bleed_px: int) -> Image.Image:
    """Grow the card by `bleed_px` a side, continuing its own art outward.

    The alternative the app shipped first is a flat colour frame, which is
    fine on a black-bordered card and obvious on a full-art one. This keeps
    the cut running through something that looks like the card.
    """
    if bleed_px <= 0:
        return im
    im = im.convert("RGB")
    w, h = im.size
    b = int(bleed_px)
    out = Image.new("RGB", (w + 2 * b, h + 2 * b))
    out.paste(im, (b, b))

    if _edge_is_framed(np.asarray(im)):
        # stretch a thin slice: on a frame that just continues the frame
        s = min(BLEED_STRETCH_SLICE, w // 2, h // 2)
        out.paste(im.crop((0, 0, s, h)).resize((b, h)), (0, b))
        out.paste(im.crop((w - s, 0, w, h)).resize((b, h)), (w + b, b))
        out.paste(im.crop((0, 0, w, s)).resize((w, b)), (b, 0))
        out.paste(im.crop((0, h - s, w, h)).resize((w, b)), (b, h + b))
        corners = ((0, 0, s, s, 0, 0), (w - s, 0, w, s, w + b, 0),
                   (0, h - s, s, h, 0, h + b), (w - s, h - s, w, h, w + b, h + b))
        for x0, y0, x1, y1, dx, dy in corners:
            out.paste(im.crop((x0, y0, x1, y1)).resize((b, b)), (dx, dy))
        return out

    # full art: mirror the edge band outward. The band is taken a few pixels
    # deeper than the bleed so the mirrored copy overlaps its own source and
    # the join does not fall exactly on a hard edge.
    band = min(b + BLEED_MIRROR_BLEND, w, h)
    left = im.crop((0, 0, band, h)).transpose(Image.FLIP_LEFT_RIGHT)
    out.paste(left.crop((band - b, 0, band, h)), (0, b))
    right = im.crop((w - band, 0, w, h)).transpose(Image.FLIP_LEFT_RIGHT)
    out.paste(right.crop((0, 0, b, h)), (w + b, b))
    top = im.crop((0, 0, w, band)).transpose(Image.FLIP_TOP_BOTTOM)
    out.paste(top.crop((0, band - b, w, band)), (b, 0))
    bottom = im.crop((0, h - band, w, h)).transpose(Image.FLIP_TOP_BOTTOM)
    out.paste(bottom.crop((0, 0, w, b)), (b, h + b))

    # corners: flipped both ways, so each meets the two edges beside it
    for x0, y0, dx, dy in ((0, 0, 0, 0), (w - b, 0, w + b, 0),
                           (0, h - b, 0, h + b), (w - b, h - b, w + b, h + b)):
        piece = im.crop((x0, y0, x0 + b, y0 + b)).transpose(
            Image.FLIP_LEFT_RIGHT).transpose(Image.FLIP_TOP_BOTTOM)
        out.paste(piece, (dx, dy))
    return out


def _flatten(png_path: Path, jpeg_quality, profile=None, sharpen=None,
             shadow=0, deepen_border=False, border_amount=1.0,
             border_width=0.0, corner_radius_mm=0.0, suffix="_sheet",
             border_style=BORDER_STYLE_CONTRAST, edge_width=CONTRAST_EDGE_WIDTH,
             edge_contrast=CONTRAST_CONTRAST,
             edge_brightness=CONTRAST_BRIGHTNESS, bleed_px=0) -> Path:
    """
    Flatten transparent rounded corners onto black, apply the print-time
    adjustments, and write the temp file the PDF will embed.

    jpeg_quality None -> PNG (Flate, pixel-identical apart from adjustments)
    corner_radius_mm > 0 rounds the output corners to transparency (forces
    PNG so the alpha survives; drawn over paper/bleed with mask='auto').
    """
    im = Image.open(png_path).convert("RGBA")
    alpha = im.split()[3]
    bg = Image.new("RGB", im.size, (0, 0, 0))
    bg.paste(im, mask=alpha)

    if (profile and profile[1:] != (1.0, 1.0, 1.0)) or shadow > 0:
        bg = _apply_profile(bg, profile, shadow)
    if sharpen:
        radius, percent, threshold = sharpen
        bg = bg.filter(ImageFilter.UnsharpMask(
            radius=radius, percent=percent, threshold=threshold))
    if deepen_border:
        # last, so it also undoes the shadow lift inside the border
        opaque = np.asarray(alpha) > 250
        if border_style == BORDER_STYLE_CONTRAST:
            bg = _contrast_edges(bg, opaque, border_amount, edge_width,
                                 edge_contrast, edge_brightness)
        else:
            bg = _deepen_black_border(bg, opaque, border_amount, border_width)

    # Grown last, so every adjustment above is already in the pixels being
    # carried outward. With rounded corners on, the radius applies to the
    # extended outline: the cut runs inside the bleed anyway, so the card's own
    # corners are still cut round.
    if bleed_px > 0:
        bg = extend_bleed(bg, bleed_px)

    if corner_radius_mm > 0:
        out = TEMP_FOLDER / (png_path.stem + suffix + ".png")
        _round_corners(bg, corner_radius_mm).save(out, "PNG", dpi=(1200, 1200))
    elif jpeg_quality is None:
        out = TEMP_FOLDER / (png_path.stem + suffix + ".png")
        bg.save(out, "PNG", dpi=(1200, 1200))
    else:
        out = TEMP_FOLDER / (png_path.stem + suffix + ".jpg")
        bg.save(out, "JPEG", quality=jpeg_quality, dpi=(1200, 1200))
    return out


# --------------------------------------------------------------------------
# page drawing
# --------------------------------------------------------------------------

# guide-cross colors selectable in the export dialog
GUIDE_COLORS = {
    "White": (1, 1, 1),
    "Black": (0, 0, 0),
    "Gray": (0.45, 0.45, 0.45),
    "None": None,
}

# bleed-frame colors (edge printed around each card, cut runs through it)
BLEED_COLORS = {
    "Black": (0, 0, 0),
    "White": (1, 1, 1),
}

# ...or no colour at all: grow the card's own art into the bleed instead. A
# flat frame is fine behind a black-bordered card and obvious behind full art.
BLEED_EXTEND = "Extend art"


# --- Silhouette / Cricut registration marks -------------------------------
# Geometry the cutter's optical sensor expects (same spec the silhouette-card-
# maker project implements): a 5x5 mm filled square at the top-left plus
# L-shaped brackets at the other corners. The CAMEO 5a reads a 4-mark pattern
# where the top-left square is an L too.
REG_SQUARE_MM = 5.0          # side of the filled top-left square (3-mark)
REG_LENGTH_MIN_MM = 5.0
REG_LENGTH_MAX_MM = 20.0
REG_THICK_MIN_MM = 0.5
REG_THICK_MAX_MM = 1.0
# How close a mark may sit to the paper edge.
#
# Studio documents 0.394 in (10 mm) as its minimum, and that was our floor,
# but it is what costs card slots, because the corner marks land on the corner
# cards. Measured on our own layouts: Letter 3x3 goes from 6 usable cards to 9,
# Letter 4x2 from 6 to 8, A4 3x3 from 7 to 9, purely by moving the marks
# outward. silhouette-card-maker (the project this geometry came from) ships
# 3.5 mm for its borderless layouts, so Studio's "minimum" is evidently a
# recommendation rather than a hard limit.
#
# 3.5 mm is the floor rather than something smaller because most inkjets
# cannot print within ~3 mm of the paper edge (the same reason MIN_BOTTOM
# exists) - a mark below that would simply be clipped off by the printer.
# The DEFAULT stays at Studio's 10 mm: lowering it is a lever the user can
# reach for when they want the slots back, not a silent change to their output.
REG_INSET_MIN_MM = 3.5
# Silhouette Studio's published figures, cross-checked against the settings
# panel Proxxied exposes (its numbers are in inches):
#
#     mark inset      0.394 in = 10.008 mm   (minimum)
#     mark length     0.350 in =  8.890 mm   (default)
#     mark thickness  0.039 in =  0.991 mm   (maximum)
#
# The inset minimum and thickness maximum already matched REG_INSET_MIN_MM and
# REG_THICK_MAX_MM, which is what confirms these are the same spec this code
# was built from. The length did NOT: it defaulted to 5 mm (our own minimum)
# where Studio expects 8.89, so marks came out visibly shorter than a
# Studio-made template's. That, not the inset, is the size mismatch.
REG_INSET_DEFAULT_MM = 10.0     # Studio's minimum, and what Proxxied ships
REG_LENGTH_DEFAULT_MM = 8.89    # 0.350 in, Studio's default
REG_PADDING_MM = 1.5            # clear space the sensor needs around a mark
REG_PATTERNS = ["3 marks (standard)", "4 marks (CAMEO 5a)"]


def _reg_geometry(pw, ph, inset_mm, length_mm, thick_mm, four=False):
    """Marks as ([(x0,y0,x1,y1) filled rects], [keep-clear boxes]) in points.

    Coordinates are reportlab's (origin bottom-left). Each mark is drawn as
    filled rectangles so the thickness is exact at any resolution.
    """
    length_mm = max(REG_LENGTH_MIN_MM, min(length_mm, REG_LENGTH_MAX_MM))
    thick_mm = max(REG_THICK_MIN_MM, min(thick_mm, REG_THICK_MAX_MM))
    inset_mm = max(REG_INSET_MIN_MM, inset_mm)

    ins, ln, th = inset_mm * mm, length_mm * mm, thick_mm * mm
    sq = REG_SQUARE_MM * mm
    pad = REG_PADDING_MM * mm
    rects, clear = [], []

    def L(cx, cy, dx, dy):
        """Bracket with its corner at (cx, cy), arms running dx/dy (±1)."""
        x0, x1 = sorted((cx, cx + dx * ln))
        y0, y1 = sorted((cy, cy + dy * th))
        rects.append((x0, y0, x1, y1))                    # horizontal arm
        x2, x3 = sorted((cx, cx + dx * th))
        y2, y3 = sorted((cy, cy + dy * ln))
        rects.append((x2, y2, x3, y3))                    # vertical arm
        bx0, bx1 = sorted((cx, cx + dx * ln))
        by0, by1 = sorted((cy, cy + dy * ln))
        clear.append((bx0 - pad, by0 - pad, bx1 + pad, by1 + pad))

    # top-left: filled square (3-mark) or bracket (4-mark)
    if four:
        L(ins, ph - ins, +1, -1)
    else:
        # 5x5 mm filled, then grown by half the line thickness on every side.
        # silhouette-card-maker draws this as a Rectangle with edgecolor and
        # linewidth=thickness, and a stroke is centred on the path - so their
        # square reaches 5 + thickness across (6 mm at the 1 mm default) while
        # a plain filled 5 mm rect, which is what this used to be, comes out a
        # millimetre smaller. Reported from Reddit as "marks smaller than SCM's".
        half = th / 2.0
        x0, y0 = ins - half, ph - ins - sq - half
        side = sq + th
        rects.append((x0, y0, x0 + side, y0 + side))
        clear.append((x0 - pad, y0 - pad, x0 + side + pad, y0 + side + pad))

    L(pw - ins, ph - ins, -1, -1)          # top-right
    L(ins, ins, +1, +1)                    # bottom-left
    if four:
        L(pw - ins, ins, -1, +1)           # bottom-right
    return rects, clear


def _draw_reg_marks(c, pw, ph, inset_mm, length_mm, thick_mm, four=False):
    rects, _ = _reg_geometry(pw, ph, inset_mm, length_mm, thick_mm, four)
    c.setFillColorRGB(0, 0, 0)
    for x0, y0, x1, y1 in rects:
        c.rect(x0, y0, x1 - x0, y1 - y0, stroke=0, fill=1)


def best_inset(page_name, card_w, card_h, layout, length_mm, thick_mm,
               four=False, start_mm=None):
    """
    The LARGEST mark inset that still keeps every slot on this layout, or None
    if no allowed inset does.

    Largest, not smallest: a mark further from the paper edge is the safer one
    (more margin before the printer's unprintable border), so the useful advice
    is the gentlest move that recovers the cards rather than the extreme.
    """
    page = PAGES.get(page_name, A4)
    cols, rows, landscape = LAYOUTS.get(layout, LAYOUTS[DEFAULT_LAYOUT])
    pw, ph = (page[1], page[0]) if landscape else page
    bw, bh = cols * card_w, rows * card_h
    if bw > pw or bh > ph:
        return None
    ox, oy = _block_origin(pw, ph, bw, bh, 0.0)
    pos = layout_positions(layout, ox, oy, bh, 0.0, cols, rows, card_w, card_h)

    top = start_mm if start_mm is not None else REG_INSET_DEFAULT_MM
    steps = int((top - REG_INSET_MIN_MM) / 0.5)
    for i in range(steps + 1):
        inset = round(top - i * 0.5, 2)
        if inset < REG_INSET_MIN_MM:
            break
        if not _reg_blocked_slots(pos, card_w, card_h, pw, ph,
                                  inset, length_mm, thick_mm, four):
            return inset
    return None


def clean_layouts(page_name, card_w, card_h, inset_mm, length_mm, thick_mm,
                  four=False):
    """Names of the layouts that keep every slot on this page, marks and all.

    Computed rather than remembered: which layouts stay clean depends on the
    page, the card size and the mark geometry, and the advice went stale once
    the marks moved to Silhouette Studio's dimensions.
    """
    page = PAGES.get(page_name, A4)
    clean = []
    for name, (cols, rows, landscape) in LAYOUTS.items():
        pw, ph = (page[1], page[0]) if landscape else page
        bw, bh = cols * card_w, rows * card_h
        if bw > pw or bh > ph:
            continue
        ox, oy = _block_origin(pw, ph, bw, bh, 0.0)
        pos = layout_positions(name, ox, oy, bh, 0.0, cols, rows, card_w, card_h)
        if not _reg_blocked_slots(pos, card_w, card_h, pw, ph,
                                  inset_mm, length_mm, thick_mm, four):
            clean.append(name)
    return clean


def _reg_blocked_slots(positions, card_w, card_h, pw, ph,
                       inset_mm, length_mm, thick_mm, four=False):
    """Indices of `positions` whose card would collide with a mark's
    keep-clear box. Those slots are left empty so the sensor can read them."""
    _, clear = _reg_geometry(pw, ph, inset_mm, length_mm, thick_mm, four)
    blocked = set()
    for idx, (x, y) in enumerate(positions):
        for cx0, cy0, cx1, cy1 in clear:
            if x < cx1 and x + card_w > cx0 and y < cy1 and y + card_h > cy0:
                blocked.add(idx)
                break
    return blocked


def _boundaries(origin, size, gutter, count=3):
    """Card-edge coordinates along one axis (duplicates removed at gutter 0)."""
    edges = []
    for i in range(count):
        a = origin + i * (size + gutter)
        edges.append(a)
        edges.append(a + size)
    return sorted(set(edges))


def _draw_marks(c, ox, oy, block_w, block_h, gutter=0.0, guide_rgb=(1, 1, 1),
                cols=COLS, rows=ROWS, guide_len_mm=4.0, guide_thick=0.4,
                guide_style="Cross", guide_offset_mm=0.0,
                card_w=CARD_W, card_h=CARD_H, clear_boxes=()):
    xs = _boundaries(ox, card_w, gutter, cols)
    ys = _boundaries(oy, card_h, gutter, rows)
    tick = guide_len_mm * mm
    # The gap between the corner and where each arm starts. "Corner" guides
    # default to a small gap (crop-mark look); an explicit offset overrides it
    # for either style. "Cross" with no offset is a solid plus.
    if guide_offset_mm > 0:
        gap = guide_offset_mm * mm
    else:
        gap = 0.9 * mm if guide_style == "Corner" else 0.0

    # Nothing may land inside a registration mark's keep-clear area: the
    # cutter reads those marks optically and a stray line beside one can throw
    # the scan off. On A4 at the default inset several marks did exactly that.
    def _clear(x0, y0, x1, y1):
        lx0, lx1 = sorted((x0, x1))
        ly0, ly1 = sorted((y0, y1))
        for bx0, by0, bx1, by1 in clear_boxes:
            if not (lx1 < bx0 or lx0 > bx1 or ly1 < by0 or ly0 > by1):
                return False
        return True

    # ticks at every card corner (over borders / bleed frames)
    if guide_rgb is not None:
        c.setLineWidth(guide_thick)
        c.setStrokeColorRGB(*guide_rgb)
        for x in xs:
            for y in ys:
                for seg in (
                    # vertical arms (up / down from the corner)
                    (x, min(y + gap, oy + block_h),
                     x, min(y + tick, oy + block_h)),
                    (x, max(y - gap, oy), x, max(y - tick, oy)),
                    # horizontal arms (right / left from the corner)
                    (min(x + gap, ox + block_w), y,
                     min(x + tick, ox + block_w), y),
                    (max(x - gap, ox), y, max(x - tick, ox), y),
                ):
                    if _clear(*seg):
                        c.line(*seg)

    # Dark tick marks in the margins, aligned to every boundary.
    #
    # These are guides too. Turning guides off used to leave them printed
    # (the setting only gated the corner crosses above), so the page still came
    # out with dark marks in the margins.
    if guide_rgb is None:
        return

    c.setLineWidth(0.4)
    c.setStrokeColorRGB(0.4, 0.4, 0.4)
    for x in xs:
        for seg in ((x, oy + block_h + MARK_GAP,
                     x, oy + block_h + MARK_GAP + MARK_LEN),
                    (x, oy - MARK_GAP, x, oy - MARK_GAP - MARK_LEN)):
            if _clear(*seg):
                c.line(*seg)
    for y in ys:
        for seg in ((ox - MARK_GAP, y, ox - MARK_GAP - MARK_LEN, y),
                    (ox + block_w + MARK_GAP, y,
                     ox + block_w + MARK_GAP + MARK_LEN, y)):
            if _clear(*seg):
                c.line(*seg)


def _card_pos(idx, ox, oy, block_h, gutter=0.0, cols=COLS,
              card_w=CARD_W, card_h=CARD_H):
    col = idx % cols
    row = idx // cols
    x = ox + col * (card_w + gutter)
    y = oy + block_h - (row + 1) * card_h - row * gutter
    return x, y


def layout_positions(layout, ox, oy, block_h, gutter, cols, rows,
                     card_w=CARD_W, card_h=CARD_H):
    """Card origins for one sheet, in placement order. Plain grids fill
    left-to-right, top-to-bottom; SEVEN_CARD uses its own arrangement."""
    if layout == SEVEN_CARD:
        pos = [(ox, oy + (block_h - card_h) / 2)]          # lone left card
        for i in range(6):
            col, row = 1 + i % 3, i // 3
            pos.append((ox + col * (card_w + gutter),
                        oy + block_h - (row + 1) * card_h - row * gutter))
        return pos
    return [_card_pos(i, ox, oy, block_h, gutter, cols, card_w, card_h)
            for i in range(cols * rows)]


def mirror_x(x, ox, block_w, card_w):
    """Reflect a card origin across the block's vertical centre line, so a
    back lands behind its front when the sheet is flipped on the long edge."""
    return ox + block_w - (x - ox) - card_w


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------

def build_pdf(images, out_path, page_name="A4", quality=PDF_DEFAULT_QUALITY,
              sharpen_name="Off", profile_id=1, shadow_name="Off",
              pages_per_file=0, backs=None, back_offset=(0.0, 0.0),
              back_bleed_mm=1.5, back_rotation_deg=0.0, shift_down_mm=0.0,
              edge_bleed_mm=0.0, bleed_color="Black", guide_color="White",
              back_guides=True,
              guide_len_mm=4.0, guide_thick=0.4, guide_style="Cross",
              guide_offset_mm=0.0, corner_radius_mm=0.0,
              layout=DEFAULT_LAYOUT, deepen_border=False, border_modes=None,
              border_style=BORDER_STYLE_CONTRAST,
              edge_width=CONTRAST_EDGE_WIDTH,
              edge_contrast=CONTRAST_CONTRAST,
              edge_brightness=CONTRAST_BRIGHTNESS,
              border_amount=1.0, border_width=0.0, sheets_sel=None,
              card_size_mm=None, reg_marks=False,
              reg_inset_mm=REG_INSET_DEFAULT_MM,
              reg_length_mm=REG_LENGTH_DEFAULT_MM,
              reg_thick_mm=1.0, reg_pattern=REG_PATTERNS[0],
              status_callback=None) -> list[Path]:
    """
    Compose `images` (paths, in order) into one or more print-sheet PDFs.

    pages_per_file: 0 = single file; N = split every N sheets into
                    name-01.pdf, name-02.pdf, ...
    backs:          None = fronts only. Otherwise a list parallel to
                    `images`: a back-face path per slot, or None to use the
                    user-supplied back.png. Each front page is followed by a
                    column-mirrored back page for duplex printing
                    (flip on long edge).
    back_offset:    (dx_mm, dy_mm) shift applied to the back pages only, to
                    compensate the printer's duplex misalignment. The back's
                    cut guides move with its cards - they mark where those
                    cards will be, not where the fronts are.
    back_bleed_mm:  backs are drawn oversized by this much on every edge, so
                    duplex drift up to ~that amount never exposes a white
                    sliver when cutting along the FRONT's marks.
    back_rotation_deg: back pages are rotated by this angle about the page
                    centre, to correct angular duplex drift (instead of hiding
                    it with more back bleed). Dial it in with build_duplex_test.
    guide_len_mm / guide_thick / guide_style: cut-guide length, line width and
                    "Cross" (solid +) vs "Corner" (gapped crop marks).
    corner_radius_mm: >0 rounds every card's printed corners.
    card_size_mm:   (w, h) in mm for non-MTG TCGs; None = 63x88.
    reg_marks:      draw Silhouette/Cricut registration marks. Card slots that
                    a mark would sit on are left empty so the cutter's sensor
                    can read them, which lowers the cards per sheet.
    edge_bleed_mm:  fronts get a colored bleed frame this wide around each
                    card; cards are separated by a 2x gutter so the cut runs
                    through the frame - small cut drift shows frame color,
                    never white paper or the neighboring card.
    bleed_color:    key of BLEED_COLORS for that frame.
    guide_color:    key of GUIDE_COLORS for the corner cross guides.
    back_guides:    draw those guides on the BACK pages too. On by default,
                    which is how it always behaved. Turning it off matters for
                    duplex: the back's guides never land exactly where the
                    front's do, so a second set that disagrees with the one you
                    are cutting to is worse than none. You cut by the front.
    Returns the list of files written.
    """
    images = [Path(p) for p in images]
    if not images:
        raise ValueError("No images to lay out")

    if backs is not None:
        default_back = find_back_image()
        if any(b is None for b in backs) and default_back is None:
            raise ValueError(
                "back.png not found.\nPut a card-back image named back.png "
                "(or back.jpg) in the Cardwright folder - it is used for "
                "every card that has no double-faced back of its own.")
        backs = [Path(b) if b else default_back for b in backs]

    jpeg_quality = PDF_QUALITY_MODES.get(
        quality, PDF_QUALITY_MODES[PDF_DEFAULT_QUALITY])
    sharpen = SHARPEN_MODES.get(sharpen_name)
    profile = CALIBRATION_PROFILES.get(profile_id)
    shadow = SHADOW_LIFTS.get(shadow_name, 0)

    cols, rows, landscape = LAYOUTS.get(layout, LAYOUTS[DEFAULT_LAYOUT])
    per_page = cols * rows
    page = PAGES.get(page_name, A4)
    if landscape:
        page = (page[1], page[0])
    pw, ph = page
    card_w, card_h = ((card_size_mm[0] * mm, card_size_mm[1] * mm)
                      if card_size_mm else (CARD_W, CARD_H))
    gutter = 2 * edge_bleed_mm * mm
    block_w = cols * card_w + (cols - 1) * gutter
    block_h = rows * card_h + (rows - 1) * gutter
    if block_w > pw - 2 * MIN_BOTTOM or block_h > ph - 2 * MIN_BOTTOM:
        raise ValueError("Card block too large for this page size "
                         "(reduce edge bleed, card size or grid)")
    # Registration marks make shift-down pointless and harmful: the cutter
    # finds the marks wherever the paper actually fed and cuts relative to
    # them, so it self-compensates. Shifting only the cards would break that
    # card-to-mark relationship (and push cards under the marks).
    ox, oy = _block_origin(pw, ph, block_w, block_h,
                           0.0 if reg_marks else shift_down_mm)
    guide_rgb = GUIDE_COLORS.get(guide_color, (1, 1, 1))

    bleed_rgb = BLEED_COLORS.get(bleed_color, (0, 0, 0))
    ebleed = edge_bleed_mm * mm
    # "Extend art" grows the image instead of painting a frame behind it, so
    # the card is drawn over the whole slot-plus-bleed rather than inside it.
    extend_art = bleed_color == BLEED_EXTEND and ebleed > 0
    grow_px = 0
    if extend_art:
        # the flattened card is CARD_W wide in points; convert the bleed to
        # that image's own pixels so the band is exactly edge_bleed_mm
        with Image.open(images[0]) as _probe:
            grow_px = int(round(_probe.width * (ebleed / card_w)))
    dx = back_offset[0] * mm
    dy = back_offset[1] * mm
    img_mask = "auto" if corner_radius_mm > 0 else None

    # Slots a registration mark sits on are left empty: the cutter's sensor
    # needs those corners clear, so cards flow into the remaining slots.
    all_pos = layout_positions(layout, ox, oy, block_h, gutter, cols, rows,
                               card_w, card_h)
    reg_four = reg_pattern == REG_PATTERNS[1]

    # Keep-clear boxes around the registration marks, so no guide or margin
    # tick lands beside one. Empty when marks are off - nothing to avoid then.
    reg_clear = ()
    if reg_marks:
        _, reg_clear = _reg_geometry(pw, ph, reg_inset_mm, reg_length_mm,
                                     reg_thick_mm, reg_four)

    # The back page draws its guides inside the offset transform (below), so
    # the keep-clear boxes - which are page coordinates - have to be restated
    # in that frame or the shift would walk a guide into a mark.
    back_clear = tuple((x0 - dx, y0 - dy, x1 - dx, y1 - dy)
                       for x0, y0, x1, y1 in reg_clear)

    blocked = _reg_blocked_slots(
        all_pos, card_w, card_h, pw, ph, reg_inset_mm, reg_length_mm,
        reg_thick_mm, reg_four) if reg_marks else set()
    usable = [p for i, p in enumerate(all_pos) if i not in blocked]
    if not usable:
        raise ValueError("Registration marks cover every card slot - "
                         "use a smaller grid, card size or mark length")
    slots_per_page = len(usable)

    # split the card list into sheets, then sheets into files
    idxs = list(range(len(images)))
    batches = [idxs[i:i + slots_per_page]
               for i in range(0, len(idxs), slots_per_page)]
    if sheets_sel is not None:
        # keep only the chosen sheets (0-based indices), e.g. "print sheet 1"
        batches = [b for i, b in enumerate(batches) if i in sheets_sel]
        if not batches:
            raise ValueError("The selected sheet range has no sheets")

    # Count what will ACTUALLY be placed, not how many cards exist: with a
    # sheet selection the progress read "card 3/90" while only 9 were going
    # into the PDF.
    to_place = sum(len(b) for b in batches)
    if pages_per_file and pages_per_file > 0:
        groups = [batches[i:i + pages_per_file]
                  for i in range(0, len(batches), pages_per_file)]
    else:
        groups = [batches]

    out_path = Path(out_path)
    written = []
    flat_cache = {}

    modes = border_modes or {}

    def flat(img):
        # "auto" follows the global switch; "on"/"off" are per-card overrides
        mode = modes.get(str(img), "auto")
        do_border = deepen_border if mode == "auto" else (mode == "on")
        # a forced card uses the manual width, if one is set; auto cards
        # always measure their own
        width = border_width if mode == "on" else 0.0
        key = (str(img), do_border, width, border_style, grow_px)
        if key not in flat_cache:
            flat_cache[key] = _flatten(img, jpeg_quality, profile, sharpen,
                                       shadow, do_border, border_amount, width,
                                       corner_radius_mm=corner_radius_mm,
                                       border_style=border_style,
                                       edge_width=edge_width,
                                       edge_contrast=edge_contrast,
                                       edge_brightness=edge_brightness,
                                       bleed_px=grow_px)
        return flat_cache[key]

    placed = 0
    for gi, group in enumerate(groups):
        if len(groups) == 1:
            target = out_path
        else:
            target = out_path.with_name(f"{out_path.stem}-{gi + 1:02d}{out_path.suffix}")

        c = canvas.Canvas(str(target), pagesize=page)
        c.setTitle("Cardwright print sheet")

        for batch in group:
            # ---- front page
            if ebleed > 0 and not extend_art:
                c.setFillColorRGB(*bleed_rgb)
                for k in range(len(batch)):
                    x, y = usable[k]
                    c.rect(x - ebleed, y - ebleed,
                           card_w + 2 * ebleed, card_h + 2 * ebleed,
                           stroke=0, fill=1)
            for k, i in enumerate(batch):
                placed += 1
                if status_callback:
                    status_callback(f"Placing card {placed}/{to_place}…")
                x, y = usable[k]
                if extend_art:
                    c.drawImage(ImageReader(str(flat(images[i]))),
                                x - ebleed, y - ebleed,
                                card_w + 2 * ebleed, card_h + 2 * ebleed,
                                mask=img_mask)
                else:
                    c.drawImage(ImageReader(str(flat(images[i]))), x, y,
                                card_w, card_h, mask=img_mask)
            _draw_marks(c, ox, oy, block_w, block_h, gutter, guide_rgb,
                        cols, rows, guide_len_mm, guide_thick, guide_style,
                        guide_offset_mm, card_w, card_h, reg_clear)
            if reg_marks:
                _draw_reg_marks(c, pw, ph, reg_inset_mm, reg_length_mm,
                                reg_thick_mm, reg_four)
            c.showPage()

            # ---- mirrored back page (duplex, flip on long edge)
            if backs is not None:
                bleed = back_bleed_mm * mm
                c.saveState()
                if back_rotation_deg:
                    # rotate the whole back layout about the page centre to
                    # cancel angular duplex drift. Registration marks are the
                    # one thing left square to the page - the cutter's sensor
                    # hunts for them at a fixed inset.
                    c.translate(pw / 2, ph / 2)
                    c.rotate(back_rotation_deg)
                    c.translate(-pw / 2, -ph / 2)
                # The offset moves the cards AND their cut guides together. A
                # guide left on the front's grid is a guide the scissors follow
                # to the wrong place: the whole point of the offset is that the
                # back's ink lands somewhere else on the paper, so a guide that
                # does not carry it is off by exactly the drift being corrected.
                c.translate(dx, dy)
                for k, i in enumerate(batch):
                    x, y = usable[k]
                    x = mirror_x(x, ox, block_w, card_w)
                    # oversized by the bleed on every edge: small duplex
                    # drift stays covered when cutting along the front
                    c.drawImage(ImageReader(str(flat(backs[i]))),
                                x - bleed, y - bleed,
                                card_w + 2 * bleed, card_h + 2 * bleed,
                                mask=img_mask)
                if back_guides:
                    _draw_marks(c, ox, oy, block_w, block_h, gutter, guide_rgb,
                                cols, rows, guide_len_mm, guide_thick,
                                guide_style, guide_offset_mm, card_w, card_h,
                                back_clear)
                c.restoreState()
                if reg_marks:
                    _draw_reg_marks(c, pw, ph, reg_inset_mm, reg_length_mm,
                                    reg_thick_mm, reg_four)
                c.showPage()

        c.save()
        written.append(target)

    for t in flat_cache.values():
        try:
            t.unlink()
        except OSError:
            pass

    return written


def build_calibration(image_path, out_path, page_name="A4",
                      shift_down_mm=0.0, status_callback=None) -> Path:
    """
    One page with the same card rendered through all 9 calibration
    profiles, numbered, to print and compare against a real card.
    """
    image_path = Path(image_path)
    page = PAGES.get(page_name, A4)
    pw, ph = page
    block_w, block_h = COLS * CARD_W, ROWS * CARD_H
    ox, oy = _block_origin(pw, ph, block_w, block_h, shift_down_mm)

    c = canvas.Canvas(str(out_path), pagesize=page)
    c.setTitle("Cardwright calibration sheet")

    temp_files = []
    for idx, (pid, profile) in enumerate(sorted(CALIBRATION_PROFILES.items())):
        if status_callback:
            status_callback(f"Rendering variant {pid}/9…")
        x, y = _card_pos(idx, ox, oy, block_h)
        flat = _flatten(image_path, 97, profile, None, suffix=f"_cal{pid}")
        temp_files.append(flat)
        c.drawImage(ImageReader(str(flat)), x, y, CARD_W, CARD_H)

        # number badge on the card's top-left corner
        c.setFillColorRGB(1, 1, 1)
        c.rect(x + 2 * mm, y + CARD_H - 8 * mm, 8 * mm, 6 * mm, stroke=0, fill=1)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 11)
        c.drawCentredString(x + 6 * mm, y + CARD_H - 6.4 * mm, str(pid))

    _draw_marks(c, ox, oy, block_w, block_h)

    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.setFont("Helvetica", 8)
    c.drawCentredString(pw / 2, oy - MARK_LEN - 4 * mm,
                        "Cardwright calibration - print at 100% scale, no printer color correction. "
                        "Pick the number closest to a real card.")
    c.showPage()
    c.save()

    for t in temp_files:
        try:
            t.unlink()
        except OSError:
            pass

    return Path(out_path)


def build_duplex_test(out_path, page_name="A4", layout=DEFAULT_LAYOUT,
                      back_offset=(0.0, 0.0), back_rotation_deg=0.0,
                      edge_bleed_mm=0.0, shift_down_mm=0.0,
                      status_callback=None) -> Path:
    """
    Two-page duplex registration test. Page 1 draws the card grid (outlines +
    diagonals) for the FRONTS; page 2 draws the same grid for the BACKS with
    the current back offset and rotation applied (and column-mirrored, exactly
    like build_pdf). Print double-sided, hold to the light: wherever the front
    and back grids don't overlap tells you how much offset / rotation to add.
    """
    cols, rows, landscape = LAYOUTS.get(layout, LAYOUTS[DEFAULT_LAYOUT])
    page = PAGES.get(page_name, A4)
    if landscape:
        page = (page[1], page[0])
    pw, ph = page
    gutter = 2 * edge_bleed_mm * mm
    block_w = cols * CARD_W + (cols - 1) * gutter
    block_h = rows * CARD_H + (rows - 1) * gutter
    ox, oy = _block_origin(pw, ph, block_w, block_h, shift_down_mm)
    dx, dy = back_offset[0] * mm, back_offset[1] * mm

    c = canvas.Canvas(str(out_path), pagesize=page)
    c.setTitle("Cardwright duplex alignment test")

    def cell(slot):
        col, row = slot % cols, slot // cols
        x = ox + col * (CARD_W + gutter)
        y = oy + block_h - (row + 1) * CARD_H - row * gutter
        return x, y

    def grid(mirror):
        c.setLineWidth(0.5)
        c.setStrokeColorRGB(0, 0, 0)
        for slot in range(cols * rows):
            s = slot
            if mirror:
                col, row = slot % cols, slot // cols
                s = row * cols + (cols - 1 - col)
            x, y = cell(s)
            c.rect(x, y, CARD_W, CARD_H, stroke=1, fill=0)
            c.line(x, y, x + CARD_W, y + CARD_H)
            c.line(x, y + CARD_H, x + CARD_W, y)

    # page 1: fronts
    if status_callback:
        status_callback("Front registration page…")
    grid(mirror=False)
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.drawCentredString(pw / 2, oy - MARK_LEN - 4 * mm,
                        "Duplex test FRONT - print double-sided at 100% scale, "
                        "no printer color correction, then hold to the light.")
    c.showPage()

    # page 2: backs (column-mirrored + offset + rotation, like build_pdf)
    if status_callback:
        status_callback("Back registration page…")
    c.saveState()
    if back_rotation_deg:
        c.translate(pw / 2, ph / 2)
        c.rotate(back_rotation_deg)
        c.translate(-pw / 2, -ph / 2)
    c.translate(dx, dy)
    grid(mirror=True)
    c.restoreState()
    c.setFont("Helvetica", 8)
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.drawCentredString(
        pw / 2, oy - MARK_LEN - 4 * mm,
        f"Duplex test BACK - offset {back_offset[0]:+.1f}, {back_offset[1]:+.1f} mm, "
        f"rotation {back_rotation_deg:+.2f}°. Adjust until it overlaps the front.")
    c.showPage()
    c.save()
    return Path(out_path)


def build_shadow_test(image_path, out_path, page_name="A4", profile_id=1,
                      shift_down_mm=0.0, status_callback=None) -> Path:
    """
    One page with the same card at 9 shadow-lift levels (the chosen color
    profile already applied), labeled with the +N value. Pick the lowest
    number where dark details (artist signatures, shadow texture) become
    visible without the blacks looking washed.
    """
    image_path = Path(image_path)
    profile = CALIBRATION_PROFILES.get(profile_id)
    page = PAGES.get(page_name, A4)
    pw, ph = page
    block_w, block_h = COLS * CARD_W, ROWS * CARD_H
    ox, oy = _block_origin(pw, ph, block_w, block_h, shift_down_mm)

    c = canvas.Canvas(str(out_path), pagesize=page)
    c.setTitle("Cardwright shadow test")

    temp_files = []
    for idx, level in enumerate(SHADOW_TEST_LEVELS[:PER_PAGE]):
        if status_callback:
            status_callback(f"Rendering +{level}…")
        x, y = _card_pos(idx, ox, oy, block_h)
        flat = _flatten(image_path, 97, profile, None, level,
                        suffix=f"_sh{level}")
        temp_files.append(flat)
        c.drawImage(ImageReader(str(flat)), x, y, CARD_W, CARD_H)

        c.setFillColorRGB(1, 1, 1)
        c.rect(x + 2 * mm, y + CARD_H - 8 * mm, 11 * mm, 6 * mm, stroke=0, fill=1)
        c.setFillColorRGB(0, 0, 0)
        c.setFont("Helvetica-Bold", 10)
        c.drawCentredString(x + 7.5 * mm, y + CARD_H - 6.4 * mm, f"+{level}")

    _draw_marks(c, ox, oy, block_w, block_h)
    c.setFillColorRGB(0.3, 0.3, 0.3)
    c.setFont("Helvetica", 8)
    c.drawCentredString(pw / 2, oy - MARK_LEN - 4 * mm,
                        "Shadow lift test - pick the lowest +N where dark details "
                        "(signature) are visible after laminating.")
    c.showPage()
    c.save()

    for t in temp_files:
        try:
            t.unlink()
        except OSError:
            pass

    return Path(out_path)
