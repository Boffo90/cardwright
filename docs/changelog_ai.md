# Cardwright - Changelog

Registro por versión. Actualizar en cada release.

## v2.17.10 (unreleased) - the sheet shows where a card will land
- **Dragging a card now draws an insertion line** where it will go, instead of
  leaving you to let go and find out. A slot is split down the middle: the left
  half means before that card, the right half after it, and the line is drawn
  on the edge the card will land against.
- **Dropping either side of the card being dragged draws nothing**, so a
  gesture that would change nothing reads as cancelled rather than as a move
  that failed.
- **Empty slots are drop targets too.** The first empty slot after the last
  card is where "put it at the end" lives; before this a sheet with room
  offered nowhere to aim.
- Reordering used to work relative to whichever card you dropped on, always
  inserting before it. It now works on the same index the indicator was drawn
  from, so what you saw is what happens.
- **A card can be dragged to any sheet.** Every slot on every sheet is a
  target, and the edge scroll now runs on a timer: rest the cursor near the top
  or bottom of the preview and it keeps moving, faster the closer to the edge
  you hold it. It used to advance one notch per mouse movement, so holding
  still did nothing and crossing a single sheet took about ten deliberate
  wiggles.
- **Quantity per card.** *Add 1*, *Add 3* and *Add copies…* in the right-click
  menu, or **Ctrl+click** a card for one more. **Alt+click** removes it. The
  menu shows how many of that card are already on the sheet and prints both
  shortcuts, since the menu is the only place anyone will find them.
- Copies land next to the original rather than at the end, and however many you
  ask for arrive as **one** undo step.
- **Change a card's art without leaving the dialog.** *Change art…* opens the
  same gallery the main window uses, across every catalogue; the pick is
  downloaded and upscaled with your usual settings and drops straight into the
  sheet. Seeing the wrong printing used to mean cancelling out, fixing the
  queue and setting the sheet up again.
- A card with copies also offers *Change art for all N copies…*, so fixing a
  playset takes one action while four different basic-land arts stay possible.
- **The card gallery no longer crops its own artwork.** The third and fourth
  columns came out narrow, with the art cut off and the set line truncated
  mid-word. The set-and-artist line under each card was not wrapped, so a long
  one set that tile's width and squeezed the rest of the row. It wraps now, and
  the window's width is derived from the grid's spacing rather than a number
  typed once.
- **A double-faced card picked from the Scryfall gallery now brings its back**,
  in the queue as well as here. The gallery's download link points at the front
  face only, so picking one used to queue half a card and let the sheet fall
  back on back.png. The pick carries the card's Scryfall id too, and resolving
  that returns every face. This is the same fault fixed for MPC order files in
  v2.17.6 and the MPC gallery in v2.17.7; Scryfall was the last route still
  carrying it.

## v2.17.9 - the antivirus question, answered in the app
- **New FAQ entry: "My antivirus flags Cardwright as a trojan."** Raised on
  r/mtgproxies by someone who checked the download on VirusTotal before running
  it, which is the right instinct and deserves a real answer rather than "trust
  me".
- The entry names the detection (`Trojan:Win32/Wacatac.C!ml`), explains that
  `!ml` is a machine-learning verdict about the file's shape rather than a
  signature match, and lists the three things the app genuinely does that
  malware also does: single-file packaging, downloading and running the AI
  engine on first launch, and replacing its own exe when you accept an update.
  All three are visible in the public source.
- It also gives the `certutil` command to check the download against the
  SHA-256 published with every release, so nobody has to take any of it on
  faith.
- The README carries the same explanation, and release notes now publish the
  SHA-256 of both files.

## v2.17.8 - the back lookup no longer loses a race
- **Fixes v2.17.7, which only worked if you waited.** Finding a gallery pick's
  back face takes two network calls, measured at **6.5 s** for Cosima, God of
  the Voyage. That work ran in the background, so pressing *Upscale all* inside
  that window read the card's download list before the back had been added and
  processed the front alone, silently. Reported with a Cosima that arrived in
  the output folder with no second face.
- Processing now waits for a lookup still in flight, showing "Finding the back
  face…" while it does, and gives up after 30 s rather than stranding the
  queue. A card whose lookup times out still upscales, front only, and the log
  records why.
- The regression test drives the real `_process_item` against a lookup that has
  not finished, and was checked to fail without the wait.

## v2.17.7 - gallery picks keep their double-faced backs
- **Picking a double-faced card from the MPC gallery now brings its back
  face.** v2.17.6 fixed this for imported order files, but a card chosen by
  art in the gallery went down a different path and still fell through to the
  shared back.png. Reported with Rona, Herald of Invasion.
