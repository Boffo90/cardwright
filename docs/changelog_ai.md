# Cardwright — Changelog

Registro por versión. Actualizar en cada release.

## v2.12.1 — keep copyright microtext crisp
- Border deepening no longer eats the anti-aliasing of the white microtext in
  the bottom band (copyright / collector line). `BORDER_TONE_MAX` 100 → 58:
  measured across 5 cards, anti-aliasing preserved went from 45-62% to 100%
  while the frame still snaps to solid black. Fixes strokes looking thicker
  and 'o'/'a'/'e' closing up in print.

## v2.12.0 — visual revamp (stage 1: design system, main window, Export tabs)
- New **`theme.py`**: one set of colour / spacing / radius / type tokens.
- Repalette to a **neutral graphite** scheme with a single warm accent, in the
  spirit of a professional tool. Accent now means "primary action or active
  state" only; headings use the text ramp. Contrast verified against WCAG.
- Typography unified on Segoe UI Variable (fallback Segoe UI); Georgia and the
  mana-dot decoration removed.
- Main window: header simplified, options and actions split into two rows so
  the buttons stop clipping, ghost/secondary/primary button hierarchy,
  accent-coloured switches instead of CustomTkinter's default blue.
- **Export dialog is now tabbed** — Layout / Image / Backs / Cutting / Tests —
  instead of ~30 controls in one scrolling column. Presets moved above the tabs.
- Queue rows: flat cards with a hairline border, smaller status dot, calmer
  status palette (muted idle, accent while working, green done, red error),
  slimmer progress bars.
- Dialogs: inputs share one height/radius/fill, outlines meet the 3:1 non-text
  contrast threshold, search-gallery tiles and buttons follow the same
  hierarchy, decklist box uses Cascadia Mono.

## v2.11.0 — Yu-Gi-Oh card search (YGOPRODeck)
- New **"Yu-Gi-Oh…"** search: gallery over the YGOPRODeck API, one entry per
  artwork, click to queue. `ygoprodeck.py` is new and mirrors `mpcfill.py`'s
  interface (search / download / fetch_thumb).
- Respects their terms: requests throttled well under 20/s, and thumbnails are
  cached on disk because they ask you not to keep hotlinking their images.
- **Card size moved into the main window** next to the model picker (still one
  shared setting with Export). It has to be right at upscale time — a Yu-Gi-Oh
  card is 59×86 mm (aspect 0.686) and fitting it to Magic's 63×88 (0.716)
  stretches it. Adding a Yu-Gi-Oh card switches the size over automatically
  the first time.
- `MPCDialog` generalised into `CardSearchDialog`, which takes the catalogue
  backend as a parameter, so MPC and YGOPRODeck share one gallery.
- Google Drive card dumps offered for Pokémon/Digimon/One Piece/Dragon Ball
  were **declined** — see project_state.md for why (no index, quota-bound
  single account, distribution-index risk).

## v2.10.0 — 7-card Silhouette layout
- New **"7-card Silhouette"** layout, requested by a Cameo user: a 4×2 grid
  whose left column holds a single vertically-centred card, with the other 6
  in a 3×2 block. That frees both left corners, where the marks a Cameo
  depends on most sit — clearance from the lower-left mark goes from ~5 mm
  (4×2) to ~49 mm. Backs mirror automatically (the lone card moves right).
- Slot placement is now driven by `layout_positions()` instead of grid index
  maths, and duplex mirroring by `mirror_x()`, so non-grid layouts work
  everywhere (PDF, preview, bleed frames, mark-collision detection).
- Same idea as ProxySheet's "SevenCard" template; geometry reimplemented from
  scratch (that project is GPL-3.0, so none of its code was used).

## v2.9.0 — cutting-machine registration marks + other TCG card sizes
From Reddit feedback after the public launch.
- **Registration marks** (Silhouette / Cricut print-and-cut): 3-mark standard
  or 4-mark CAMEO 5a pattern, with inset / length / thickness settings.
  Geometry follows the spec the sensor expects (5×5 mm filled square + L
  brackets, arms 5–20 mm, 0.5–1 mm thick, inset ≥10 mm, 1.5 mm clear zone).
  Defaults are the spec minimums (10 mm inset, 5 mm arms) so **no card slots
  are lost**: A4 3×3 keeps all 9, A4/Letter 4×2 keep all 8. Letter 3×3 can't
  fit marks (7.7 mm margin vs 10 mm minimum inset) — it warns and skips those
  slots, moving the cards to the next sheet (nothing is ever discarded).
  A live hint reports usable vs total slots.
  Shift-down is ignored while marks are on: the cutter locates the printed
  marks and self-compensates, so shifting only the cards would misalign them.
- **Card size selector** for other TCGs: MTG/Pokémon 63×88 (Pokémon already
  matched MTG, so it needed nothing), Yu-Gi-Oh 59×86, mini 44×68, tarot
  70×120. Drives both fit-to-card upscaling and the PDF layout/preview.
  The MTG size keeps its exact legacy 2976×4160 px (clean x4 of Scryfall).

## v2.8.0 — renamed ProxyForge → Cardwright
- App and brand renamed to **Cardwright** (ProxyForge was too generic and
  clashed with other *Forge proxy tools). No functional changes.
