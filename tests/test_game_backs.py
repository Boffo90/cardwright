"""
Card backs chosen per game.

A sheet mixing Magic and Pokemon used to print one back over all of it, which
is wrong on half the cards. The catalogue a card came from says which game it
is, so the right back can be picked per card. The images stay user-supplied:
the artwork belongs to Wizards, Nintendo and Konami, and shipping it inside a
downloadable binary is not the same as a website serving it.
"""

import pytest

import config


@pytest.fixture
def backs(tmp_path, monkeypatch):
    """Point the lookup at a temp folder and let a test drop files in it."""
    monkeypatch.setattr(config, "ROOT", tmp_path)
    monkeypatch.setattr(config, "BACK_IMAGE_CANDIDATES",
                        [tmp_path / "back.png", tmp_path / "back.jpg"])

    def put(*names):
        for n in names:
            (tmp_path / n).write_bytes(b"not really a png")
    return put


def test_each_game_gets_its_own_back(backs):
    backs("back-mtg.png", "back-pokemon.png", "back-yugioh.png")
    assert config.find_back_image("scryfall").name == "back-mtg.png"
    assert config.find_back_image("pokemon").name == "back-pokemon.png"
    assert config.find_back_image("ygo").name == "back-yugioh.png"


def test_gatherer_and_mpc_are_magic_too(backs):
    backs("back-mtg.png")
    assert config.find_back_image("gatherer").name == "back-mtg.png"
    assert config.find_back_image("mpc").name == "back-mtg.png"


def test_a_missing_game_back_falls_through_to_the_plain_one(backs):
    """Anyone with a single back keeps exactly the behaviour they had."""
    backs("back.png")
    assert config.find_back_image("pokemon").name == "back.png"


def test_no_source_uses_the_plain_back(backs):
    backs("back.png", "back-mtg.png")
    assert config.find_back_image(None).name == "back.png"


def test_an_unknown_source_uses_the_plain_back(backs):
    backs("back.png", "back-mtg.png")
    assert config.find_back_image("some-future-catalogue").name == "back.png"


def test_jpg_is_accepted_for_a_game_back(backs):
    backs("back-pokemon.jpg")
    assert config.find_back_image("pokemon").name == "back-pokemon.jpg"


def test_png_wins_over_jpg(backs):
    backs("back-pokemon.png", "back-pokemon.jpg")
    assert config.find_back_image("pokemon").name == "back-pokemon.png"


def test_nothing_at_all_is_not_an_error(backs):
    assert config.find_back_image("scryfall") is None
    assert config.find_back_image() is None


def test_every_source_the_app_offers_maps_somewhere():
    """A catalogue with no entry here silently gets the generic back, so this
    fails when a game is added and its back is forgotten."""
    import sources
    for src in sources.ALL:
        assert src.ID in config.GAME_BACKS, f"{src.ID} has no card back mapping"
