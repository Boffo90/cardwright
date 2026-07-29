"""
Upscale pipeline.

    input image (any format)
        -> normalize to PNG if needed (+ optional MPC bleed trim)
        -> Real-ESRGAN x4 (ncnn / vulkan)   [skipped if already >= card size]
        -> resize to exact MTG card size (optional)
        -> embed 1200 DPI metadata
        -> output PNG
"""

import re
import subprocess
from pathlib import Path

from PIL import Image

from config import (
    REALESRGAN_EXE,
    OUTPUT_FOLDER,
    TEMP_FOLDER,
    MODELS,
    DEFAULT_MODEL,
    AUTO_MODEL,
    RENDER_ERA_START,
    AUTO_DIGITAL_MAX_BYTES,
    REALISTIC_SETS,
    AUTO_DIGITAL_MODEL,
    AUTO_REALISTIC_MODEL,
    AUTO_SCAN_MODEL,
    SUPPORTED_INPUT,
    TARGET_DPI,
    CARD_WIDTH_PX,
    CARD_HEIGHT_PX,
    card_size_px,
    FIT_TO_CARD_DEFAULT,
    MPC_BLEED_RATIO_MIN,
    MPC_BLEED_RATIO_MAX,
    MPC_CARD_W_FRAC,
    MPC_CARD_H_FRAC,
)

# Prevents the Windows console window from flashing.
CREATE_NO_WINDOW = 0x08000000

_percent_re = re.compile(r"(\d+[.,]\d+)%")


def generate_output_name(file: Path) -> str:
    """
    ltr-123-Lightning Bolt   ->   Lightning Bolt-ltr-123.png

    (Scryfall downloads already come as Name-set-number, which has 3 parts
    too but in the desired order, so they pass through unchanged-ish.)
    """
    parts = file.stem.split("-", 2)
    if len(parts) != 3:
        return file.stem + ".png"
    setcode, number, fullname = parts
    return f"{fullname}-{setcode}-{number}.png"


def _has_mpc_bleed(im) -> bool:
    """True if the image's proportions match an MPC full-bleed card."""
    w, h = im.size
    if h == 0:
        return False
    ratio = w / h
    return MPC_BLEED_RATIO_MIN <= ratio <= MPC_BLEED_RATIO_MAX


def _crop_mpc_bleed(im):
    """Return the centred card area of an MPC full-bleed image."""
    w, h = im.size
    cw, ch = w * MPC_CARD_W_FRAC, h * MPC_CARD_H_FRAC
    x0 = round((w - cw) / 2)
    y0 = round((h - ch) / 2)
    return im.crop((x0, y0, round(x0 + cw), round(y0 + ch)))


def _normalize_input(file: Path, trim_bleed=False,
                     status_callback=None) -> Path:
    """
    Real-ESRGAN reads png/jpg/webp. Anything else (or images with odd modes)
    is converted to a temporary PNG first. If trim_bleed is set and the image
    looks like an MPC full-bleed card, its bleed is cropped off first.
    """
    plain = file.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}

    # True/False stay valid so nothing else has to change; "always" skips the
    # ratio test for an image that carries bleed it cannot recognise.
    mode = {True: "auto", False: "never"}.get(trim_bleed, trim_bleed)

    if mode in ("auto", "always"):
        im = Image.open(file)
        if mode == "always" or _has_mpc_bleed(im):
            if status_callback:
                status_callback("Trimming MPC bleed...")
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA")
            out = _crop_mpc_bleed(im)
            temp = TEMP_FOLDER / (file.stem + "_trim.png")
            out.save(temp)
            return temp

    if plain:
        return file

    if status_callback:
        status_callback(f"Converting {file.suffix} to PNG...")

    im = Image.open(file)
    if im.mode not in ("RGB", "RGBA"):
        im = im.convert("RGBA")
    temp = TEMP_FOLDER / (file.stem + "_in.png")
    im.save(temp)
    return temp


def _postprocess(path: Path, fit_to_card: bool, target=None):
    """Resize to exact card size (optional) and stamp DPI metadata in place."""
    im = Image.open(path)
    target = target or (CARD_WIDTH_PX, CARD_HEIGHT_PX)

    if fit_to_card and im.size != target:
        im = im.resize(target, Image.LANCZOS)

    im.save(path, "PNG", dpi=(TARGET_DPI, TARGET_DPI))


