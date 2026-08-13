# Cardwright - TODO

## ▶ START HERE (handoff, 2026-08-02)
**v2.17.3 is built, released and pushed. Nothing is half-finished; the tree is
clean and every release from 2.12.1 to 2.17.3 is published on GitHub.**

Ten releases went out in this stretch, most of them driven by real reports from
r/mtgproxies. **All of those threads have been answered.** The public state is
consistent: README, FAQ (in-app, under Help) and `decisions.md` all describe
what actually ships.

Nothing is urgent. Pick from "Next up" below, or wait for the next report.

### The one thing worth doing first
The in-app FAQ answer *"Which paper and layout should I use with a cutting
machine?"* recommends A4 4×2 / 7-card. That was true when written, but **A3
arrived in v2.17.0 with 4×4 grids** and is now the better answer: more margin
means the registration marks stop competing with card slots, and it fits 16
cards. The answer is not wrong, just no longer the best advice. `FAQ` lives at
the top of `gui.py`.

### Two things only the community can close
- **trevorstarick** (has a Silhouette, we do not) was asked to confirm that a
  mark inset of **3.5 mm** still registers on real hardware. `REG_INSET_MIN_MM`
  was lowered to 3.5 on the strength of silhouette-card-maker shipping it, not
  on a test. If it turns out not to read, raise the floor.
- **salmetore** was asked whether the 8.89 mm mark length fixed their
  ProxySheets template alignment.

## Print-sheet UX revamp (opened 2026-08-04)
The export dialog matches or beats the competition on features but not on how it
feels to use. `ux_audit.md` compares it against Proxxied and proxy-print,
prioritises the twelve real gaps and concludes that Tier 1 and Tier 2 are all
reachable in CustomTkinter - a Qt rewrite is not justified yet.

Done so far: the file-per-copy model (v2.17.4) - copies are instances sharing an
image, so a quantity control is now just a number - and **undo/redo** (v2.17.5).
Next from Tier 1: a drop indicator with droppable empty slots, dragging between
sheets, quantity per card, and changing a card's art without leaving the dialog.

## Next up (nothing blocking)
From the July 2026 comparison against Proxy-PDF-Maker, fabricard.net and
silhouette-card-maker. Tier 1 was done in v2.17.0; these are what was ranked
below it and still look worth having:

- **SVG cut-file export** - Proxy-PDF-Maker's "Export Exact Guides". Directly
  answers the `.studio3` requests and is far cheaper than a proprietary format.
  **Check first** whether the *free* edition of Silhouette Studio imports SVG:
  it may be a Designer Edition feature, which would sink the idea.
- **Two-colour dashed cut guides** - alternating colours so a guide is visible
  against both light and dark card edges. Cheap, and better than our single
  colour.
- **Save / load project** - export presets save *settings*; this would save the
  working session (card list, quantities, assigned backs). Losing a hand-built
  100-card queue on close is the pain it solves.
- **Live image sliders** (brightness, contrast, saturation…) per card, the way
  fabricard does. Our 9 calibration profiles are better for the common case
  because they are matched to a printer; this is for the one-off card.

## Deliberately not doing
Recorded so they are not re-researched from scratch:
- **Colour cube (.CUBE LUT) support** - powerful, but the profile system covers
  the common case and this is for people who already know what a LUT is.
- **Mixed card orientation, margin modes, base-PDF registration** - we have
  native registration marks, which beats overlaying a base PDF.
- **Prebuilt deck browser / EDHREC suggestions** (fabricard has 815 decks):
  perpetual content maintenance, and it pushes the project toward being a deck
  index rather than a tool. Same line already drawn over curated Drive folders.
- **CLI, themes, unit switching** - low value for this audience.
- **Running the AI twice and downsampling** - 6× sharper on small sources but
  15.3 s and a 125 MB intermediate per card against 2.0 s. Staying light is why
  people move here from Proxxied. See `decisions.md`.

## Open questions for the author
- **Licence.** The author said in July 2026 that they do not care about the code
  being open source and only want donations. Nothing was changed. If it is ever
  revisited: **decide before merging the first PR** - the current LICENSE takes
  contributions under *its* terms, so relicensing afterwards needs every
  contributor's permission. GPL-3.0 was the suggested fit (forks must stay
  open, nobody can close and sell it) with the name protected separately as a
  trademark note.
- **Code signing** still pending, and the cheap route is **gone**: Azure Trusted
  Signing limits individual developers to the USA and Canada, so the ~US$10/mo
  plan this entry used to assume is not available from Chile. Realistic options
  are Certum Cloud or SSL.com IV, annual, cloud-HSM, and capped at 458 days
  from March 2026. See `decisions.md` for the full reasoning, including why
  signing alone would not settle the antivirus detection.
- **Antivirus false positive.** Defender flags the release exe as
  `Trojan:Win32/Wacatac.C!ml` (the installer is not flagged). **This repeats
  every release**: the clearance applies to one file hash, and every build is a
  new hash. The step is in `release.md`. Keep a Defender exclusion on the repo
  folder or the build will be quarantined out from under you mid-release.

  Submissions so far, newest first:
  | Version | SHA-256 (first 8) | Date | Submission ID |
  | --- | --- | --- | --- |
  | 2.17.9 | `b031a2bf` | 2026-08-13 | `f669dbf4-945e-4a39-bf48-3dcda5510ff3` |
  | 2.17.8 | `53c72c7f` | 2026-08-11 | `1940f3c3-54f4-42fb-8a04-3298c8eb50df` |

  If a submission clears, note whether the detection actually stopped: two
  cleared hashes in a row without the next build being flagged would be the
  first evidence that reputation is accruing, and that is the thing worth
  knowing before spending money on a certificate.
- **Linux .deb** - requested at launch. Still undecided, but **cheaper than it
  was**: the macOS port (PR #1, v2.17.5) put every platform branch behind
  `IS_WINDOWS` in `config.py` and left a test suite that asserts both sides, so
  Linux is now mostly a third engine zip and a packaging story rather than a
  rewrite of `bootstrap`/`update`/`upscale`.
- **How far to support macOS.** It runs from source and CI covers it, but there
  is no build, no release and no Mac to test on. Reports will arrive anyway.
  Decide whether that stays "from source, best effort" or grows a real release
  before the first Mac bug report forces the answer.

## Known limits (not bugs)
- MPC search depends on mpcfill.com + Google Drive; fragile if they change.
- Removing or duplicating a card recompacts the sheets - inherent to not
  wasting paper.
- Pokémon art tops out at 600×825 across every catalogue, against Scryfall's
  745×1040. A source limit, not ours. Mitigated by pre-scaling before the AI.
- **One Piece / Digimon / Dragon Ball**: `apitcg.com` covers all three but
  demands an API key on every call, which a binary handed to strangers cannot
  honour. Blocked on that, not on the data existing.
- **mpcfill OCR fork (GPL)** - consuming their HTTP API would be fine (GPL
  covers distributing code, not using a service); we must NOT vendor their code.
  Waiting on their API/spec.

## Backlog (interactive preview)
- Drag whole sheets to reorder them (only cards reorder today).
- Add cards from the preview - needs the upscaling pipeline inside
  ExportDialog (cross-module; deferred).
- The preview still loads every card's working image up front. Fully lazy thumb
  loading would help 300+ card decks.
