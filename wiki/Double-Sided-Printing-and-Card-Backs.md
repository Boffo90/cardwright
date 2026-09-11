## Card backs

Cardwright does not ship card backs. A Magic back belongs to Wizards and a
Pokémon one to Nintendo, and putting their artwork inside a download is not the
same as a website showing it. So you supply the image once, and it is used from
then on.

Drop a file named **`back.png`** (or `.jpg`) in the Cardwright folder and every
single-faced card uses it.

Mixing games on one sheet? Name them per game and each card takes the right one
automatically:

| File | Used for |
| --- | --- |
| `back-mtg.png` | Magic, from Scryfall, Gatherer or MPC |
| `back-pokemon.png` | Pokémon |
| `back-yugioh.png` | Yu-Gi-Oh |
| `back-riftbound.png` | Riftbound |

Anything without a matching file falls back to `back.png`, so add only the ones
you need. A card with its own second face, like a transforming card, always
prints that instead. To override everything for one run, use **File…** beside
*Back image* on the export dialog's **Backs** tab, or **MPC…** to pick one from
MPC Autofill.

## Printing double-sided

Set **Backs > Card backs** to *Duplex (DFC + back.png)* to print them. Each front sheet is followed by its
back sheet, laid out mirrored so the two land on each other when the paper
turns over.

**Flip on the long edge**, like turning the page of a book, left to right.
That is what the back sheet is laid out for. Flipping on the short edge puts
every back on the wrong card.

### Getting the two sides to line up

No printer puts the second side exactly where the first went. Correct for it
instead of guessing:

1. **Tests > Duplex align…** prints a two-sided alignment sheet.
2. Print it double-sided and hold it up to a light.
3. Where the back grid does not sit on the front grid, set **Back offset X/Y**
   in millimetres, and **Back rotation** if it is skewed rather than shifted.
4. Print it again until it lines up.

**Back bleed** draws each back slightly larger than the card, so whatever drift
is left does not show as white paper at the cut.

### Double-faced cards

A double-faced card's back is a real card face, with a frame and a text box
that have to match the front's exactly. That makes it far less forgiving than a
plain card back, which is symmetric and has nothing near its edge to compare.

Cardwright draws the back at exactly the same size as the front at every bleed
setting, and mirroring the back sheet lands it on the front to within 0.085 mm.
What is left is your printer, which is what the alignment sheet above is for.

### Printers with manual duplex

Many inkjets, like the Epson EcoTank L-series, have no automatic two-sided
printing: you turn the stack over and feed it back in by hand. Two things
follow:

- **You** decide which edge it flips on, not the driver. Flip on the long edge.
- Every sheet is re-fed, so the drift varies a little from sheet to sheet. The
  back offset corrects what repeats; it cannot correct what changes each time.

### If duplex will not line up at all

Print-and-play players often skip duplex for double-faced cards entirely:

1. Print the fronts on one sheet and the backs on another.
2. Glue them back to back, lining them up against a window or lightbox
   *before* cutting.
3. Cut both layers together.

You see any misalignment before you cut instead of discovering it after. The
back sheets Cardwright produces are already mirrored the right way for this,
so nothing needs changing.
