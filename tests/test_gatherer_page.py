"""
New-style Gatherer links, and the language Scryfall does not have.

Gatherer moved to per-language pages addressed by set / locale / number, with
no multiverse id anywhere on them. The app resolved those links through
Scryfall to find an id - and **Scryfall does not carry every printing Gatherer
does**. TLA #315 is on Gatherer in Spanish and on Scryfall in English only, so
pasting the Spanish link handed back the English card while the user was
looking at the Spanish one on screen.

The page names its own image through og:image, so it is both the correct
language and, at `medium` as PNG, 744x1039 - the same as Scryfall and well
above the 646x902 JPEG the old Handlers/Image.ashx serves.
"""

import pytest

import scryfall

ES = "https://gatherer.wizards.com/TLA/es-es/315/fire-lord-zuko"
EN = "https://gatherer.wizards.com/TLA/en-us/315/fire-lord-zuko"
OLD = "https://gatherer.wizards.com/Pages/Card/Details.aspx?multiverseid=226749"

HASH = "B1A51A141CFDD1A8E5492EC64643123BFCF8C47715F393AE1449E3EB8B7477D2"
PAGE = (
    '<html><head><meta property="og:image" content='
    f'"https://gatherer-static.wizards.com/Cards/medium/{HASH}.webp"/>'
    "</head></html>"
)


# ---------------------------------------------------------------- parsing

def test_a_new_style_link_keeps_its_url():
    """The page is the only thing that knows this printing, so the parser has
    to hand it on rather than reducing the link to set/number/lang."""
    g = scryfall._gatherer_parse(ES)
    assert g["set"] == "tla" and g["number"] == "315" and g["lang"] == "es"
    assert g["url"] == ES


def test_an_old_style_link_still_parses_to_a_multiverse_id():
    assert scryfall._gatherer_parse(OLD) == {"mid": 226749}


def test_the_spanish_locale_maps_to_scryfalls_code():
    assert scryfall._gatherer_parse(ES)["lang"] == "es"
    assert scryfall._gatherer_parse(EN)["lang"] == "en"


# ------------------------------------------------------- the page's image

@pytest.fixture
def page(monkeypatch, tmp_path):
    """Serve the page HTML, then a PNG, recording what was asked for."""
    from PIL import Image
    import io as _io

    buf = _io.BytesIO()
    Image.new("RGB", (744, 1039), (20, 30, 40)).save(buf, "PNG")
    png = buf.getvalue()
    asked = []

    class _R:
        def __init__(self, body, status=200):
            self.status_code = status
            self._body = body

        @property
        def text(self):
            return self._body if isinstance(self._body, str) else ""

        @property
        def content(self):
            return self._body if isinstance(self._body, bytes) else b""

    def fake_get(url, **kw):
        asked.append(url)
        if url.startswith("https://gatherer.wizards.com"):
            return _R(PAGE)
        if url.startswith("https://gatherer-static"):
            return _R(png)
        raise AssertionError(f"unexpected url {url}")

    monkeypatch.setattr(scryfall.requests, "get", fake_get)
    monkeypatch.setattr(scryfall, "TEMP_FOLDER", tmp_path)
    return asked


def test_the_png_is_taken_not_the_webp(page):
    """Same pixels either way, but the webp is heavily compressed and this is
    the image the AI has to upscale from."""
    scryfall._gatherer_page_image(ES, "zuko")
    assert page[-1].endswith(".png")
    assert HASH in page[-1]


def test_it_asks_for_medium(page):
    """large and above answer 403, so medium is the ceiling - and it is
    already 744x1039."""
    scryfall._gatherer_page_image(ES, "zuko")
    assert "/Cards/medium/" in page[-1]


def test_a_page_with_no_card_image_is_an_error(monkeypatch, tmp_path):
    class _R:
        status_code = 200
        text = "<html><head></head></html>"

    monkeypatch.setattr(scryfall.requests, "get", lambda u, **kw: _R())
    with pytest.raises(scryfall.ScryfallError):
        scryfall._gatherer_page_image(ES, "zuko")


def test_a_dead_page_is_an_error(monkeypatch, tmp_path):
    class _R:
        status_code = 502
        text = ""

    monkeypatch.setattr(scryfall.requests, "get", lambda u, **kw: _R())
    with pytest.raises(scryfall.ScryfallError):
        scryfall._gatherer_page_image(ES, "zuko")


# ------------------------------------------------------- through fetch()

def _scryfall_card(lang="en"):
    return {
        "name": "Fire Lord Zuko",
        "set": "tla",
        "collector_number": "315",
        "lang": lang,
        "released_at": "2025-11-21",
        "multiverse_ids": [700000],
        "image_uris": {"png": "https://cards.scryfall.io/png/x.png"},
    }


def test_the_file_is_named_for_the_LINKS_language(page, monkeypatch):
    """Scryfall only knows this printing in English, so the resolved card says
    lang=en. The file being written is the Spanish one and has to say so, or a
    later Spanish and English copy collide on one name."""
    monkeypatch.setattr(scryfall, "_get",
                        lambda url, **kw: type("R", (), {
                            "status_code": 404, "json": lambda s: {}})())
    monkeypatch.setattr(scryfall, "_printing_by_name",
                        lambda *a, **kw: _scryfall_card("en"))
    paths, meta = scryfall.fetch(ES)
    assert paths[0].name == "Fire Lord Zuko-tla-315-es.png"