- The back is not in the search result, but it is in the catalogue under its
  own name. Scryfall says what the second face is called, the catalogue is
  searched for it, and the entry by **the front's own contributor** wins,
  preferring the one whose art variant matches. Contributors upload both faces
  together, so this finds the right art rather than guessing: checked against
  every Rona printing in the catalogue, where Chilli_Axe, WillieTanner's (a)
  and (b), and PsilosX each pair correctly.
- If only another contributor has the back, it is used and the queue row says
  where it came from.
- Split, flip and adventure cards are not affected: they have two card faces
  but one piece of cardboard, and the check reuses the same test the
  downloader already uses to decide how many images a card is worth.
- The lookup runs in the background and fails quietly, so an unreachable
  Scryfall never stops a card from queueing.

## v2.17.6 - MPC orders keep their double-faced backs
- **An MPC Autofill order no longer loses the back of a double-faced card.**
  The order file's `<backs>` section was documented in `mpcfill.py` but never
  parsed, so an imported MDFC arrived with only its front and quietly took the
  shared back.png instead of its real second face. Reported by the author.
- Backs are keyed by the same slot numbers the fronts use, checked against MPC
  Autofill's own export tests rather than assumed. Both faces now download with
  `-front` / `-back` names, which is the pairing convention Scryfall
  double-faced cards already arrive with, so the preview and the duplex export
  needed no changes at all.
- A front entry covering several slots is **split** when those slots do not
  share a back, instead of letting the first slot speak for all of them.
- `<cardback>`, the order's shared back for ordinary cards, is still not
  imported on purpose: the app has its own card-back setting and importing it
  would override a deliberate choice.
- Seven tests cover the parsing, including the split case and a malformed
  `<backs>` entry.

## v2.17.5 - undo, and macOS from source

### macOS
- **Runs from source on macOS**, contributed by `cc3xz` in PR #1 - the
  project's first outside contribution. No `.app`, DMG, signing or macOS
  release: Windows is still the only platform with a build. Apple Silicon is
  native, reaching the GPU through Metal, so there is no Vulkan runtime to
  install.
- The compatibility fixes were real crashes, not cosmetics: `creationflags`
  raises `ValueError` on POSIX and broke every upscale, `os.startfile` does not
  exist there, bootstrap fetched the Windows zip, and the engine came out of
  the archive without its exec bit.
- **`numpy` was never declared in `requirements.txt`** although `gui.py` and
  `print_sheet.py` both import it, so a clean install following the README
  could not start the app. A Windows bug, found from a Mac.
- A test suite covering every platform branch, and CI on windows-latest and
  macos-latest. The tests assert the **Windows** side too, so a branch written
  the wrong way round fails on whichever machine runs it.
- The engine is now told where its models are with an absolute `-m`. On macOS
  it would otherwise find none unless launched from the app's own folder. The
  PR reported this as affecting Windows as well; measured before merging, and
  it does not - the Windows engine resolves the path relative to the
  executable. Passing it is still right, just not a Windows fix.

### Undo/redo in the export preview
- **Ctrl+Z / Ctrl+Y**, and a pair of buttons beside the page nav. Covers
  everything you can do to the working set: reorder, duplicate, remove, add
  cards, and the black-border cycle - which matters most, because a stray
  left-click on a card changed its border with nothing to say so and no way
  back.
- The buttons **name what they would take back** ("Undo move card") on hover,
  and disable when there is nothing there. Undoing reports what it did in the
  status line, so it is never a silent jump.
- **Deleting a card's file clears the history instead of being undoable.** The
  file is gone; undoing past it would put cards on the sheet pointing at
  nothing. Refusing to offer the undo is the honest answer.
- Ctrl+Z inside a text field still belongs to the text field.
- History is 50 steps deep. A snapshot is a shallow copy of the four
  containers that hold the working set, so no action has to know how to invert
  itself.

## v2.17.4 - duplex cut guides, and copies stop being files

### Cutting
- **Duplex offset now moves the cut guides with the cards.** Setting a back
  offset shifted the back page's cards but left its guides on the front's
  grid, so they missed the cards by exactly the drift the offset was
  correcting - cutting the back by them came out crooked. Back rotation had
  the same fault. Cards and guides are now drawn under one transform, the way
  the duplex test sheet already did it. Registration marks stay square to the
  page on purpose: the cutter's sensor hunts for them at a fixed inset.
