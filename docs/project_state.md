# Cardwright — Project State

## Objective
Free (not open-source) Windows desktop app that turns MTG card images into print-ready proxies at **true 1200 DPI** via GPU AI upscaling, and builds print-ready PDFs. Distributed globally via GitHub. Repo: **Boffo90/cardwright**. Author: Boffo90. Donations: paypal.me/warchazzz. Separate from the local proxy-selling business (never mention sales).

## Current version
2.9.0 (see `changelog_ai.md`). App renamed **ProxyForge → Cardwright** in v2.8.0 (July 2026); GitHub repo is `Boffo90/cardwright` (old URL redirects). Publicly launched on Reddit (r/mtgproxies) with mostly positive feedback; v2.9.0 acts on that feedback.

## Solved (history in changelog_ai.md)
Auto-update (3 iterations: PID → imagename, timeout without console, START fails → direct exec), duplex preview pairing, black border (5+ iterations), mottling, Winota extended-art, MPC search, multi-sheet preview, card exclusion, custom card back, interactive scroll+drag-reorder preview, Pillow decompression-bomb cap on huge MPC images.
