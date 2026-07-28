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
- **Linux .deb** — requested. Real cost: Real-ESRGAN ncnn has Linux builds, but `update.py` (Windows `.bat` swap), `bootstrap.py` (downloads the Windows zip) and packaging all need a Linux path. A real port, not a tweak. Undecided.
- **Card fetching for other TCGs** — Yu-Gi-Oh via YGOPRODeck (v2.11.0), Pokémon via TCGdex (v2.15.0). **One Piece / Digimon / Dragon Ball**: `apitcg.com` covers all three but requires an API key on every call, which a binary handed to strangers cannot honour (shipped keys are extractable and shared). Blocked on that, not on the data existing — revisit only if they offer keyless access.
- **mpcfill OCR fork (GPL)** — a user is building an OCR'd catalog + vote federation. Consuming their **HTTP API is fine** (GPL covers distributing code, not using a service); we must NOT vendor their GPL code into Cardwright. Wait for their API/spec.

## Reference projects — not adopted
- Manual bleed override ("Assume no/full bleed") when MPC auto-detect misfires — worth doing if reported.
- Margin modes, mixed card orientation, base-PDF registration — low value for our fixed grid.