- **The preview's Backs view shows the offset and rotation too.** It used to
  draw backs on the unshifted grid, which is why a wrong offset only turned up
  at the cut. The sheet caption now names the correction in force - "backs,
  mirrored · offset +4/−3 mm" - so a crooked preview reads as a crooked
  setting rather than a broken preview. Hover, the loupe and right-click
  follow the moved cards.

### Fixed
- **A crash in the preview.** Whenever registration marks cost a card slot
  (A4 3×3, anything on Letter) the preview raised `AttributeError` and stopped
  redrawing. `best_inset()` had been deleted by accident along with a
  neighbouring helper in v2.16.0 while the code calling it stayed. Present in
  every release from 2.16.0 to 2.17.3.
- **Pasted Gatherer links stop failing on two whole classes of card.** Two
  separate faults, both ending in "Could not find a Gatherer image id":
  - **Gatherer's set codes are not Scryfall's.** Urza's Saga is `UZ` on
    Gatherer and `usg` on Scryfall, so `/cards/uz/291` 404'd for Copper
    Gnomes - a card both sites have. New-style links carry the card's name
    slug too, and that is the part they agree on, so it is now the fallback
    lookup: name, then the printing whose collector number matches. Verified
    on `UZ/en-us/291/copper-gnomes`, which resolves to usg/291 and downloads
    the Gatherer image as intended.
  - **No multiverse id was still fatal here.** The decklist import learned to
    fall back to the Scryfall image in v2.17.1, but a link pasted straight
    into the box still raised. Secret Lairs, promos and foils have no
    Gatherer entry, so `SOC/en-us/291/tyvars-stand` simply failed. It now
    serves the Scryfall image, as the import does. Same for a link whose id
    resolves but whose image Gatherer will not serve.

  A link only fails now when neither site recognises the card at all.

### Copies
- **A copy of a card is no longer a file on disk.** Quantity wrote one PNG per
  copy - a 4-of left four identical images in the output folder, and
  *Duplicate* in the preview wrote another every time it was used. Copies are
  now instances pointing at the same image: the sheet lists that path once per
  copy and `build_pdf` flattens it once and draws it as many times as asked
  (verified: a sheet with a duplicate draws 3 cards from 1 distinct image).
  Reordering, removing and assigning a back still act on the single copy you
  clicked. **Border treatment is now per image rather than per copy**, because
  that is how the export has always keyed it - two copies of one card could
  never really print with different borders.
- Deleting a card's file from the output folder now removes every copy of it
  from the sheet, and says so before asking, instead of leaving copies behind
  pointing at a file that is gone.

### Docs
- **New FAQ entry: "insufficient memory" on the printer.** Reported on
  r/mtgproxies with a Brother 3240 CDW, which has 128 MB against a ~217 MB
  lossless sheet. The answer is Adobe Reader's *Print as Image*, with the
  warning that its resolution dropdown defaults to 300 dpi - leaving it there
  rasterises away the 1200 DPI the app exists to produce.
- The cutting-machine guidance is current again: **A3 and Tabloid keep every
  slot in every layout**, 16 cards a sheet at 4×4. Legal keeps all nine in
  3×3. A4 wants 4×2 or the 7-card layout. The FAQ, the README and the
  preview hint all said A4 was the best answer, which stopped being true when
  A3 and the bigger grids arrived in v2.17.0.

## v2.17.3 - custom card sizes

### Custom card sizes
- **"Custom size…"** in the Card size dropdown takes a width and height in mm
  (20-200 a side), remembers it, and lists it from then on. Requested on
  r/mtgproxies.
- It drives the upscale target as well as the sheet, since everything reads
  `card_size_mm` / `card_size_px`. Verified end to end at 63.5×88.9 on A4 3×3,
  70×120 on A3 4×2 and 44×68 on A4 4×4.
- Reachable from the main window and from Export, since both show the picker.

### Fixed
- Exporting a subset of sheets counted against **every** card in the queue, so
  printing sheet 1 of a 90-card deck read "Placing card 3/90" while only 9 were
  going into the PDF. It now counts what is actually being placed.

## v2.17.2 - Gatherer imports stop dropping cards
- **A Gatherer import no longer rejects cards Gatherer does not carry.** It
  falls back to the Scryfall image and tells you which ones, instead of
  leaving you with an incomplete deck.
- That was hitting hard: Gatherer has no entry for Secret Lairs, promos, or
  **any foil printing** - Scryfall numbers foils with a star (`198` vs `198★`)
  and gives the starred one no Gatherer id. One real 100-card import lost 24
  cards to this.
- The substitution is reported the way the language fallback is: an info
  popup, not the red "issues" path, because it isn't a failure.
