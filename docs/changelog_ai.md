# ProxyForge — Changelog

Registro por versión. Actualizar en cada release.

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
