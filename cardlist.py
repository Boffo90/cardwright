"""
Card list files: a batch of cards named by image URL.

The gap this fills: every import path Cardwright has is Magic-only. A decklist
resolves through Scryfall, and an MPC order carries Drive ids - so a Pokemon,
Yu-Gi-Oh or Riftbound order has to be typed into the gallery card by card,
even when whoever sent it already knows exactly which art they want.

A card list says it directly. One JSON file, one entry per card, each naming
the image to print:

    {
      "format": "cardwright-list",
      "version": 1,
      "name": "Order 57",
      "cards": [
        {
          "name": "Dark Magician",
          "quantity": 3,
          "image": "https://.../46986416.jpg",
          "back": "https://.../my-back.png",
          "game": "ygo",
          "note": "Premium 300g"
        }
      ]
    }

Only `name` and `image` are required. `game` is any catalogue id from
`sources` (mtg is accepted as an alias for scryfall) and decides the card back
and the card size; `back` is that card's own reverse, the same thing a
double-faced card carries; `note` rides along in the queue label, which is
where a print shop's finish or paper ends up.

The entries come out in the shape `mpcfill.parse_order_xml` returns, so the
importer treats both the same way.
"""

import json

# The largest quantity worth believing. A hand-written file with a stray zero
# should not queue ten thousand downloads.
MAX_QTY = 999

# Everyday names for the catalogues, so a file does not have to know that
# Magic is called "scryfall" inside this app.
_GAME_ALIASES = {
    "mtg": "scryfall",
    "magic": "scryfall",
    "yugioh": "ygo",
    "yu-gi-oh": "ygo",
    "pokémon": "pokemon",
}

FORMAT = "cardwright-list"


class CardListError(Exception):
    pass


def _url(value) -> str:
    """An http(s) url, or "" for anything else.

    Deliberately narrow: this file comes from outside, and `download_to_temp`
    would happily follow whatever it is handed.
    """
    if not isinstance(value, str):
        return ""
    v = value.strip()
    return v if v.startswith("https://") or v.startswith("http://") else ""


def _qty(value) -> int:
    try:
        n = int(value)
    except (TypeError, ValueError):
        return 1
    return max(1, min(n, MAX_QTY))


def _game(value) -> str:
    """A catalogue id from `sources`, or "" when the file does not say.

    The valid ids are read from `sources` rather than listed here, so adding a
    catalogue does not leave a second list behind to drift. An unrecognised
    game is ignored rather than refused: the image url is still perfectly
    good, and only the card back and the card size depend on knowing which
    game it is.
    """
    if not isinstance(value, str):
        return ""
    import sources
    v = value.strip().lower()
    v = _GAME_ALIASES.get(v, v)
    return v if any(s.ID == v for s in sources.ALL) else ""


def parse_list(text: str) -> tuple[list[dict], list[str]]:
    """
    Parse a card list into (cards, problems).

    Each card: {name, qty, download, game, note, source, dpi, size, thumb,
    ext, identifier}, plus {back_download, back_name} when it has its own
    reverse - the same keys an MPC order produces.

    Problems are per-card and never fatal: one bad entry in a sixty-card order
    should not throw away the other fifty-nine, it should say which one was
    dropped.
    """
    try:
        data = json.loads(text.strip())
    except ValueError as e:
        raise CardListError(f"That does not parse as JSON: {e}") from e

    if not isinstance(data, dict):
        raise CardListError("Expected a card list object, got a "
                            f"{type(data).__name__}")

    declared = data.get("format")
    if declared and declared != FORMAT:
        raise CardListError(
            f"That file says it is '{declared}', not a {FORMAT} file")

    rows = data.get("cards")
    if not isinstance(rows, list):
        raise CardListError("No 'cards' list in that file")

    cards, problems = [], []
    for i, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            problems.append(f"entry {i} - not a card")
            continue

        name = (row.get("name") or "").strip() if isinstance(
            row.get("name"), str) else ""
        image = _url(row.get("image"))
        if not name:
            problems.append(f"entry {i} - no name")
            continue
        if not image:
            problems.append(f"{name} - no usable image url")
            continue

        note = row.get("note")
        note = note.strip() if isinstance(note, str) else ""

        entry = {
            "name": name,
            "qty": _qty(row.get("quantity", 1)),
            # The label is what the queue shows. The note is the reason this
            # format carries one: which paper a card is printed on does not
            # belong to the card, but the person at the printer needs it.
            "source": note or "card list",
            "game": _game(row.get("game")),
            "note": note,
            "dpi": 0,
            "size": 0,
            "thumb": "",
            "download": image,
            "ext": "png",
            # Nothing in the file is guaranteed unique, and two entries can
            # name the same card with different art. The position is, and the
            # importer folds it into the download filename so copies of one
            # name do not overwrite each other.
            "identifier": f"{i}",
        }

        back = _url(row.get("back"))
        if back:
            entry["back_download"] = back
            entry["back_identifier"] = f"{i}-back"
            entry["back_name"] = f"{name} back"
        cards.append(entry)

    if not cards and not problems:
        problems.append("The 'cards' list is empty")
    return cards, problems
