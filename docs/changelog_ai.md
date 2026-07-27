# Cardwright — Changelog

Registro por versión. Actualizar en cada release.

## v2.9.0 — cutting-machine registration marks + other TCG card sizes
From Reddit feedback after the public launch.
- **Registration marks** (Silhouette / Cricut print-and-cut): 3-mark standard
  or 4-mark CAMEO 5a pattern, with inset / length / thickness settings.
  Geometry follows the spec the sensor expects (5×5 mm filled square + L
  brackets, arms 5–20 mm, 0.5–1 mm thick, inset ≥10 mm, 1.5 mm clear zone).
  Card slots a mark would sit on are **left empty** and cards flow into the
  remaining slots (A4 3×3 goes 9 → 6 cards/sheet, or 5 with 4 marks), which
  is required for the sensor to read them. Shown in the preview.
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
