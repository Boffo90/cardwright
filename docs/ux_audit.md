# Cardwright - Print-sheet UX audit (August 2026)

## Why this exists
The export dialog does everything the competition does and several things none of
them do, but it does not *feel* as good to use as Proxxied or proxy-print. That is
an interaction-design gap, not a feature gap, and the two are worth separating
before deciding whether the toolkit has to change. This records what the
references actually do, what we actually do, and which differences are worth
closing.

## What was read, and when
- **proxxied.com/app** - the live Proxy Builder, 2026-08-04. Full control
  inventory read off the running app, not the marketing page.
- **github.com/alex-taxiera/proxy-print** @ `trunk`, 2026-08-04 - `src/components/Preview/*`
  read directly. Stack: React + Chakra UI + `@dnd-kit`, image work in wasm.
- **Cardwright** - `ExportDialog`, `gui.py:1234`–`gui.py:2910`.

## What Cardwright's preview does today
Scrolls every sheet at once, drag-to-reorder with a ghost (`_start_drag_ghost`),
edge auto-scroll while dragging, hover loupe, Fronts/Backs toggle, per-card
right-click (duplicate / remove / delete file), left-click cycles the black-border
mode, live redraw on every setting change, registration-mark slot-collision
analysis that names the inset which fixes it.

## Gaps worth closing

### A - Direct manipulation of the sheet
1. ~~**No drop feedback.**~~ **Done in v2.17.10.** An insertion line follows the
   cursor and is drawn on the edge the card will land against. A slot is split
   down the middle: left half means before, right half means after. Dropping
   either side of the dragged card draws nothing, so a no-op reads as cancelled
   rather than as a move that failed.
2. ~~**Cannot drop into a specific slot.**~~ **Done in v2.17.10.** Every usable
   slot is a target, including the first empty one, which is where "put it at
   the end" lives.
3. ~~**Cannot drag to another sheet.**~~ **Done in v2.17.10.** Making every
   slot on every sheet a drop target closed half of it for free, since the
   preview already stacks all sheets in one canvas. The other half was the edge
   scroll: it moved one notch per motion event, so holding still did nothing
   and crossing a sheet took about ten deliberate wiggles inside a 24 px band.
   It runs on a timer now, accelerating with how deep into the band the cursor
   sits, so resting at the edge *is* the gesture. Measured: about 660 px of
   travel per second held, against a 560 px sheet.

   Worth noting we did not need proxy-print's Prev/Next drop zones. Those exist
   because it paginates one page at a time; scrolling a single stack is a
   different shape of problem and the same gesture covers it.
4. **No multi-select.** proxy-print carries a selection through the whole preview:
   click to select, and every context-menu action applies to the group, including
   dragging them together (`source.data.images` is a list).
5. **No per-slot disable.** Proxxied lets you turn individual slots off and has
   *Center Cards Across Disabled Gaps* for layouts like 3×3 minus the middle.

### B - Getting out of a mistake
6. ~~**No undo.**~~ **Done in v2.17.5.** Ctrl+Z / Ctrl+Y plus buttons that name
   what they would take back. Deleting a file clears the history rather than
   pretending to be undoable. What is still missing against Proxxied is the
   *visible* Action History list - the buttons show one step, not the trail.

### C - Changing a card without leaving the sheet
7. **Art cannot be changed from the preview.** Seeing the wrong printing means
   cancelling out to the main window and re-running the card. Proxxied has a
   global *Preferred Art Source* (Scryfall / MPC Autofill) plus Advanced Search;
   proxy-print puts *Set back…*, upscale, revert-to-original and bleed on the card
   itself. This is the most common reason to touch a sheet at all.
8. ~~**Quantity is one duplicate at a time.**~~ **Done in v2.17.10.** *Add 1*,
   *Add 3* and *Add copies…* per card, plus Ctrl+click for one. Copies land
   next to the original rather than at the end, and however many you ask for
   they go in as **one** undo step: four presses of Ctrl+Z to take back one
   action would read as broken. The context menu also says how many of that
   card are already on the sheet, which is the number you actually want before
   deciding.

   The file-per-copy model that blocked this went away in v2.17.4, so this
   turned out to be interaction work only, with no model change at all.