- New FAQ entry explaining the star.

## v2.17.1 - cards no longer vanish on repeated names
- **An MPC order with the same card twice lost all but one copy.** The download
  filename came from the card name alone, so an order with 2 Plains, 3 Islands
  and 2 Arcane Signets wrote 85 files instead of 89 - and the survivors were
  the wrong art. The order's slot number is now part of the name. Reported on a
  real 89-card order.
- The card gallery had the same flaw: two Yu-Gi-Oh artworks from one set, or
  two MPC arts by one contributor, shared a filename and one replaced the
  other. Picks now carry the catalogue's own id.

## v2.17.0 - help, more import routes, tokens, bigger paper

### Help: FAQ and About
- New **Help** button in the header. A FAQ answering the questions people
  actually asked after release - why marks cost card slots and which inset
  fixes it, which paper and layout to use with a cutter, why a Pokémon card is
  less sharp, why a card came back in English, which border mode to use, the
  unsigned-publisher warning, and where the log is.
- An About tab with the version, links, licence, the card-data credits and
  what the app is built on.

### More ways in
- The decklist importer can pull art from **Gatherer** instead of Scryfall.
  Cards Gatherer does not carry (no multiverse id) are reported rather than
  silently dropped.
- **Load an MPC Autofill order `.xml`** and get exactly the art you already
  picked there - a name search cannot reproduce that. Quantities come from the
  slot count; entries missing an image id are listed instead of skipped
  silently.
### Tokens
- **"Also add the tokens these cards make"** in the decklist importer. Scryfall
  lists them in `all_parts`, so it is exact rather than guesswork - a card that
  makes none contributes none. Fetched in one bulk call, appended after the
  deck.
- **Every card in the deck is scanned**, not just the commander.
- Reprints of the same token collapse to one - three goblin-makers give you
  one Goblin, the newest printing. Tokens that merely share a *name* do not:
  "Elemental" has 26 genuinely different versions, and you get the ones your
  deck actually makes.

### Paper and grids
- Added **A3, Legal, Tabloid and A5** to the page sizes (was A4 / Letter only).
- Added **3×4 and 4×4 portrait** grids, because otherwise a bigger sheet still
  printed 9 cards: **A3 and Tabloid now hold 16**. Not Legal - 4 rows come to
  352 mm against a 356 mm page, which the 3 mm unprintable margin eats.
- A5 cannot hold a 63×88 grid at all and says so rather than exporting
  something broken; it is there for the mini card size.

### Fixed - the registration square was a millimetre small
- The 3-mark square is drawn 5 mm filled **plus half the line thickness on
  every side**, matching silhouette-card-maker, which strokes its square with
  the mark thickness. At the 1 mm default that is 6 mm across, not 5.

### Manual bleed override
- "Trim MPC bleed" becomes **Auto-detect / Assume bleed / Assume none**.
  Turning the old switch off covered "wrongly detected", but there was no way
  to say "this *does* carry bleed the ratio test can't see". Now there is.
- Detection is still by aspect ratio, and still only runs on sources that can
  carry a bleed (MPC and local files).

## v2.16.0 - Moxfield decks, and your card slots back
### Moxfield deck import
- **Paste a Moxfield deck URL and it imports**, like Archidekt already did.
  Commanders, companions and sideboards come along; the maybeboard does not.
- The app used to refuse Moxfield links. If Moxfield ever closes the endpoint
  off, every failure path points at their Export → paste route, which works
  regardless.

### Get your card slots back
- **The mark inset can now go down to 3.5 mm** (was 10). That floor was ours,
  not the machine's: 10 mm is what Silhouette Studio documents as a minimum,
  but silhouette-card-maker ships 3.5 mm for its borderless layouts.
- It is what was costing cards. Marks are corner brackets, so what blocks a
  slot is a mark landing on a *corner card* - moving the marks outward frees
  them. **Letter 4×2 goes from 6 usable cards to 8 by dropping the inset half
  a millimetre**, to 9.5 mm. A4 3×3 goes from 7 to 9 at 6 mm.
- The default stays at 10 mm, so nothing changes unless you reach for it.
- When marks do cost you slots, the preview now **names the exact inset that
  keeps them all**, picking the largest one that works - a mark further from
  the paper edge is the safer one. If no inset helps, it names a layout that
  does.
- 3.5 mm is the floor because most inkjets cannot print closer than ~3 mm to
  the paper edge; below that the mark is simply clipped off.

## v2.15.0 - Pokémon cards, sharper small sources
- A source too small for one AI pass to reach the card is now **resized up to
  exactly target/scale before the pass**, so the AI lands on the card instead
  of leaving a plain stretch to do afterwards.
