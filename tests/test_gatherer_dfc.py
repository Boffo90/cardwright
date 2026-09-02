"""
Double-faced cards imported through Gatherer.

A DFC is TWO Gatherer records: Scryfall lists both ids in `multiverse_ids`,
front first. The Gatherer path took only the first, so importing a decklist
with "Images from: Gatherer" - or pasting a Gatherer link - queued the front
alone. Silently, because a card with one face is a perfectly ordinary thing.

The decklist resolver was never at fault: it works out both faces and then the
GUI drops them, because a Gatherer entry carries a `ref` instead. So the fix
belongs where the ref is turned into files.
"""

import pytest

import scryfall


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


DELVER = {
    "name": "Delver of Secrets // Insectile Aberration",
    "set": "isd",
    "collector_number": "51",
    "multiverse_ids": [226749, 226755],
    "card_faces": [
        {"name": "Delver of Secrets", "image_uris": {"png": "s-front"}},
        {"name": "Insectile Aberration", "image_uris": {"png": "s-back"}},
    ],
}

SOL_RING = {
    "name": "Sol Ring",
    "set": "c21",
    "collector_number": "263",
    "multiverse_ids": [519298],
    "image_uris": {"png": "s-solring"},
}

SPLIT = {
    "name": "Fire // Ice",
    "set": "apc",
    "collector_number": "128",
    # Gatherer numbers each half, so a split card has two ids even though it
    # is one piece of cardboard. The face images are what settle it.
    "multiverse_ids": [27166, 27167],
    "image_uris": {"png": "s-fireice"},
    "card_faces": [{"name": "Fire"}, {"name": "Ice"}],
}


@pytest.fixture
def gatherer(monkeypatch):
    """Record which multiverse ids the Gatherer image handler is asked for."""
    asked = []

    def fake_image(mid, base, status_callback=None):
        asked.append((mid, base))
        return [f"{base}.png"]

    monkeypatch.setattr(scryfall, "_gatherer_image", fake_image)
    return asked


def _fetch(card, gatherer_ref_mid, monkeypatch):
    monkeypatch.setattr(scryfall, "_get", lambda url, **kw: _Resp(card))
    return scryfall.fetch(
        "https://gatherer.wizards.com/Pages/Card/Details.aspx"
        f"?multiverseid={gatherer_ref_mid}")


# ------------------------------------------------- which faces are fetched

def test_a_double_faced_card_fetches_both_gatherer_records(gatherer, monkeypatch):
    paths, _ = _fetch(DELVER, 226749, monkeypatch)
    assert [mid for mid, _ in gatherer] == [226749, 226755]
    assert len(paths) == 2


def test_the_two_faces_are_named_so_the_sheet_can_pair_them(gatherer,
                                                            monkeypatch):
    """The export dialog pairs a DFC by its -front / -back filename suffix, so
    fetching both faces is only half the job."""
    paths, _ = _fetch(DELVER, 226749, monkeypatch)
    assert paths[0].endswith("-front.png")
    assert paths[1].endswith("-back.png")


def test_a_single_faced_card_still_fetches_one(gatherer, monkeypatch):
    paths, _ = _fetch(SOL_RING, 519298, monkeypatch)
    assert [mid for mid, _ in gatherer] == [519298]
    assert len(paths) == 1


def test_a_split_card_is_one_piece_of_cardboard(gatherer, monkeypatch):
    """Two multiverse ids is not enough to make a card double-faced: Gatherer
    numbers each half of a split card too. Only faces with images of their own
    are two physical sides."""
    paths, _ = _fetch(SPLIT, 27166, monkeypatch)
    assert len(paths) == 1


# --------------------------------------------------------- when it cannot

def test_a_face_missing_from_gatherer_falls_back_to_scryfall_for_both(
        monkeypatch):
    """Half a card is worse than a consistent one. If either face is missing,
    both come from Scryfall rather than printing two that do not match."""
    monkeypatch.setattr(scryfall, "_get", lambda url, **kw: _Resp(DELVER))

    def only_the_front(mid, base, status_callback=None):
        if mid != 226749:
            raise scryfall.ScryfallError("no image")
        return [f"{base}.png"]

    monkeypatch.setattr(scryfall, "_gatherer_image", only_the_front)
    got = []
    monkeypatch.setattr(scryfall, "_download_card",
                        lambda c, cb=None, finish=None: (got.append(c) or
                                                         (["a", "b"], {})))
    paths, _ = scryfall.fetch(
        "https://gatherer.wizards.com/Pages/Card/Details.aspx"
        "?multiverseid=226749")
    assert got and got[0] is DELVER
    assert paths == ["a", "b"]


# ------------------------------------------------- the shared predicate

def test_two_faced_is_about_images_not_face_count():
    assert scryfall.two_faced(DELVER)
    assert not scryfall.two_faced(SOL_RING)
    assert not scryfall.two_faced(SPLIT)
