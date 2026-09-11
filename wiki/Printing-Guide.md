## The two rules

1. **Print at 100% scale.** Turn off "fit to page" and "shrink oversized
   pages". Anything else and the cards come out the wrong size.
2. **Turn off the printer's own colour correction.** Cardwright's calibration
   assumes it is getting the ink it asked for.

## Colour

Inkjets typically print darker and less saturated than a screen shows.

- **Color profile.** **Export > Tests > Calibration…** prints the same card
  through nine profiles, numbered. Compare them against a real card under
  normal light and pick the closest number.
- **Shadow lift.** Dark detail gets crushed on an inkjet, and worse under matte
  lamination. **Tests > Shadow test…** shows the levels side by side. It only
  touches the darkest tones; midtones and highlights are left alone.
- **Deepen black border.** Scans carry their black border at a dark grey, which
  prints as grey. **Contrast edges**, the default, pushes the dark pixels in a
  fixed band at the edge and detects nothing, so there is no judgement to get
  wrong on art that runs to the edge. **Auto-detect** measures the frame and
  snaps it to black: crisper on an ordinary scan, but it can misjudge full art.
  Right-click a card in the preview to override it for that card.
- **Sharpening** offsets the softening of ink spreading into paper.

All of this is applied when you export. Your upscaled cards are never changed.

## Paper and layout

| Page | 63×88 cards | Notes |
| --- | --- | --- |
| Letter, A4 | 9 in 3×3, or 8 in 4×2 landscape | The everyday choice. |
| Legal | 9 in 3×3 | |
| A3, Tabloid | up to 16 in 4×4 | The best choice for cutting machines. |
| 4x6 photo | 2 in 2×1 landscape | For photo labs. See below. |

If the grid you picked does not fit the page at your card size, the export says
so rather than overlapping cards.

## Output formats

**Image > Output format**: **PDF**, **PNG** or **JPEG**.

PDF is what a home printer wants. PNG and JPEG are for photo labs, which often
accept nothing else. A bitmap has no pages, so each sheet becomes its own
numbered file.

**Image DPI** sets the bitmap's resolution: 300, 600 or 1200. Most labs print
at about 300 natively. Ask yours what it accepts: sending more pixels than it
wants is harmless, sending fewer is not.

### 4x6 photo prints

In some countries two cards on a 4x6 photo print cost a fraction of nine on A4
or Letter. Set **Page size** to *4x6 photo*, **Card grid** to *2x1 landscape*,
and **Output format** to PNG or JPEG. At 300 DPI that is 1800×1200 pixels, with
the two cards exactly 63×88 mm each.

## Printers that waste an edge

Some feeds cannot print part of the page. A rear top loader can eat 20 mm or
more and leave roller marks. **Layout > Shift down** and **Shift right** move
the whole layout, and both take negative numbers, so it can go up, down, left
or right. Cut guides move with the cards, so what you cut to stays correct.

The line under the two fields says how far you can actually go on this page and
grid. If that is less than your printer wastes, no shift will fix it: the cards
do not fit clear of the dead zone. Use a smaller grid or a bigger page. Letter
3×3 leaves only 4.7 mm; 4×2 landscape leaves 17.

With registration marks on, the shift is ignored on purpose. The cutter finds
the marks wherever the paper actually fed, so it already compensates.

## "Insufficient memory" or an error page

A lossless 1200 DPI sheet is around 217 MB, and a home printer has to rasterise
the whole thing in its own RAM. Most do not have it.

Let the PC do it instead: in Adobe Reader, **Print > Advanced > Print as
Image**, and set that dialog's resolution to the highest your printer offers,
600 or 1200. It often defaults to 300, which throws away the resolution you came
for. Still failing? **Image > Quality: JPEG q97** is near-lossless at about a
third the size, and **Layout > File split: 1 page / PDF** means the printer only
ever holds one sheet.