- Measured on a 600×825 scan: sharpness (Laplacian variance) goes from **54 to
  84**, for **+0.5 s** and no extra memory.
- Never fires for MTG - Scryfall's 745 px × 4 already clears the target. It is
  for Gatherer (646 px) and the Pokémon catalogues (600 px).
- Running the AI twice and downsampling scores much higher (331) but costs
  15.3 s per card and a 125 MB intermediate. **Not implemented on purpose**:
  staying light matters more than the last of the sharpness.

### Pokémon cards
- New **Pokémon** tab in the card gallery, via the **TCGdex** API. No API key,
  no account, and the card-language picker drives it (6 languages with real
  images). Pokémon cards are 63×88 mm, so no card-size switch is needed.
- Chosen over pokemontcg.io after measuring both: identical `600×825` image
  ceiling, but TCGdex needs no key, is open source, and pokemontcg.io has been
  absorbed into a commercial product. The gallery states the resolution limit
  rather than hiding it.

### Fixed - Pokémon cards came out cropped
- The MPC bleed trim decides by aspect ratio, and TCGdex's 600×825 images land
  at 0.7273 - **inside the 0.725-0.745 MPC window** - so every Pokémon card was
  cropped 4.4% a side and lost its border. Scryfall (0.7163) and Gatherer
  (0.7162) fall outside it, which is why the heuristic had never misfired.
- The trim now only runs for sources that could actually carry a bleed: MPC
  and local files. Local files keep the heuristic, since a hand-fed MPC
  download has nothing else to go on.

### Fixed - search errors arrived empty
- `except Exception as e:` unbinds `e` when the block ends, so every deferred
  error handler (`self.after(0, lambda: self._failed(e))`) had lost it by the
  time it ran. Failures reached the user as **"Search failed: None"** and the
  log recorded `NoneType: None` instead of a traceback. Seven handlers fixed.

## v2.14.0 - contrast-edges border mode
- **New "Contrast edges" border mode, now the default.** It pushes the dark
  pixels inside a fixed band at the card's edge instead of measuring how deep
  the frame runs, so there is no detection to misjudge on artwork that reaches
  the cut edge. Quadratic falloff, tone weighting (only pixels below 140/255
  move) and a contrast curve keep it off the artwork.
- The old behaviour stays available as **"Auto-detect"**, no longer the
  default. Off is unchanged.
- Three new fields in Export → Image: edge width (% of the card's shorter
  side), edge contrast and edge brightness.
- Reimplemented in numpy from the approach Proxxied uses (MIT per its README,
  `acoreyj/proxies-at-home`) - their code is GLSL, this is not a copy.
- **Apply to, per source.** Checkboxes in Export → Image decide which
  catalogues get border treatment at all. **MPC and card backs are off by
  default** - MPC art already carries a true black edge, so touching it is
  risk with no upside. A per-card override from the preview still wins over
  the source rule, and the preview reflects the same rules the export uses.
- **Settings migration**: "On (auto-detect)" is mapped to "Auto-detect". The
  rename would otherwise drop existing users back to "Off" silently.

## v2.13.0 - cards in other languages
- New **Card language** picker in the main window (its own row under Model /
  Card size, so the row-0 width budget that v2.12.0 fixed stays intact).
  Persisted as `card_lang`; worker threads read it from settings, never off
  the widget.
- Applies to the two paths that used to be English-only: **card-name lookups**
  and **decklist imports**. Pasting a link that already names a language
  (`/card/m11/149/ja/…`, any Gatherer URL) still wins over the picker.
- **English fallback per card.** Cards with no printing in the chosen language
  are added in English and listed in the import summary - an info popup, not
  the red "issues" path, because it isn't a failure. Verified against a
  Secret Lair printing, which is English-only.
- Scryfall has no bulk language lookup (`/cards/collection` takes no `lang`),
  so a decklist costs one extra request per unique printing, ~0.1 s each.
- 11 languages, matching Scryfall's own printings.

### Best scan (same release)
- New **Best scan** switch (on by default): when the lookup is just a card
  name, compare that card's printings and take the one with the best image
  instead of whichever Scryfall returns first. A weak scan is exactly what
  upscaling to 1200 DPI magnifies.
- Every Scryfall PNG is 745×1040, so quality is judged by `image_status`
  first (placeholders and missing art are dropped outright - a placeholder
  can out-weigh a real scan) and then by **Content-Length via HEAD**, which
  reads the true byte size without downloading the image. Bytes only break
  ties *within* the best status tier; across tiers a grainy low-res scan
  would beat a clean high-res one, since noise is what PNG compresses worst.
