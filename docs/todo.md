# Cardwright - TODO

## ▶ START HERE (handoff, 2026-08-28)

### 4x6 photo sheets with PNG output: **done**
Shipped in v2.17.11. New *4x6 photo* page size, *2x1 landscape* grid, and
*Output format* (PDF / PNG / JPEG) with a DPI choice on the Image tab.

Raster output goes through `_RasterCanvas` in `print_sheet.py`, a Pillow
stand-in for the canvas calls `build_pdf` makes, so there is one layout
implementation rather than two - guides, ticks, bleed frames, registration
marks and mirrored backs all come through unchanged. The reasoning, including
why rasterising the PDF was closed off, is in `decisions.md`.

**The one question that was put to the user is still unanswered**: what
maximum resolution their photo lab accepts. It no longer blocks anything - the
DPI is a choice (300 / 600 / 1200) rather than a hard-coded 300, which is what
was planned if no answer came. If they do reply, the only thing worth changing
is which value the dropdown defaults to.

### Page shift on both axes: **done**
Also v2.17.11. *Shift down* takes negative numbers and *Shift right* is new,
so the whole layout moves in any direction instead of down only. Reported by
**XTR3M3brutality** on Reddit: an Epson ET-8500/8550 rear top loader wastes
0.8 in of the page and leaves roller marks, and down-only could not reach that
edge - they said they were going back to proxxied.com over it.

The hint under the two entries names how much room the current page and grid
actually leave, because it is often less than the printer wastes (Letter 3x3
gives 4.7 mm against the 20 mm they need) and silence there reads as a broken
setting. **Worth telling them**: on that printer the answer is 4x2 landscape,
Legal, A3 or Tabloid - Letter 3x3 cannot dodge 0.8 in at any setting.

