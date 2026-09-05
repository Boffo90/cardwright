"""
The card size follows an imported batch, not just a gallery pick.

`_apply_card_size_hint` used to live inside the gallery path only, so picking
one Yu-Gi-Oh card moved the size to 59x86 but importing sixty of them left it
on Magic's 63x88 - and fit-to-card stretched every one of them. Nothing caught
it because until card lists existed, every import was Magic.
"""

import config
import gui


class _Menu:
    """Stands in for the card-size option menu."""

    def __init__(self, value=config.CARD_SIZE_DEFAULT):
        self.value = value

    def get(self):
        return self.value

    def set(self, v):
        self.value = v


class _App:
    """The app, reduced to what `_add_resolved_cards` actually touches."""

    def __init__(self, size=config.CARD_SIZE_DEFAULT):
        self.card_size_menu = _Menu(size)
        self.persisted = []
        self.added = []

    _apply_card_size_hint = gui.App._apply_card_size_hint
    _add_resolved_cards = gui.App._add_resolved_cards

    def _persist_card_size(self, name):
        self.persisted.append(name)

    def _add_item(self, ref, kind, **kw):
        self.added.append((ref, kind, kw))


def _cards(*srcs):
    return [{"display": "Card", "qty": 1, "downloads": [("Card", "u")],
             "src": s} for s in srcs]


def test_a_yugioh_batch_moves_the_card_size():
    app = _App()
    app._add_resolved_cards(_cards("ygo", "ygo", "ygo"))
    assert app.card_size_menu.get().startswith("Yu-Gi-Oh")
    assert app.persisted == [app.card_size_menu.get()]


def test_a_magic_batch_leaves_the_size_alone():
    app = _App()
    app._add_resolved_cards(_cards("scryfall", "scryfall"))
    assert app.card_size_menu.get() == config.CARD_SIZE_DEFAULT
    assert app.persisted == []


def test_a_batch_mixing_games_moves_nothing():
    """There is no one right answer for a mixed order - Magic and Yu-Gi-Oh are
    two print runs at two sizes, and guessing one would silently stretch the
    other half."""
    app = _App()
    app._add_resolved_cards(_cards("ygo", "scryfall"))
    assert app.card_size_menu.get() == config.CARD_SIZE_DEFAULT


def test_a_size_the_user_chose_is_never_overruled():
    app = _App(size="Tarot (70×120 mm)")
    app._add_resolved_cards(_cards("ygo"))
    assert app.card_size_menu.get() == "Tarot (70×120 mm)"
    assert app.persisted == []


def test_an_unknown_game_moves_nothing():
    """A card list may name a game this app has no catalogue for."""
    app = _App()
    app._add_resolved_cards(_cards("card", "card"))
    assert app.card_size_menu.get() == config.CARD_SIZE_DEFAULT


def test_every_card_still_reaches_the_queue():
    app = _App()
    app._add_resolved_cards(_cards("ygo", "ygo"))
    assert len(app.added) == 2
    assert [kw["src"] for _, _, kw in app.added] == ["ygo", "ygo"]
