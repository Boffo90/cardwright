"""
Card image sources for the search gallery.

Each source matches the interface CardSearchDialog already expects from
mpcfill / ygoprodeck: search(query) -> [card dict], fetch_thumb(url) -> bytes,
plus an `ADD_KIND` marker telling the queue how a pick should be fetched:

    "card"      the dict carries a direct image URL, download it as-is
    "scryfall"  the dict carries a reference to resolve through scryfall.fetch

Scryfall and Gatherer are both built on the Scryfall API, because Gatherer has
no search of its own: Scryfall finds the printing, Gatherer serves the image.
That is the same split `scryfall._fetch_gatherer` already documents.
"""

import requests

import scryfall
from config import SCRYFALL_HEADERS, card_lang_code, load_settings


def _lang() -> str:
    return card_lang_code(load_settings().get("card_lang"))


def _face(card: dict) -> dict:
    """The dict holding a card's images (the front face, for double-faced)."""
    if card.get("image_uris"):
        return card
    for f in card.get("card_faces") or []:
        if f.get("image_uris"):
            return f
    return card


def _thumb_url(card: dict) -> str:
    uris = _face(card).get("image_uris") or {}
    return uris.get("small") or uris.get("normal") or ""


def _png_url(card: dict) -> str:
    uris = _face(card).get("image_uris") or {}
    return uris.get("png") or uris.get("large") or ""


def _printings(query: str):
    """
    Every printing of whatever `query` names, best scan first.

    The query is fuzzy-resolved first so a partial name still works, then
    expanded to the full print run. Ordering reuses the same ranking as the
    Best scan switch, so the recommended version leads the gallery.
    """
    card = scryfall._card_from_reference(query)
    lang = _lang()

    prints = scryfall._printings(card["name"], lang)
    if not prints and lang != "en":
        prints = scryfall._printings(card["name"], "en")
    if not prints:
        prints = [card]

    usable = [c for c in prints if _thumb_url(c)]
    if not usable:
        return []

    # Same order the Best scan pick uses: real scans first, newest first.
    usable.sort(key=lambda c: c.get("released_at") or "", reverse=True)
    usable.sort(
        key=lambda c: scryfall._IMAGE_STATUS_RANK.get(c.get("image_status"), 9))
    return usable


def _label(card: dict) -> tuple[str, str]:
    """(display name, subtitle) for a gallery tile."""
    name = card.get("printed_name") or card.get("name", "?")
    bits = [f"{(card.get('set') or '').upper()} #{card.get('collector_number', '?')}"]
    if card.get("lang") and card["lang"] != "en":
        bits.append(card["lang"].upper())
    status = card.get("image_status")
    if status == "lowres":
        bits.append("low-res scan")
    elif status in ("placeholder", "missing"):
        # Not the card at all - a stand-in. Say so, or it looks like a normal
        # option that simply came out blurry.
        bits.append("no real scan")
    if card.get("artist"):
        bits.append(card["artist"])
    return name, " · ".join(bits)


def _fetch_thumb(url: str) -> bytes | None:
    if not url:
        return None
    try:
        r = requests.get(url, headers=SCRYFALL_HEADERS, timeout=20)
        return r.content if r.status_code == 200 else None
    except requests.RequestException:
        return None


# --------------------------------------------------------------------------
# Scryfall
# --------------------------------------------------------------------------

class _Scryfall:
    ID = "scryfall"
    LABEL = "Scryfall"
    ADD_KIND = "card"
    EMPTY = "No printings found on Scryfall."
    PLACEHOLDER = "Card name (e.g. Lightning Bolt)"

    @staticmethod
    def search(query: str, limit: int = 60) -> list[dict]:
        out = []
        for c in _printings(query)[:limit]:
            name, sub = _label(c)
            out.append({
                "name": name,
                "source": sub,
                "dpi": 0,
                "thumb": _thumb_url(c),
                "download": _png_url(c),
                "ext": "png",
                "identifier": c.get("id", ""),
            })
        return [c for c in out if c["download"]]

    @staticmethod
    def fetch_thumb(url: str) -> bytes | None:
        return _fetch_thumb(url)


# --------------------------------------------------------------------------
# Gatherer
# --------------------------------------------------------------------------

class _Gatherer:
    ID = "gatherer"
    LABEL = "Gatherer"
    ADD_KIND = "scryfall"
    EMPTY = ("No Gatherer printings found. Gatherer only carries cards with a "
             "multiverse id, so promos and newer supplemental sets are often "
             "missing.")
    PLACEHOLDER = "Card name (e.g. Lightning Bolt)"
    # Measured across several cards, consistently: Gatherer serves 646x902 at
    # heavy compression while Scryfall serves 745x1040 at ~1 MB. Worth saying
    # out loud - it is roughly 15x less data to upscale from.
    NOTE = ("Gatherer images are 646×902 and heavily compressed (~60 KB vs "
            "Scryfall's ~1 MB) - a weaker source to upscale from.")

    @staticmethod
    def search(query: str, limit: int = 60) -> list[dict]:
        out = []
        for c in _printings(query):
            mids = c.get("multiverse_ids") or []
            if not mids:
                continue          # not on Gatherer at all
            name, sub = _label(c)
            # Thumbnails come from Scryfall even here: Gatherer's own handler
            # serves one full-size image per request, which is far too heavy
            # for a gallery. Only the pick pulls the Gatherer image.
            out.append({
                "name": name,
                "source": sub,
                "dpi": 0,
                "thumb": _thumb_url(c),
                "download": scryfall.GATHERER_IMAGE.format(mid=mids[0]),
                "ref": ("https://gatherer.wizards.com/Pages/Card/Details.aspx"
                        f"?multiverseid={mids[0]}"),
                "ext": "png",
                "identifier": str(mids[0]),
            })
            if len(out) >= limit:
                break
        return out

    @staticmethod
    def fetch_thumb(url: str) -> bytes | None:
        return _fetch_thumb(url)


