"""
Where a dragged card lands, and where the preview says it will.

The old behaviour reordered relative to whichever card you dropped on and
always inserted before it, so the only way to learn the result was to let go.
These cover the insertion model that replaced it: a slot is split down the
middle, empty slots are targets too, and the index the indicator was drawn from
is the index the move uses.
"""

import gui


def _dialog(n):
    """An ExportDialog with `n` cards and no Tk behind it."""
    d = gui.ExportDialog.__new__(gui.ExportDialog)
    d._order = [gui._Card(f"card{i}.png") for i in range(n)]
    d._img_xoff = 0
    d._undo = []
    d._push_undo = lambda label: d._undo.append(label)
    d._draw_preview = lambda: None
    return d


def _slot(d, i, key_index, w=100):
    """Register one drop target: slot i, holding the card at key_index."""
    key = d._order[key_index].uid if key_index is not None else None
    x0 = i * w
    d._drops.append((x0, 0, x0 + w, 140, key))
    return x0


def _grid(d, filled, empties=0, w=100):
    d._drops = []
    for i in range(filled):
        _slot(d, i, i, w)
    for j in range(empties):
        _slot(d, filled + j, None, w)


# ------------------------------------------------------------ where it lands

def test_the_left_half_of_a_slot_means_before_it():
    d = _dialog(3)
    _grid(d, 3)
    idx, x, _, _ = d._drop_at(120, 50)      # slot 1, left half
    assert idx == 1
    assert x == 100, "the line belongs on the leading edge"


def test_the_right_half_of_a_slot_means_after_it():
    d = _dialog(3)
    _grid(d, 3)
    idx, x, _, _ = d._drop_at(180, 50)      # slot 1, right half
    assert idx == 2
    assert x == 200, "the line belongs on the trailing edge"


def test_an_empty_slot_appends_to_the_end():
    d = _dialog(3)
    _grid(d, 3, empties=2)
    idx, _, _, _ = d._drop_at(350, 50)      # first empty slot
    assert idx == 3 == len(d._order)


def test_pointing_at_nothing_is_not_a_drop():
    d = _dialog(3)
    _grid(d, 3)
    assert d._drop_at(9999, 50) is None


# ------------------------------------------------------------- the move

def _uids(d):
    return [c.uid for c in d._order]


def test_moving_a_card_forward_does_not_land_a_slot_late():
    """Pulling the card out shifts everything after it down one. Forgetting
    that is the classic off-by-one, and it puts the card one slot past where
    the indicator promised."""
    d = _dialog(4)
    before = _uids(d)
    d._reorder(before[0], 3)          # card0 goes before card3
    assert _uids(d) == [before[1], before[2], before[0], before[3]]


def test_moving_a_card_backward_lands_where_the_line_was():
    d = _dialog(4)
    before = _uids(d)
    d._reorder(before[3], 1)          # card3 goes before card1
    assert _uids(d) == [before[0], before[3], before[1], before[2]]


def test_dropping_at_the_end_puts_the_card_last():
    d = _dialog(3)
    before = _uids(d)
    d._reorder(before[0], 3)
    assert _uids(d) == [before[1], before[2], before[0]]


def test_dropping_either_side_of_itself_changes_nothing():
    for index_offset in (0, 1):
        d = _dialog(3)
        before = _uids(d)
        d._reorder(before[1], 1 + index_offset)
        assert _uids(d) == before
        assert d._undo == [], "a no-op must not cost an undo step"


def test_a_real_move_is_undoable():
    d = _dialog(3)
    d._reorder(d._order[0].uid, 2)
    assert d._undo == ["move card"]


# ------------------------------------------------- edge scroll while dragging
# Every sheet lives in one scrolling canvas, so a card can be dragged to any of
# them, but only if the view follows. The old code scrolled one notch per
# motion event, so resting at the edge did nothing and crossing a sheet took
# about ten deliberate wiggles. These cover the decision, not the animation.

class _FakeCanvas:
    def __init__(self, height):
        self._h = height

    def winfo_height(self):
        return self._h


def _dragging(cursor_y, height=560):
    d = gui.ExportDialog.__new__(gui.ExportDialog)
    d.canvas = _FakeCanvas(height)
    d._drag = {"key": "card1", "moved": True}
    d._drag_pos = (200, cursor_y)
    d._scroll_job = None
    d._scroll_dir = 0
    d._scroll_step = 0.0
    d._scheduled = []
    d.after = lambda ms, fn: (d._scheduled.append(ms), "job")[1]
    d.after_cancel = lambda job: d._scheduled.clear()
    return d


def test_the_top_edge_scrolls_up():
    d = _dragging(cursor_y=5)
    d._autoscroll()
    assert d._scroll_dir == -1
    assert d._scroll_job is not None, "resting at the edge has to keep scrolling"


def test_the_bottom_edge_scrolls_down():
    d = _dragging(cursor_y=558)
    d._autoscroll()
    assert d._scroll_dir == 1
    assert d._scroll_job is not None


def test_the_middle_of_the_canvas_does_not_scroll():
    d = _dragging(cursor_y=280)
    d._autoscroll()
    assert d._scroll_job is None


def test_leaving_the_band_stops_an_active_scroll():
    d = _dragging(cursor_y=5)
    d._autoscroll()
    assert d._scroll_job is not None
    d._drag_pos = (200, 280)
    d._autoscroll()
    assert d._scroll_job is None


def test_deeper_into_the_band_scrolls_faster():
    shallow = _dragging(cursor_y=38)
    shallow._autoscroll()
    deep = _dragging(cursor_y=1)
    deep._autoscroll()
    assert deep._scroll_step > shallow._scroll_step
    assert shallow._scroll_step >= gui.ExportDialog._EDGE_MIN
    assert deep._scroll_step <= gui.ExportDialog._EDGE_MAX


def test_releasing_the_card_stops_the_scroll():
    d = _dragging(cursor_y=5)
    d._autoscroll()
    d._drag = None
    d._autoscroll()
    assert d._scroll_job is None