### Riftbound: **done**
Shipped in v2.17.13 via Riftcodex (no API key, Riot's own images at 744x1039).
Battlefields are stood upright on the way in rather than needing the
mixed-orientation layout work. Reasoning in `decisions.md`.

**Untested against real hardware**: nobody here has printed a Battlefield. The
quarter turn is the only thing that could look wrong, and it should not - a
Battlefield prints its rules text both ways up because it sits between two
players.

### Next task: pick from the list below
Nothing is teed up. The two that were sized and ranked highest after 4x6 are
**mixed card sizes on one sheet** (needs per-card size plus a small packing
problem) and **collapsing the main window into the export dialog** (the
obvious end state, and large enough to want a clear run). Both are described
under "Asked for by users".

### State of the tree
**v2.17.12 is released and pushed** (2026-08-28), tree clean, 155 tests
passing. Releases are batched, see `release.md` for the rule and its two
exceptions.

Two releases went out that day. v2.17.11 carried multi-select in the preview,
projects (save/load the queue), cut guides that can be turned off on the backs,
the exact-printing search made findable, a retry around card saves that Windows
briefly locks, 4x6 photo sheets with PNG/JPEG output, and the two-axis page
shift. v2.17.12 followed because that page shift pushed the Layout tab past the
bottom of the panel with no scrollbar, so two controls were invisible: it fixes
that, opens the export dialog with an empty queue, moves the cut guides to the
Cutting tab, and links Discussions from About.

**v2.17.12 broke the batching rule on purpose**, under the "regression people
are already hitting" exception in `release.md`: v2.17.11 shipped with a control
you could not reach.

**Owed right now, and only the author can do it:** the Microsoft
false-positive submission, for *three* binaries. v2.17.10's hash was never
submitted, and v2.17.11 and v2.17.12 followed. Both are in the table below. It is a web form
(<https://www.microsoft.com/en-us/wdsi/filesubmission>, "Software developer" /
"Incorrectly detected as malware"), so it cannot be automated from here.

The UX audit's **Tier 1 and almost all of Tier 2 are done**. What is left in
`ux_audit.md`: per-slot disable, sort & filter, and dragging a whole selection
as a group.

### Two things only the community can close
- **trevorstarick** (has a Silhouette, we do not) was asked to confirm that a
  mark inset of **3.5 mm** still registers on real hardware. `REG_INSET_MIN_MM`
  was lowered to 3.5 on the strength of silhouette-card-maker shipping it, not
  on a test. If it turns out not to read, raise the floor.
- **salmetore** was asked whether the 8.89 mm mark length fixed their
  ProxySheets template alignment.

## Print-sheet UX revamp (opened 2026-08-04)
The export dialog matched or beat the competition on features but not on how it
felt to use. `ux_audit.md` compares it against Proxxied and proxy-print,
prioritises the twelve real gaps, and concluded that Tier 1 and Tier 2 were
both reachable in CustomTkinter: a Qt rewrite was not justified, and building
Tier 1 bore that out.

**Tier 1 is done.** What is left, in `ux_audit.md`: multi-select, a real
border-mode indicator, per-slot disable, and sort & filter.

## Asked for by users, assessed but not started
Raised on r/mtgproxies in August 2026 and sized here so the next look does not
start from nothing. 4x6 with PNG output was the top of this list and shipped in
v2.17.11.

- **Mixed card sizes on one sheet**, to save paper across games. Card size is
  currently one setting for the whole export and the layout code assumes every
  slot is identical, so this needs per-card size *and* a small packing problem
  solved. Real value for multi-game printing, not a quick one.
- **Search every catalogue at once**, without picking a game first. Doable and
  a good idea. The catch is measured: MPC Autofill takes about **5 seconds** to
  answer, so an everything-search is as slow as its slowest source. The answer
  is probably to show results as they arrive rather than waiting for all of
  them.
- **Collapse the main window into the export dialog.** A user's observation,
  and a fair one: the main window is now just a queue with a search box, while
  the export dialog is where the work happens since it gained drag, reorder,
  quantities and change-art. Collapsing the two is the obvious end state. It is
  also large enough that it wants a clear run rather than a spare afternoon.

## Next up (nothing blocking)
From the July 2026 comparison against Proxy-PDF-Maker, fabricard.net and
silhouette-card-maker. Tier 1 was done in v2.17.0; these are what was ranked
below it and still look worth having:

- **Two-colour dashed cut guides** - alternating colours so a guide is visible
  against both light and dark card edges. Cheap, and better than our single
  colour.
- **Live image sliders** (brightness, contrast, saturation…) per card, the way
  fabricard does. Our 9 calibration profiles are better for the common case
  because they are matched to a printer; this is for the one-off card.

## Deliberately not doing
Recorded so they are not re-researched from scratch:
- **SVG cut-file export** - the check this was gated on came back no
  (2026-08-27). Importing SVG needs **Designer Edition**, a paid upgrade;
  Silhouette Studio's free Basic Edition cannot open one. The people who most
  need a cut file handed to them are exactly the ones who could not use it,
  and anyone on Designer Edition can already build the template themselves.
  **DXF is the format that would work** - Basic Edition opens it, with cut
  lines already live and no tracing - but DXF carries no unit information, so
  it commonly lands at the wrong scale, and a cut file that imports 4% off is
  worse than none. That is only settleable on real hardware, which this
  project does not have: see the two questions above that have been open for
  the same reason. Revisit if someone with a Silhouette offers to test.
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
  | 2.17.12 | `baf347b3` | **not submitted** | - |
  | 2.17.11 | `cb0b7626` | **not submitted** | - |
  | 2.17.10 | `817d473f` | **not submitted** | - |
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
  honour. Blocked on that, not on the data existing. Riftbound shipped in
  v2.17.13 precisely because Riftcodex asks for no key - if an open API turns
  up for these three, the same shape of module works.
- **mpcfill OCR fork (GPL)** - consuming their HTTP API would be fine (GPL
  covers distributing code, not using a service); we must NOT vendor their code.
  Waiting on their API/spec.

## Backlog (interactive preview)
- Drag whole sheets to reorder them (only cards reorder today).
- Add cards from the preview - needs the upscaling pipeline inside
  ExportDialog (cross-module; deferred).
- The preview still loads every card's working image up front. Fully lazy thumb
  loading would help 300+ card decks.