- **Same artwork only.** This is a scan upgrade, not an art swap - otherwise
  "Silence" in English lands on a Secret Lair by a different artist.
- Only bare names are eligible. A link or a decklist line already names the
  printing the user chose and is never second-guessed.

### Card source gallery (same release)
- Typing a **bare card name** in the main search box now opens a gallery of
  that card's printings with thumbnails, instead of silently queueing one.
  You see what you are about to upscale before committing to it. A link or a
  decklist line still goes straight to the queue - it already chose.
- A **Source** switcher flips the same query between **Scryfall**, **Gatherer**
  and **MPC Autofill** without leaving the dialog, so alternate art from any
  catalogue is one click away.
- New **`sources.py`** holds the three adapters behind the interface
  `CardSearchDialog` already expected from `mpcfill` / `ygoprodeck`.
- Gatherer has no search of its own, so Scryfall finds the printing and
  Gatherer serves the image - the split `_fetch_gatherer` already used.
  Only printings carrying a multiverse id can appear.
- The gallery warns that **Gatherer images are 646×902 at ~60 KB** against
  Scryfall's 745×1040 at ~1 MB: measured consistently across cards, roughly
  15× less data to upscale from.
- Gallery thumbnails always come from Scryfall, including on the Gatherer
  tab - Gatherer's handler serves one full-size image per request, far too
  heavy for a grid.

### Interface pass (same release)
- Top bar down to three secondary buttons at one width and one colour:
  **Browse cards… / Add files… / Import list…**. The per-catalogue buttons are
  gone - every catalogue, Yu-Gi-Oh included, is now a tab in the gallery, so
  picking one still switches the card size over.
- Options panel rebuilt as an aligned label/control grid with the plain
  toggles stacked beside it. It was one flat row of loose parts whose labels
  never lined up; required width dropped 868 → 798 px.
- Footer utilities are one ghost tier at one height. "Clear" was a filled
  button 6 px taller than its neighbours, which made the row look crooked.
- "From files…" renamed **"PDF from files…"** - it exports, and the old name
  read like a second "Add files…".
- The button no longer re-labels itself "UPSCALE ALL" in caps after a run.

### Fixed - guides off left marks on the page
- Turning guides off only gated the corner crosses; the dark tick marks in
  the margins were drawn unconditionally, so pages still came out with marks
  beside the registration corners.
- Measuring that turned up an unreported collision: on **A4 at the default
  10 mm inset, 5-6 margin ticks landed inside a registration mark's
  keep-clear box**, where a stray line can throw the cutter's optical scan
  off. Guides and ticks now both skip anything intersecting those boxes.
- **Registration marks now match Silhouette Studio's published geometry.**
  Cross-checked against the settings panel Proxxied exposes: inset
  `0.394 in = 10.008 mm` (min), length `0.350 in = 8.890 mm` (default),
  thickness `0.039 in = 0.991 mm` (max). Our inset minimum and thickness
  maximum already matched; **the mark length did not** - it defaulted to 5 mm,
  our own minimum, where Studio expects 8.89, so marks printed visibly
  shorter than a Studio-made template's. Length now defaults to 8.89 mm.
  That costs slots where longer marks reach onto the grid: A4 3×3 goes 9
  usable cards to 7, Letter 4×2 8 to 6, Letter 7-card 7 to 6; A4 4×2 and A4
  7-card keep every slot. Both fields name Studio's value in their hint.

### Logging
- New **`applog.py`**: a rotating log file next to the app (`cardwright.log`,
  512 KB × 3), plus a **Log** button in the header that opens it.
- The app had no logging at all. The only error surface was a truncated line
  in a queue row, so a report of "it doesn't fetch cards" was unactionable:
  nothing recorded *why*. Failures now log the full traceback along with what
  was being fetched.
- Unhandled exceptions are hooked on the main thread **and in worker
  threads**. The windowed build has no console, so a crash inside a download
  or upscale thread previously vanished without a trace.
- The finished-with-errors dialog points at the log and asks for it to be
  attached to reports.
- A read-only install directory degrades to no logging instead of stopping
  the app from starting.

## v2.12.1 - keep copyright microtext crisp
- Border deepening no longer eats the anti-aliasing of the white microtext in
  the bottom band (copyright / collector line). `BORDER_TONE_MAX` 100 → 58:
  measured across 5 cards, anti-aliasing preserved went from 45-62% to 100%
  while the frame still snaps to solid black. Fixes strokes looking thicker
  and 'o'/'a'/'e' closing up in print.

