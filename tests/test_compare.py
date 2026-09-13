"""
Comparing gallery cards up close.

Asked for by a user who wanted to click a result, see it enlarged, and put two
or three side by side before choosing. At the gallery's 150 px thumbnails,
telling two scans of the same art apart is guesswork.
"""

import pytest

import gui
import sources

CompareWindow = gui.CompareWindow


def _tray():
    """The window's tray rule, without the widgets it drives."""
    w = CompareWindow.__new__(CompareWindow)
    w._keys = []
    return w


def _card(ident, source="scryfall"):
    return {"identifier": ident, "_source": source, "download": f"u/{ident}"}


# ------------------------------------------------------------------ the tray

def test_it_holds_up_to_three():
    """"Two or three" is what was asked for, and a fourth would shrink every
    card on a laptop screen to where comparing stops being the point."""
    assert CompareWindow.MAX == 3


def test_a_card_already_there_is_not_added_twice():
    w = _tray()
    key = CompareWindow.key_of(_card("a"))
    assert w._admit(key) == (True, None)
    assert w._admit(key) == (False, None)
    assert w._keys == [key]


def test_a_full_tray_lets_the_oldest_go():
    """The one just clicked is the one being looked at, so it stays."""
    w = _tray()
    keys = [CompareWindow.key_of(_card(x)) for x in "abcd"]
    for k in keys[:3]:
        w._admit(k)
    is_new, evicted = w._admit(keys[3])
    assert is_new and evicted == keys[0]
    assert w._keys == keys[1:]


def test_the_same_art_in_two_catalogues_is_two_cards():
    """They are different downloads - a Gatherer image and a Scryfall one of
    the same printing do not look the same - so both can sit side by side."""
    a = CompareWindow.key_of(_card("x", "scryfall"))
    b = CompareWindow.key_of(_card("x", "gatherer"))
    assert a != b


# ------------------------------------------------------------ the preview

def test_scryfall_offers_its_large_image_as_the_preview():
    """672x936 at ~106 KB, against the 760 KB PNG: near full resolution for a
    seventh of the download, for something you may not keep."""
    card = {"image_uris": {"small": "s", "normal": "n", "large": "L",
                           "png": "P"}}
    assert sources._preview_url(card) == "L"


def test_the_preview_falls_back_when_there_is_no_large():
    assert sources._preview_url({"image_uris": {"png": "P"}}) == "P"


def test_a_scryfall_preview_is_fetched_with_scryfalls_user_agent(monkeypatch):
    """Scryfall asks every client to identify itself; the other hosts get a
    browser's, which is what the Gatherer handler wants."""
    seen = {}

    class _R:
        status_code = 200
        content = b"x" * 5000

    def fake_get(url, headers=None, **kw):
        seen[url] = headers
        return _R()

    monkeypatch.setattr(sources.requests, "get", fake_get)
    sources.fetch_preview("https://cards.scryfall.io/large/x.jpg")
    sources.fetch_preview("https://gatherer.wizards.com/Handlers/x")
    assert seen["https://cards.scryfall.io/large/x.jpg"] is sources.SCRYFALL_HEADERS
    assert "Mozilla" in seen["https://gatherer.wizards.com/Handlers/x"][
        "User-Agent"]


def test_a_failed_preview_is_none_not_an_exception(monkeypatch):
    def boom(*a, **kw):
        raise sources.requests.RequestException("offline")

    monkeypatch.setattr(sources.requests, "get", boom)
    assert sources.fetch_preview("https://example.com/x.png") is None
    assert sources.fetch_preview("") is None


def test_previews_do_not_go_through_the_thumbnail_cache(monkeypatch):
    """Those caches key on the file name, and a thumbnail and a preview of
    the same card can share one - YGOPRODeck's cards_small/1234.jpg and
    cards/1234.jpg. Through that cache, the preview would come back as the
    150 px thumbnail blown up. So every thumbnail fetcher is booby-trapped
    here, and the preview has to arrive anyway."""
    import mpcfill
    import pokemon
    import riftbound
    import ygoprodeck

    def trap(*a, **kw):
        raise AssertionError("a preview went through a thumbnail cache")

    for mod in (mpcfill, pokemon, riftbound, ygoprodeck):
        monkeypatch.setattr(mod, "fetch_thumb", trap)
    monkeypatch.setattr(sources, "_fetch_thumb", trap)

    class _R:
        status_code = 200
        content = b"x" * 5000

    monkeypatch.setattr(sources.requests, "get", lambda *a, **kw: _R())
    url = "https://images.ygoprodeck.com/images/cards/46986416.jpg"
    assert sources.fetch_preview(url) == b"x" * 5000


# ------------------------------------------------ the sources that set one

def test_mpc_previews_use_the_medium_thumbnail_not_the_drive_file(monkeypatch):
    """The download is the whole Drive file, often 12 MB. The medium
    thumbnail is 588x800 at ~570 KB."""
    import mpcfill

    class _R:
        def __init__(self, payload):
            self.status_code = 200
            self._p = payload

        def json(self):
            return self._p

    card = {
        "name": "Sol Ring", "identifier": "id1",
        "smallThumbnailUrl": "https://drive.google.com/thumbnail?sz=w400-h400&id=id1",
        "mediumThumbnailUrl": "https://drive.google.com/thumbnail?sz=w800-h800&id=id1",
        "downloadLink": "https://drive.google.com/uc?id=id1&export=download",
    }

    def fake_post(url, **kw):
        # editorSearch answers ids per query; /2/cards/ answers the cards
        if url.endswith("/2/cards/"):
            return _R({"results": {"id1": card}})
        return _R({"results": {"sol ring": {"CARD": ["id1"]}}})

    monkeypatch.setattr(mpcfill, "_throttle", lambda: None)
    monkeypatch.setattr(mpcfill, "_sources", lambda: [])
    monkeypatch.setattr(mpcfill.requests, "post", fake_post)
    hits = mpcfill.search("Sol Ring", 5)
    assert hits and "w800" in hits[0]["preview"]
    assert hits[0]["preview"] != hits[0]["download"]


def test_riftbound_previews_ask_the_cdn_to_scale_down_as_jpeg(monkeypatch):
    """Left as PNG the CDN answered 1.2 MB, barely lighter than the full
    file; as JPEG at the same size it is 145 KB. And never upward: that CDN
    will happily upsample the 744-wide original into fake detail."""
    import riftbound
    monkeypatch.setattr(riftbound, "_get", lambda p, q: {"items": [{
        "id": "a", "name": "Jinx - Rebel",
        "media": {"image_url": "https://cmsassets.rgpub.io/x/abc.png?t=1"}}]})
    tile = riftbound.search("Jinx - Rebel")[0]
    assert "fm=jpg" in tile["preview"]
    assert f"w={riftbound._PREVIEW_WIDTH}" in tile["preview"]
    assert riftbound._PREVIEW_WIDTH < 744
