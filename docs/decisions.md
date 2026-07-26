# ProxyForge — Technical Decisions

Settled decisions. Do not re-litigate; add new ones here.

## Language
**Everything in the project is English** (global app): UI, code, comments, docs, README, changelog, and GitHub release titles/descriptions. Chat with the user is in Spanish, but anything that lives in the repo or is shown to the end user is English.

## Licensing
**Source-available** (not MIT): code visible, redistribution/selling/rebranding forbidden.

## Printing / calibration
- User's printer (Epson ET-2800, 300gsm cold-matte laminated): **color profile 9, shadow lift Medium (+14)**, sharpening Off, shift-down per paper.
- Shadow lift: surgical curve only below level 75 (never touches midtones).
- Deepen border: **binary** snap to black (not proportional) to avoid mottling; per-line detection with chroma guard (neutral frame chroma ≤14) and **per-side coverage ≥88%** (rejects art sides). Manual per-card override in preview (left-click cycles auto/off/on) + Amount/Manual-width sliders.
- MPC bleed: proportional crop (0.733 vs 0.716), "Trim MPC bleed" toggle ON by default.

## Data sources
- Gatherer link → ALWAYS the Gatherer image (Scryfall only provides multiverse id + metadata).
- Pillow `MAX_IMAGE_PIXELS` is disabled in `config.py` (set to None). MPC/Google-Drive art can top ~190M px, above Pillow's ~178M "decompression bomb" guard, which otherwise errored the card before it reached export. Sources are user-chosen and trusted, so the guard is off process-wide.
- `upscale()` skips the Real-ESRGAN step when the normalized (bleed-trimmed) source is already ≥ 2976×4160, and just fits-to-card + stamps DPI. x4 on an already-card-sized image only bloats it ~16x (a card-sized input became 11912×16620), slowing the preview and PDFs. This runs even when "Fit to card" is off, so high-res sources never balloon.

## Duplex / cut guides / corners (v2.7.0, ideas from Proxy-PDF-Maker)
- Backside rotation rotates the back page about the PAGE centre (not per-card), matching how a printer's duplex angular drift pivots; cut marks are drawn after `restoreState` so they stay on the grid. Range clamped ±5°. Dial it with the duplex alignment test rather than guessing.
- `build_duplex_test` is the calibration tool for offset+rotation: page 1 = front grid, page 2 = back grid column-mirrored + offset + rotation (exactly like `build_pdf`), so holding the print to the light shows the real misregistration.
- Rounded corners use transparency + reportlab `mask='auto'` (forces PNG so alpha survives), so corners show paper/bleed. Not baked onto black. Radius is mm → px via card width (63 mm).

## Export preview
- The preview is an editable workspace, not a static image: a scrollable canvas stacks every sheet; the on-screen order IS the PDF order. `self._order` (list of front paths) is the source of truth; drag-and-drop reorders it, `self._back_of` keeps DFC backs paired. Built on a raw `tk.Canvas` (not a CTkLabel) so it can scroll, overlay the loupe, and show a drag ghost.

## Do NOT retry (known dead ends)
- **Moxfield API**: rejected by their support (WotC concerns). Don't re-request or scrape.
- **Integrating sales into the app / mentioning sales**: forbidden by the user.
- **Argentine voseo**: user is Chilean, use neutral Spanish/tuteo.
- **START/PowerShell/explorer to relaunch** the exe after update: fails on the user's PC; use direct exec (cmd child).
- **`timeout` in a .bat without console**: fails; use `ping` for pauses, absolute System32 paths.
- **Proportional weight in deepen border**: causes mottling; use binary snap.
- **Whole-card border detection**: rejects SPG (art on 3 sides + bottom band); use per-side / per-line.
- **mean/std weighting in detection**: outliers break it; use percentiles.
