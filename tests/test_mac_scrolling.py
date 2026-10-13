"""
Scrolling on macOS under Tk 9.

Tk 8.7 made a wheel notch report ±120 on macOS (it was ±1..±n) and sends
trackpad scrolling as <TouchpadScroll>, so customtkinter's darwin branch threw
lists ~960 px per notch and trackpads did nothing. These cover the conversion
helpers from any OS, assert that Windows still takes customtkinter's and the
preview's original paths, and, where Tk 9 is available, drive a real frame.
They also cover the filter on the window's own <Configure> handler, which macOS
ran once per widget on every scroll step.
"""

import sys
import tkinter as tk

import customtkinter as ctk
import pytest

import gui


def _pack(dx, dy):
    """Pack pixel deltas the way Tk does for <TouchpadScroll>."""
    return (dx << 16) | (dy & 0xFFFF)


class _FakeCanvas:
    """Just enough canvas for _scroll_canvas_px: a 200 px view of 1000 px."""

    def __init__(self, first=0.2, visible=200, content=1000):
        self.first, self.visible, self.content = first, visible, content
        self.moves, self.units = [], []

    def yview(self, *args):
        if args:
            self.moves.append(args)
            return None
        return self.first, self.first + self.visible / self.content

    def xview(self, *args):
        assert not args, "nothing here scrolls sideways"
        return 0.0, 1.0

    def winfo_width(self):
        return 300

    def winfo_height(self):
        return self.visible

    def yview_scroll(self, n, what):
        self.units.append((n, what))


# ------------------------------------------------------------- conversions

def test_a_tk9_notch_scrolls_a_fixed_step_not_120_units(monkeypatch):
    monkeypatch.setattr(gui, "_MAC_TK9", True)
    assert gui.wheel_pixels(120) == -gui.WHEEL_STEP_PX      # up
    assert gui.wheel_pixels(-240) == 2 * gui.WHEEL_STEP_PX  # two notches down


def test_a_tk86_notch_still_scrolls(monkeypatch):
    """±1 is a whole notch there; dividing by 120 rounded it to nothing."""
    monkeypatch.setattr(gui, "_MAC_TK9", False)
    assert gui.wheel_pixels(1) == -8
    assert gui.wheel_pixels(-3) == 24


@pytest.mark.parametrize("dx, dy", [(0, -5), (0, 7), (-3, -5), (4, 300),
                                    (-1, -1), (0, -32768), (12, 32767)])
def test_touchpad_deltas_unpack_like_tk(dx, dy):
    # Tk scrolls by the negated deltas: fingers up moves the content down.
    assert gui.touchpad_pixels(_pack(dx, dy)) == (-dx, -dy)


def test_scroll_canvas_px_moves_by_pixels():
    c = _FakeCanvas(first=0.2)
    gui._scroll_canvas_px(c, 0, 50)
    assert c.moves == [("moveto", pytest.approx(0.25))]


def test_scroll_canvas_px_leaves_content_that_fits_alone():
    c = _FakeCanvas(first=0.0, content=200)
    gui._scroll_canvas_px(c, 0, 50)
    assert c.moves == []


# ------------------------------------------------------ Windows is untouched

def test_windows_frames_keep_customtkinters_wheel_handling(monkeypatch):
    seen = []
    monkeypatch.setattr(gui, "_MAC_TK9", False)
    monkeypatch.setattr(ctk.CTkScrollableFrame, "_mouse_wheel_all",
                        lambda self, e: seen.append(e))
    f = gui.ScrollableFrame.__new__(gui.ScrollableFrame)
    f._mouse_wheel_all("event")
    assert seen == ["event"]


def _preview(canvas):
    d = gui.ExportDialog.__new__(gui.ExportDialog)
    d.canvas = canvas
    return d