def test_an_english_link_gets_no_language_suffix(page, monkeypatch):
    monkeypatch.setattr(scryfall, "_get",
                        lambda url, **kw: type("R", (), {
                            "status_code": 404, "json": lambda s: {}})())
    monkeypatch.setattr(scryfall, "_printing_by_name",
                        lambda *a, **kw: _scryfall_card("en"))
    paths, _ = scryfall.fetch(EN)
    assert paths[0].name == "Fire Lord Zuko-tla-315.png"


DELVER = {
    "name": "Delver of Secrets // Insectile Aberration",
    "set": "isd", "collector_number": "51", "lang": "en",
    "multiverse_ids": [226749, 226755],
    "card_faces": [
        {"name": "Delver of Secrets", "image_uris": {"png": "a"}},
        {"name": "Insectile Aberration", "image_uris": {"png": "b"}},
    ],
}


def test_the_multiverse_ids_are_the_fallback_when_the_pages_fail(monkeypatch,
                                                                 tmp_path):
    """An older set has ids as well as pages. The pages are tried first,
    because only they honour the language the link names, but a card that has
    ids is not left empty-handed when Gatherer's page route breaks."""
    monkeypatch.setattr(scryfall, "_get",
                        lambda url, **kw: type("R", (), {
                            "status_code": 200, "json": lambda s: DELVER})())
    used = []
    monkeypatch.setattr(scryfall, "_gatherer_image",
                        lambda mid, base, cb=None: used.append(mid) or [base])

    def dead_page(*a, **kw):
        raise scryfall.ScryfallError("page route down")

    monkeypatch.setattr(scryfall, "_gatherer_page_image", dead_page)
    scryfall.fetch("https://gatherer.wizards.com/ISD/en-us/51a/delver-of-secrets")
    assert used == [226749, 226755]


# ------------------------------------------- double-faced, the new way

AANG = {
    "name": "Aang, Swift Savior // Aang and La, Ocean's Fury",
    "set": "tla",
    # Scryfall resolves the link by NAME and lands on a different printing,
    # because it has no 347. That is the whole difficulty.
    "collector_number": "204",
    "lang": "en",
    "multiverse_ids": [],          # TLA predates nothing - Gatherer never
                                   # gave this set multiverse ids at all
    "card_faces": [
        {"name": "Aang, Swift Savior", "image_uris": {"png": "a"}},
        {"name": "Aang and La, Ocean's Fury", "image_uris": {"png": "b"}},
    ],
}

AANG_REF = "https://gatherer.wizards.com/TLA/es-es/347a/aang-swift-savior"


def test_the_back_face_page_is_derived_from_the_other_faces_name():
    """Editing 347a to 347b is not enough: the slug is the back face's own
    name, and the link only carries the front's."""
    g = scryfall._gatherer_parse(AANG_REF)
    faces = scryfall._gatherer_faces(AANG_REF, g, AANG)
    assert [u for u, _ in faces] == [
        "https://gatherer.wizards.com/TLA/es-es/347a/aang-swift-savior",
        "https://gatherer.wizards.com/TLA/es-es/347b/aang-and-la-oceans-fury",
    ]
    assert [lbl for _, lbl in faces] == ["-front", "-back"]


def test_a_single_faced_card_stays_one_page():
    g = scryfall._gatherer_parse(ES)
    single = {"name": "Fire Lord Zuko", "image_uris": {"png": "x"}}
    assert scryfall._gatherer_faces(ES, g, single) == [(ES, "")]


def test_a_link_with_no_face_letter_is_not_guessed_at():
    """Without an a/b the link does not name a face, so there is no sibling
    page to derive. One correct face beats a guessed URL."""
    ref = "https://gatherer.wizards.com/TLA/es-es/347/aang-swift-savior"
    g = scryfall._gatherer_parse(ref)
    assert scryfall._gatherer_faces(ref, g, AANG) == [(ref, "")]


def test_the_slug_drops_accents_and_punctuation():
    assert scryfall._url_slug("Aang and La, Ocean's Fury") == \
        "aang-and-la-oceans-fury"
    assert scryfall._url_slug("Señor del Fuego Zuko") == "senor-del-fuego-zuko"


def test_both_faces_are_fetched_and_named_for_pairing(page, monkeypatch):
    monkeypatch.setattr(scryfall, "_get",
                        lambda url, **kw: type("R", (), {
                            "status_code": 404, "json": lambda s: {}})())
    monkeypatch.setattr(scryfall, "_printing_by_name",
                        lambda *a, **kw: AANG)
    paths, _ = scryfall.fetch(AANG_REF)
    assert [p.name.split("-")[-1] for p in paths] == ["front.png", "back.png"]


def test_the_filename_carries_the_LINKS_printing_not_scryfalls(page,
                                                               monkeypatch):
    """Scryfall lands on TLA 204 by name. The files are 347, and saying 204
    would claim a printing they are not."""
    monkeypatch.setattr(scryfall, "_get",
                        lambda url, **kw: type("R", (), {
                            "status_code": 404, "json": lambda s: {}})())
    monkeypatch.setattr(scryfall, "_printing_by_name",
                        lambda *a, **kw: AANG)
    paths, _ = scryfall.fetch(AANG_REF)
    assert "tla-347-es" in paths[0].name
    assert "204" not in paths[0].name
