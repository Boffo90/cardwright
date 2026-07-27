# Cardwright — Technical Decisions

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

## Microtext vs border deepening (v2.12.1)
- `BORDER_TONE_MAX` went 100 → **58**. The bottom band carries the copyright/collector line as WHITE microtext on black, and its anti-aliased edges ramp through ~60-160. The binary snap at 100 crushed those to pure black, so in print the strokes thickened and the counters of 'o', 'a', 'e' closed up. Measured across 5 cards: only **45-62% of the anti-aliasing survived at 100, vs 100% at 58**, while the frame still snaps to solid black (99.3-100% of the top edge). A washed scan border sits near 37 after the shadow lift, so 58 keeps the original purpose intact.
- Diagnosis note for the future: if a user reports "black looks thicker" on tiny text, compare the exported PDF with the border option Off vs On **on screen at 800%** before touching the printer driver — it isolates software from dot gain without wasting paper.

## Visual design system (v2.12.0)
- All colour, spacing, radius and type live in **`theme.py`**. `gui.py` keeps its historical names (GOLD, PANEL, ROW…) as aliases onto those tokens, so the whole app restyled without touching every widget call.
- Direction: **neutral pro tool** (Linear/Figma feel) — a low-chroma graphite ramp for every surface, with **one** warm accent (`#E0A33E`). The accent is reserved for the primary action, the active tab/filter and progress; headings and section labels use the text ramp. Previously gold was used for headings *and* buttons, which flattened the hierarchy.
- Every foreground/background pair is contrast-checked: text 15.7:1, secondary 8.2:1, muted 5.3:1, accent 7.9:1, on-accent 8.4:1. `BORDER` is decorative; `BORDER_STRONG` is for input outlines and clears the 3:1 non-text threshold.
- Fonts: Segoe UI Variable Text when present (Win 11), falling back to Segoe UI. Resolved in `App.__init__` because `tkfont.families()` needs a live Tk root. Georgia and the WUBRG mana dots are gone — they read as themed rather than professional.
- **Export dialog is tabbed** (Layout / Image / Backs / Cutting / Tests) instead of ~30 controls in one scrolling column; each tab now fits without scrolling. Implementation trick: the row helpers close over a `left` variable that `tab()` rebinds, so switching tabs needed no changes to the ~30 existing control definitions. Presets sit above the tabs since they apply across all of them.

## Multi-TCG sources (v2.11.0)
- One catalogue backend interface: a module exposing `search(query)` → list of dicts with `name / source / dpi / thumb / download / ext / identifier`, plus `download(card, target)` and `fetch_thumb(url)`. `mpcfill.py` and `ygoprodeck.py` both implement it, and `CardSearchDialog(backend=...)` renders either. Add a game by writing one module.
- YGOPRODeck rules shape the client: ≤20 req/s (we throttle to ~8) and *"do not continually hotlink images — download and re-host"*. Full images already land in the user's output folder; search thumbnails are cached under `TEMP_FOLDER/ygo_thumbs` so a repeated search never re-hits their CDN.
- **Card size must be set before upscaling, not just before printing.** `fit_to_card` force-resizes, so a Yu-Gi-Oh card (59×86, aspect 0.686) squeezed into MTG's 2976×4160 (0.716) comes out stretched. Hence the selector now sits in the main window too, sharing `settings["card_size"]` with Export, and queueing a Yu-Gi-Oh card flips it automatically the first time.

## Non-grid layouts (v2.10.0)
- Card slots come from `print_sheet.layout_positions(layout, ...)` which returns explicit (x, y) origins in placement order, not from `index % cols` maths. It is unit-agnostic, so the preview calls it in mm and `build_pdf` in points — one source of truth for both.
- Duplex mirroring uses `mirror_x(x, ox, block_w, card_w)` (reflect across the block centre) instead of column-index flipping. Equivalent for grids, and the only thing that works for non-grid layouts.
- **7-card Silhouette** = 4×2 grid, left column holding one vertically centred card + a 3×2 block. Purpose is clearance around the marks a Cameo relies on: lower-left mark clearance goes ~5 mm → ~49 mm vs 4×2. Copied the *arrangement* (a geometric fact) from ProxySheet's SevenCard template; that repo is **GPL-3.0**, so no code was taken — ours is written from our own math.

## Registration marks & card sizes (v2.9.0)
- Registration-mark geometry is a **hardware spec** (what the Silhouette/Cricut optical sensor looks for), taken from the MIT-licensed `Alan-Cha/silhouette-card-maker` and reimplemented in reportlab: 5×5 mm filled square top-left (3-mark) or an L there too (4-mark, CAMEO 5a); L brackets at the other corners; arms 5–20 mm, thickness 0.5–1 mm, inset ≥10 mm (Studio default 15.875 mm = 0.625 in), 1.5 mm keep-clear padding.
- **Defaults are the spec minimums** (inset 10 mm, arms 5 mm) rather than Silhouette Studio's own 15.875/20: the Studio footprint eats 3 card slots on a 3×3 sheet, while 10/5 keeps every card and is still inside the readable range. Users can raise both if a machine fails to detect. Measured: A4 3×3 9/9, A4 4×2 8/8, Letter 4×2 8/8 — **Letter 3×3 is impossible** (only 7.7 mm of top/bottom margin vs the 10 mm minimum inset), so it warns and skips 3 slots.
- **Registration marks disable shift-down.** `shift_down_mm` compensates a printer that feeds heavy stock late, but a cutter locates the *physical* marks and cuts relative to them, so it already self-compensates. Shifting only the cards would break the card↔mark relationship and (with the user's 15 mm shift) push the bottom row under the marks. So `build_pdf` and the preview both pass 0 for shift when `reg_marks` is on, and the hint says so.
- **When marks do collide** (e.g. Letter 3×3), `_reg_blocked_slots` finds which slots a mark's clear box overlaps and leaves them EMPTY; cards flow into the rest. `build_pdf` and the preview share the same `usable[k]` mapping, so what you see is what prints. A live hint in the dialog reports usable vs total slots.
- Card size is one persisted setting (`settings["card_size"]`) used by BOTH fit-to-card upscaling and the PDF layout, so masters and print stay consistent. Pokémon needed no work (63×88, same as MTG). `card_size_px` special-cases the MTG default to keep the legacy 2976×4160 (88 mm at 1200 dpi would round to 4157).

## Export preview performance & presets (v2.7.0)
- The preview canvas renders **lazily**: `_render_visible` paints only sheets whose rows intersect the viewport (+one sheet of look-ahead), caches each as a PhotoImage, and hooks `yscrollcommand` so scrolling paints new sheets. Treated-border thumbnails (`_treated_thumb`) are built on demand per visible card, not for the whole deck on every slider move. This is what makes 100+ card decks usable.
- Gotcha (fixed): `render_sheet` is a closure whose layout locals (cw, ch, left, top, X…) are read at *paint* time, which happens after `_draw_preview` returns. Never reuse those names later in `_draw_preview` — a stray `cw = canvas.winfo_width()` clobbered the card-cell width and broke the corner mask. Keep the tail's own locals distinctly named.
- Export presets: `_collect_settings()` / `_apply_settings()` are the single read/write of every control; `_persist` and the named presets (`settings["export_presets"]`) both go through them. Sliders register a setter in `self._slider_setters` so a preset can update both value and label.

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
