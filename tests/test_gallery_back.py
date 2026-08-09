"""
Double-faced cards picked from a catalogue gallery.

A gallery pick is one image, so a double-faced card used to arrive with only
its front and fall through to the shared back.png. The back lives in the same
catalogue under its own card name, and contributors upload both faces
together, so the right back is findable rather than a guess.
"""

import gui
import scryfall

App = gui.App


def _r(name, source):
    return {"name": name, "source": source, "download": f"url/{name}"}


# ------------------------------------------------------------ name parsing

def test_the_art_variant_is_read_off_the_catalogue_name():
    assert App._plain_name("Rona, Herald of Invasion (MOM 75)") == \
        "Rona, Herald of Invasion"
    assert App._variant_of("Rona, Herald of Invasion (MOM 75)") == "mom 75"


def test_a_name_with_no_variant_is_left_alone():
    assert App._plain_name("Island") == "Island"
    assert App._variant_of("Island") == ""


# --------------------------------------------------------------- the pick

def test_the_back_by_the_same_contributor_and_variant_wins():
    front = _r("Rona, Herald of Invasion (b)", "WillieTanner")
    results = [_r("Rona, Tolarian Obliterator (MOM 75)", "Chilli_Axe"),
               _r("Rona, Tolarian Obliterator (a)", "WillieTanner"),
               _r("Rona, Tolarian Obliterator (b)", "WillieTanner")]
    pick, same_src = App._pick_back(results, front)
    assert pick["name"] == "Rona, Tolarian Obliterator (b)"
    assert same_src


def test_the_contributor_beats_the_variant_when_only_one_can_match():
    """Same artist, different variant name, still the better answer than a
    stranger's art that happens to share a suffix."""
    front = _r("Card (Borderless)", "PsilosX")
    results = [_r("Back (Borderless)", "SomeoneElse"),
               _r("Back (Extended)", "PsilosX")]
    pick, same_src = App._pick_back(results, front)
    assert pick["source"] == "PsilosX"
    assert same_src


def test_a_back_from_another_contributor_is_used_but_flagged():
    front = _r("Card (MOM 75)", "Chilli_Axe")
    results = [_r("Back (MOM 75)", "WillieTanner")]
    pick, same_src = App._pick_back(results, front)
    assert pick["source"] == "WillieTanner"
    assert not same_src, "the caller has to be able to say this was a fallback"


# ------------------------------------------------- what counts as two faces

class _Resp:
    def __init__(self, payload):
        self._payload = payload
        self.status_code = 200

    def json(self):
        return self._payload


def _scryfall_returning(payload, monkeypatch):
    monkeypatch.setattr(scryfall, "_get", lambda url, **kw: _Resp(payload))


def test_a_transforming_card_reports_its_second_face(monkeypatch):
    _scryfall_returning({"card_faces": [
        {"name": "Rona, Herald of Invasion", "image_uris": {"png": "u1"}},
        {"name": "Rona, Tolarian Obliterator", "image_uris": {"png": "u2"}},
    ]}, monkeypatch)
    assert scryfall.back_face_name("Rona") == "Rona, Tolarian Obliterator"


def test_a_split_card_is_one_piece_of_cardboard(monkeypatch):
    """Split, flip and adventure cards have two card_faces but a single
    top-level image. Treating them as double-faced would queue a second
    download that does not exist."""
    _scryfall_returning({
        "image_uris": {"png": "u"},
        "card_faces": [{"name": "Fire"}, {"name": "Ice"}],
    }, monkeypatch)
    assert scryfall.back_face_name("Fire // Ice") is None


def test_a_plain_card_has_no_second_face(monkeypatch):
    _scryfall_returning({"image_uris": {"png": "u"}}, monkeypatch)
    assert scryfall.back_face_name("Island") is None


def test_a_lookup_failure_is_not_fatal(monkeypatch):
    """A catalogue pick must still queue when Scryfall is unreachable."""
    def boom(url, **kw):
        raise scryfall.requests.RequestException("no network")
    monkeypatch.setattr(scryfall, "_get", boom)
    assert scryfall.back_face_name("Rona") is None
