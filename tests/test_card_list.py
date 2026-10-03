"""
Card list files.

The format exists because every other import here is Magic-only, so the cases
worth pinning are the ones that decide whether a non-Magic order survives the
trip: the game (which picks the card back and the card size), a card's own
back, and quantities. The file comes from outside the app, so the tests also
cover what it may not do - a `file://` image url is a download the user never
asked for.
"""

import json

import pytest

import cardlist


def _list(cards, **extra):
    return json.dumps({"format": "cardwright-list", "cards": cards, **extra})


def _card(**over):
    card = {"name": "Dark Magician",
            "image": "https://img.example/dm.jpg"}
    card.update(over)
    return card


def test_a_minimal_entry_needs_only_a_name_and_an_image():
    cards, problems = cardlist.parse_list(_list([_card()]))
    assert problems == []
    assert len(cards) == 1
    c = cards[0]
    assert c["name"] == "Dark Magician"
    assert c["download"] == "https://img.example/dm.jpg"
    assert c["qty"] == 1
    assert c["game"] == ""
    assert "back_download" not in c


def test_the_game_survives_and_takes_its_everyday_name():
    """The file should not have to know Magic is called "scryfall" in here."""
    cards, _ = cardlist.parse_list(_list([
        _card(game="ygo"), _card(game="mtg"), _card(game="Yu-Gi-Oh")]))
    assert [c["game"] for c in cards] == ["ygo", "scryfall", "ygo"]


def test_an_unknown_game_is_dropped_but_the_card_is_kept():
    """The image url is still good; only the back and the size needed the game."""
    cards, problems = cardlist.parse_list(_list([_card(game="lorcana")]))
    assert problems == []
    assert cards[0]["game"] == ""
    assert cards[0]["download"] == "https://img.example/dm.jpg"


def test_a_card_with_its_own_back_brings_both_faces():
    cards, _ = cardlist.parse_list(_list([
        _card(back="https://img.example/back.png")]))
    c = cards[0]
    assert c["back_download"] == "https://img.example/back.png"
    assert c["back_name"] == "Dark Magician back"


def test_entries_are_told_apart_by_position():
    """Two arts of one card share a name, and the download filename is built
    from it. Without something unique per entry they overwrite each other and
    one of the two arts is silently lost."""
    cards, _ = cardlist.parse_list(_list([
        _card(image="https://img.example/art1.jpg"),
        _card(image="https://img.example/art2.jpg")]))
    assert cards[0]["identifier"] != cards[1]["identifier"]


def test_the_note_rides_along_to_the_queue_label():
    """Which paper a card is printed on is not part of the card, but the
    person at the printer still needs to see it."""
    cards, _ = cardlist.parse_list(_list([_card(note="Premium 300g")]))
    assert cards[0]["note"] == "Premium 300g"
    assert cards[0]["source"] == "Premium 300g"


@pytest.mark.parametrize("image", [
    "file:///C:/Windows/System32/config",
    "data:image/png;base64,AAAA",
    "ftp://somewhere/card.png",
    "",
    None,
    12,
])
def test_only_http_images_are_accepted(image):
    """`download_to_temp` follows whatever it is handed, and this file came
    from outside the app."""
    cards, problems = cardlist.parse_list(_list([_card(image=image)]))
    assert cards == []
    assert problems and "image" in problems[0]


def test_a_non_http_back_is_dropped_without_losing_the_card():
    cards, problems = cardlist.parse_list(_list([
        _card(back="file:///etc/passwd")]))
    assert problems == []
    assert "back_download" not in cards[0]


@pytest.mark.parametrize("given,expected", [
    (3, 3), ("4", 4), (0, 1), (-2, 1), (None, 1), ("muchas", 1),
    (10_000, cardlist.MAX_QTY),
])
def test_quantities_are_clamped_to_something_believable(given, expected):
    cards, _ = cardlist.parse_list(_list([_card(quantity=given)]))
    assert cards[0]["qty"] == expected


def test_one_bad_entry_does_not_throw_away_the_good_ones():
    cards, problems = cardlist.parse_list(_list([
        _card(name="Blue-Eyes"),
        {"name": "sin imagen"},
        "no soy una carta",
        _card(name="Red-Eyes"),
    ]))
    assert [c["name"] for c in cards] == ["Blue-Eyes", "Red-Eyes"]
    assert len(problems) == 2


def test_a_file_claiming_another_format_is_refused():
    text = json.dumps({"format": "mpc-autofill", "cards": [_card()]})
    with pytest.raises(cardlist.CardListError):
        cardlist.parse_list(text)


def test_the_format_key_is_optional():
    cards, _ = cardlist.parse_list(json.dumps({"cards": [_card()]}))
    assert len(cards) == 1


@pytest.mark.parametrize("text", [
    "no soy json",
    "[]",
    json.dumps({"cards": "no soy una lista"}),
])
def test_a_file_that_is_not_a_card_list_says_so(text):
    with pytest.raises(cardlist.CardListError):
        cardlist.parse_list(text)


def test_an_empty_list_is_reported_rather_than_silently_adding_nothing():
    cards, problems = cardlist.parse_list(_list([]))
    assert cards == []
    assert problems


# --- images next to the list (a rendered batch: a zip of PNGs plus the list) ---

def _png(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\0" * 4000)
    return path


def test_an_image_next_to_the_list_is_accepted(tmp_path):
    card_file = _png(tmp_path / "cards" / "001-badlands.png")
    cards, problems = cardlist.parse_list(
        _list([_card(image="cards/001-badlands.png")]), base_dir=tmp_path)
    assert problems == []
    assert cards[0]["download"] == card_file.resolve().as_uri()


def test_a_local_back_is_accepted_too(tmp_path):
    _png(tmp_path / "front.png")
    back = _png(tmp_path / "back.png")
    cards, _ = cardlist.parse_list(
        _list([_card(image="front.png", back="back.png")]), base_dir=tmp_path)
    assert cards[0]["back_download"] == back.resolve().as_uri()


def test_without_the_lists_folder_a_path_is_not_an_image(tmp_path):
    """Pasted text has no folder: only urls mean anything there."""
    _png(tmp_path / "card.png")
    cards, problems = cardlist.parse_list(_list([_card(image="card.png")]))
    assert cards == [] and problems


@pytest.mark.parametrize("image", [
    "../outside.png",              # climbs out of the list's folder
    "cards/../../outside.png",
    "missing.png",                 # does not exist
    "notes.txt",                   # not a picture
])
def test_a_local_path_must_stay_inside_the_folder_and_be_an_image(tmp_path, image):
    folder = tmp_path / "batch"
    folder.mkdir()
    _png(tmp_path / "outside.png")
    (folder / "notes.txt").write_text("hola")
    cards, problems = cardlist.parse_list(_list([_card(image=image)]),
                                          base_dir=folder)
    assert cards == []
    assert problems and "image" in problems[0]


def test_an_absolute_path_is_refused_even_inside_the_folder(tmp_path):
    card_file = _png(tmp_path / "card.png")
    cards, _ = cardlist.parse_list(_list([_card(image=str(card_file))]),
                                   base_dir=tmp_path)
    assert cards == []


def test_a_local_image_is_copied_instead_of_downloaded(tmp_path, monkeypatch):
    import scryfall
    temp = tmp_path / "temp"
    temp.mkdir()
    monkeypatch.setattr(scryfall, "TEMP_FOLDER", temp)
    card_file = _png(tmp_path / "batch" / "card.png")
    target = scryfall.download_to_temp("Badlands", card_file.resolve().as_uri())
    assert target == temp / "Badlands.png"
    assert target.read_bytes() == card_file.read_bytes()
