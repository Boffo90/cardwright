"""
Selecting cards on the sheet.

With quantity and change-art living on a card, doing either to twenty of them
was twenty trips through the menu. A plain click now selects, which is what a
click means everywhere else; the black-border cycle it used to do moved into
the right-click menu, where it can at least say which state the card is in.
"""

import gui


def _dialog(n=4):
    d = gui.ExportDialog.__new__(gui.ExportDialog)
    d._order = [gui._Card(f"c{i}.png") for i in range(n)]
    d._selected = set()
    d._excluded = set()
    d._back_of = {c.uid: None for c in d._order}
    d._undo = []
    d._push_undo = lambda label: d._undo.append(label)
    d._draw_preview = lambda: None
    return d


def _uids(d):
    return [c.uid for c in d._order]


# ------------------------------------------------------------- selecting

def test_a_plain_click_replaces_the_selection():
    d = _dialog()
    d._select_only(_uids(d)[0])
    d._select_only(_uids(d)[2])
    assert d._selected == {_uids(d)[2]}


def test_shift_click_adds_and_removes():
    d = _dialog()
    a, b = _uids(d)[0], _uids(d)[1]
    d._select_only(a)
    d._toggle_selected(b)
    assert d._selected == {a, b}
    d._toggle_selected(b)
    assert d._selected == {a}


def test_clicking_nothing_clears():
    d = _dialog()
    d._select_only(_uids(d)[0])
    d._select_only(None)
    assert d._selected == set()


# ------------------------------------------------- what an action applies to

def test_acting_on_a_selected_card_takes_the_whole_selection():
    d = _dialog()
    a, b, c = _uids(d)[:3]
    d._selected = {a, b, c}
    assert set(d._targets(b)) == {a, b, c}


def test_acting_on_a_card_outside_the_selection_takes_only_it():
    """A right-click somewhere else is about that card. Quietly applying to a
    selection elsewhere on the sheet would be a nasty surprise."""
    d = _dialog()
    a, b = _uids(d)[0], _uids(d)[1]
    d._selected = {a}
    assert d._targets(b) == [b]


def test_a_selection_of_one_is_just_that_card():
    d = _dialog()
    a = _uids(d)[0]
    d._selected = {a}
    assert d._targets(a) == [a]


def test_targets_come_back_in_sheet_order():
    """So copies land predictably and undo labels count what you expect."""
    d = _dialog()
    order = _uids(d)
    d._selected = {order[2], order[0]}
    assert d._targets(order[0]) == [order[0], order[2]]


# --------------------------------------------------------------- batching

def test_adding_to_a_selection_is_one_undo_step():
    """Three cards, three copies added, one press of Ctrl+Z to take it back."""
    d = _dialog(3)
    d._selected = set(_uids(d))
    d._add_copies_to(d._targets(_uids(d)[0]), 1)
    assert len(d._order) == 6
    assert d._undo == ["add 1 to 3 cards"]


def test_adding_to_one_card_still_reads_singular():
    d = _dialog(3)
    d._add_copies_to([_uids(d)[0]], 2)
    assert d._undo == ["add 2 copies"]


def test_removing_a_selection_is_one_undo_step():
    d = _dialog(4)
    keys = _uids(d)[:3]
    d._selected = set(keys)
    d._remove_cards(keys)
    assert len(d._order) == 1
    assert d._undo == ["remove 3 cards"]


def test_removing_clears_those_cards_from_the_selection():
    """A card that is gone must not still be selected, or the next action
    would target something that no longer exists."""
    d = _dialog(3)
    keys = _uids(d)[:2]
    d._selected = set(_uids(d))
    d._remove_cards(keys)
    assert d._selected == {_uids(d)[0]}


def test_an_empty_batch_does_nothing_and_costs_no_undo():
    d = _dialog(2)
    d._add_copies_to([], 3)
    d._remove_cards([])
    assert len(d._order) == 2
    assert d._undo == []
