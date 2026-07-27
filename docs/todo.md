# Cardwright — TODO

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
- **7-card layout for Silhouette users** (requested; waiting on info). Complaint is that registration marks sit too close to the cards on 4×2 — measured clearance is 2.0 mm on A4 4×2, 5.0 mm on Letter 4×2, 1.5 mm on A4 3×3. 7 is prime, so it can't be a plain grid: it needs **mixed orientation** (likely 6 upright + 1 rotated), which means per-card rotation in build_pdf, the preview, duplex mirroring and cut guides. Cheap alternative that helps today: smaller grids (3×2 = 6) leave ~38 mm of clearance on Letter. User is collecting links/screenshots of the sites that use this layout so the geometry can be copied instead of guessed.
- **Linux .deb** — requested. Real cost: Real-ESRGAN ncnn has Linux builds, but `update.py` (Windows `.bat` swap), `bootstrap.py` (downloads the Windows zip) and packaging all need a Linux path. A real port, not a tweak. Undecided.
- **Card fetching for other TCGs** — only the size is configurable now; Scryfall search is still MTG-only. Yu-Gi-Oh/Pokémon users must add files or use MPC search.
- **mpcfill OCR fork (GPL)** — a user is building an OCR'd catalog + vote federation. Consuming their **HTTP API is fine** (GPL covers distributing code, not using a service); we must NOT vendor their GPL code into Cardwright. Wait for their API/spec.

## Reference projects — not adopted
- Manual bleed override ("Assume no/full bleed") when MPC auto-detect misfires — worth doing if reported.
- Margin modes, mixed card orientation, base-PDF registration — low value for our fixed grid.