def test_windows_preview_still_scrolls_in_units(monkeypatch):
    monkeypatch.setattr(gui, "IS_WINDOWS", True)
    c = _FakeCanvas()
    _preview(c)._preview_wheel(type("E", (), {"delta": -120})())
    assert c.units == [(1, "units")] and c.moves == []


def test_mac_preview_scrolls_on_a_tk86_notch(monkeypatch):
    monkeypatch.setattr(gui, "IS_WINDOWS", False)
    monkeypatch.setattr(gui, "_MAC_TK9", False)
    c = _FakeCanvas(first=0.2)
    _preview(c)._preview_wheel(type("E", (), {"delta": -1})())
    assert c.moves == [("moveto", pytest.approx(0.2 + 8 / 1000))]


# ------------------------------------------------------ a real Tk 9 frame

@pytest.mark.skipif(sys.platform == "win32" or tk.TkVersion < 8.7,
                    reason="<TouchpadScroll> is the macOS Tk 9 event")
def test_real_frame_follows_trackpad_and_wheel():
    try:
        root = ctk.CTk()
    except tk.TclError as e:
        pytest.skip(f"no display: {e}")
    try:
        root.geometry("300x200")
        frame = gui.ScrollableFrame(root, height=150)
        frame.pack(fill="both", expand=True)
        rows = [ctk.CTkLabel(frame, text=f"row {i}") for i in range(60)]
        for r in rows:
            r.pack()
        root.update()
        canvas = frame._parent_canvas
        target = rows[3]
        assert canvas.yview()[0] == 0.0

        target.event_generate("<TouchpadScroll>", delta=_pack(0, -30),
                              when="now")
        root.update()
        after_trackpad = canvas.yview()[0]
        assert after_trackpad > 0.0, "trackpad did not scroll"

        target.event_generate("<MouseWheel>", delta=-120, when="now")
        root.update()
        first, last = canvas.yview()
        content = canvas.winfo_height() / (last - first)
        moved = (first - after_trackpad) * content
        # one notch is a step, not the ~960 px customtkinter would scroll
        assert moved == pytest.approx(gui.WHEEL_STEP_PX, abs=2)
    finally:
        root.destroy()


# ---------------------------------------- the window's own <Configure> handler

class _FakeWindow:
    _w = ".!exportdialog"

    def __init__(self, script):
        self.script = script

    def bind(self, seq, script=None):
        assert seq == "<Configure>"
        if script is None:
            return self.script
        self.script = script


def test_window_handler_only_runs_for_the_window_itself():
    ctk_line = ('if {"[123_update_dimensions_event %# %W]" == "break"} break')
    other = 'if {"[456_on_resize %W]" == "break"} break'
    w = _FakeWindow(ctk_line + "\n" + other + "\n")
    gui._window_configure_only(w)
    lines = w.script.splitlines()
    assert lines[0] == f'if {{"%W" eq "{w._w}"}} {{{ctk_line}}}'
    assert lines[1] == other, "the app's own bindings must be left alone"
    # a second scrollable frame in the same window must not wrap it again
    gui._window_configure_only(w)
    assert w.script.splitlines() == lines


@pytest.fixture
def root():
    try:
        r = ctk.CTk()
    except tk.TclError as e:
        pytest.skip(f"no display: {e}")
    r.geometry("300x200")
    yield r
    r.destroy()


def test_window_still_tracks_its_own_resize(monkeypatch, root):
    monkeypatch.setattr(gui, "IS_WINDOWS", False)
    gui.ScrollableFrame(root).pack(fill="both", expand=True)
    root.update()
    assert "%W" in root.bind("<Configure>")
    root.geometry("420x330")
    root.update()
    assert (root._current_width, root._current_height) == (420, 330)


def test_windows_leaves_the_window_binding_alone(monkeypatch, root):
    monkeypatch.setattr(gui, "IS_WINDOWS", True)
    monkeypatch.setattr(gui, "_MAC_TK9", False)
    before = root.bind("<Configure>")
    gui.ScrollableFrame(root)
    assert root.bind("<Configure>") == before
