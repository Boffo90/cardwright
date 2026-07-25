# ProxyForge — TODO

## Pending / possible issues
- MPC search depends on mpcfill.com API + Google Drive (fragile if they change).
- Foreign cards Scryfall doesn't know: no multiverse id → can't download from Gatherer.
- MPC images are already 1200dpi but still go through the AI (no skip optimization).
- Card exclusion: PDF recompacts (no gaps); preview shows original position with an X.
- Code signing pending (Azure Trusted Signing ~US$10/mo) → SmartScreen warns "unknown publisher".

## Next steps
- Publish release v2.7.0 (upload ProxyForge.exe FIRST, then installer/ProxyForge_Setup-2.7.0.exe; tag v2.7.0).
- r/mtgproxies promotion when the user wants.

## Backlog (interactive preview, later phases)
- Drag whole sheets to reorder them (only cards reorder today).
- Add cards from the preview — needs the upscaling pipeline inside ExportDialog (cross-module; deferred).
- Big decks: the preview loads every card's working image + renders all sheets each redraw; consider lazy/visible-only rendering if it lags.
