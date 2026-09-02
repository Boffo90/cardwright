"""
Riftbound (Riot's LoL TCG) through the Riftcodex API.

Chosen over the alternatives because it needs no API key, which is the exact
thing that still blocks One Piece, Digimon and Dragon Ball: apitcg.com demands
one on every call and a binary handed to strangers cannot honour it.

The one new idea in the integration is the rotation. Battlefields are the only
landscape cards, and their art is 1039x744 - the same aspect as 88:63 lying
down - so a Battlefield is an ordinary 63x88 card you hold sideways, not a
different size. Standing it up on the way in keeps it out of the
mixed-orientation layout work that was deliberately not done.
"""

import pytest
from PIL import Image

import riftbound
import sources
import upscale


class _Resp:
    def __init__(self, payload, status=200):
        self._payload = payload
        self.status_code = status

    def json(self):
        return self._payload


IMG = "https://cmsassets.rgpub.io/sanity/images/x/y/abc-744x1039.png"
BF_IMG = "https://cmsassets.rgpub.io/sanity/images/x/y/def-1039x744.png"


def _card(name, cid, image=IMG, orientation="portrait", ctype="Unit"):
    return {
        "id": cid,
        "name": name,
        "collector_number": 202,
        "orientation": orientation,
        "set": {"set_id": "OGN", "label": "Origins"},
        "classification": {"type": ctype, "rarity": "Epic"},
        "media": {"image_url": image + "?accountingTag=RB"},
    }


# ------------------------------------------------------------------ search

def test_exact_printings_come_before_fuzzy_neighbours(monkeypatch):
    """A named card lists its whole print run first. Fuzzy is capped at 10 by
    the server, so on its own it buries the three printings of "Jinx - Rebel"
    among Demolitionist and Loose Cannon."""
    calls = []

    def fake_get(path, params):
        calls.append(params)
        if "exact" in params:
            return {"items": [_card("Jinx - Rebel", "a"),
                              _card("Jinx - Rebel", "b")]}
        return {"items": [_card("Jinx - Rebel", "a"),          # duplicate
                          _card("Jinx - Demolitionist", "c")]}

    monkeypatch.setattr(riftbound, "_get", fake_get)
    out = riftbound.search("Jinx - Rebel")
    assert [c["identifier"] for c in out] == ["a", "b", "c"]
    assert [set(p) - {"size"} for p in calls] == [{"exact"}, {"fuzzy"}]


def test_a_card_with_no_image_is_skipped(monkeypatch):
    monkeypatch.setattr(riftbound, "_get", lambda p, q: {"items": [
        {"id": "x", "name": "No art", "media": {}},
        _card("Real", "y"),
    ]})
    assert [c["identifier"] for c in riftbound.search("x")] == ["y"]


def test_an_empty_query_asks_for_nothing(monkeypatch):
    def boom(path, params):
        raise AssertionError("should not have called the API")
    monkeypatch.setattr(riftbound, "_get", boom)
    assert riftbound.search("   ") == []


def test_the_tile_says_when_a_card_is_landscape(monkeypatch):
    """It changes what comes out of the printer, so it is not a detail to
    leave off the tile."""
    monkeypatch.setattr(riftbound, "_get", lambda p, q: {"items": [
        _card("Star Spring", "s", BF_IMG, "landscape", "Battlefield")]})
    tile = riftbound.search("Star Spring")[0]
    assert "landscape" in tile["source"]
    assert "Battlefield" in tile["source"]


def test_the_thumbnail_asks_the_cdn_to_go_down_not_up(monkeypatch):
    """The full image is ~1.4 MB. Asking that CDN to go UP is the trap: it
    upsamples the 744-wide original and calls it 3000 wide."""
    monkeypatch.setattr(riftbound, "_get", lambda p, q: {"items": [_card("A", "a")]})
    tile = riftbound.search("A")[0]
    assert tile["thumb"] == f"{IMG}?w={riftbound._THUMB_WIDTH}"
    assert riftbound._THUMB_WIDTH < 744
    assert tile["download"] == IMG           # native size, no resize param


# ------------------------------------------------------------- the registry

def test_riftbound_is_a_source_the_gallery_can_drive():
    src = sources.by_id("riftbound")
    assert src.ID == "riftbound"
    assert src.ADD_KIND == "card"
    assert hasattr(src, "search") and hasattr(src, "fetch_thumb")
    assert src in sources.ALL


def test_it_does_not_switch_the_card_size():
    """A Riftbound card is 63x88 mm like Magic, Battlefields included - their
    art is landscape but their cardboard is not."""
    assert not hasattr(sources.by_id("riftbound"), "CARD_SIZE_HINT")


# ------------------------------------------------------------ the rotation

@pytest.fixture
def img(tmp_path):
    def make(w, h):
        p = tmp_path / f"{w}x{h}.png"
        Image.new("RGB", (w, h), (40, 90, 160)).save(p)
        return p
    return make


CARD = (2976, 4160)          # 63x88 mm at 1200 DPI


def test_a_sideways_card_is_stood_up(img):
    out = upscale._orient_to_card(img(1039, 744), CARD)
    assert out is not None
    with Image.open(out) as im:
        assert im.size == (744, 1039)


def test_a_portrait_card_is_left_alone(img):
    assert upscale._orient_to_card(img(744, 1039), CARD) is None


def test_a_wide_picture_that_is_not_a_card_is_left_alone(img):
    """Only something shaped like the card lying down gets turned. A banner
    someone dropped in is not silently rotated behind their back."""
    assert upscale._orient_to_card(img(1600, 400), CARD) is None


def test_a_square_image_is_left_alone(img):
    assert upscale._orient_to_card(img(800, 800), CARD) is None


def test_no_card_size_means_no_opinion(img):
    assert upscale._orient_to_card(img(1039, 744), None) is None


def test_the_turn_is_lossless(img):
    """Rotating by a quarter turn must not resample: this runs before the AI
    and any softening here is softening the AI then has to invent back."""
    src = img(1039, 744)
    out = upscale._orient_to_card(src, CARD)
    with Image.open(src) as a, Image.open(out) as b:
        assert sorted(a.size) == sorted(b.size)
        assert a.rotate(upscale.ROTATE_LANDSCAPE_DEG, expand=True).tobytes() \
            == b.convert(a.mode).tobytes()