# --------------------------------------------------------------------------
# MPC Autofill
# --------------------------------------------------------------------------

class _MPC:
    ID = "mpc"
    LABEL = "MPC Autofill"
    ADD_KIND = "card"
    EMPTY = "No matches on MPC Autofill."
    PLACEHOLDER = "Card name (e.g. Sol Ring)"

    @staticmethod
    def search(query: str, limit: int = 60) -> list[dict]:
        import mpcfill
        return mpcfill.search(query, limit)

    @staticmethod
    def fetch_thumb(url: str) -> bytes | None:
        import mpcfill
        return mpcfill.fetch_thumb(url)


# --------------------------------------------------------------------------
# Yu-Gi-Oh (YGOPRODeck)
# --------------------------------------------------------------------------

class _YGO:
    ID = "ygo"
    LABEL = "Yu-Gi-Oh"
    ADD_KIND = "card"
    EMPTY = "No matches on YGOPRODeck."
    PLACEHOLDER = "Card name (e.g. Dark Magician)"
    # A Yu-Gi-Oh card is 59×86 mm. Fit-to-card would stretch it into Magic's
    # 63×88, so picking one switches the size over.
    CARD_SIZE_HINT = "Yu-Gi-Oh"
    NOTE = "Card size switches to Yu-Gi-Oh when you add one."

    @staticmethod
    def search(query: str, limit: int = 60) -> list[dict]:
        import ygoprodeck
        return ygoprodeck.search(query, limit)

    @staticmethod
    def fetch_thumb(url: str) -> bytes | None:
        import ygoprodeck
        return ygoprodeck.fetch_thumb(url)


# --------------------------------------------------------------------------
# Pokemon (TCGdex)
# --------------------------------------------------------------------------

class _Pokemon:
    ID = "pokemon"
    LABEL = "Pokémon"
    ADD_KIND = "card"
    EMPTY = "No matches on TCGdex."
    PLACEHOLDER = "Card name (e.g. Charizard)"
    # No CARD_SIZE_HINT: a Pokemon card is 63x88 mm, the same as Magic, so the
    # default card size is already right.
    #
    # Worth stating plainly - 600x825 is the ceiling across every Pokemon
    # catalogue, not a TCGdex limitation, and it is below what a 63x88 mm card
    # needs at 1200 DPI. The pipeline normalizes before the AI pass to make
    # the most of it.
    NOTE = ("Pokémon art tops out at 600×825 everywhere - below Scryfall's "
            "745×1040, so expect a little less detail than Magic cards.")

    @staticmethod
    def search(query: str, limit: int = 60) -> list[dict]:
        import pokemon
        return pokemon.search(query, limit, lang=_lang())

    @staticmethod
    def fetch_thumb(url: str) -> bytes | None:
        import pokemon
        return pokemon.fetch_thumb(url)


# --------------------------------------------------------------------------
# Riftbound (Riftcodex)
# --------------------------------------------------------------------------

class _Riftbound:
    ID = "riftbound"
    LABEL = "Riftbound"
    ADD_KIND = "card"
    EMPTY = "No matches on Riftcodex."
    PLACEHOLDER = "Card name (e.g. Jinx - Rebel)"
    # No CARD_SIZE_HINT: a Riftbound card is 63x88 mm like Magic, so the
    # default size is already right - including the Battlefields, whose art is
    # landscape but whose cardboard is not.
    NOTE = ("Images come from Riot's own CDN at 744×1039, the same class as "
            "Scryfall. Battlefields are turned upright to fit the sheet; the "
            "printed card is one you hold sideways.")

    @staticmethod
    def search(query: str, limit: int = 60) -> list[dict]:
        import riftbound
        return riftbound.search(query, limit)

    @staticmethod
    def fetch_thumb(url: str) -> bytes | None:
        import riftbound
        return riftbound.fetch_thumb(url)


SCRYFALL = _Scryfall
GATHERER = _Gatherer
MPC = _MPC
YGO = _YGO
POKEMON = _Pokemon
RIFTBOUND = _Riftbound

ALL = [SCRYFALL, GATHERER, MPC, POKEMON, YGO, RIFTBOUND]


def by_id(source_id: str):
    for s in ALL:
        if s.ID == source_id:
            return s
    return SCRYFALL