- GitHub repo renamed to `Boffo90/cardwright` (old URL redirects; auto-update
  for 2.7.0 clients still works via the redirect + the non-installer-exe
  fallback in update.py).
- New installer AppId + `Cardwright.exe` / `Cardwright_Setup-2.8.0.exe`.

## v2.7.0 — interactive preview: scroll all sheets, drag to reorder
- Export preview is now a scrollable canvas showing every sheet stacked.
- Drag a card to reorder it (before the card you drop on); order = PDF order.
- Left-click still cycles the black border; right-click still drops a card.
- Fix: lifted Pillow's `MAX_IMAGE_PIXELS` cap (config.py) — huge MPC images
  (~190M px) no longer fail with "decompression bomb"; they now reach export.
- Skip AI upscale when the (trimmed) source is already >= card size — MPC /
  pre-rendered / reprocessed cards no longer balloon to ~16x pixels; just
  fit-to-card + DPI. Faster, and safe even if "Fit to card" is off.
- Backside rotation (Duplex backs): corrects angular duplex drift by rotating
  the back page about its centre, instead of only hiding drift with back bleed.
- Duplex alignment test ("Duplex align..."): 2-page front/back registration
  grid PDF to dial in back offset + rotation by holding it to the light.
- Cut-guide detail: Guide style (Cross / Corner crop-marks), length (mm) and
  thickness (pt). Reflected in the preview.
- Rounded corners (Corner radius mm): rounds every printed card's corners
  (transparent, drawn over paper/bleed). Reflected in the preview.
- Faster preview for big decks: sheets render lazily (only those near the
  viewport, cached) and treated-border thumbs rebuild only for visible cards,
  so slider tweaks no longer re-process the whole deck.
- Export presets: save/load named configurations (Presets section — Save… /
  Delete) stored in settings.json under `export_presets`.
- Cut-guide offset (mm): gap between the guide and the card corner.
- "PDF from files…" button: pick specific already-upscaled cards (from the
  output folder or anywhere) straight into a PDF, no queue needed.
- Sheet selection: a "Sheets" box (e.g. 1 or 1-3,5) prints only those sheets;
  unselected sheets show "(not printed)" in the preview.
- Direct card management in the export: right-click a card → "Duplicate"
  (makes a 'name (2).png' copy right after it), "Remove from PDF" (file kept)
  or "Delete from output folder…" (removes the PNG from disk, with
  confirmation); plus an "Add cards…" button to append more (re-picking a card
  already in the set adds a duplicate). Replaces the old exclude-with-an-X
  toggle. The preview help line now wraps instead of clipping.
- Loading spinner: cards whose thumbnail is still loading show a small animated
  spinner instead of a flat grey slot, so it reads as loading, not an error.
- Fix: preview no longer caps thumbnails at the first 12 cards — cards on
  sheet 2+ (e.g. Gatherer imports past #12) now render.
- Ideas adapted from Malacath-92/Proxy-PDF-Maker.

## v2.6.0 — full preview, card selection, custom backs
- Preview de todas las hojas (◀▶), no solo la primera.
- Clic derecho descarta/restaura carta del PDF (X roja); conteos se recalculan.
- Elegir cardback (File… / MPC…) para no-DFC; DFC conservan su reverso.

## v2.5.0 — MPC Autofill search
- Botón "MPC search…": galería sobre mpcfill.com, elige versión, a la cola. Descarga de Google Drive + recorte de bleed. `mpcfill.py` nuevo.

## v2.4.0 — Gatherer images, MPC bleed trim, reject art edges
- Gatherer link → imagen de Gatherer (no Scryfall).
- Recorte de bleed MPC por proporción; toggle "Trim MPC bleed".
- Borde: rechaza lado cuyo marco no cubre ≥88% (extended-art Winota).

## v2.3.3 — solid-black frame, no more mottled edge
- Snap binario a negro (no proporcional) → elimina moteado (mat/41).

## v2.3.2 — magnifier on export preview
- Lupa ~6x al hover; cartas en memoria a 640×896.

## v2.3.1 — border amount & manual width
- Sliders Amount (0-100%) y Manual width para cartas forzadas ON.

## v2.3.0 — per-card border control
- Clic en preview cicla auto/off/on por carta (Winota falso positivo).

## v2.2.x — border detection (por lado, por línea, croma, texto colección)
- v2.2.4 por-línea + croma + texto; v2.2.3 por-lado; v2.2.2 resolución nativa; v2.2.1 por-borde; v2.2.0 deepen border inicial.

## v2.2.3.1 — source-available license (MIT → propia)

## v2.1.4 — duplex preview pairing fix
## v2.1.3 — relaunch post-update via ejecución directa (no START)
## v2.1.2 — swap script timeout/ping fix
## v2.1.1 — auto-update wait on imagename (2 procesos)
## v2.1.0 — 4×2 landscape layout + Inno Setup installer
## v2.0.0 — release público inicial: upscaling IA 1200dpi, Scryfall/Gatherer/decklist/Archidekt, print sheets, calibración, shadow lift, duplex, auto-update, bootstrap
