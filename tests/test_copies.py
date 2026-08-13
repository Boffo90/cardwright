"""
Quantity per card.

Copies are instances sharing one image, so "four of this card" is four entries
in the print order, not a number stored anywhere. What was missing was a way to
say four in one go: the old menu offered Duplicate, once per press.
"""

import gui


def _dialog(paths):
    d = gui.ExportDialog.__new__(gui.ExportDialog)
    d._order = [gui._Card(p) for p in paths]
    d._back_of = {c.uid: None for c in d._order}
    d._undo = []
    d._push_undo = lambda label: d._undo.append(label)
    d._draw_preview = lambda: None
    return d


def _names(d):
    return [c.path.stem for c in d._order]


def test_copies_land_together_after_the_card():
    """Copies go next to the original, not at the end: they are cut from the
    same sheet and hunting for them defeats the point."""
    d = _dialog(["a.png", "b.png"])
    d._add_copies(d._order[0].uid, 3)
    assert _names(d) == ["a", "a", "a", "a", "b"]


def test_a_copy_is_a_new_instance_of_the_same_image():
    d = _dialog(["a.png"])
    d._add_copies(d._order[0].uid, 1)
    first, second = d._order
    assert first.path == second.path, "same image"
    assert first.uid != second.uid, "addressed separately on the sheet"


def test_a_copy_inherits_the_original_back():
    d = _dialog(["a.png"])
    d._back_of[d._order[0].uid] = "its-back.png"
    d._add_copies(d._order[0].uid, 2)
    assert [d._back_of[c.uid] for c in d._order] == ["its-back.png"] * 3


def test_adding_several_is_one_undo_step():
    """Four presses of Ctrl+Z to take back one action would read as broken."""
    d = _dialog(["a.png"])
    d._add_copies(d._order[0].uid, 4)
    assert d._undo == ["add 4 copies"]


def test_adding_one_reads_as_singular():
    d = _dialog(["a.png"])
    d._add_copies(d._order[0].uid, 1)
    assert d._undo == ["add 1 copy"]


def test_a_silly_number_is_capped_rather_than_obeyed():
    d = _dialog(["a.png"])
    d._add_copies(d._order[0].uid, 5000)
    assert len(d._order) == 1 + gui.ExportDialog._MAX_COPIES


def test_zero_or_negative_does_nothing():
    for n in (0, -3):
        d = _dialog(["a.png"])
        d._add_copies(d._order[0].uid, n)
        assert len(d._order) == 1
        assert d._undo == []


def test_an_unknown_card_is_ignored():
    d = _dialog(["a.png"])
    d._add_copies("not-a-card", 2)
    assert len(d._order) == 1
    assert d._undo == []


# ------------------------------------------------------------- the counter

def test_the_count_includes_the_card_itself():
    d = _dialog(["a.png", "b.png"])
    assert d._copies_of(d._order[0].uid) == 1


def test_the_count_follows_the_image_not_the_instance():
    """Two copies are two instances of one path, and the menu has to say 3x
    for every one of them."""
    d = _dialog(["a.png", "b.png"])
    d._add_copies(d._order[0].uid, 2)
    counts = [d._copies_of(c.uid) for c in d._order if c.path.stem == "a"]
    assert counts == [3, 3, 3]
    assert d._copies_of(next(c.uid for c in d._order if c.path.stem == "b")) == 1


def test_counting_an_unknown_card_is_zero():
    d = _dialog(["a.png"])
    assert d._copies_of("not-a-card") == 0
