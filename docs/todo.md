# Cardwright — TODO

## ▶ START HERE (handoff, 2026-07-27)
**v2.12.1 is committed and pushed but NOT built or released yet.** Everything
else is done and documented.

To ship it, follow `release.md`:
1. Close Cardwright if it's running (the exe can't be replaced while open).
2. Build with PyInstaller, copy the exe to the repo root, run ISCC, delete the
   old `installer/Cardwright_Setup-2.12.0.exe`.
3. `gh release create v2.12.0` → use **v2.12.1**, assets: `Cardwright.exe`
   FIRST, then `installer/Cardwright_Setup-2.12.1.exe`. gh is installed and
   authed as Boffo90.

What v2.12.1 fixes: border deepening was crushing the anti-aliasing of the
white copyright/collector microtext, so it printed with thicker strokes and
closed letter counters. `BORDER_TONE_MAX` 100 → 58; validated on 5 cards
(anti-aliasing kept 45-62% → 100%, frame still snaps to black). Details in
`decisions.md` → "Microtext vs border deepening".

Release notes angle for v2.12.1: it also carries the whole v2.12.0 visual
revamp and the v2.11.0 Yu-Gi-Oh search if those weren't announced separately
— v2.12.0 was published, so 2.12.1 can be a short patch note.

Not verified by me and worth a real human pass: drag & drop in the export
preview, the magnifier on hover, and actual GPU upscaling (I only exercised
the skip-AI path).

## Pending / possible issues
- MPC search depends on mpcfill.com API + Google Drive (fragile if they change).
- Foreign cards Scryfall doesn't know: no multiverse id → can't download from Gatherer.
- Removing/duplicating a card recompacts the sheets (no gaps) — inherent to not wasting paper.
- Code signing pending (Azure Trusted Signing ~US$10/mo) → SmartScreen warns "unknown publisher".

## Next steps
- r/mtgproxies promotion when the user wants.

## Backlog (interactive preview, later phases)
- Drag whole sheets to reorder them (only cards reorder today).
- Add cards from the preview — needs the upscaling pipeline inside ExportDialog (cross-module; deferred).
- Preview still loads every card's working image up front (raw thumbs); only the treated copies and sheet painting are lazy now. Fully lazy thumb loading could help 300+ card decks.

## From the Reddit launch (July 2026)
- **Linux .deb** — requested. Real cost: Real-ESRGAN ncnn has Linux builds, but `update.py` (Windows `.bat` swap), `bootstrap.py` (downloads the Windows zip) and packaging all need a Linux path. A real port, not a tweak. Undecided.
- **Card fetching for other TCGs** — Yu-Gi-Oh done via YGOPRODeck (v2.11.0). Pokémon/One Piece/Digimon/Dragon Ball have no open API found yet; revisit if one appears.
- **mpcfill OCR fork (GPL)** — a user is building an OCR'd catalog + vote federation. Consuming their **HTTP API is fine** (GPL covers distributing code, not using a service); we must NOT vendor their GPL code into Cardwright. Wait for their API/spec.

## Reference projects — not adopted
- Manual bleed override ("Assume no/full bleed") when MPC auto-detect misfires — worth doing if reported.
- Margin modes, mixed card orientation, base-PDF registration — low value for our fixed grid.
