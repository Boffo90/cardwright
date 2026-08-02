# Cardwright — Project State

## Direction (set July 2026)
Goal is the **best all-in-one proxy tool for TCGs in general** — MTG stays the primary game and the default experience, but other games are first-class where a real data source exists.

Rule for adding a game: **only integrate sources with a proper API** (Scryfall, Gatherer, MPC Autofill, YGOPRODeck). Curated Google Drive folders were offered and **declined**: no index or stable ids, one person's account as a single point of failure (public Drive folders hit download quotas), and shipping curated links to scanned catalogues shifts the project from "fetches on the user's request" toward being a distribution index. Users can still use those images via "Add files…" — the app handles any local image and the card size is configurable.

## Objective
Free (not open-source) Windows desktop app that turns MTG card images into print-ready proxies at **true 1200 DPI** via GPU AI upscaling, and builds print-ready PDFs. Distributed globally via GitHub. Repo: **Boffo90/cardwright**. Author: Boffo90. Donations: paypal.me/warchazzz. Separate from the local proxy-selling business (never mention sales).

## Current version
2.17.3 (see `changelog_ai.md`). App renamed **ProxyForge → Cardwright** in v2.8.0 (July 2026); GitHub repo is `Boffo90/cardwright` (old URL redirects).

Publicly launched on Reddit (r/mtgproxies). **Most of v2.12–v2.17 came from that feedback loop**: a reader reports something, it gets measured, fixed and released, usually the same day. That loop is the project's main source of direction — treat a report as a lead worth reproducing, not a complaint to answer.

Highlights of that run: card languages, the printing gallery with five catalogues, Best scan, Pokémon via TCGdex, Moxfield and MPC-order imports, tokens, bigger paper and grids, custom card sizes, the contrast-edges border mode, Silhouette-accurate registration marks, an in-app FAQ, and a log file so reports arrive with evidence.

## Solved (history in changelog_ai.md)
Auto-update (3 iterations: PID → imagename, timeout without console, START fails → direct exec), duplex preview pairing, black border (5+ iterations), mottling, Winota extended-art, MPC search, multi-sheet preview, card exclusion, custom card back, interactive scroll+drag-reorder preview, Pillow decompression-bomb cap on huge MPC images.
