# ProxyForge — TODO

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

## Reference project (Malacath-92/Proxy-PDF-Maker) — not adopted
- Manual bleed override ("Assume no/full bleed") when MPC auto-detect misfires — worth doing if reported.
- Custom card size / other TCGs (Lorcana, FaB) — big scope, changes MTG identity.
- Margin modes, mixed card orientation, base-PDF registration — low value for our fixed grid.
