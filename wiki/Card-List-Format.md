A card list is a batch of cards named by image URL, in one `.json` file. Load it
with **Import list… > Card list…**.

It exists because every other import is Magic-only: a decklist resolves through
Scryfall, and an MPC order carries Google Drive ids. A card list works for any
game, and for games Cardwright has no catalogue for, because it does not care
where an image URL came from.

## Example

```json
{
  "format": "cardwright-list",
  "version": 1,
  "name": "Order 57",
  "cards": [
    {
      "name": "Dark Magician",
      "quantity": 3,
      "image": "https://example.com/cards/46986416.jpg",
      "back": "https://example.com/backs/my-back.png",
      "game": "ygo",
      "note": "Premium 300g"
    },
    {
      "name": "Jinx - Rebel",
      "image": "https://example.com/cards/jinx-rebel.png",
      "game": "riftbound"
    }
  ]
}
```

## Fields

Only **`name`** and **`image`** are required.

| Field | Required | Meaning |
| --- | --- | --- |
| `name` | yes | What the card is called. Shown in the queue. |
| `image` | yes | An `http://` or `https://` URL to the card's front. |
| `quantity` | no | How many copies. Defaults to 1, capped at 999. |
| `back` | no | URL of this card's own reverse. Prints behind it instead of your generic back, the same way a double-faced card's second face does. |
| `game` | no | Which game the card belongs to. Picks the card back and the card size. |
| `note` | no | Free text shown on the card in the queue. Meant for the paper or finish, the thing the person at the printer needs. |

At the top level, `format` should be `"cardwright-list"` if present; anything
else is refused, so a file meant for some other tool is not half-imported.
`version` and `name` are informational.

### `game` values

| Value | Game |
| --- | --- |
| `scryfall`, `mtg`, `magic` | Magic |
| `gatherer`, `mpc` | Magic, from those sources |
| `pokemon` | Pokémon |
| `ygo`, `yugioh`, `yu-gi-oh` | Yu-Gi-Oh |
| `riftbound` | Riftbound |

An unknown `game` is ignored rather than refused: the image is still perfectly
good, and only the card back and size depended on knowing the game.

## How it behaves

- **One bad entry never throws away the file.** A sixty-card order with one
  broken row imports fifty-nine and tells you which one it dropped, and why.
- **The card size follows the batch.** A file of Yu-Gi-Oh cards switches the
  size to 59×86 mm, so they are not stretched into Magic's 63×88. It only ever
  moves off the default: a size you chose yourself is never overruled, and a
  file mixing games moves nothing, because there is no one right answer.
- **Two entries can name the same card with different art.** Each keeps its
  own image; they do not overwrite each other.
- **Only web URLs are followed.** A `file://` path or anything else is dropped,
  since the file comes from outside and should not be able to point the app at
  your disk.
