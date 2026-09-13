## The gallery

Type a card name and a gallery opens with every printing of it, thumbnails and
all, so you see what you are about to upscale before committing to it. The row
at the top switches source without leaving the gallery:

| Source | Game | Notes |
| --- | --- | --- |
| **Scryfall** | Magic | 745×1040, the best Magic source. |
| **Gatherer** | Magic | Wizards' own. See [Gatherer](#gatherer) below. |
| **MPC Autofill** | Magic, mostly | Community art. Bleed edges are trimmed automatically. |
| **Pokémon** | Pokémon | From TCGdex. |
| **Yu-Gi-Oh** | Yu-Gi-Oh | From YGOPRODeck. Picking one switches the card size to 59×86 mm. |
| **Riftbound** | Riftbound | From Riftcodex; the images are Riot's own. |

**Click a card's picture** to see it large. Click more and they line up
side by side, up to three, so you can compare versions of the same art before
choosing; a fourth makes the oldest give way. Each has its own **Add**. The
enlarged image is what you would actually get from that source, not a
stand-in.

**Best scan**, on by default, picks the sharpest printing of a name you type,
keeping the same artwork. It never swaps the art for a different one, and it
never overrides a link or a decklist line, since those already name a printing
you chose.

### Why some cards come out sharper than others

The AI reconstructs detail, but it starts from what the source gives it:

- Magic from Scryfall, Riftbound, and new-style Gatherer links: **744 to 745 px
  wide**. Plenty.
- Pokémon: **600×825** in every catalogue. That is a limit of the source data,
  not of the app; no Pokémon API has anything better. Small sources are resized
  to the right size *before* the AI pass, which recovers a good part of the
  difference.

## One exact printing, by name

Type the card the way a decklist writes it: the name, the set code in brackets,
then the collector number.

```
Sol Ring (SLD) 2560
```

That fetches exactly that printing. A bare name does not choose one, so the app
picks for you, which is usually not the art you had in mind. The line is
forgiving: a quantity in front works (`3x Sol Ring (SLD) 2560`), the set code is
case-insensitive, and a trailing `[matte]` or `*F*` is ignored.

## Decklists

**Import list…** takes that same format, one card per line, which is what
Moxfield, Archidekt and most deckbuilders export. Their deck URLs work too.

- **Images from: Scryfall or Gatherer.** Gatherer has no entry for Secret
  Lairs, promos, or any foil printing, so those fall back to Scryfall and are
  listed, rather than dropped.
- **Also add the tokens these cards make.** Taken from Scryfall's own data, so
  it is exact rather than guessed.
- **MPC XML…** loads an MPC Autofill order file, to get exactly the art you
  picked there.
- **Card list…** loads a batch from any game. See
  [Card List Format](Card-List-Format).

## Links

Pasting a **Scryfall or Gatherer card link** goes straight to the queue. You
already chose the printing, so nothing second-guesses it.

### Gatherer

A Gatherer link always uses the Gatherer image, never a substitute, and **in the
language the link names**. That matters more than it sounds: Gatherer carries
printings Scryfall does not have. `TLA/es-es/315/fire-lord-zuko` exists in
Spanish on Gatherer and only in English on Scryfall.

New-style links, the ones shaped like `/TLA/es-es/315/...`, are also the better
image: 744×1039 PNG, the same as Scryfall. Old `multiverseid=` links get the
older 646×902 JPEG.

## Languages

**Card language** fetches printings in any of the languages Scryfall carries.
Not every card was printed in every language: promos, Secret Lairs and older
sets are often English-only. Those come back in English and are listed after
the import, so you know which ones. It is not a failure.

## Double-faced cards

A card with two physical faces, like a transforming card, fetches **both** and
keeps them paired, from Scryfall and from Gatherer alike. On the sheet, its own
back face prints behind it instead of your generic card back.

Split, flip and adventure cards also have two halves on Scryfall, but they are
one piece of cardboard, so they fetch one image. That is correct.

On Gatherer each face has its own page, numbered like `347a` and `347b`. Paste
either one and both come.

## Projects

**Project… > Save** keeps the queue itself: the cards, their quantities, the
printings you chose and any per-card model. Save after upscaling and it reopens
ready to export, without running the AI again. If a card's files are gone from
disk by then, it comes back queued rather than pretending to be finished.