### D - Discoverability
9. **Left-click cycles a three-state border mode** (auto → off → on) with no
   indicator of which state a card is in and no visible affordance. It is
   documented only in the hint line under the canvas.
10. ~~**No keyboard shortcuts at all** in the dialog.~~ **Largely done.** Ctrl+Z
    and Ctrl+Y in v2.17.5; Ctrl+click to add a copy and Alt+click to remove in
    v2.17.10, both printed as accelerators in the context menu the way
    proxy-print does it, since the menu is the only place anyone will find
    them.
11. **One 3-line hint paragraph** carries every interaction the preview supports
    (`gui.py:1624`). Anything not in that sentence is undiscoverable.

### E - Session
12. **No save/load of the working session.** Proxxied names the project
    ("Untitled Project"). Already recorded in `todo.md`.

## Feature differences that are not UX
Noted so they are not confused with the above: Proxxied has sort/filter by mana
value and colour, page labels, an SVG cutting template (already on our list),
electronic-cutter presets that print the recommended numbers inline, ZIP export
and decklist round-tripping. Separate decisions, separate costs.

## Where Cardwright is ahead
Worth stating so the revamp does not trade it away: true 1200 DPI local AI
upscaling (both references upscale in-browser), 9 printer calibration profiles,
calibration / shadow / duplex test sheets, registration-mark collision analysis
that names the fixing inset rather than just warning, and a preview that scrolls
**every sheet at once** where both references paginate one page at a time.

## Priority
**Tier 1 - the "feels bad" core.** ~~Undo/redo~~ (v2.17.5) · ~~drop indicator +
droppable empty slots~~ (v2.17.10) · ~~drag between sheets~~ (v2.17.10) ·
~~quantity per card~~ (v2.17.10) · **change art from the preview** is all that
is left, and it is the expensive one: it needs the upscaling pipeline reachable
from `ExportDialog`.

**Tier 2.** Multi-select · keybinds printed in the context menu · a real border-mode
indicator · per-slot disable.

**Tier 3.** Save/load project · sort & filter.

## Can Tkinter carry this?
Item by item, honestly:

| Item | In Tkinter |
| --- | --- |
| Undo/redo | Yes - it is a model concern (`_order`, `_excluded`, `_back_of`, `_border_modes`); nothing to draw |
| Drop indicator | Yes - one canvas rectangle drawn at the target slot |
| Droppable empty slots | Yes - `usable` already holds every slot position; `_key_at` needs to return empty slots too |
| Drag between sheets | Yes - the edge auto-scroll already exists |
| Quantity per card | Yes, but needs the file-per-copy model replaced with a count |
| Change art from the preview | Yes, but cross-module: needs the upscaling pipeline reachable from `ExportDialog` (already flagged in `todo.md`) |
| Multi-select | Yes - a set of keys plus a selection outline |
| Keybinds / indicators | Yes |
| **Animated reflow, transitions, 60 fps drag** | **No** |

The only structural loss is animation, and none of the Tier 1/Tier 2 complaints
are about animation. **Recommendation: close Tier 1 and Tier 2 in CustomTkinter.**
Revisit PySide6 only if something on that list actually proves impossible - that
would be a decision made on evidence instead of on feel, and the backend
(`print_sheet.py`, `upscale.py`, the source modules) is untouched either way.

## One thing to fix first - done in v2.17.4
`_copy_of` wrote a real PNG per duplicate, and the queue's quantity wrote one
per copy, so a 4-of cost four identical files. Copies are now `_Card` instances
sharing one path: identity for the copy, path for the image. `_copy_of` is gone.
Quantity is a number now, so Tier 1's per-card quantity control has nothing left
in its way.

One consequence to keep in mind: border treatment is per **image**, not per
copy, because `build_pdf`'s `border_modes` is keyed by path and always was.