def upscale(
    file_path,
    model_label: str = DEFAULT_MODEL,
    fit_to_card: bool = FIT_TO_CARD_DEFAULT,
    rename: bool = True,
    released_at: str | None = None,
    set_code: str | None = None,
    ai: bool = True,
    trim_bleed: bool = False,
    card_size: str | None = None,
    progress_callback=None,
    status_callback=None,
):
    """
    Upscale a single image and return the output Path.

    rename      -> apply the legacy "set-number-name" -> "name-set-number"
                   renaming (True for user files). Scryfall downloads are
                   already correctly named, so pass rename=False for those.
    released_at -> "YYYY-MM-DD" from Scryfall, used by Auto mode to pick
                   the model by image era (scan vs official render).
    set_code    -> Scryfall set code; sets in REALISTIC_SETS divert Auto
                   to the face-friendly model.
    progress_callback(value)  -> value in 0..1
    status_callback(text)     -> short text for the GUI
    """
    file = Path(file_path)

    if not file.exists():
        raise FileNotFoundError(file)

    # target pixels for the chosen TCG card size (MTG/Pokemon by default)
    card_w_px, card_h_px = card_size_px(card_size)

    if not ai or not REALESRGAN_EXE.exists():
        # No compatible GPU (or engine missing): plain high-quality resize.
        # Still yields a correctly sized 1200 DPI file, just without the AI
        # detail reconstruction.
        source = _normalize_input(file, trim_bleed, status_callback)
        out_name = generate_output_name(file) if rename else file.stem + ".png"
        output = OUTPUT_FOLDER / out_name
        if status_callback:
            status_callback("Resizing (no GPU — AI disabled)…")
        im = Image.open(source)
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        im = im.resize((card_w_px, card_h_px), Image.LANCZOS)
        im.save(output, "PNG", dpi=(TARGET_DPI, TARGET_DPI))
        if progress_callback:
            progress_callback(1.0)
        if status_callback:
            status_callback("Done (resize only)")
        return output

    if model_label == AUTO_MODEL:
        if set_code and set_code.lower() in REALISTIC_SETS:
            # photorealistic art (Marvel etc.): UltraSharp breaks faces/hands
            kind, why = "realistic", f"set {set_code.upper()}"
            model_label = AUTO_REALISTIC_MODEL
        elif released_at:
            # date is authoritative: Scryfall switched from scans to official
            # WotC renders with LTR (June 2023)
            digital = released_at >= RENDER_ERA_START
            kind = "render" if digital else "scan"
            why = f"released {released_at}"
            model_label = AUTO_DIGITAL_MODEL if digital else AUTO_SCAN_MODEL
        else:
            # no date (local file): renders compress small, scans weigh more
            size = file.stat().st_size
            digital = size < AUTO_DIGITAL_MAX_BYTES
            kind = "render" if digital else "scan"
            why = f"{size/1e6:.2f} MB"
            model_label = AUTO_DIGITAL_MODEL if digital else AUTO_SCAN_MODEL
        if status_callback:
            status_callback(f"Auto: {kind} ({why}) -> {MODELS[model_label][0]}")

    model_name, scale = MODELS.get(model_label, MODELS[AUTO_SCAN_MODEL])

    source = _normalize_input(file, trim_bleed, status_callback)

    out_name = generate_output_name(file) if rename else file.stem + ".png"
    output = OUTPUT_FOLDER / out_name

    # Skip the AI when the (trimmed) source already has at least card
    # resolution. MPC art, pre-rendered high-res and previously-processed
    # cards gain nothing from x4 — it would only balloon them to ~16x the
    # pixels (slow preview, heavy PDFs). Just fit to card (if asked) + DPI.
    with Image.open(source) as probe:
        w, h = probe.size
    if w >= card_w_px and h >= card_h_px:
        if status_callback:
            status_callback("Already high-res — skipping AI upscale")
        im = Image.open(source)
        if im.mode not in ("RGB", "RGBA"):
            im = im.convert("RGBA")
        if fit_to_card and im.size != (card_w_px, card_h_px):
            im = im.resize((card_w_px, card_h_px), Image.LANCZOS)
        im.save(output, "PNG", dpi=(TARGET_DPI, TARGET_DPI))
        if progress_callback:
            progress_callback(1.0)
        if status_callback:
            status_callback("Done (no AI needed)")
        return output

    # A source too small for one AI pass to reach the card gets resized up to
    # exactly target/scale FIRST, so the pass lands on the card instead of
    # leaving a plain stretch to do afterwards. The interpolation happens
    # before the reconstruction rather than after it, and that is the whole
    # difference: measured on a 600x825 Pokemon scan, sharpness went from 54
    # to 84 (Laplacian variance) for +0.5 s and no extra memory.
    #
    # For MTG this never fires — Scryfall's 745 px x4 already clears 2976.
    # Gatherer (646) and the Pokemon catalogues (600) are what it is for.
    #
    # Running the AI twice and downsampling scores far higher (331) but costs
    # 15.3 s per card and a 125 MB intermediate; at PARALLEL_JOBS that is the
    # kind of load this app exists to avoid. Deliberately not done.
    need_w = -(-card_w_px // scale)      # ceil, so the pass never lands short
    need_h = -(-card_h_px // scale)
    if w < need_w or h < need_h:
        if status_callback:
            status_callback("Small source — normalizing before AI…")
        pre = TEMP_FOLDER / (source.stem + "_pre.png")
        with Image.open(source) as im:
            if im.mode not in ("RGB", "RGBA"):
                im = im.convert("RGBA")
            im.resize((max(w, need_w), max(h, need_h)), Image.LANCZOS).save(pre)
        source = pre

    cmd = [
        str(REALESRGAN_EXE),
        "-i", str(source),
        "-o", str(output),
        "-n", model_name,
        "-s", str(scale),
    ]

    if status_callback:
        status_callback("Upscaling...")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        creationflags=CREATE_NO_WINDOW,
    )

    while True:
        line = process.stdout.readline()
        if not line and process.poll() is not None:
            break
        line = line.strip()
        if not line:
            continue

        match = _percent_re.search(line)
        if match:
            percent = float(match.group(1).replace(",", ".")) / 100
            # reserve the last 10% for post-processing
            if progress_callback:
                progress_callback(percent * 0.9)
            if status_callback:
                status_callback(f"Upscaling... {percent*100:.0f}%")

    process.wait()

    if process.returncode != 0:
        raise RuntimeError(f"Real-ESRGAN exited with code {process.returncode}")

    if status_callback:
        status_callback("Finalizing (DPI / size)...")

    _postprocess(output, fit_to_card, (card_w_px, card_h_px))

    if progress_callback:
        progress_callback(1.0)
    if status_callback:
        status_callback("Done")

    return output