## v2.12.0 - visual revamp (stage 1: design system, main window, Export tabs)
- New **`theme.py`**: one set of colour / spacing / radius / type tokens.
- Repalette to a **neutral graphite** scheme with a single warm accent, in the
  spirit of a professional tool. Accent now means "primary action or active
  state" only; headings use the text ramp. Contrast verified against WCAG.
- Typography unified on Segoe UI Variable (fallback Segoe UI); Georgia and the
  mana-dot decoration removed.
- Main window: header simplified, options and actions split into two rows so
  the buttons stop clipping, ghost/secondary/primary button hierarchy,
  accent-coloured switches instead of CustomTkinter's default blue.
- **Export dialog is now tabbed** (Layout / Image / Backs / Cutting / Tests)
  instead of ~30 controls in one scrolling column. Presets moved above the tabs.
- Queue rows: flat cards with a hairline border, smaller status dot, calmer
  status palette (muted idle, accent while working, green done, red error),
  slimmer progress bars.
- Dialogs: inputs share one height/radius/fill, outlines meet the 3:1 non-text
  contrast threshold, search-gallery tiles and buttons follow the same
  hierarchy, decklist box uses Cascadia Mono.

## v2.11.0 - Yu-Gi-Oh card search (YGOPRODeck)
- New **"Yu-Gi-Oh…"** search: gallery over the YGOPRODeck API, one entry per
  artwork, click to queue. `ygoprodeck.py` is new and mirrors `mpcfill.py`'s
  interface (search / download / fetch_thumb).
- Respects their terms: requests throttled well under 20/s, and thumbnails are
  cached on disk because they ask you not to keep hotlinking their images.
- **Card size moved into the main window** next to the model picker (still one
  shared setting with Export). It has to be right at upscale time - a Yu-Gi-Oh
  card is 59×86 mm (aspect 0.686) and fitting it to Magic's 63×88 (0.716)
  stretches it. Adding a Yu-Gi-Oh card switches the size over automatically
  the first time.
- `MPCDialog` generalised into `CardSearchDialog`, which takes the catalogue
  backend as a parameter, so MPC and YGOPRODeck share one gallery.
- Google Drive card dumps offered for Pokémon/Digimon/One Piece/Dragon Ball
  were **declined** - see project_state.md for why (no index, quota-bound
  single account, distribution-index risk).

## v2.10.0 - 7-card Silhouette layout
- New **"7-card Silhouette"** layout, requested by a Cameo user: a 4×2 grid
  whose left column holds a single vertically-centred card, with the other 6
  in a 3×2 block. That frees both left corners, where the marks a Cameo
  depends on most sit - clearance from the lower-left mark goes from ~5 mm
  (4×2) to ~49 mm. Backs mirror automatically (the lone card moves right).
- Slot placement is now driven by `layout_positions()` instead of grid index
  maths, and duplex mirroring by `mirror_x()`, so non-grid layouts work
  everywhere (PDF, preview, bleed frames, mark-collision detection).
- Same idea as ProxySheet's "SevenCard" template; geometry reimplemented from
  scratch (that project is GPL-3.0, so none of its code was used).

## v2.9.0 - cutting-machine registration marks + other TCG card sizes
From Reddit feedback after the public launch.
- **Registration marks** (Silhouette / Cricut print-and-cut): 3-mark standard
  or 4-mark CAMEO 5a pattern, with inset / length / thickness settings.
  Geometry follows the spec the sensor expects (5×5 mm filled square + L
  brackets, arms 5–20 mm, 0.5–1 mm thick, inset ≥10 mm, 1.5 mm clear zone).
  Defaults are the spec minimums (10 mm inset, 5 mm arms) so **no card slots
  are lost**: A4 3×3 keeps all 9, A4/Letter 4×2 keep all 8. Letter 3×3 can't
  fit marks (7.7 mm margin vs 10 mm minimum inset) - it warns and skips those
  slots, moving the cards to the next sheet (nothing is ever discarded).
  A live hint reports usable vs total slots.
  Shift-down is ignored while marks are on: the cutter locates the printed
  marks and self-compensates, so shifting only the cards would misalign them.
- **Card size selector** for other TCGs: MTG/Pokémon 63×88 (Pokémon already
  matched MTG, so it needed nothing), Yu-Gi-Oh 59×86, mini 44×68, tarot
  70×120. Drives both fit-to-card upscaling and the PDF layout/preview.
  The MTG size keeps its exact legacy 2976×4160 px (clean x4 of Scryfall).

