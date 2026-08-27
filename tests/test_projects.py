"""
Saving and loading a queue.

A hundred cards chosen printing by printing, with quantities and per-card
models, used to vanish when the window closed. Export presets save settings;
this saves the list itself. Both backlogs had it, and v2.17.10 made losing it
cost more by giving the session more to lose.
"""

from pathlib import Path

import gui


class _Menu:
    def __init__(self, value="Auto"):
        self.value = value

    def get(self):
        return self.value

    def set(self, v):
        self.value = v


class _Item:
    def __init__(self, **kw):
        self.ref = kw.get("ref", "Sol Ring")
        self.kind = kw.get("kind", "scryfall")
        self.label = kw.get("label", "Sol Ring")
        self.qty = kw.get("qty", 1)
        self.released_at = kw.get("released_at")
        self.set_code = kw.get("set_code")
        self.src = kw.get("src", "scryfall")
        self.downloads = kw.get("downloads")
        self.outputs = kw.get("outputs", [])
        self.status = kw.get("status", "pending")
        self.model_menu = _Menu(kw.get("model", "Auto"))

    def set_status(self, status, info=None, progress=None):
        self.status = status


def _app(items=()):
    a = gui.App.__new__(gui.App)
    a.items = list(items)
    return a


# ------------------------------------------------------------ what is saved

def test_a_project_records_what_it_takes_to_rebuild_a_card():
    a = _app([_Item(ref="Sol Ring (SLD) 2560", qty=3, set_code="sld",
                    model="UltraSharp", src="scryfall")])
    row = a._project_dict()["items"][0]
    assert row["ref"] == "Sol Ring (SLD) 2560"
    assert row["qty"] == 3
    assert row["model"] == "UltraSharp"
    assert row["set_code"] == "sld"
    assert row["src"] == "scryfall"


def test_the_format_is_stamped_so_a_future_version_can_tell():
    a = _app([_Item()])
    d = a._project_dict()
    assert d["cardwright_project"] == gui.App.PROJECT_FORMAT
    assert d["app_version"] == gui.APP_VERSION


def test_downloads_survive_as_pairs():
    """A gallery pick carries its own urls; without them the card cannot be
    fetched again."""
    a = _app([_Item(kind="card", downloads=[("Bolt [MPC]", "http://u")])])
    assert a._project_dict()["items"][0]["downloads"] == [["Bolt [MPC]", "http://u"]]


# --------------------------------------------------------- what is restored

def _loader(tmp_path, monkeypatch):
    a = gui.App.__new__(gui.App)
    a.items = []
    a._clear = lambda: a.items.clear()
    a._refresh_empty = lambda: None

    def add(ref, kind, downloads=None, label=None, qty=1, released_at=None,
            set_code=None, src=None):
        it = _Item(ref=ref, kind=kind, downloads=downloads, label=label,
                   qty=qty, released_at=released_at, set_code=set_code, src=src)
        a.items.append(it)
        return it
    a._add_item = add
    monkeypatch.setattr(gui.messagebox, "showinfo", lambda *x, **k: None)
    return a


def test_a_card_whose_files_are_gone_is_queued_again(tmp_path, monkeypatch):
    """A project outlives the images it points at. Restoring it as done would
    export an empty slot instead of the card."""
    a = _loader(tmp_path, monkeypatch)
    a._load_project({"items": [{"ref": "x", "kind": "file", "status": "done",
                                "outputs": [str(tmp_path / "gone.png")]}]})
    assert a.items[0].status == "pending"
    assert a.items[0].outputs == []


def test_a_card_whose_files_are_there_comes_back_done(tmp_path, monkeypatch):
    """Saving after an upscale means not paying the AI for it twice."""
    real = tmp_path / "card.png"
    real.write_bytes(b"x")
    a = _loader(tmp_path, monkeypatch)
    a._load_project({"items": [{"ref": "x", "kind": "file", "status": "done",
                                "outputs": [str(real)]}]})
    assert a.items[0].status == "done"
    assert a.items[0].outputs == [real]


def test_a_half_missing_set_of_copies_is_not_trusted(tmp_path, monkeypatch):
    """Two of three files left is not a finished card."""
    ok = tmp_path / "a.png"
    ok.write_bytes(b"x")
    a = _loader(tmp_path, monkeypatch)
    a._load_project({"items": [{"ref": "x", "kind": "file", "status": "done",
                                "outputs": [str(ok), str(tmp_path / "b.png")]}]})
    assert a.items[0].status == "pending"


def test_a_model_override_is_restored(tmp_path, monkeypatch):
    a = _loader(tmp_path, monkeypatch)
    a._load_project({"items": [{"ref": "x", "kind": "scryfall",
                                "model": "UltraSharp"}]})
    assert a.items[0].model_menu.get() == "UltraSharp"


def test_a_nonsense_model_name_is_ignored(tmp_path, monkeypatch):
    """A project from a future version might name a model this build has no
    idea about; that must not leave the picker showing something unusable."""
    a = _loader(tmp_path, monkeypatch)
    a._load_project({"items": [{"ref": "x", "kind": "scryfall",
                                "model": "Some Future Model"}]})
    assert a.items[0].model_menu.get() == "Auto"


def test_loading_replaces_the_queue_rather_than_appending(tmp_path, monkeypatch):
    a = _loader(tmp_path, monkeypatch)
    a.items.append(_Item(label="already here"))
    a._load_project({"items": [{"ref": "x", "kind": "scryfall"}]})
    assert len(a.items) == 1
