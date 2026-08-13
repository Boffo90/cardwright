"""
Changing a card's art without leaving the export dialog.

Also covers the fourth place this project lost the back of a double-faced card:
the Scryfall gallery hands back a url for the FRONT face only, so a pick made
there arrived as half a card. The pick carries the Scryfall id as well, and
resolving that returns every face.
"""

import gui
import scryfall
import sources


class _Src:
    def __init__(self, sid, add_kind="card", label="Scryfall"):
        self.ID = sid
        self.ADD_KIND = add_kind
        self.LABEL = label


def _dialog(paths):
    d = gui.ExportDialog.__new__(gui.ExportDialog)
    d._order = [gui._Card(p) for p in paths]
    d._back_of = {c.uid: None for c in d._order}
    d.card_sources = {}
    d._undo = []
    d._push_undo = lambda label: d._undo.append(label)
    d._draw_preview = lambda: None
    d._set_status = lambda text: None
    d._load_thumbs = lambda: None
    return d


def _names(d):
    return [c.path.stem for c in d._order]


# ------------------------------------------------- which pick becomes a ref

def _ref_for(monkeypatch, pick, src):
    """What _fetch_art would resolve, without downloading anything."""
    seen = {}
    monkeypatch.setattr(sources, "by_id", lambda _id: src)
    monkeypatch.setattr(scryfall, "fetch",
                        lambda ref, **kw: (seen.setdefault("ref", ref), ([], {}))[1])
    monkeypatch.setattr(scryfall, "download_to_temp",
                        lambda base, url: seen.setdefault("direct", url) or base)
    monkeypatch.setattr(gui, "upscale", lambda t, **kw: t)
    d = _dialog(["a.png"])
    d._fetch_art(pick, {"lang": "en", "best_scan": False, "model": "m",
                        "fit": True, "trim": "never", "card_size": None,
                        "ai": False})
    return seen.get("ref")


def test_a_scryfall_pick_resolves_by_id_not_by_its_front_image(monkeypatch):
    """The download url in a gallery pick is the front face. Following it is
    what lost the back."""
    ref = _ref_for(monkeypatch,
                   {"_source": "scryfall", "identifier": "abc-123",
                    "name": "Rona", "download": "https://.../front/x.png"},
                   _Src("scryfall"))
    assert ref == f"{scryfall.SCRYFALL_API}/cards/abc-123"


def test_a_source_with_its_own_reference_keeps_using_it(monkeypatch):
    ref = _ref_for(monkeypatch,
                   {"_source": "gatherer", "ref": "https://gatherer/...",
                    "name": "Bolt"},
                   _Src("gatherer", add_kind="scryfall", label="Gatherer"))
    assert ref == "https://gatherer/..."


def test_a_catalogue_without_an_id_still_downloads_directly(monkeypatch):
    """MPC and the rest have no Scryfall id, so they keep the direct path."""
    seen = {}
    monkeypatch.setattr(sources, "by_id", lambda _id: _Src("mpc"))
    monkeypatch.setattr(scryfall, "fetch",
                        lambda ref, **kw: seen.setdefault("ref", ref))
    monkeypatch.setattr(scryfall, "download_to_temp",
                        lambda base, url: seen.setdefault("direct", url) or base)
    monkeypatch.setattr(gui, "upscale", lambda t, **kw: t)
    d = _dialog(["a.png"])
    d._fetch_art({"_source": "mpc", "name": "Bolt", "source": "Chilli_Axe",
                  "download": "https://drive/x.png", "identifier": "drive-id"},
                 {"lang": "en", "best_scan": False, "model": "m", "fit": True,
                  "trim": "never", "card_size": None, "ai": False})
    assert "ref" not in seen, "an MPC pick has no Scryfall card to resolve"
    assert seen["direct"] == "https://drive/x.png"


def test_an_explicit_pick_is_not_overridden_by_the_global_preferences():
    """best_scan would swap the printing and a language preference would swap
    the language. Both are supposed to stand down for an explicit pick, and
    that is what makes routing a gallery pick through fetch safe."""
    ref = f"{scryfall.SCRYFALL_API}/cards/f487b582-e73f-4325-939f-95fc5a9aba49"
    assert scryfall.ref_names_a_printing(ref)
    assert scryfall._ref_pins_language(ref)


# ------------------------------------------------------------- the swap

def test_changing_one_copy_leaves_the_others_alone():
    d = _dialog(["a.png", "a.png", "b.png"])
    d._swap_art(d._order[1].uid, False, [gui.Path("new.png")])
    assert _names(d) == ["a", "new", "b"]


def test_changing_all_copies_follows_the_image():
    d = _dialog(["a.png", "a.png", "b.png"])
    d._swap_art(d._order[0].uid, True, [gui.Path("new.png")])
    assert _names(d) == ["new", "new", "b"]


def test_the_card_is_replaced_rather_than_edited():
    """Undo snapshots the order with a shallow copy, on the understanding that
    a card's path never changes under it. Editing one in place would rewrite
    the history as well as the sheet."""
    d = _dialog(["a.png"])
    before = d._order[0]
    d._swap_art(before.uid, False, [gui.Path("new.png")])
    assert d._order[0] is not before
    assert before.path.stem == "a", "the old card must still describe the old art"


def test_a_double_faced_pick_attaches_its_back():
    d = _dialog(["a.png"])
    key = d._order[0].uid
    d._swap_art(key, False, [gui.Path("new-front.png"), gui.Path("new-back.png")])
    new = d._order[0]
    assert new.path.stem == "new-front"
    assert d._back_of[new.uid].stem == "new-back"


def test_a_single_faced_pick_keeps_whatever_back_was_assigned():
    d = _dialog(["a.png"])
    key = d._order[0].uid
    d._back_of[key] = gui.Path("chosen-back.png")
    d._swap_art(key, False, [gui.Path("new.png")])
    assert d._back_of[d._order[0].uid].stem == "chosen-back"


def test_the_old_card_stops_carrying_a_back():
    d = _dialog(["a.png"])
    old = d._order[0].uid
    d._back_of[old] = gui.Path("b.png")
    d._swap_art(old, False, [gui.Path("new.png")])
    assert old not in d._back_of, "a card no longer on the sheet keeps nothing"


def test_changing_several_copies_is_one_undo_step():
    d = _dialog(["a.png", "a.png", "a.png"])
    d._swap_art(d._order[0].uid, True, [gui.Path("new.png")])
    assert d._undo == ["change art on 3 copies"]


def test_changing_one_says_so():
    d = _dialog(["a.png", "a.png"])
    d._swap_art(d._order[0].uid, False, [gui.Path("new.png")])
    assert d._undo == ["change art"]


def test_an_unknown_card_is_ignored():
    d = _dialog(["a.png"])
    d._swap_art("not-a-card", False, [gui.Path("new.png")])
    assert _names(d) == ["a"]
    assert d._undo == []