## v2.8.0 - renamed ProxyForge → Cardwright
- App and brand renamed to **Cardwright** (ProxyForge was too generic and
  clashed with other *Forge proxy tools). No functional changes.
- GitHub repo renamed to `Boffo90/cardwright` (old URL redirects; auto-update
  for 2.7.0 clients still works via the redirect + the non-installer-exe
  fallback in update.py).
- New installer AppId + `Cardwright.exe` / `Cardwright_Setup-2.8.0.exe`.

## v2.7.0 - interactive preview: scroll all sheets, drag to reorder
- Export preview is now a scrollable canvas showing every sheet stacked.
- Drag a card to reorder it (before the card you drop on); order = PDF order.
- Left-click still cycles the black border; right-click still drops a card.
- Fix: lifted Pillow's `MAX_IMAGE_PIXELS` cap (config.py) - huge MPC images
  (~190M px) no longer fail with "decompression bomb"; they now reach export.
- Skip AI upscale when the (trimmed) source is already >= card size - MPC /
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
- Faster preview for big decks: sheets render lazily (only those near the
  viewport, cached) and treated-border thumbs rebuild only for visible cards,
  so slider tweaks no longer re-process the whole deck.
- Export presets: save/load named configurations (Presets section - Save… /
  Delete) stored in settings.json under `export_presets`.
- Cut-guide offset (mm): gap between the guide and the card corner.
- "PDF from files…" button: pick specific already-upscaled cards (from the
  output folder or anywhere) straight into a PDF, no queue needed.
- Sheet selection: a "Sheets" box (e.g. 1 or 1-3,5) prints only those sheets;
  unselected sheets show "(not printed)" in the preview.
- Direct card management in the export: right-click a card → "Duplicate"
  (makes a 'name (2).png' copy right after it), "Remove from PDF" (file kept)
  or "Delete from output folder…" (removes the PNG from disk, with
  confirmation); plus an "Add cards…" button to append more (re-picking a card
  already in the set adds a duplicate). Replaces the old exclude-with-an-X
  toggle. The preview help line now wraps instead of clipping.
- Loading spinner: cards whose thumbnail is still loading show a small animated
  spinner instead of a flat grey slot, so it reads as loading, not an error.
- Fix: preview no longer caps thumbnails at the first 12 cards - cards on
  sheet 2+ (e.g. Gatherer imports past #12) now render.
- Ideas adapted from Malacath-92/Proxy-PDF-Maker.

## v2.6.0 - full preview, card selection, custom backs
- Preview de todas las hojas (◀▶), no solo la primera.
- Clic derecho descarta/restaura carta del PDF (X roja); conteos se recalculan.
- Elegir cardback (File… / MPC…) para no-DFC; DFC conservan su reverso.

## v2.5.0 - MPC Autofill search
- Botón "MPC search…": galería sobre mpcfill.com, elige versión, a la cola. Descarga de Google Drive + recorte de bleed. `mpcfill.py` nuevo.

## v2.4.0 - Gatherer images, MPC bleed trim, reject art edges
- Gatherer link → imagen de Gatherer (no Scryfall).
- Recorte de bleed MPC por proporción; toggle "Trim MPC bleed".
- Borde: rechaza lado cuyo marco no cubre ≥88% (extended-art Winota).

## v2.3.3 - solid-black frame, no more mottled edge
- Snap binario a negro (no proporcional) → elimina moteado (mat/41).

## v2.3.2 - magnifier on export preview
- Lupa ~6x al hover; cartas en memoria a 640×896.

## v2.3.1 - border amount & manual width
- Sliders Amount (0-100%) y Manual width para cartas forzadas ON.

## v2.3.0 - per-card border control
- Clic en preview cicla auto/off/on por carta (Winota falso positivo).

## v2.2.x - border detection (por lado, por línea, croma, texto colección)
- v2.2.4 por-línea + croma + texto; v2.2.3 por-lado; v2.2.2 resolución nativa; v2.2.1 por-borde; v2.2.0 deepen border inicial.

## v2.2.3.1 - source-available license (MIT → propia)

## v2.1.4 - duplex preview pairing fix
## v2.1.3 - relaunch post-update via ejecución directa (no START)
## v2.1.2 - swap script timeout/ping fix
## v2.1.1 - auto-update wait on imagename (2 procesos)
## v2.1.0 - 4×2 landscape layout + Inno Setup installer
## v2.0.0 - release público inicial: upscaling IA 1200dpi, Scryfall/Gatherer/decklist/Archidekt, print sheets, calibración, shadow lift, duplex, auto-update, bootstrap
