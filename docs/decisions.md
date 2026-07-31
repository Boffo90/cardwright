# Cardwright — Technical Decisions

Settled decisions. Do not re-litigate; add new ones here.

## Language
**Everything in the project is English** (global app): UI, code, comments, docs, README, changelog, and GitHub release titles/descriptions. Chat with the user is in Spanish, but anything that lives in the repo or is shown to the end user is English.

This covers the **interface**. The *cards* are a separate axis — see below. Translating the UI itself was weighed in July 2026 and **deferred**, not rejected: ~123 literal strings in `gui.py` alone, plus a re-layout risk because CustomTkinter widths are fixed and were tuned for English during the v2.12.0 revamp. If it ever happens, start with Spanish and Portuguese (verifiable by the author) rather than machine-translating a dozen locales.

## Card language (v2.13.0)
A global **Card language** picker (main window, under Model/Card size, persisted as `card_lang`) drives which printing gets fetched.
- **English is the fallback, always.** Promos, Secret Lairs and older sets are frequently English-only, so every lookup must survive the target language not existing. A miss is reported, never raised.
- **Scryfall has no bulk language lookup**: `/cards/collection` identifiers accept `id`/`set`/`collector_number`/etc. but *not* a language. So decklists resolve in bulk first (cheap) and then take one `/cards/{set}/{number}/{lang}` round trip per unique printing — ~0.1 s each at `SCRYFALL_DELAY`. Do not go looking for a batch endpoint; there isn't one.
- **An explicit link beats the picker.** A `/card/m11/149/ja/...` URL or any Gatherer link is left alone (`_ref_pins_language`) — pasting a specific printing is a deliberate act.
- Queue labels keep the **English card name** even for localized printings (Scryfall's `printed_name` holds the localized one); it matches the decklist the user pasted and stays searchable. Filenames carry the `-<lang>` suffix.
- The picker is labelled **"Card language"**, never just "Language" — beside Model and Card size a bare "Language" reads as the app's own UI language. A user asking for French cards in July 2026 had 2.14.0 installed, where it said "Language", and did not find it. Qualify the noun.
- A language fallback is **not** an import failure: it gets an info popup and neutral status text, not the red "Imported with issues" path.

## Best scan selection (v2.13.0)
When a lookup is a bare card name, pick the printing with the best image rather than Scryfall's first result. On by default (`best_scan`) because a weak scan is what upscaling to 1200 DPI magnifies.
- **Pixel dimensions are useless here** — Scryfall serves every PNG at 745×1040. Quality is `image_status` plus real byte size.
- **Filter by `image_status` before weighing bytes.** Measured on Silence: the m11 *placeholder* is 810 KB while the real m14 scan is 801 KB, so weight alone picks the placeholder.
- **`Content-Length` via HEAD**, not a download — exact size, no image transfer. Verified working on `cards.scryfall.io`.
- **Bytes only break ties within one `image_status` tier.** Across tiers they mislead: grain is what PNG compresses worst, so a noisy low-res scan can out-weigh a clean high-res one.
- **Restrict to the same `illustration_id`.** Without it, English "Silence" jumps to a Secret Lair by a different artist — an art swap, not a quality upgrade. If no printing in the target language shares the art, the restriction is dropped rather than failing.
- Shortlist capped (`_BEST_SCAN_CANDIDATES`) so cards with dozens of printings (basic lands) stay to a handful of HEADs.

## Card source gallery (v2.13.0)
A bare card name opens the printing gallery; a link or decklist line does not (`scryfall.ref_names_a_printing`). Sources live in `sources.py` behind the interface `CardSearchDialog` already expected — `search(query)`, `fetch_thumb(url)`, plus `ADD_KIND` saying how a pick is fetched.
- **Gatherer has no search API.** Scryfall finds the printing, Gatherer serves the image, same split `_fetch_gatherer` uses. Only printings with a `multiverse_id` can appear at all.
- **Gatherer is the weaker source and the UI says so.** Measured across Lightning Bolt / Counterspell / Sol Ring, consistently 646×902 at 53-76 KB against Scryfall's 745×1040 at 837-1285 KB — ~15× less data to upscale from. Kept because it's a genuinely different scan, not because it's better.
- **Thumbnails always come from Scryfall**, even on the Gatherer tab: Gatherer's handler serves one full-size image per request, far too heavy for a grid.
- Gatherer picks are queued as a **reference**, not a direct URL, so `scryfall.fetch` handles them and converts Gatherer's webp to PNG. Do not shortcut that into a plain download.
- Printings whose `image_status` is `placeholder`/`missing` are labelled "no real scan" rather than hidden — in a manual picker the user can see the thumbnail and judge.

## Import routes (v2.17.0)
- **Gatherer decklist import** resolves through Scryfall as usual (set + collector number) and then queues a *reference*, not a download — `scryfall.fetch` pulls the Gatherer image and converts its webp. Cards with no `multiverse_ids` cannot come from Gatherer and are reported.
- **MPC Autofill order XML** (`<order><fronts><card><id><slots><name>`): `id` is a Google Drive file id, the same identifier the search returns, so the existing download path is unchanged. Quantity is the *length* of the comma-separated `slots` list. `<slot>` singular is accepted too — some generators write it that way. The point of importing the file rather than re-searching is that it names the exact art the user already chose.
- Both are tagged with their `src` (`gatherer`, `mpc`) so the bleed trim and border rules apply correctly — MPC art does carry a bleed, Gatherer art does not.

## Help dialog (v2.17.0)
The FAQ is written from questions people actually asked after the public release, not from what seemed likely. When a support answer gets given twice, it belongs there.

## Tokens, paper sizes, bleed modes (v2.17.0)
Taken from a comparison against Proxy-PDF-Maker, fabricard.net and silhouette-card-maker. Tokens appeared in two of the three independently, which is what promoted it.
- **Tokens come from Scryfall's `all_parts`**, filtered to `component == "token"` and fetched with one bulk `/collection` call (identifiers accept `id`). Never guess a token from the oracle text. A token failure never fails the import — they are a bonus.
- **Deduped by what makes a token different, not by id and not by name.** By id you get three Goblins from three goblin-makers, because each card points at the Goblin printed in its own set. By name alone you lose real tokens: "Elemental" has 94 printings but **26 genuinely distinct** tokens (3/1, 5/5, */*, 2/2 …). The key is `(name, type_line, power, toughness, oracle_text)`, keeping the newest printing — same best-scan reasoning as the card path.
- **A bigger page needs a bigger grid or it buys nothing.** Adding A3 while the grids stayed at 3×3 would still print 9 cards on it. A3 and Tabloid hold 4×4 = 16; Legal does not hold 4 rows because 352 mm + 2×`MIN_BOTTOM` exceeds its 356 mm.
- **A5 holds no 63×88 grid.** The existing "Card block too large" guard catches it, so it is offered for the mini card size rather than hidden.
- **Bleed needs three states, not two.** Off only covers "wrongly detected"; "Assume bleed" covers an image whose proportions hide its bleed. `trim_bleed` still accepts `True`/`False` so nothing else had to change.
- Watch `and` with mode strings: `trim and _may_have_bleed(item)` collapses every mode to `True`, which would trim on "Assume none". Use a conditional.

## MPC bleed trim is source-gated (v2.15.0)
The trim decides by aspect ratio, and **TCGdex's 600×825 Pokémon images land at 0.7273 — inside the 0.725-0.745 MPC window** — so every Pokémon card was cropped 4.4% a side, cutting its border off. Reported on Charizard (Base Set 4) and reproduced exactly.
- Scryfall (0.7163) and Gatherer (0.7162) sit outside the window, which is why the heuristic survived this long unnoticed.
- The trim now only runs for sources that **could** carry a bleed: `mpc` and local `file`. Local files keep the heuristic — someone can hand-feed an MPC download and there is nothing else to go on.
- **Any new source must be checked against that ratio window** before being added. A catalogue whose images are not exactly the card's proportions will trip it.

## Registration square must match SCM's stroke (v2.17.0)
The 3-mark square was a plain filled 5×5 mm rect. silhouette-card-maker draws it as a `Rectangle` with `edgecolor='black', linewidth=thickness_pt`, and a stroke is centred on the path — so **their square reaches 5 + thickness across (6 mm at the 1 mm default)** and ours came out a millimetre smaller. Reported from Reddit as "the registration marks are smaller than those generated by SCM". Ours now grows by half the thickness on every side, matching both the size and the outer edge position.
- Read `page_manager.py`, not the prose: two summaries of their docs misled this analysis. One claimed the square sits top-right (it is top-left, confirmed by a comment at `utilities.py:825`); another claimed 1.25 mm card gaps (that constant is `MINIMUM_BLEED = 15` px of bleed *on the card*, not spacing). The arm geometry does match ours — `length` reach from the corner in both.
- SCM defines `MIN_REG_INSET_MM = 10.0` but **never enforces it** — line 65 applies only the maximum. That is how its borderless layouts ship a 3.5 mm inset.
- **Card positions differ for a different reason**: SCM's Letter default is 4×2 landscape with an 8.04 mm mark, ours defaults to 3×3 portrait at 8.89 mm, and SCM *computes* its grid around the mark exclusion zone where we centre a fixed grid and blank colliding slots. Comparing the two PDFs at their respective defaults compares two different layouts.

## Registration mark inset vs card slots (v2.16.0)
What blocks a card slot is a **corner mark landing on a corner card** — the marks are corner brackets, they do not span the page. An earlier note here modelled it as `rows × 88 mm + 2 × (inset + length)` against the page height and concluded Letter 3×3 was geometrically impossible. **That model was wrong** and the conclusion with it.
- The real lever is the **inset**, and our own floor was the problem: `REG_INSET_MIN_MM` was 10 mm (Studio's documented minimum) and `_reg_geometry` clamps to it, so the UI could not go lower even when asked. Measured with the clamp lifted, at length 8.89: **Letter 4×2 goes 6 → 8 usable at 9.5 mm** (half a millimetre!), **A4 3×3 goes 7 → 9 at 6 mm**, Letter 3×3 needs about 2 mm.
- silhouette-card-maker — the project this geometry came from — ships **3.5 mm** for its borderless layouts, so Studio's "minimum" is a recommendation, not a hard limit. The floor is now 3.5 mm.
- **3.5 mm and no lower**: most inkjets cannot print within ~3 mm of the paper edge (the same reason `MIN_BOTTOM` exists), so a mark below that is simply clipped off.
- **The default stays 10 mm.** Lowering it is a lever the user reaches for, not a silent change to everyone's output.
- The preview hint calls `best_inset()`, which returns the **largest** inset that still keeps every slot — the gentlest move that works, since a mark further from the edge is the safer one.
- Not verified on hardware: neither the author nor this analysis has a cutter. SCM shipping 3.5 mm in production is the evidence.

## Pokémon source: TCGdex, not pokemontcg.io (v2.15.0)
Both were measured before choosing. Resolution did **not** decide it — every Pokémon catalogue tops out at `600×825` ("high"), confirmed identical on pokemontcg.io and TCGdex and unchanged between a 1999 and a 2020 set. That is an ecosystem ceiling, not a vendor limit.
- **No API key.** pokemontcg.io meters unauthenticated use (1000/day) and its terms allow one key per person — unworkable in a binary handed to strangers, where a shipped key is extractable and shared by everyone. TCGdex asks for nothing.
- **pokemontcg.io has been absorbed into Scrydex**, a commercial product. A free app should not depend on that.
- **6 languages with real images** (en/fr/de/es/it/pt), so the card-language picker drives it. Japanese returns nothing for latin-script queries and falls back to English.
- `low.webp` thumbnails are ~16 KB against pokemontcg.io's 161 KB small PNG.
- Set names come from one cached `/sets` call (218 sets, 34 KB); a card's brief record carries no set, and per-card lookups would be one request per tile.
- Records without an `image` are dropped — 14 of 125 in one search would have been empty tiles.
- **API TCG** (apitcg.com) covers One Piece / Digimon / Dragon Ball but **requires a key for every call**, so it is blocked for the same reason. Recorded so it is not researched again from scratch.

## Guides vs registration marks (v2.13.0)
- **"Guides off" means every guide**, corner crosses *and* margin ticks. The ticks used to ignore the setting entirely.
- **Nothing may intersect a registration mark's keep-clear box.** `_reg_geometry` already returned those boxes for card placement; `_draw_marks` now takes them too. Measured before the fix: A4 at the 10 mm default put 5-6 ticks inside one. Letter at the same inset was clean, which is why it went unnoticed.
- **Registration geometry follows Silhouette Studio's published figures**, cross-checked against the settings panel Proxxied exposes (in inches): inset `0.394 in = 10.008 mm` (minimum), length `0.350 in = 8.890 mm` (default), thickness `0.039 in = 0.991 mm` (maximum).
- Our `REG_INSET_MIN_MM` (10.0) and `REG_THICK_MAX_MM` (1.0) already matched those, which is what confirms the constants came from the same spec. **The length did not**: it defaulted to 5 mm — our own minimum — where Studio expects 8.89. Marks came out visibly shorter than a Studio-made template's, and that is the size mismatch, not the inset.
- **15.875 mm (0.625 in) is not a Studio figure.** An unverified code comment claimed it was Studio's default; it appears nowhere in Studio's numbers and Proxxied ships 10 mm. Briefly shipped as the default in v2.13.0 and reverted. Do not reintroduce it without a primary source.
- The 8.89 mm length costs slots where longer marks reach further onto the grid: A4 3×3 goes 9 usable → 7, Letter 4×2 8 → 6, Letter 7-card 7 → 6. A4 4×2 and A4 7-card keep every slot. Correctness wins here — marks the cutter cannot register are worth nothing, and anyone not using a cutter turns marks off entirely.

## Logging (v2.13.0)
One rotating file at `ROOT/cardwright.log`, no console handler (the build is windowed, there is nothing to write to). Added after a public bug report — "it doesn't fetch cards" — was unactionable because the only error surface was a truncated queue row.
- **Hook worker threads, not just `sys.excepthook`.** Downloads and upscaling run in threads; without `threading.excepthook` those crashes were invisible.
- Log the *context* with the traceback (what ref, which source, which model), because the reporter cannot be asked to reproduce on demand.
- **Never let logging stop the app**: a read-only install directory degrades to no logging rather than raising at startup.
- Keep it small (512 KB × 3). This is meant to be attached to a bug report, not archived.

## Border deepening: two algorithms (v2.13.0)
`Off` / `Contrast edges` / `Auto-detect`, defaulting to **Contrast edges**.
- **Auto-detect** (the original) measures how deep the uniform dark frame runs, then snaps it to black. Its weakness is the measurement: artwork that reaches the cut edge is what it can misjudge.
- **Contrast edges** detects nothing. The band is a fixed fraction of the card's shorter side (`CONTRAST_EDGE_WIDTH`, 8%), so there is no judgement to get wrong. Reimplemented in numpy from the approach Proxxied uses (MIT per its README, `acoreyj/proxies-at-home`); their code is GLSL, ours is not a copy.
- Three things keep it off the artwork: **quadratic falloff** to the inner edge of the band (no seam), **tone weighting** so only pixels below `CONTRAST_TONE_KNEE` (140/255) are pushed, and a **contrast curve** `(v-0.5)*contrast + 0.5 + brightness` rather than a binary snap.
- This does not overturn the "binary, not proportional" decision below — that one is about the auto-detect path, which still snaps. Contrast edges avoids mottling by the falloff instead.
- **Border treatment is per source** (`BORDER_SOURCES`, checkboxes in Export → Image). MPC art already carries a true black edge and card backs are usually correct, so both are **off by default** — running the effect there is risk with no upside.
- Resolution order for a card's mode, all in `_mode_for()`: an explicit per-card override (left-click in the preview) beats the source rule, which beats the global switch. The preview and the export both call it, so what you see is what prints.
- Back images go through the same flatten path as fronts, so their paths are mapped to the `back` source or the checkbox would control nothing.
- **Renaming a mode breaks saved settings.** "On (auto-detect)" became "Auto-detect"; without `config.border_mode()` mapping the old label, the picker falls back to "Off" and silently stops treating borders for every existing user. Any future rename needs the same migration.

## Small sources: normalize before the AI, never a second pass (v2.15.0)
A source too small for one x4 pass to reach the card is resized up to exactly `target/scale` **before** the pass, so the AI lands on the card instead of leaving a plain stretch behind it. The interpolation happens before the reconstruction rather than after, and that is the whole difference.
- Measured on a 600×825 Pokémon scan taken to 2976×4160, sharpness by Laplacian variance: **current x4-then-stretch 54 · pre-scale-then-x4 84 · two x4 passes then downsample 331**. Halving the AI factor (the intuitive fix) scores **25** — worse than doing nothing, because less AI means *more* plain stretch, and the plain stretch is what softens.
- **The double pass is deliberately not implemented.** 331 is by far the sharpest, but it costs **15.3 s per card against 2.0 s** and a **125 MB intermediate**; at `PARALLEL_JOBS = 3` that is ~375 MB concurrent and ~15 min for a 60-card deck. Staying light is the reason people move to this app, so the quality is not worth the risk. Pre-scaling gets +56% for +0.5 s and no extra memory.
- Never fires for MTG: Scryfall's 745 px × 4 = 2980 already clears 2976. It exists for Gatherer (646) and the Pokémon catalogues (600).
- `2976 / 4 = 744` is exactly Scryfall's native width, which is the size the whole pipeline was built around.

## Footer options layout
The options panel keeps each row in its **own frame**. Tk's grid shares column widths across rows, so a wide label in one row silently widens the row above it: adding the Card language row directly to the shared grid pushed the panel from 903 px to 1027 against a 900 px minimum window — reintroducing exactly the clipping v2.12.0 fixed. Measure `winfo_reqwidth()` of the options frame after touching this area; it should stay under 900. Long help text goes on its own row with `wraplength` rebound on `<Configure>`, never inline beside controls.

## Licensing
**Source-available** (not MIT): code visible, redistribution/selling/rebranding forbidden.

## Printing / calibration
- User's printer (Epson ET-2800, 300gsm cold-matte laminated): **color profile 9, shadow lift Medium (+14)**, sharpening Off, shift-down per paper.
- Shadow lift: surgical curve only below level 75 (never touches midtones).
- Deepen border: **binary** snap to black (not proportional) to avoid mottling; per-line detection with chroma guard (neutral frame chroma ≤14) and **per-side coverage ≥88%** (rejects art sides). Manual per-card override in preview (left-click cycles auto/off/on) + Amount/Manual-width sliders.
- MPC bleed: proportional crop (0.733 vs 0.716), "Trim MPC bleed" toggle ON by default.

## Data sources
- Gatherer link → ALWAYS the Gatherer image (Scryfall only provides multiverse id + metadata).
- Pillow `MAX_IMAGE_PIXELS` is disabled in `config.py` (set to None). MPC/Google-Drive art can top ~190M px, above Pillow's ~178M "decompression bomb" guard, which otherwise errored the card before it reached export. Sources are user-chosen and trusted, so the guard is off process-wide.
- `upscale()` skips the Real-ESRGAN step when the normalized (bleed-trimmed) source is already ≥ 2976×4160, and just fits-to-card + stamps DPI. x4 on an already-card-sized image only bloats it ~16x (a card-sized input became 11912×16620), slowing the preview and PDFs. This runs even when "Fit to card" is off, so high-res sources never balloon.

## Duplex / cut guides / corners (v2.7.0, ideas from Proxy-PDF-Maker)
- Backside rotation rotates the back page about the PAGE centre (not per-card), matching how a printer's duplex angular drift pivots; cut marks are drawn after `restoreState` so they stay on the grid. Range clamped ±5°. Dial it with the duplex alignment test rather than guessing.
- `build_duplex_test` is the calibration tool for offset+rotation: page 1 = front grid, page 2 = back grid column-mirrored + offset + rotation (exactly like `build_pdf`), so holding the print to the light shows the real misregistration.
- Rounded corners use transparency + reportlab `mask='auto'` (forces PNG so alpha survives), so corners show paper/bleed. Not baked onto black. Radius is mm → px via card width (63 mm).

## Microtext vs border deepening (v2.12.1)
- `BORDER_TONE_MAX` went 100 → **58**. The bottom band carries the copyright/collector line as WHITE microtext on black, and its anti-aliased edges ramp through ~60-160. The binary snap at 100 crushed those to pure black, so in print the strokes thickened and the counters of 'o', 'a', 'e' closed up. Measured across 5 cards: only **45-62% of the anti-aliasing survived at 100, vs 100% at 58**, while the frame still snaps to solid black (99.3-100% of the top edge). A washed scan border sits near 37 after the shadow lift, so 58 keeps the original purpose intact.
- Diagnosis note for the future: if a user reports "black looks thicker" on tiny text, compare the exported PDF with the border option Off vs On **on screen at 800%** before touching the printer driver — it isolates software from dot gain without wasting paper.

## Visual design system (v2.12.0)
- All colour, spacing, radius and type live in **`theme.py`**. `gui.py` keeps its historical names (GOLD, PANEL, ROW…) as aliases onto those tokens, so the whole app restyled without touching every widget call.
- Direction: **neutral pro tool** (Linear/Figma feel) — a low-chroma graphite ramp for every surface, with **one** warm accent (`#E0A33E`). The accent is reserved for the primary action, the active tab/filter and progress; headings and section labels use the text ramp. Previously gold was used for headings *and* buttons, which flattened the hierarchy.
- Every foreground/background pair is contrast-checked: text 15.7:1, secondary 8.2:1, muted 5.3:1, accent 7.9:1, on-accent 8.4:1. `BORDER` is decorative; `BORDER_STRONG` is for input outlines and clears the 3:1 non-text threshold.
- Fonts: Segoe UI Variable Text when present (Win 11), falling back to Segoe UI. Resolved in `App.__init__` because `tkfont.families()` needs a live Tk root. Georgia and the WUBRG mana dots are gone — they read as themed rather than professional.
- **Export dialog is tabbed** (Layout / Image / Backs / Cutting / Tests) instead of ~30 controls in one scrolling column; each tab now fits without scrolling. Implementation trick: the row helpers close over a `left` variable that `tab()` rebinds, so switching tabs needed no changes to the ~30 existing control definitions. Presets sit above the tabs since they apply across all of them.

## Multi-TCG sources (v2.11.0)
- One catalogue backend interface: a module exposing `search(query)` → list of dicts with `name / source / dpi / thumb / download / ext / identifier`, plus `download(card, target)` and `fetch_thumb(url)`. `mpcfill.py` and `ygoprodeck.py` both implement it, and `CardSearchDialog(backend=...)` renders either. Add a game by writing one module.
- YGOPRODeck rules shape the client: ≤20 req/s (we throttle to ~8) and *"do not continually hotlink images — download and re-host"*. Full images already land in the user's output folder; search thumbnails are cached under `TEMP_FOLDER/ygo_thumbs` so a repeated search never re-hits their CDN.
- **Card size must be set before upscaling, not just before printing.** `fit_to_card` force-resizes, so a Yu-Gi-Oh card (59×86, aspect 0.686) squeezed into MTG's 2976×4160 (0.716) comes out stretched. Hence the selector now sits in the main window too, sharing `settings["card_size"]` with Export, and queueing a Yu-Gi-Oh card flips it automatically the first time.

## Non-grid layouts (v2.10.0)
- Card slots come from `print_sheet.layout_positions(layout, ...)` which returns explicit (x, y) origins in placement order, not from `index % cols` maths. It is unit-agnostic, so the preview calls it in mm and `build_pdf` in points — one source of truth for both.
- Duplex mirroring uses `mirror_x(x, ox, block_w, card_w)` (reflect across the block centre) instead of column-index flipping. Equivalent for grids, and the only thing that works for non-grid layouts.
- **7-card Silhouette** = 4×2 grid, left column holding one vertically centred card + a 3×2 block. Purpose is clearance around the marks a Cameo relies on: lower-left mark clearance goes ~5 mm → ~49 mm vs 4×2. Copied the *arrangement* (a geometric fact) from ProxySheet's SevenCard template; that repo is **GPL-3.0**, so no code was taken — ours is written from our own math.

## Registration marks & card sizes (v2.9.0)
- Registration-mark geometry is a **hardware spec** (what the Silhouette/Cricut optical sensor looks for), taken from the MIT-licensed `Alan-Cha/silhouette-card-maker` and reimplemented in reportlab: 5×5 mm filled square top-left (3-mark) or an L there too (4-mark, CAMEO 5a); L brackets at the other corners; arms 5–20 mm, thickness 0.5–1 mm, inset ≥10 mm (Studio default 15.875 mm = 0.625 in), 1.5 mm keep-clear padding.
- **Defaults are the spec minimums** (inset 10 mm, arms 5 mm) rather than Silhouette Studio's own 15.875/20: the Studio footprint eats 3 card slots on a 3×3 sheet, while 10/5 keeps every card and is still inside the readable range. Users can raise both if a machine fails to detect. Measured: A4 3×3 9/9, A4 4×2 8/8, Letter 4×2 8/8 — **Letter 3×3 is impossible** (only 7.7 mm of top/bottom margin vs the 10 mm minimum inset), so it warns and skips 3 slots.
- **Registration marks disable shift-down.** `shift_down_mm` compensates a printer that feeds heavy stock late, but a cutter locates the *physical* marks and cuts relative to them, so it already self-compensates. Shifting only the cards would break the card↔mark relationship and (with the user's 15 mm shift) push the bottom row under the marks. So `build_pdf` and the preview both pass 0 for shift when `reg_marks` is on, and the hint says so.
- **When marks do collide** (e.g. Letter 3×3), `_reg_blocked_slots` finds which slots a mark's clear box overlaps and leaves them EMPTY; cards flow into the rest. `build_pdf` and the preview share the same `usable[k]` mapping, so what you see is what prints. A live hint in the dialog reports usable vs total slots.
- Card size is one persisted setting (`settings["card_size"]`) used by BOTH fit-to-card upscaling and the PDF layout, so masters and print stay consistent. Pokémon needed no work (63×88, same as MTG). `card_size_px` special-cases the MTG default to keep the legacy 2976×4160 (88 mm at 1200 dpi would round to 4157).

## Export preview performance & presets (v2.7.0)
- The preview canvas renders **lazily**: `_render_visible` paints only sheets whose rows intersect the viewport (+one sheet of look-ahead), caches each as a PhotoImage, and hooks `yscrollcommand` so scrolling paints new sheets. Treated-border thumbnails (`_treated_thumb`) are built on demand per visible card, not for the whole deck on every slider move. This is what makes 100+ card decks usable.
- Gotcha (fixed): `render_sheet` is a closure whose layout locals (cw, ch, left, top, X…) are read at *paint* time, which happens after `_draw_preview` returns. Never reuse those names later in `_draw_preview` — a stray `cw = canvas.winfo_width()` clobbered the card-cell width and broke the corner mask. Keep the tail's own locals distinctly named.
- Export presets: `_collect_settings()` / `_apply_settings()` are the single read/write of every control; `_persist` and the named presets (`settings["export_presets"]`) both go through them. Sliders register a setter in `self._slider_setters` so a preset can update both value and label.

## Export preview
- The preview is an editable workspace, not a static image: a scrollable canvas stacks every sheet; the on-screen order IS the PDF order. `self._order` (list of front paths) is the source of truth; drag-and-drop reorders it, `self._back_of` keeps DFC backs paired. Built on a raw `tk.Canvas` (not a CTkLabel) so it can scroll, overlay the loupe, and show a drag ghost.

## Moxfield deck import (v2.16.0)
Moxfield URLs import directly, via `api2.moxfield.com/v3/decks/all/{id}` — the same unauthenticated endpoint their web client calls. A deck comes back with set and collector number per card, which is exactly `resolve_decklist`'s input.
- **The history matters and is not hidden**: Moxfield's support was asked for API access and declined, citing WotC concerns, and this project recorded "do not scrape". Retested July 2026, the endpoint answers 200 for search and for a real deck. The author weighed that and **deliberately reversed the decision**, knowing it is an internal API after a refusal.
- Because that access is theirs to withdraw at will, **every failure path names the fallback**: 401/403/429, a network error, unreadable JSON and a non-200 all tell the user to paste a Moxfield Export instead, which has always worked. If they do close it off, the app degrades to that rather than breaking.
- The maybeboard is excluded (cards the author did *not* put in the deck); commanders, companions, signature spells and the oddball boards are included.

## Do NOT retry (known dead ends)
- **Moxfield API**: their support declined an official API request (WotC concerns). **Do not re-request.** Deck import was nevertheless implemented in July 2026 against the unauthenticated `api2.moxfield.com` endpoint their own web client uses — see "Moxfield deck import" below. Reversing that is the author's call, already taken; do not quietly undo it, and do not go asking them again.
- **Integrating sales into the app / mentioning sales**: forbidden by the user.
- **Argentine voseo**: user is Chilean, use neutral Spanish/tuteo.
- **START/PowerShell/explorer to relaunch** the exe after update: fails on the user's PC; use direct exec (cmd child).
- **`timeout` in a .bat without console**: fails; use `ping` for pauses, absolute System32 paths.
- **Proportional weight in deepen border**: causes mottling; use binary snap.
- **Whole-card border detection**: rejects SPG (art on 3 sides + bottom band); use per-side / per-line.
- **mean/std weighting in detection**: outliers break it; use percentiles.
