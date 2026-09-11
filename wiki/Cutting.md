Everything about separating the cards lives in the export dialog's **Cutting**
tab: cut guides for scissors or a guillotine first, registration marks for a
machine below.

## Cut guides

Short lines at every card corner showing where to cut, plus ticks in the
margin lined up with each edge.

- **Style.** *Cross* is a solid plus at each corner. *Corner* is gapped crop
  marks.
- **Cut guides** sets the colour: *White*, *Black*, *Gray*, or *None*. Colour matters as much as
  width: white vanishes on a light card and black on a dark border. If a guide
  disappears on some cards but not others, try **Gray**, which survives both.
- **Length** and **offset**, in millimetres. Offset is the gap between the
  card's corner and where the line starts.
- **Cut guides on backs too.** Worth turning off when printing double-sided.
  The back's guides never land exactly where the front's do, so a second set
  that disagrees with the one you are cutting to is worse than none. You cut by
  the front.

### Thickness

Thickness is in points, and a point is small. The field shows the millimetres
under it. Measured on a real sheet at 1200 DPI:

| Setting | On paper | Ink dots |
| --- | --- | --- |
| 0.25 pt | 0.09 mm | 4 |
| **0.40 pt** (default) | **0.15 mm** | **7** |
| 0.60 pt | 0.21 mm | 10 |
| 1.00 pt | 0.36 mm | 17 |

0.25 pt is the thinnest it goes. Below that the line is two or three ink dots
and an inkjet simply loses it. If you want no guides at all, set the colour to
*None* rather than making them too thin to see.

## Bleed

**Layout > Edge bleed** puts a band around each card and spaces them apart, so
the cut runs through the band. A cut that drifts a little then shows band, not
white paper or the neighbouring card.

**Bleed color** is *Black*, *White*, or **Extend art**, which grows the card's
own artwork outward instead of painting a flat frame. On a black-bordered card
that continues the frame; on full art it mirrors the edge, so the picture keeps
going under the cut.

**Corner radius** rounds the printed corners.

## Registration marks (Silhouette, Cricut)

For print-and-cut machines, which read printed marks to find where the sheet
is. **Cutting > Registration marks** turns them on.

- **3 marks** is the standard pattern. **4 marks** is for the CAMEO 5a.
- The geometry follows **Silhouette Studio's own published figures**: 0.394 in
  inset, 0.350 in (8.89 mm) length, 0.039 in thickness. A sheet then lands on a
  template built in Studio. If yours was built around other numbers, set these
  to match, and match the grid too.

### Marks cost card slots on small pages

The marks are corner brackets, so what blocks a slot is a mark landing on a
corner card. When one would, that slot is left empty and the card moves to the
next sheet. The hint under the preview names the exact **Mark inset** that
would keep them all.

| Page | Keeps every slot at the default marks |
| --- | --- |
| **A3, Tabloid** | every layout, including 4×4 (16 cards) |
| Legal | 3×3 (9) |
| A4 | 4×2 landscape (8) or the 7-card layout (7). 3×3 drops to 6. |
| Letter | none at the defaults. Lower the inset; the hint says how far. |

Lowering the inset frees slots: on A4 3×3, going from 10 mm to 6 mm takes you
from 6 cards back to 9. The floor is 3.5 mm, since most inkjets cannot print
closer to the edge than that and the mark would simply be clipped off.

### The 7-card layout

One card centred in the left column plus a 3×2 block. It clears both left
corners, where a Cameo's key marks sit, which is the whole reason it exists.

Guides and margin ticks never print inside a mark's clear area, since a stray
line beside a mark can throw the machine's scan off.
