import io
import json
import os
import re
import subprocess
import threading
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import numpy as np
from PIL import Image as PILImage, ImageDraw as PILDraw, ImageTk as PILImageTk
from reportlab.lib.units import mm as mm_pt      # 1 mm in PDF points

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    _DND = True
except Exception:
    _DND = False

from config import (
    WINDOW_TITLE,
    WINDOW_WIDTH,
    WINDOW_HEIGHT,
    MODELS,
    DEFAULT_MODEL,
    AUTO_MODEL,
    OUTPUT_FOLDER,
    SUPPORTED_INPUT,
    FIT_TO_CARD_DEFAULT,
    MPC_TRIM_DEFAULT,
    BLEED_MODES,
    BLEED_MODE_DEFAULT,
    bleed_mode_code,
    PARALLEL_JOBS,
    PDF_PAGE_SIZES,
    PDF_DEFAULT_PAGE,
    PDF_QUALITY_MODES,
    PDF_DEFAULT_QUALITY,
    PAGES_PER_FILE,
    PAGES_PER_FILE_DEFAULT,
    OUTPUT_FORMATS,
    OUTPUT_FORMAT_DEFAULT,
    OUTPUT_DPI_CHOICES,
    OUTPUT_DPI_DEFAULT,
    SHARPEN_MODES,
    SHARPEN_DEFAULT,
    SHADOW_LIFTS,
    SHADOW_DEFAULT,
    BORDER_MODES,
    BORDER_SOURCES,
    border_mode,
    BORDER_DEFAULT,
    BORDER_AMOUNT_DEFAULT,
    BORDER_WIDTH_DEFAULT,
    CALIBRATION_PROFILES,
    BACKS_MODES,
    CARD_SIZES,
    CARD_SIZE_DEFAULT,
    CUSTOM_SIZE_EDIT,
    CUSTOM_SIZE_MIN_MM,
    CUSTOM_SIZE_MAX_MM,
    card_size_options,
    custom_card_size,
    save_custom_card_size,
    CARD_LANGS,
    CARD_LANG_DEFAULT,
    BEST_SCAN_DEFAULT,
    card_lang_code,
    card_size_mm,
    find_back_image,
    GAME_BACKS,
    ICON_FILE,
    IS_WINDOWS,
    load_settings,
    save_settings,
)
from upscale import upscale
import applog
import scryfall
import sources
import mpcfill
import ygoprodeck
import print_sheet
import bootstrap
import update as app_update
import theme
from version import APP_NAME, APP_VERSION, DONATE_URL, GITHUB_REPO


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")


def _has_font(name: str) -> bool:
    """Segoe UI Variable ships with Windows 11; fall back on older systems."""
    try:
        from tkinter import font as tkfont
        return name in tkfont.families()
    except Exception:
        return False


def _open_folder(path):
    """
    Show a folder in the system file manager (Explorer / Finder).

    os.startfile is Windows-only. `open` reports failure through its exit
    status rather than an exception, so that is translated into the OSError
    callers already expect from startfile.
    """
    if IS_WINDOWS:
        os.startfile(path)
        return
    if subprocess.run(["open", str(path)]).returncode != 0:
        raise OSError(f"could not open {path}")

# ---- palette ------------------------------------------------------------
# Everything comes from theme.py so the whole app shares one set of tokens.
# These aliases keep the historical names used throughout this file.
BG         = theme.BG
PANEL      = theme.SURFACE
ROW        = theme.SURFACE_ALT
GOLD       = theme.ACCENT            # primary actions / active state
GOLD_HOVER = theme.ACCENT_HOVER
GOLD_TEXT  = theme.ON_ACCENT
BLUE       = theme.CONTROL           # secondary actions are neutral now
BLUE_HOVER = theme.CONTROL_HOVER
GRAY_BTN   = theme.CONTROL
GRAY_HOVER = theme.CONTROL_HOVER
MUTED      = theme.TEXT_MUTED
TEXT       = theme.TEXT
TEXT_DIM   = theme.TEXT_DIM
BORDER     = theme.BORDER
BORDER_STRONG = theme.BORDER_STRONG

CONTROL_ALT = theme.SURFACE_HOVER
SURFACE_INPUT = theme.BG           # inputs sit darker than their panel
TEXT_MUTED_ = theme.TEXT_MUTED     # section eyebrows

# resolved once the Tk root exists (font families need one) - see App.__init__
UI = theme.FONT_FALLBACK


def _switch(parent, text, **kw):
    """Switch styled with the accent, so nothing keeps CTk's default blue."""
    return ctk.CTkSwitch(
        parent, text=text, font=(UI, theme.TYPE["body"]), text_color=TEXT_DIM,
        progress_color=theme.ACCENT, button_color=theme.TEXT,
        button_hover_color="#FFFFFF", fg_color=theme.SURFACE_HOVER,
        width=40, switch_width=38, switch_height=18, **kw)


# short per-row model names -> full config labels (None = follow global menu)
ROW_MODELS = {
    "Auto": None,
    "Anime v3": "AnimeVideo v3 x4 (scanned cards)",
    "Hi-Fi": "High Fidelity x4 (digital renders)",
    "UltraSharp": "UltraSharp x4 (max crisp, flat art)",
    "x4+ real": "Real-ESRGAN x4+ (realistic art / faces)",
}

# status -> (dot color, text color)
STATUS_COLORS = {
    # (dot, caption) - muted while idle, accent while working, semantic at rest
    "pending":    (theme.TEXT_MUTED, theme.TEXT_MUTED),
    "processing": (theme.ACCENT, theme.TEXT_DIM),
    "done":       (theme.SUCCESS, theme.TEXT_MUTED),
    "error":      (theme.DANGER, theme.DANGER),
}


# --------------------------------------------------------------------------
# root that also supports drag & drop (tkinterdnd2 mixed into CTk)
# --------------------------------------------------------------------------
if _DND:
    class _Root(ctk.CTk, TkinterDnD.DnDWrapper):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self.TkdndVersion = TkinterDnD._require(self)
else:
    _Root = ctk.CTk


# --------------------------------------------------------------------------
# a single row in the queue
# --------------------------------------------------------------------------
# Only images that could actually carry an MPC bleed edge are eligible for the
# trim. The trim is decided by aspect ratio, and a 600x825 TCGdex Pokemon
# image lands at 0.7273 - inside the 0.725-0.745 MPC window - so it was being
# cropped by 4.4% a side, eating the card's border. Scryfall (0.7163) and
# Gatherer (0.7162) sit outside the window, which is why this only ever showed
# up on Pokemon.
#
# Local files keep the heuristic: someone can perfectly well feed in an MPC
# download by hand, and there is nothing else to go on there.
_BLEED_CAPABLE_SOURCES = {"mpc", "file"}


def _may_have_bleed(item) -> bool:
    return getattr(item, "src", "file") in _BLEED_CAPABLE_SOURCES


class QueueItem(ctk.CTkFrame):
    def __init__(self, master, ref, kind, on_remove, downloads=None, label=None,
                 qty=1, released_at=None, set_code=None, on_status=None):
        super().__init__(master, corner_radius=theme.RADIUS_MD, fg_color=ROW,
                         border_width=1, border_color=BORDER)
        self.ref = ref              # file path or scryfall reference
        self.kind = kind            # "file" | "scryfall" | "card"
        self.downloads = downloads  # for "card": [(basename, png_url), ...]
        self.qty = qty              # number of physical copies requested
        self.released_at = released_at  # "YYYY-MM-DD" or None (Auto mode hint)
        self.set_code = set_code    # Scryfall set code or None (Auto mode hint)
        self.outputs = []           # produced files (incl. qty copies)
        self.status = "pending"
        self.on_remove = on_remove
        self.on_status = on_status  # notified after every status change

        self.grid_columnconfigure(1, weight=1)

        self.dot = ctk.CTkLabel(self, text="●", width=14,
                                text_color=STATUS_COLORS["pending"][0],
                                font=(UI, 11))
        self.dot.grid(row=0, column=0, padx=(12, 6), pady=8)

        if label is not None:
            pass
        elif kind == "file":
            label = Path(ref).name
        else:
            label = ref
        self.label = label          # untrimmed, so a project can restore it
        self.name = ctk.CTkLabel(self, text=self._trim(label), anchor="w",
                                 text_color=TEXT,
                                 font=(UI, theme.TYPE["body"]))
        self.name.grid(row=0, column=1, sticky="ew", pady=(8, 0))

        self.info = ctk.CTkLabel(self, text="Pending", anchor="w",
                                 text_color=STATUS_COLORS["pending"][1],
                                 font=(UI, theme.TYPE["caption"]))
        self.info.grid(row=1, column=1, sticky="ew", pady=(0, 8))

        self.model_menu = ctk.CTkOptionMenu(
            self, values=list(ROW_MODELS.keys()), width=104, height=28,
            font=(UI, theme.TYPE["caption"]), corner_radius=theme.RADIUS_SM,
            fg_color=SURFACE_INPUT, button_color=CONTROL_ALT,
            button_hover_color=GRAY_HOVER, text_color=TEXT_DIM,
            dropdown_fg_color=ROW, dropdown_text_color=TEXT,
            dropdown_hover_color=GRAY_HOVER,
            command=self._model_changed)
        self.model_menu.set("Auto")
        self.model_menu.grid(row=0, column=2, rowspan=2, padx=(4, 2))

        self.bar = ctk.CTkProgressBar(self, height=4, width=120,
                                      corner_radius=2, fg_color=SURFACE_INPUT,
                                      progress_color=GOLD)
        self.bar.set(0)
        self.bar.grid(row=0, column=3, rowspan=2, padx=8)

        self.remove_btn = ctk.CTkButton(self, text="✕", width=28, height=28,
                                        corner_radius=theme.RADIUS_SM,
                                        font=(UI, theme.TYPE["small"]),
                                        text_color=MUTED,
                                        fg_color="transparent", hover_color=GRAY_HOVER,
                                        command=lambda: on_remove(self))
        self.remove_btn.grid(row=0, column=4, rowspan=2, padx=(0, 10))

    @property
    def model_override(self):
        return ROW_MODELS.get(self.model_menu.get())

    def _model_changed(self, _choice):
        # picking a new model on a finished card re-queues it, so
        # UPSCALE ALL will redo it (output file gets overwritten)
        if self.status in ("done", "error"):
            self.set_status("pending", "Re-queued (model changed)", 0)

    def _trim(self, text, n=54):
        return text if len(text) <= n else text[: n - 1] + "…"

    def set_status(self, status, info=None, progress=None):
        changed = status != self.status
        self.status = status
        dot_c, txt_c = STATUS_COLORS[status]
        self.dot.configure(text_color=dot_c)
        self.info.configure(text=info or status.capitalize(), text_color=txt_c)
        if progress is not None:
            self.bar.set(progress)
        if status == "done":
            self.bar.set(1)
        if changed and self.on_status:
            self.on_status(self)


# --------------------------------------------------------------------------
# main application
# --------------------------------------------------------------------------
class App(_Root):
    def __init__(self):
        super().__init__()
        global UI
        if _has_font(theme.FONT):        # needs a live Tk root, so not at import
            UI = theme.FONT
        self.title(WINDOW_TITLE)
        self.geometry(f"{WINDOW_WIDTH}x{WINDOW_HEIGHT}")
        self.minsize(900, 620)
        self.configure(fg_color=BG)
        try:
            self.iconbitmap(str(ICON_FILE))
        except Exception:
            pass

        self.items: list[QueueItem] = []
        self.running = False
        self.ai_ok = load_settings().get("gpu_ok", True)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        self._build_header()
        self._build_inputs()
        self._build_queue()
        self._build_footer()

        if _DND:
            self.queue_frame.drop_target_register(DND_FILES)
            self.queue_frame.dnd_bind("<<Drop>>", self._on_drop)

        # first-run setup (engine/models download + GPU probe)
        if bootstrap.missing_components():
            self.after(400, lambda: SetupDialog(self))
        elif "gpu_ok" not in load_settings():
            threading.Thread(target=self._probe_gpu_silent, daemon=True).start()

        # a failed update leaves the download behind; don't keep 38 MB around
        app_update.cleanup_leftovers()

        # silent update check
        threading.Thread(target=self._check_update, daemon=True).start()

    def _probe_gpu_silent(self):
        ok, name = bootstrap.probe_gpu()
        self.ai_ok = ok
        if not ok:
            self._ui(messagebox.showwarning, "No compatible GPU",
                     "No Vulkan-compatible GPU was found.\n\nThe app will "
                     "still work, but cards are resized without AI "
                     "enhancement.")

    def _check_update(self):
        info = app_update.check_for_update()
        if info:
            self._ui(self._show_update, info)

    def _show_update(self, info):
        self.update_btn = ctk.CTkButton(
            self.header, text=f"Update {info['version']} ↓", width=120,
            fg_color=GOLD, hover_color=GOLD_HOVER, text_color=GOLD_TEXT,
            command=lambda: self._apply_update(info))
        self.update_btn.pack(side="right", padx=4)

    def _apply_update(self, info):
        if self.running:
            messagebox.showinfo("Busy", "Finish the current batch first.")
            return
        if not messagebox.askyesno(
                "Update available",
                f"Version {info['version']} is available. Download and "
                f"restart now?\n\n{info['notes'][:400]}"):
            return
        self.update_btn.configure(state="disabled", text="Downloading…")

        def run():
            try:
                app_update.apply_update(info["url"])
                self._ui(self._quit_for_update)
            except Exception as e:
                self._ui(messagebox.showerror, "Update failed", str(e))
                self._ui(lambda: self.update_btn.configure(
                    state="normal", text=f"Update {info['version']} ↓"))

        threading.Thread(target=run, daemon=True).start()

    def _quit_for_update(self):
        """
        Exit immediately so the swap script can replace the exe. We skip the
        normal teardown on purpose: this process is being replaced, and a
        slow/erroring shutdown would keep the file locked.
        """
        try:
            self.destroy()
        except Exception:
            pass
        os._exit(0)

    # ---------------------------------------------------------------- header
    def _build_header(self):
        self.header = header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(20, 6))
        ctk.CTkLabel(header, text=APP_NAME,
                     font=(UI, theme.TYPE["display"], "bold"),
                     text_color=TEXT).pack(side="left")
        ctk.CTkLabel(header, text="1200 DPI print-ready proxies",
                     font=(UI, theme.TYPE["small"]),
                     text_color=MUTED).pack(side="left", padx=(10, 0), pady=(6, 0))
        ctk.CTkLabel(header, text=f"v{APP_VERSION}",
                     font=(UI, theme.TYPE["caption"]),
                     text_color=MUTED).pack(side="right", pady=(6, 0))
        ctk.CTkButton(header, text="Donate", width=76, height=28,
                      fg_color="transparent", hover_color=GRAY_HOVER,
                      border_width=1, border_color=GOLD, text_color=GOLD,
                      font=(UI, 12),
                      command=lambda: webbrowser.open(DONATE_URL)).pack(
            side="right", padx=(4, 10), pady=(10, 0))
        ctk.CTkButton(header, text="Help", width=58, height=28,
                      fg_color="transparent", hover_color=GRAY_HOVER,
                      border_width=1, border_color=BORDER_STRONG,
                      text_color=TEXT_DIM, font=(UI, 12),
                      command=lambda: HelpDialog(self)).pack(
            side="right", padx=(4, 0), pady=(10, 0))
        # A bug report is only as good as what the reporter can attach.
        ctk.CTkButton(header, text="Log", width=52, height=28,
                      fg_color="transparent", hover_color=GRAY_HOVER,
                      border_width=1, border_color=BORDER_STRONG,
                      text_color=TEXT_DIM, font=(UI, 12),
                      command=self._open_log).pack(
            side="right", padx=(4, 0), pady=(10, 0))

    def _open_log(self):
        """Show the log file in the file manager, ready to drag onto a report."""
        path = applog.LOG_PATH
        if not path.exists():
            messagebox.showinfo(
                "No log yet",
                f"Nothing has been logged yet.\n\nThe file will appear at:\n{path}")
            return
        try:
            _open_folder(path.parent)
        except OSError:
            applog.log.error("Could not open the log folder", exc_info=True)
            messagebox.showinfo("Log file", str(path))

    # ---------------------------------------------------------------- inputs
    def _build_inputs(self):
        bar = ctk.CTkFrame(self, corner_radius=12, fg_color=PANEL)
        bar.grid(row=1, column=0, sticky="ew", padx=24, pady=8)
        bar.grid_columnconfigure(0, weight=1)

        self.ref_entry = ctk.CTkEntry(
            bar, height=theme.H_BUTTON_LG, fg_color=SURFACE_INPUT,
            border_color=BORDER_STRONG, corner_radius=theme.RADIUS_SM,
            font=(UI, theme.TYPE["body"]), text_color=TEXT,
            # Naming the exact-printing form here is the whole documentation
            # most people will ever read: it was supported all along and a user
            # asked for it as a feature, because nothing said it existed.
            placeholder_text="Card name, \"Sol Ring (SLD) 2560\" for one exact "
                             "printing, or a Scryfall / Gatherer link")
        self.ref_entry.grid(row=0, column=0, sticky="ew", padx=(12, 8), pady=12)
        self.ref_entry.bind("<Return>", lambda e: self._add_scryfall())

        ctk.CTkButton(bar, text="Add card", width=100, height=40,
                      fg_color=GOLD, hover_color=GOLD_HOVER, text_color=GOLD_TEXT,
                      font=(UI, 13, "bold"),
                      command=self._add_scryfall).grid(row=0, column=1, padx=4, pady=12)
        # One secondary tier, one width, one colour. The per-catalogue buttons
        # are gone: every catalogue is a tab inside the browse gallery now, so
        # the bar states three intents instead of five entry points.
        def secondary(text, cmd, col, right=4):
            ctk.CTkButton(
                bar, text=text, width=124, height=theme.H_BUTTON_LG,
                corner_radius=theme.RADIUS_SM,
                font=(UI, theme.TYPE["body"]),
                fg_color=CONTROL_ALT, hover_color=GRAY_HOVER, text_color=TEXT,
                command=cmd).grid(row=0, column=col, padx=(4, right), pady=12)

        secondary("Browse cards…", self._open_sources, 2)
        secondary("Add files…", self._add_files, 3)
        secondary("Import list…", self._open_import, 4, right=12)

    # ----------------------------------------------------------------- queue
    def _build_queue(self):
        wrap = ctk.CTkFrame(self, corner_radius=12, fg_color=PANEL)
        wrap.grid(row=2, column=0, sticky="nsew", padx=24, pady=8)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(wrap, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
        ctk.CTkLabel(top, text="Queue", text_color=TEXT_DIM,
                     font=(UI, 13, "bold")).pack(side="left")

        self.status_filter = "All"
        self.filter_btn = ctk.CTkSegmentedButton(
            top, values=["All", "Pending", "Processing", "Done", "Error"],
            command=self._set_filter, height=26,
            font=(UI, 11),
            fg_color=BG, unselected_color=BG, unselected_hover_color=GRAY_HOVER,
            selected_color=GOLD, selected_hover_color=GOLD_HOVER,
            text_color="#d7dbe4")
        self.filter_btn.set("All")
        self.filter_btn.pack(side="right")

        self.queue_frame = ctk.CTkScrollableFrame(
            wrap, corner_radius=10, fg_color=PANEL)
        self.queue_frame.grid(row=1, column=0, sticky="nsew", padx=6, pady=6)
        self.queue_frame.grid_columnconfigure(0, weight=1)

        hint = "Drag & drop images here" if _DND else "Use “Add files…” to add images"
        self.empty_hint = ctk.CTkLabel(
            self.queue_frame, text=f"\n\n{hint}\n",
            text_color=MUTED, font=(UI, 14))
        self.empty_hint.grid(row=0, column=0, pady=40)

    # ---------------------------------------------------------------- footer
    def _build_footer(self):
        # Row 1 - how cards get processed (settings only, no actions)
        opts = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=theme.RADIUS_LG)
        opts.grid(row=3, column=0, sticky="ew", padx=24, pady=(4, 0))
        pad = theme.SPACE
        opts.grid_columnconfigure(1, weight=1)

        # Two blocks: named settings on the left in an aligned label/control
        # grid, plain on/off toggles stacked on the right. Previously these
        # were interleaved on one grid, so the labels never lined up and the
        # panel read as a row of loose parts.
        fields = ctk.CTkFrame(opts, fg_color="transparent")
        fields.grid(row=0, column=0, sticky="w", padx=(pad["lg"], 0),
                    pady=pad["md"])

        MENU_W = 220

        def field(text, row, col, values, width=MENU_W, command=None):
            # No fixed width: grid already aligns the column to the widest
            # label in it, and padding it out just opens a gap after the
            # shorter ones.
            ctk.CTkLabel(fields, text=text, font=(UI, theme.TYPE["small"]),
                         text_color=TEXT_DIM, anchor="w").grid(
                row=row, column=col * 2, sticky="w",
                padx=(0 if col == 0 else pad["xl"], pad["sm"]),
                pady=(0 if row == 0 else pad["sm"], 0))
            menu = ctk.CTkOptionMenu(
                fields, values=values, width=width, height=theme.H_INPUT,
                font=(UI, theme.TYPE["body"]), corner_radius=theme.RADIUS_SM,
                fg_color=ROW, button_color=CONTROL_ALT,
                button_hover_color=GRAY_HOVER, text_color=TEXT,
                dropdown_fg_color=ROW, dropdown_text_color=TEXT,
                dropdown_hover_color=GRAY_HOVER, command=command)
            menu.grid(row=row, column=col * 2 + 1, sticky="w",
                      pady=(0 if row == 0 else pad["sm"], 0))
            return menu

        self.model_menu = field("Model", 0, 0,
                                [AUTO_MODEL] + list(MODELS.keys()))
        self.model_menu.set(DEFAULT_MODEL)

        # Card size drives what fit-to-card resizes to, so it lives here and
        # not only in Export - a Yu-Gi-Oh card forced into Magic proportions
        # comes out stretched.
        self.card_size_menu = field("Card size", 0, 1, card_size_options(),
                                    command=self._persist_card_size)
        self.card_size_menu.set(
            load_settings().get("card_size", CARD_SIZE_DEFAULT))

        # "Language" alone reads as the app's own language - a user hunting
        # for French cards did not recognise it. It qualifies the card, like
        # "Card size" beside it.
        self.card_lang_menu = field("Card language", 1, 0, list(CARD_LANGS.keys()),
                                    command=self._persist_card_lang)
        self.card_lang_menu.set(
            load_settings().get("card_lang", CARD_LANG_DEFAULT))

        toggles = ctk.CTkFrame(opts, fg_color="transparent")
        toggles.grid(row=0, column=1, sticky="w", padx=(pad["xl"], pad["lg"]),
                     pady=pad["md"])

        self.fit_switch = _switch(toggles, "Fit to card (1200 DPI)")
        if FIT_TO_CARD_DEFAULT:
            self.fit_switch.select()
        self.fit_switch.grid(row=0, column=0, sticky="w")

        # Three states, not two: turning it off covers "wrongly detected", but
        # not "has bleed the ratio test can't see". That needs its own mode.
        bleedfr = ctk.CTkFrame(toggles, fg_color="transparent")
        bleedfr.grid(row=1, column=0, sticky="w", pady=(pad["sm"], 0))
        ctk.CTkLabel(bleedfr, text="MPC bleed", font=(UI, theme.TYPE["small"]),
                     text_color=TEXT_DIM).pack(side="left", padx=(0, pad["sm"]))
        self.trim_menu = ctk.CTkOptionMenu(
            bleedfr, values=BLEED_MODES, width=132, height=theme.H_INPUT - 6,
            font=(UI, theme.TYPE["small"]), corner_radius=theme.RADIUS_SM,
            fg_color=ROW, button_color=CONTROL_ALT,
            button_hover_color=GRAY_HOVER, text_color=TEXT,
            dropdown_fg_color=ROW, dropdown_text_color=TEXT,
            dropdown_hover_color=GRAY_HOVER, command=self._persist_bleed_mode)
        self.trim_menu.set(load_settings().get("bleed_mode", BLEED_MODE_DEFAULT))
        self.trim_menu.pack(side="left")

        self.best_scan_switch = _switch(toggles, "Best scan")
        if load_settings().get("best_scan", BEST_SCAN_DEFAULT):
            self.best_scan_switch.select()
        self.best_scan_switch.configure(command=self._persist_best_scan)
        self.best_scan_switch.grid(row=2, column=0, sticky="w",
                                   pady=(pad["sm"], 0))

        # Row 2 - actions
        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=24, pady=(pad["md"], 18))
        footer.grid_columnconfigure(0, weight=1)

        self.overall = ctk.CTkProgressBar(
            footer, height=6, corner_radius=3, progress_color=GOLD,
            fg_color=ROW)
        self.overall.set(0)
        self.overall.grid(row=0, column=0, sticky="ew", padx=(0, pad["lg"]))

        def ghost(text, cmd, w):
            return ctk.CTkButton(
                footer, text=text, width=w, height=theme.H_BUTTON,
                corner_radius=theme.RADIUS_SM, font=(UI, theme.TYPE["body"]),
                fg_color="transparent", hover_color=GRAY_HOVER,
                border_width=1, border_color=BORDER_STRONG, text_color=TEXT_DIM,
                command=cmd)

        # Utilities read as one tier at one height; only "Upscale all" is
        # allowed to look like a primary action. Clear used to be a filled
        # button 6 px taller than its neighbours, which made the whole row
        # look misaligned.
        # One slot rather than two: the footer was already full, and save and
        # open belong together anyway.
        # Column 0 is the progress bar, which stretches; the utilities run
        # from 1 and "Upscale all" stays last as the only primary action.
        self.project_btn = ghost("Project…", self._project_menu, 96)
        self.project_btn.grid(row=0, column=1, padx=pad["xs"])
        ghost("Output folder", self._open_output, 118).grid(
            row=0, column=2, padx=pad["xs"])
        self.clear_btn = ghost("Clear", self._clear, 76)
        self.clear_btn.grid(row=0, column=3, padx=pad["xs"])
        ghost("PDF from files…", self._export_pdf_files, 130).grid(
            row=0, column=4, padx=pad["xs"])
        self.pdf_btn = ghost("Export PDF…", self._export_pdf, 116)
        self.pdf_btn.grid(row=0, column=5, padx=(pad["xs"], pad["lg"]))

        self.start_btn = ctk.CTkButton(
            footer, text="Upscale all", width=150, height=theme.H_BUTTON_LG,
            corner_radius=theme.RADIUS_SM,
            font=(UI, theme.TYPE["subtitle"], "bold"),
            fg_color=GOLD, hover_color=GOLD_HOVER, text_color=GOLD_TEXT,
            command=self._start)
        self.start_btn.grid(row=0, column=6)

        # Named in the Project menu as accelerators, which is the only
        # place anyone will find them.
        for seq in ("<Control-s>", "<Control-S>"):
            self.bind(seq, self._save_project)
        for seq in ("<Control-o>", "<Control-O>"):
            self.bind(seq, self._open_project)

    # ============================================================== projects
    # A queue is work: a hundred cards chosen printing by printing, with
    # quantities and per-card models. Closing the window used to throw all of
    # it away, and v2.17.10 made that worse by giving the session more to lose.
    # Export presets save settings; this saves the list itself.

    PROJECT_FORMAT = 1
    PROJECT_TYPES = [("Cardwright project", "*.cwproj"), ("All files", "*.*")]

    def _project_dict(self):
        items = []
        for it in self.items:
            items.append({
                "ref": str(it.ref),
                "kind": it.kind,
                "label": it.label,
                "qty": it.qty,
                "released_at": it.released_at,
                "set_code": it.set_code,
                "src": getattr(it, "src", None),
                "downloads": [list(d) for d in (it.downloads or [])],
                "model": it.model_menu.get(),
                # Saved after upscaling, a project can go straight to Export
                # without paying for the AI again.
                "outputs": [str(o) for o in it.outputs],
                "status": it.status,
            })
        return {
            "cardwright_project": self.PROJECT_FORMAT,
            "app_version": APP_VERSION,
            "items": items,
        }

    def _save_project(self, _event=None):
        if not self.items:
            messagebox.showinfo("Save project",
                                "The queue is empty, so there is nothing to "
                                "save yet.")
            return "break"
        target = filedialog.asksaveasfilename(
            title="Save project", defaultextension=".cwproj",
            initialdir=OUTPUT_FOLDER, initialfile="deck.cwproj",
            filetypes=self.PROJECT_TYPES)
        if not target:
            return "break"
        try:
            Path(target).write_text(
                json.dumps(self._project_dict(), indent=1, ensure_ascii=False),
                encoding="utf-8")
        except OSError as e:
            applog.log.error("Saving the project failed", exc_info=True)
            messagebox.showerror("Save project", str(e))
            return "break"
        n = len(self.items)
        messagebox.showinfo("Save project",
                            f"Saved {n} card(s) to\n{Path(target).name}")
        return "break"

    def _open_project(self, _event=None):
        if self.running:
            return "break"
        path = filedialog.askopenfilename(
            title="Open project", initialdir=OUTPUT_FOLDER,
            filetypes=self.PROJECT_TYPES)
        if not path:
            return "break"
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            applog.log.error("Opening the project failed", exc_info=True)
            messagebox.showerror("Open project",
                                 f"That file could not be read.\n\n{e}")
            return "break"
        if not isinstance(data, dict) or "cardwright_project" not in data:
            messagebox.showerror("Open project",
                                 "That is not a Cardwright project file.")
            return "break"
        if data.get("cardwright_project", 0) > self.PROJECT_FORMAT:
            messagebox.showerror(
                "Open project",
                "That project was saved by a newer version of Cardwright.\n\n"
                "Update and try again.")
            return "break"
        if self.items and not messagebox.askyesno(
                "Open project",
                f"This replaces the {len(self.items)} card(s) already in the "
                "queue.\n\nContinue?"):
            return "break"
        self._load_project(data)
        return "break"

    def _load_project(self, data):
        self._clear()
        missing = 0
        for row in data.get("items", []):
            item = self._add_item(
                row.get("ref", ""), row.get("kind", "scryfall"),
                downloads=[tuple(d) for d in row.get("downloads") or []] or None,
                label=row.get("label"), qty=int(row.get("qty", 1)),
                released_at=row.get("released_at"),
                set_code=row.get("set_code"), src=row.get("src"))
            if row.get("model") in ROW_MODELS:
                item.model_menu.set(row["model"])
            # Outputs are paths, and a project outlives the files it points at.
            # Anything gone goes back to pending rather than pretending to be
            # done and failing at export with an empty sheet.
            outs = [Path(o) for o in row.get("outputs") or []]
            alive = [o for o in outs if o.exists()]
            if outs and len(alive) < len(outs):
                missing += 1
            if alive and len(alive) == len(outs) and row.get("status") == "done":
                item.outputs = alive
                item.set_status("done", f"Done ({item.qty} copies)"
                                if item.qty > 1 else "Done", 1)
        self._refresh_empty()
        n = len(self.items)
        msg = f"Loaded {n} card(s)."
        if missing:
            msg += (f"\n\n{missing} of them had upscaled files that are no "
                    "longer on disk, so they are queued to run again.")
        messagebox.showinfo("Open project", msg)

    def _project_menu(self):
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(label="Save project…", accelerator="Ctrl+S",
                         command=self._save_project)
        menu.add_command(label="Open project…", accelerator="Ctrl+O",
                         command=self._open_project)
        try:
            x = self.project_btn.winfo_rootx()
            y = self.project_btn.winfo_rooty() + self.project_btn.winfo_height()
            menu.tk_popup(x, y)
        finally:
            menu.grab_release()

    # ============================================================ queue ops
    def _refresh_empty(self):
        if self.items:
            self.empty_hint.grid_remove()
        else:
            self.empty_hint.grid()

    def _set_filter(self, value):
        self.status_filter = value
        for it in self.items:
            self._apply_filter(it)

    def _apply_filter(self, item):
        """Show/hide a row according to the active status filter."""
        if self.status_filter == "All" or item.status == self.status_filter.lower():
            item.grid()
        else:
            item.grid_remove()

    def _add_item(self, ref, kind, downloads=None, label=None, qty=1,
                  released_at=None, set_code=None, src=None):
        item = QueueItem(self.queue_frame, ref, kind, self._remove_item,
                         downloads=downloads, label=label, qty=qty,
                         released_at=released_at, set_code=set_code,
                         on_status=self._apply_filter)
        # Which catalogue this came from, so border treatment can be skipped
        # per source (MPC art already carries a true black edge).
        item.src = src or ("file" if kind == "file" else "scryfall")
        item.grid(row=len(self.items) + 1, column=0, sticky="ew", padx=6, pady=4)
        self.items.append(item)
        self._apply_filter(item)
        self._refresh_empty()
        return item

    def _remove_item(self, item):
        if self.running:
            return
        item.destroy()
        self.items.remove(item)
        for i, it in enumerate(self.items):
            it.grid_configure(row=i + 1)
        self._refresh_empty()

    def _add_files(self):
        exts = " ".join(f"*{e}" for e in sorted(SUPPORTED_INPUT))
        files = filedialog.askopenfilenames(
            filetypes=[("Images", exts), ("All files", "*.*")])
        for f in files:
            self._add_item(f, "file")

    def _add_scryfall(self):
        ref = self.ref_entry.get().strip()
        if not ref:
            return
        # A bare name doesn't choose a printing, so show the gallery: the user
        # sees what they are about to upscale and can switch art or source.
        # A link or a decklist line already named one - straight to the queue.
        if not scryfall.ref_names_a_printing(ref):
            self.ref_entry.delete(0, "end")
            self._open_sources(ref)
            return
        self._add_item(ref, "scryfall")
        self.ref_entry.delete(0, "end")

    def _open_sources(self, query=None):
        if self.running:
            return
        CardSearchDialog(
            self, on_pick=self._add_source_card, backend=sources.SCRYFALL,
            title="Choose a version",
            placeholder=sources.SCRYFALL.PLACEHOLDER,
            empty_msg=sources.SCRYFALL.EMPTY,
            switchable=sources.ALL, query=query)

    def _add_source_card(self, card):
        """Queue a gallery pick, however its source wants to be fetched."""
        src = sources.by_id(card.get("_source", "scryfall"))
        if src.ADD_KIND == "scryfall":
            # Gatherer: hand back the reference and let scryfall.fetch pull
            # the image, which also converts Gatherer's webp to PNG.
            self._add_item(card["ref"], "scryfall",
                           label=f"{card['name']}  [{src.LABEL}]", src=src.ID)
            return

        if src.ID == "scryfall" and card.get("identifier"):
            # The gallery's download url is the FRONT face, so picking a
            # double-faced card here used to queue half a card and leave the
            # sheet to fall back on back.png. Queue the card's id instead and
            # let scryfall.fetch resolve every face. The exact printing and its
            # language both survive that: an api url counts as naming a
            # printing, so best_scan and the language preference leave it be.
            self._add_item(f"{scryfall.SCRYFALL_API}/cards/{card['identifier']}",
                           "scryfall",
                           label=f"{card['name']}  [{card['source'] or src.LABEL}]",
                           src=src.ID)
            return

        base = f"{card['name']}  [{card['source'] or src.LABEL}]"
        # Same hazard as the MPC order import: two picks that share a name and
        # a source write the same file and one silently replaces the other.
        # Two MPC arts by one contributor, or two Yu-Gi-Oh artworks from one
        # set, do exactly that. The catalogue's own id is unique, so tack a
        # slice of it on.
        safe = re.sub(r'[<>:"/\\|?*]', "", base)
        ident = str(card.get("identifier") or "")[:10]
        if ident:
            safe = f"{safe} {re.sub(r'[^A-Za-z0-9_-]', '', ident)}"
        item = self._add_item(base, "card",
                              downloads=[(safe, card["download"])], label=base,
                              src=src.ID)

        # A gallery pick is one image, but a double-faced card is two. MPC
        # keeps the back under its own card name, so it can be found and
        # queued alongside the front instead of the card silently falling
        # through to back.png. Off the UI thread: it costs a Scryfall lookup
        # and a catalogue search, and nothing is downloaded until Upscale all.
        if src.ID == "mpc":
            # Kept on the item because processing has to wait for it: the two
            # network calls take several seconds, and pressing Upscale all
            # inside that window would read item.downloads before the back was
            # added and lose it without a word.
            item.back_job = threading.Thread(
                target=self._attach_gallery_back, args=(item, card, safe),
                daemon=True)
            item.back_job.start()

        # A source printed at another size (Yu-Gi-Oh) has to move the card
        # size with it, or fit-to-card stretches it into Magic proportions.
        hint = getattr(src, "CARD_SIZE_HINT", None)
        if hint and self.card_size_menu.get() == CARD_SIZE_DEFAULT:
            for name in CARD_SIZES:
                if name.startswith(hint):
                    self.card_size_menu.set(name)
                    self._persist_card_size(name)
                    break

    # A catalogue entry is "Card Name (MOM 75)" or "Card Name (Borderless
    # Victor Adame)": the card, then which art. Both faces of one artist's
    # double-faced card carry the same suffix, which is what makes the right
    # back findable rather than guessed at.
    _VARIANT_RE = re.compile(r"\s*\(([^()]*)\)\s*$")

    @classmethod
    def _plain_name(cls, name):
        return cls._VARIANT_RE.sub("", name).strip()

    @classmethod
    def _variant_of(cls, name):
        m = cls._VARIANT_RE.search(name or "")
        return (m.group(1).strip().lower() if m else "")

    @classmethod
    def _pick_back(cls, results, front):
        """Choose which back belongs with `front`. Returns (pick, same_source).

        Contributors upload both faces of a card together, so the back by the
        front's own contributor is the one that matches, and among those the
        one whose art variant reads the same. Anything else is a guess, and
        the caller says so when it has to fall back to one.
        """
        want_src = (front.get("source") or "").strip()
        want_var = cls._variant_of(front.get("name", ""))
        same_src = [r for r in results
                    if (r.get("source") or "").strip() == want_src]
        pick = (next((r for r in same_src
                      if cls._variant_of(r["name"]) == want_var), None)
                or (same_src[0] if same_src else results[0]))
        return pick, bool(same_src)

    def _attach_gallery_back(self, item, card, safe):
        """Find the back face of a double-faced gallery pick and queue it too.

        Scryfall is asked what the second face is called; the catalogue is
        then searched for that name. Contributors upload both faces together,
        so the back by the same contributor - and, better, the one whose art
        variant matches - is the one that belongs with the front the user
        actually chose.
        """
        try:
            back_name = scryfall.back_face_name(self._plain_name(card["name"]))
            if not back_name:
                return                      # single-faced, nothing to do
            results = mpcfill.search(back_name, limit=30)
        except Exception as e:
            applog.log.warning("Back face lookup failed for %r", card.get("name"),
                               exc_info=e)
            return
        if not results:
            return

        pick, same_src = self._pick_back(results, card)

        # Renaming the front is what makes the pair visible to the export
        # dialog, which matches faces by the -front / -back suffix.
        item.downloads = [(f"{safe}-front", card["download"]),
                          (f"{safe}-back", pick["download"])]
        note = f"+ back: {pick['name']}"
        if not same_src:
            # honest about it: this back is not by the front's contributor
            note += f"  (from {pick.get('source') or 'another source'})"
        applog.log.info("Queued back face for %s: %s", card["name"], pick["name"])
        self._ui(self._note_if_pending, item, note)

    def _note_if_pending(self, item, note):
        """Only touch the row if processing has not overtaken us."""
        if item.winfo_exists() and item.status == "pending":
            item.set_status("pending", note)

    def _open_import(self):
        if self.running:
            return
        ImportDialog(self, on_resolved=self._add_resolved_cards)

    def _persist_card_size(self, name):
        """Card size is one setting shared with the Export dialog."""
        if name == CUSTOM_SIZE_EDIT:
            label = ask_custom_card_size(self)
            # Cancelled: fall back to whatever was selected before, never
            # leave the picker showing the editor entry as if it were a size.
            name = label or load_settings().get("card_size", CARD_SIZE_DEFAULT)
            self.card_size_menu.configure(values=card_size_options())
            self.card_size_menu.set(name)
            if not label:
                return
        s = load_settings()
        s["card_size"] = name
        save_settings(s)

    def _persist_card_lang(self, name):
        """Worker threads read this from settings, never off the widget."""
        s = load_settings()
        s["card_lang"] = name
        save_settings(s)

    def _persist_bleed_mode(self, name):
        st = load_settings()
        st["bleed_mode"] = name
        save_settings(st)

    def _persist_best_scan(self):
        s = load_settings()
        s["best_scan"] = bool(self.best_scan_switch.get())
        save_settings(s)

    def _add_resolved_cards(self, cards):
        for c in cards:
            if c.get("ref"):
                # Gatherer import: a reference, so scryfall.fetch pulls the
                # Gatherer image and converts its webp to PNG.
                self._add_item(c["ref"], "scryfall", label=c["display"],
                               qty=c["qty"], released_at=c.get("released_at"),
                               set_code=c.get("set"), src="gatherer")
                continue
            self._add_item(c["display"], "card",
                           downloads=c["downloads"], label=c["display"],
                           qty=c["qty"], released_at=c.get("released_at"),
                           set_code=c.get("set"), src=c.get("src"))

    def _on_drop(self, event):
        # event.data is a brace/space separated list of paths
        paths = self.tk.splitlist(event.data)
        for p in paths:
            if Path(p).suffix.lower() in SUPPORTED_INPUT:
                self._add_item(p, "file")

    def _clear(self):
        if self.running:
            return
        for it in list(self.items):
            it.destroy()
        self.items.clear()
        self.overall.set(0)
        self._refresh_empty()

    def _open_output(self):
        _open_folder(OUTPUT_FOLDER)

    # ============================================================ pdf export
    def _export_images(self):
        """Cards to lay out: queue results first (order + copies), else
        everything in the output folder."""
        images = [p for it in self.items if it.status == "done"
                  for p in it.outputs if Path(p).exists()]
        srcs = {str(p): getattr(it, "src", "scryfall")
                for it in self.items if it.status == "done"
                for p in it.outputs if Path(p).exists()}
        source = "queue"
        if not images:
            images = sorted(OUTPUT_FOLDER.glob("*.png"))
            source = "output folder"
            srcs = {}          # nothing left to tell us where these came from
        return images, source, srcs

    def _export_pdf(self):
        # Opens even with nothing upscaled. The dialog is where sheets are
        # built - grids, guides, page shift, bleed - and none of that needs a
        # card to be worth looking at. Refusing to open it meant upscaling a
        # throwaway card just to reach the settings, or to add finished cards
        # from disk with "Add cards…", which the dialog can already do.
        if self.running:
            return
        images, source, srcs = self._export_images()
        ExportDialog(self, images, source, card_sources=srcs)

    def _export_pdf_files(self):
        """Pick specific already-upscaled cards (from the output folder or
        anywhere) and lay just those into a PDF - no queue needed."""
        if self.running:
            return
        files = filedialog.askopenfilenames(
            title="Choose cards for the PDF",
            initialdir=OUTPUT_FOLDER,
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")])
        if not files:
            return
        ExportDialog(self, [Path(f) for f in files], "selected files")

    # ================================================================ run
    def _start(self):
        if self.running:
            return
        if not self.items:
            messagebox.showerror("Nothing to do", "Add some cards or images first.")
            return

        self.running = True
        self.start_btn.configure(state="disabled", text="Working…")
        self.clear_btn.configure(state="disabled")
        self.overall.set(0)

        threading.Thread(target=self._worker, daemon=True).start()

    def _worker(self):
        model = self.model_menu.get()
        fit = bool(self.fit_switch.get())
        trim = bleed_mode_code(load_settings().get("bleed_mode"))
        # fit-to-card resizes to the chosen TCG's size (set in Export)
        card = load_settings().get("card_size", CARD_SIZE_DEFAULT)
        lang = card_lang_code(load_settings().get("card_lang"))
        best_scan = bool(load_settings().get("best_scan", BEST_SCAN_DEFAULT))
        pending = [it for it in self.items if it.status != "done"]
        total = len(pending)
        state = {"done": 0, "errors": 0}
        lock = threading.Lock()

        def process(item):
            try:
                self._process_item(item, model, fit, trim, card, lang, best_scan)
            except Exception as e:
                with lock:
                    state["errors"] += 1
                # The row can only hold a sentence; the log gets the traceback
                # and what was actually being fetched.
                applog.log.error("Failed on %r (kind=%s, model=%s, lang=%s)",
                                 item.ref, item.kind, model, lang, exc_info=True)
                self._ui(item.set_status, "error", f"Error: {e}")
            finally:
                with lock:
                    state["done"] += 1
                    progress = state["done"] / total
                self._ui(self.overall.set, progress)

        with ThreadPoolExecutor(max_workers=PARALLEL_JOBS) as pool:
            list(pool.map(process, pending))

        self.after(0, lambda: self._finish(total, state["errors"]))

    # Long enough for two slow catalogue calls, short enough that a hung
    # lookup never strands the queue: the card still upscales, front only.
    _BACK_LOOKUP_TIMEOUT = 30

    def _process_item(self, item, model, fit, trim, card_size=None, lang=None,
                      best_scan=False):
        self._ui(item.set_status, "processing", "Preparing…", 0)
        item.outputs = []

        # build the list of local files to upscale (2 for DFCs)
        if item.kind == "card":
            # A gallery pick may still be finding its back face. Reading
            # downloads before that lands is how a double-faced card silently
            # arrives with only its front, so wait for it here rather than
            # hoping the user was slow to press the button.
            job = getattr(item, "back_job", None)
            if job is not None and job.is_alive():
                self._ui(item.set_status, "processing", "Finding the back face…")
                job.join(timeout=self._BACK_LOOKUP_TIMEOUT)
                if job.is_alive():
                    applog.log.warning(
                        "Back-face lookup for %r did not finish in %ss; "
                        "queueing the front alone",
                        item.ref, self._BACK_LOOKUP_TIMEOUT)
            # already resolved by the importer -> just download
            targets = []
            for base, url in item.downloads:
                self._ui(item.set_status, "processing", "Downloading…")
                targets.append(str(scryfall.download_to_temp(base, url)))
            use_scryfall_name = True
        elif item.kind == "scryfall":
            paths, meta = scryfall.fetch(
                item.ref,
                status_callback=lambda t, it=item: self._ui(
                    it.set_status, "processing", t),
                lang=lang, best_scan=best_scan)
            targets = [str(p) for p in paths]
            item.released_at = meta.get("released_at")
            item.set_code = meta.get("set")
            use_scryfall_name = True
        else:
            targets = [item.ref]
            use_scryfall_name = False

        for t in targets:
            out = Path(upscale(
                t,
                model_label=item.model_override or model,
                fit_to_card=fit,
                rename=not use_scryfall_name,
                released_at=item.released_at,
                set_code=item.set_code,
                ai=self.ai_ok,
                # not `trim and ...`: with a mode string that collapses every
                # mode to True, which would trim even on "Assume none"
                trim_bleed=trim if _may_have_bleed(item) else "never",
                card_size=card_size,
                progress_callback=lambda v, it=item: self._ui(
                    it.set_status, "processing", None, v),
                status_callback=lambda s, it=item: self._ui(
                    it.set_status, "processing", s),
            ))
            # Quantity is a count, not files. The sheet lists the same path
            # once per copy and build_pdf flattens it once, so a 4-of no longer
            # leaves four identical PNGs in the output folder.
            for _ in range(item.qty):
                item.outputs.append(out)

        done_msg = f"Done ({item.qty} copies)" if item.qty > 1 else "Done"
        self._ui(item.set_status, "done", done_msg, 1)

    def _finish(self, total, errors):
        self.running = False
        self.start_btn.configure(state="normal", text="Upscale all")
        self.clear_btn.configure(state="normal")
        ok = total - errors
        if errors:
            failed = [it for it in self.items if it.status == "error"]
            names = "\n".join(
                f"  • {it.name.cget('text')} - {it.info.cget('text')}"
                for it in failed[:12])
            if len(failed) > 12:
                names += f"\n  … (+{len(failed) - 12} more)"
            messagebox.showwarning(
                "Finished with errors",
                f"{ok} succeeded, {errors} failed:\n\n{names}\n\n"
                f"Use the 'Error' filter above the queue to see them, "
                f"then 'Upscale all' retries only the failed ones.\n\n"
                f"Full details were written to the log - the 'Log' button in "
                f"the header opens it. Attach it if you report this.")
        else:
            messagebox.showinfo(
                "Completed", f"{ok} image(s) upscaled to 1200 DPI.\nSaved to:\n{OUTPUT_FOLDER}")

    # ------------------------------------------------------------- ui helper
    def _ui(self, fn, *args):
        """Marshal a call onto the Tk main thread (no-op if window is gone)."""
        try:
            self.after(0, lambda: fn(*args))
        except RuntimeError:
            pass


# --------------------------------------------------------------------------
# decklist import dialog
# --------------------------------------------------------------------------
class ImportDialog(ctk.CTkToplevel):
    PLACEHOLDER = ("Paste a decklist, or an Archidekt or Moxfield deck URL:\n\n"
                   "1 Winota, Joiner of Forces (PRM) 80807 [matte]\n"
                   "3 Plains (MSC) 866 [matte]\n"
                   "1 Ajani, Nacatl Pariah // Ajani, Nacatl Avenger (MH3) 442\n\n"
                   "https://archidekt.com/decks/1234567/my-deck\n"
                   "https://www.moxfield.com/decks/aBcDeFgHiJkLmNoPqRsTuV")

    def __init__(self, master, on_resolved):
        super().__init__(master)
        self.on_resolved = on_resolved
        self.title("Import decklist")
        self.geometry("620x520")
        self.transient(master)
        self.after(60, self.grab_set)   # after window is viewable
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        self.configure(fg_color=BG)
        ctk.CTkLabel(self, text="Import from decklist",
                     font=(UI, theme.TYPE["title"], "bold"), text_color=TEXT).grid(
            row=0, column=0, sticky="w", padx=20, pady=(18, 4))

        self.textbox = ctk.CTkTextbox(self, font=("Cascadia Mono", 12),
                                      wrap="none", fg_color=SURFACE_INPUT,
                                      border_color=BORDER_STRONG, border_width=1,
                                      corner_radius=theme.RADIUS_SM,
                                      text_color=TEXT)
        self.textbox.grid(row=1, column=0, sticky="nsew", padx=20, pady=8)
        self.textbox.insert("1.0", self.PLACEHOLDER)
        self.textbox.bind("<FocusIn>", self._clear_placeholder)
        self._has_placeholder = True

        self.status = ctk.CTkLabel(self, text="Resolves the exact printing "
                                   "(set + number), then pulls the art from "
                                   "the source below.",
                                   text_color="#9ca3af", font=(UI, 12))
        self.status.grid(row=2, column=0, sticky="w", padx=20, pady=2)

        # Two rows: options above, actions below. All of it on one line
        # overflowed a 620 px dialog and pushed the primary button off screen.
        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.grid(row=3, column=0, sticky="ew", padx=20, pady=(6, 0))

        ctk.CTkLabel(opts, text="Images from", font=(UI, theme.TYPE["small"]),
                     text_color=TEXT_DIM).pack(side="left", padx=(0, 6))
        self.src_menu = ctk.CTkOptionMenu(
            opts, values=["Scryfall", "Gatherer"], width=104,
            height=theme.H_INPUT - 6, font=(UI, theme.TYPE["small"]),
            corner_radius=theme.RADIUS_SM, fg_color=ROW,
            button_color=CONTROL_ALT, button_hover_color=GRAY_HOVER,
            text_color=TEXT, dropdown_fg_color=ROW, dropdown_text_color=TEXT,
            dropdown_hover_color=GRAY_HOVER)
        self.src_menu.set(load_settings().get("import_source", "Scryfall"))
        self.src_menu.pack(side="left", padx=(0, 16))

        # Scryfall lists a card's tokens in `all_parts`, so this is exact
        # rather than guesswork - and someone printing a Krenko deck wants
        # the goblins.
        self.tokens_var = ctk.BooleanVar(
            value=bool(load_settings().get("import_tokens", False)))
        ctk.CTkCheckBox(opts, text="Also add the tokens these cards make",
                        variable=self.tokens_var, checkbox_width=16,
                        checkbox_height=16, corner_radius=3,
                        font=(UI, theme.TYPE["small"]), fg_color=GOLD,
                        hover_color=GOLD_HOVER, text_color=TEXT_DIM).pack(
            side="left")

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=4, column=0, sticky="ew", padx=20, pady=(10, 16))
        ctk.CTkButton(btns, text="MPC XML…", width=104, height=theme.H_BUTTON,
                      corner_radius=theme.RADIUS_SM, fg_color=CONTROL_ALT,
                      hover_color=GRAY_HOVER, text_color=TEXT,
                      font=(UI, theme.TYPE["small"]),
                      command=self._load_mpc_xml).pack(side="left")

        self.import_btn = ctk.CTkButton(btns, text="Resolve & add", width=140,
                                        height=theme.H_BUTTON,
                                        corner_radius=theme.RADIUS_SM,
                                        fg_color=GOLD, hover_color=GOLD_HOVER,
                                        text_color=GOLD_TEXT,
                                        font=(UI, 13, "bold"),
                                        command=self._do_import)
        self.import_btn.pack(side="right")
        ctk.CTkButton(btns, text="Cancel", width=90, height=theme.H_BUTTON,
                      corner_radius=theme.RADIUS_SM, fg_color=CONTROL_ALT,
                      hover_color=GRAY_HOVER, text_color=TEXT,
                      command=self.destroy).pack(side="right", padx=8)

    def _load_mpc_xml(self):
        """Import an MPC Autofill order file.

        Worth having over re-searching: the order names the exact art the user
        already picked, which a name search cannot reproduce.
        """
        path = filedialog.askopenfilename(
            title="Choose an MPC Autofill order file",
            filetypes=[("MPC Autofill order", "*.xml"), ("All files", "*.*")])
        if not path:
            return
        try:
            cards, problems = mpcfill.parse_order_xml(
                Path(path).read_text(encoding="utf-8", errors="replace"))
        except Exception as e:
            applog.log.error("MPC order import failed", exc_info=e)
            messagebox.showerror("Could not read that file", str(e), parent=self)
            return

        resolved = []
        for c in cards:
            base = f"{c['name']}  [{c['source']}]"
            # The download name has to carry the slot. An MPC order names every
            # entry by card alone, so an order with three different Islands
            # repeats "Island.png" three times - without this they all write
            # the same file and two of the three arts are silently lost.
            safe = re.sub(r'[<>:"/\\|?*]', "", base)
            if c.get("slot"):
                safe = f"{safe} {c['slot']}"
            # A double-faced card downloads both faces, named so that the
            # export dialog's -front/-back pairing picks them up: that is the
            # same convention Scryfall DFCs already arrive with, so nothing
            # downstream needs to know where the card came from.
            if c.get("back_download"):
                downloads = [(f"{safe}-front", c["download"]),
                             (f"{safe}-back", c["back_download"])]
            else:
                downloads = [(safe, c["download"])]
            resolved.append({
                "display": f"{c['qty']}x {c['name']}" if c["qty"] > 1 else c["name"],
                "qty": c["qty"],
                "downloads": downloads,
                "released_at": None,
                "set": None,
                "src": "mpc",
            })
        if resolved:
            self.on_resolved(resolved)

        if problems:
            messagebox.showwarning(
                "Imported with issues",
                f"Added {len(resolved)} card(s).\n\nSkipped:\n  - "
                + "\n  - ".join(problems), parent=self)
        if resolved:
            self.destroy()

    def _clear_placeholder(self, _=None):
        if self._has_placeholder:
            self.textbox.delete("1.0", "end")
            self._has_placeholder = False

    def _do_import(self):
        if self._has_placeholder:
            return
        text = self.textbox.get("1.0", "end").strip()
        if not text:
            return
        self.import_btn.configure(state="disabled", text="Resolving…")
        st = load_settings()
        st["import_tokens"] = bool(self.tokens_var.get())
        st["import_source"] = self.src_menu.get()
        save_settings(st)
        threading.Thread(target=self._resolve, args=(text,), daemon=True).start()

    def _resolve(self, text):
        try:
            status = lambda s: self.after(
                0, lambda: self.status.configure(text=s, text_color="#9ca3af"))

            # deck site URLs
            kind = scryfall.deck_url_kind(text)
            if kind == "moxfield":
                text = scryfall.fetch_moxfield(text, status_callback=status)
            if kind == "archidekt":
                text = scryfall.fetch_archidekt(text, status_callback=status)

            lang = card_lang_code(load_settings().get("card_lang"))
            cards, not_found, bad, english_only, from_scryfall =                 scryfall.resolve_decklist(
                    text, status_callback=status, lang=lang,
                    tokens=bool(self.tokens_var.get()),
                    source=self.src_menu.get().lower())
            self.after(0, lambda: self._done(cards, not_found, bad,
                                             english_only, from_scryfall))
        except Exception as e:
            self.after(0, lambda err=e: self._failed(err))

    def _done(self, cards, not_found, bad, english_only=(), from_scryfall=()):
        if cards:
            self.on_resolved(cards)

        problems = []
        if not_found:
            problems.append("Not found on Scryfall:\n  - " + "\n  - ".join(not_found))
        if bad:
            problems.append("Could not parse these lines:\n  - " + "\n  - ".join(bad))
        if english_only:
            # Not a failure - these cards were simply never printed in the
            # chosen language, so they were added in English.
            problems.append(
                "No printing in the selected language (added in English):\n  - "
                + "\n  - ".join(english_only))
        if from_scryfall:
            # Also not a failure. Gatherer has no entry for Secret Lairs,
            # promos, or any foil printing - Scryfall numbers those with a star
            # (198★) and gives them no multiverse id - so they come from
            # Scryfall instead of being dropped.
            problems.append(
                "Not on Gatherer, so these came from Scryfall instead:\n  - "
                + "\n  - ".join(from_scryfall))

        # A language fallback is not a failure, so it must not turn the whole
        # import red - it only gets the neutral wording when nothing else
        # actually went wrong.
        failures = len(not_found) + len(bad)
        if problems:
            self.import_btn.configure(state="normal", text="Resolve & add")
            if failures:
                note = f"{failures} issue(s)"
                colour = "#fca5a5"
                title = "Imported with issues"
                popup = messagebox.showwarning
            else:
                soft = len(english_only) + len(from_scryfall)
                note = f"{soft} substituted"
                colour = MUTED
                title = "Imported"
                popup = messagebox.showinfo
            self.status.configure(
                text=f"Added {len(cards)}. {note} - see popup.",
                text_color=colour)
            popup(
                title,
                f"Added {len(cards)} card(s) to the queue.\n\n" + "\n\n".join(problems),
                parent=self)
        else:
            self.destroy()

    def _failed(self, e):
        applog.log.error("Decklist import failed", exc_info=e)
        self.import_btn.configure(state="normal", text="Resolve & add")
        self.status.configure(text=f"Error: {e}", text_color="#fca5a5")


# --------------------------------------------------------------------------
# PDF export dialog with live preview
# --------------------------------------------------------------------------
_PAGE_MM = {
    "Letter": (215.9, 279.4), "A4": (210.0, 297.0), "A3": (297.0, 420.0),
    "A5": (148.0, 210.0), "Legal": (215.9, 355.6), "Tabloid": (279.4, 431.8),
    "4x6 photo": (101.6, 152.4),
}

# Cards are kept at WORK_SIZE in memory: big enough for the detector to
# behave as it will at print resolution and for the loupe to magnify, small
# enough to redraw the whole sheet instantly.
WORK_SIZE = (640, 896)
THUMB_SIZE = (200, 279)
LOUPE_PX = 148              # size of the magnifier window, in pixels
LOUPE_MM = 12               # how much of the card it shows (~6x zoom)

# frames of the little spinner shown on cards whose thumbnail is still loading
SPINNER_FRAMES = ["◐", "◓", "◑", "◒"]

GUIDE_CHOICES = ["White", "Black", "Gray", "None"]
GUIDE_STYLE_CHOICES = ["Cross", "Corner"]
BLEED_COLOR_CHOICES = ["Black", "White", print_sheet.BLEED_EXTEND]


def _tooltip(widget, text):
    """Attach a hover tooltip, or retarget an existing one.

    Deliberately defensive: a tooltip is a nicety, and CustomTkinter widgets
    are composites whose bind() does not accept every sequence. A failure here
    must never take the dialog down with it.
    """
    state = getattr(widget, "_tip", None)
    if state is not None:
        state["text"] = text
        return
    state = {"text": text, "win": None, "job": None}

    def show():
        state["job"] = None
        if state["win"] or not widget.winfo_exists():
            return
        win = tk.Toplevel(widget)
        win.wm_overrideredirect(True)
        win.configure(bg=BORDER_STRONG)
        tk.Label(win, text=state["text"], bg=ROW, fg=TEXT, font=(UI, 10),
                 padx=8, pady=4, bd=0).pack(padx=1, pady=1)
        win.wm_geometry(f"+{widget.winfo_rootx()}"
                        f"+{widget.winfo_rooty() + widget.winfo_height() + 6}")
        state["win"] = win

    def hide(_e=None):
        if state["job"]:
            widget.after_cancel(state["job"])
            state["job"] = None
        if state["win"]:
            state["win"].destroy()
            state["win"] = None

    def enter(_e=None):
        state["job"] = widget.after(450, show)

    try:
        widget.bind("<Enter>", enter, add="+")
        widget.bind("<Leave>", hide, add="+")
        widget.bind("<ButtonPress>", hide, add="+")
    except Exception:
        return
    widget._tip = state


class _Card:
    """One card as it sits on a sheet.

    Two copies of the same art are two instances sharing one path. Copies used
    to be physical files - `name (2).png` written next to the original - purely
    so each copy had an identity the preview could address. The PDF never
    needed them: `build_pdf` takes a path list and caches its flattened images
    by path, so the same file listed twice costs one flatten and prints twice.

    So `path` is what gets drawn and exported, and keys everything about the
    *image* - thumbnails, border treatment. `uid` addresses this one copy: the
    drag, the exclusion set, the hit-boxes, its assigned back.
    """

    __slots__ = ("path", "uid")
    _seq = 0

    def __init__(self, path):
        _Card._seq += 1
        self.path = Path(path)
        self.uid = f"card{_Card._seq}"


class ExportDialog(ctk.CTkToplevel):
    """Print-sheet export: layout, quality, color pipeline, duplex backs and
    a live preview of page 1. Choices persist in settings.json."""

    def __init__(self, master, images, source, card_sources=None):
        super().__init__(master)
        self.images = images
        # Opened with nothing: the summary has no origin to name, because
        # anything on the sheet got there through "Add cards…".
        self._started_empty = not images
        self.source = source
        # path -> catalogue id, so border treatment can be skipped per source
        self.card_sources = card_sources or {}
        self.title("Export print sheet")
        # Tall enough that the fullest tab (Layout) shows every row without
        # scrolling, but never taller than the screen: on a short laptop the
        # window shrinks and the tab bodies scroll instead. 760 was set when
        # the tabs held fewer controls and the last two rows fell off the
        # bottom with nothing to say they were there.
        self.geometry(f"980x{min(880, self.winfo_screenheight() - 60)}")
        self.transient(master)
        self.after(60, self.grab_set)
        self.configure(fg_color=BG)

        self._slider_setters = {}  # key -> fn(v) that sets slider + its label
        self._thumbs = {}          # path -> raw thumbnail
        self._thumbs_raw = {}      # path -> (working-size flat image, mask)
        self._work_b = {}          # path -> working-size treated image
        self._thumbs_b = {}        # path -> thumbnail with the border treated
        self._border_modes = {}    # path -> "auto" | "on" | "off"
        self._slots = []           # preview hit-boxes: (x0, y0, x1, y1, path)
        self._selected = set()     # card ids the next action applies to
        self._drops = []           # drop targets: (x0, y0, x1, y1, uid or None)
        self._dropbar = None       # canvas id of the insertion indicator
        self._drag_pos = None      # last cursor position, widget coords
        self._scroll_job = None    # edge auto-scroll timer while dragging
        self._scroll_dir = 0       # -1 up, +1 down
        self._scroll_step = 0.0    # px per tick, set from the cursor's depth
        self._prev_job = None
        self._page = 0             # sheet the ◀▶ nav is pointing at
        self._excluded = set()     # card ids dropped from the export
        self._custom_back = None   # chosen card back for non-DFC cards
        self._img_xoff = 0         # x offset of the sheets inside the canvas
        self._sheet_tops = []      # y of each sheet in canvas coordinates
        self._sheet_geom = None    # (W, H, gap, sheets) of the current layout
        self._sheet_cache = {}     # page -> (PhotoImage, canvas id); lazy
        self._render_sheet = None  # closure that paints one sheet on demand
        self._loading = True       # thumbnails still coming in
        self._spin_items = []      # canvas ids of the loading spinners
        self._spin_job = None      # spinner animation after() id
        self._spin_frame = 0
        self._tall_w = 0           # sheet width / total stacked height, for
        self._tall_h = 0           #   loupe clamping and scroll math
        self._drag = None          # in-progress card drag
        self._undo_stack = []      # [(label, snapshot)], newest last
        self._redo_stack = []
        self._loupe_item = None    # canvas id of the magnifier overlay
        self._drag_item = None     # canvas id of the dragged thumbnail
        self._showing_backs = False

        # explicit print order (the source of truth for the PDF); backs follow
        # their front via _back_of, keyed by card id so two copies of one card
        # can carry different backs. Drag-and-drop reorders _order.
        fronts0, backs0 = self._pairs()
        self._order = [_Card(f) for f in fronts0]
        self._back_of = {c.uid: b for c, b in zip(self._order, backs0)}

        s = load_settings()

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Export print sheet",
                     font=(UI, theme.TYPE["title"], "bold"), text_color=TEXT).grid(
            row=0, column=0, sticky="w", padx=20, pady=(16, 2))
        self.summary = ctk.CTkLabel(self, text="", text_color=MUTED,
                                    font=(UI, 12))
        self.summary.grid(row=0, column=1, sticky="w", padx=8, pady=(20, 2))
        # progress/status, kept at the top so it stays visible while the left
        # panel is scrolled
        self.status = ctk.CTkLabel(self, text="", text_color=GOLD,
                                   font=(UI, 12, "bold"))
        self.status.grid(row=0, column=1, sticky="e", padx=(8, 20), pady=(20, 2))

        # ------------------------------------------------ left: controls
        # Grouped into tabs: ~30 controls in one scrolling column was the
        # dialog's worst usability problem, and a tab is short enough to read
        # at a glance.
        #
        # Each tab body scrolls anyway. It used to rely on every tab happening
        # to fit, which is a promise the next control breaks: adding the second
        # page-shift axis pushed the Layout tab two rows past the panel and the
        # overflow was simply invisible, with no scrollbar to suggest anything
        # was missing. The bars only appear when a tab actually overflows.
        panel = ctk.CTkFrame(self, width=430, fg_color=PANEL,
                             corner_radius=theme.RADIUS_LG)
        panel.grid(row=1, column=0, sticky="nsw", padx=(16, 8), pady=8)
        panel.grid_rowconfigure(1, weight=1)
        panel.grid_propagate(False)

        self.tabs = ctk.CTkTabview(
            panel, width=406, fg_color=PANEL, corner_radius=theme.RADIUS_MD,
            segmented_button_fg_color=BG,
            segmented_button_selected_color=GOLD,
            segmented_button_selected_hover_color=GOLD_HOVER,
            segmented_button_unselected_color=BG,
            segmented_button_unselected_hover_color=GRAY_HOVER,
            text_color=TEXT_DIM, text_color_disabled=MUTED,
            anchor="w")
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=6, pady=(0, 6))
        # The rows go into a scrollable body inside each tab, never into the
        # tab frame itself, so a tab that outgrows the panel scrolls instead of
        # hiding its last controls.
        self._tab_body = {}
        for _name in ("Layout", "Image", "Backs", "Cutting", "Tests"):
            self.tabs.add(_name)
            holder = self.tabs.tab(_name)
            holder.grid_columnconfigure(0, weight=1)
            holder.grid_rowconfigure(0, weight=1)
            body = ctk.CTkScrollableFrame(holder, fg_color="transparent",
                                          corner_radius=0)
            body.grid(row=0, column=0, sticky="nsew")
            body.grid_columnconfigure(1, weight=1)
            self._tab_body[_name] = body
        self.tabs._segmented_button.configure(font=(UI, theme.TYPE["small"]))

        left = self._tab_body["Layout"]
        self._r = 0

        def tab(name):
            """Point the row helpers at another tab and restart its grid."""
            nonlocal left
            left = self._tab_body[name]
            self._r = 0

        def row(label, values, initial):
            ctk.CTkLabel(left, text=label, anchor="w", text_color=TEXT_DIM,
                         font=(UI, theme.TYPE["small"])).grid(
                row=self._r, column=0, sticky="w", padx=(12, 8), pady=5)
            menu = ctk.CTkOptionMenu(
                left, values=values, width=214, height=30,
                corner_radius=theme.RADIUS_SM, font=(UI, theme.TYPE["small"]),
                fg_color=SURFACE_INPUT, button_color=CONTROL_ALT,
                button_hover_color=GRAY_HOVER, text_color=TEXT,
                dropdown_fg_color=ROW, dropdown_text_color=TEXT,
                dropdown_hover_color=GRAY_HOVER,
                command=self._refresh_preview)
            menu.set(initial if initial in values else values[0])
            menu.grid(row=self._r, column=1, sticky="w", pady=4)
            self._r += 1
            return menu

        def entry_row(label, key, default, hint=""):
            ctk.CTkLabel(left, text=label, anchor="w", text_color=TEXT_DIM,
                         font=(UI, theme.TYPE["small"])).grid(
                row=self._r, column=0, sticky="w", padx=(12, 8), pady=5)
            fr = ctk.CTkFrame(left, fg_color="transparent")
            fr.grid(row=self._r, column=1, sticky="w", pady=4)
            e = ctk.CTkEntry(fr, width=62, height=30, fg_color=SURFACE_INPUT,
                             border_color=BORDER_STRONG,
                             corner_radius=theme.RADIUS_SM,
                             font=(UI, theme.TYPE["small"]), text_color=TEXT)
            e.insert(0, str(s.get(key, default)))
            e.pack(side="left")
            e.bind("<KeyRelease>", self._refresh_preview)
            if hint:
                ctk.CTkLabel(fr, text=hint, text_color=MUTED,
                             font=(UI, 11)).pack(side="left", padx=6)
            self._r += 1
            return e

        profile_labels = [p[0] for p in CALIBRATION_PROFILES.values()]
        saved_profile = CALIBRATION_PROFILES.get(s.get("profile", 1),
                                                 CALIBRATION_PROFILES[1])[0]

        # Presets sit above the tabs: they apply to every tab at once.
        prow = ctk.CTkFrame(panel, fg_color="transparent")
        prow.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 4))
        self.preset_menu = ctk.CTkOptionMenu(
            prow, values=self._preset_names(), width=176,
            height=theme.H_INPUT, corner_radius=theme.RADIUS_SM,
            font=(UI, theme.TYPE["small"]),
            fg_color=ROW, button_color=CONTROL_ALT,
            button_hover_color=GRAY_HOVER, text_color=TEXT,
            dropdown_fg_color=ROW, dropdown_text_color=TEXT,
            dropdown_hover_color=GRAY_HOVER,
            command=self._apply_preset)
        self.preset_menu.set(self._PRESET_NONE)
        self.preset_menu.pack(side="left")
        for _t, _c in (("Save…", self._save_preset), ("Delete", self._delete_preset)):
            ctk.CTkButton(prow, text=_t, width=58, height=theme.H_INPUT,
                          corner_radius=theme.RADIUS_SM,
                          font=(UI, theme.TYPE["small"]),
                          fg_color="transparent", hover_color=GRAY_HOVER,
                          border_width=1, border_color=BORDER_STRONG,
                          text_color=TEXT_DIM,
                          command=_c).pack(side="left", padx=(6, 0))

        tab("Layout")
        self.card_size = row("Card size", card_size_options(),
                             s.get("card_size", CARD_SIZE_DEFAULT))
        self.card_size.configure(command=self._pick_card_size)
        self.layout = row("Card grid", list(print_sheet.LAYOUTS.keys()),
                          s.get("layout", print_sheet.DEFAULT_LAYOUT))
        self.page = row("Page size", PDF_PAGE_SIZES,
                        s.get("page", PDF_DEFAULT_PAGE))
        self.split = row("File split", list(PAGES_PER_FILE.keys()),
                         s.get("split", PAGES_PER_FILE_DEFAULT))
        self.sheets_sel = entry_row("Sheets", "sheets_sel", "",
                                    "blank = all · e.g. 1 or 1-3,5")
        self.edge_bleed = entry_row("Edge bleed (mm)", "edge_bleed", 0.0,
                                    "0 = cards touching")
        self.bleed_color = row("Bleed color", BLEED_COLOR_CHOICES,
                               s.get("bleed_color", "Black"))
        self.corner_radius = entry_row("Corner radius (mm)", "corner_radius",
                                       0.0, "0 = square")
        # Two axes and both signs. It began as down-only, for cardstock that
        # feeds late and clips the top; a rear top loader eats the far end
        # instead and no downward shift reaches that. Which edge is unusable
        # depends on the tray, so the control has to reach all four.
        self.shift_down = entry_row("Shift down (mm)", "shift_down", 0.0,
                                    "negative = up")
        self.shift_right = entry_row("Shift right (mm)", "shift_right", 0.0,
                                     "negative = left")
        # How far the shift can actually go is not obvious: it is whatever
        # margin the grid leaves on the page, and it can be less than the
        # printer needs. Say the number rather than clamping in silence -
        # the report that prompted this needed 20 mm, which Letter 3x3 cannot
        # give at all.
        self.shift_hint = ctk.CTkLabel(
            left, text="", text_color=MUTED, font=(UI, 11),
            wraplength=400, justify="left")
        self.shift_hint.grid(row=self._r, column=0, columnspan=2, sticky="w",
                             padx=12, pady=(0, 4))
        self._r += 1

        tab("Cutting")
        # Both halves of "how do I separate these cards" live here: guides for
        # scissors or a guillotine first, because everyone cuts and only some
        # people own a machine, then the registration marks below.
        #
        # They used to sit on Layout, which had grown to sixteen rows doing two
        # jobs at once while this tab used a third of its height. Layout is
        # where things sit on the page; cutting is what you do to it after.
        self.guides = row("Cut guides", GUIDE_CHOICES,
                          s.get("guides", "White"))
        self.guide_style = row("Guide style", GUIDE_STYLE_CHOICES,
                               s.get("guide_style", "Cross"))
        self.guide_len = entry_row("Guide length (mm)", "guide_len", 4.0)
        self.guide_thick = entry_row("Guide thickness (pt)", "guide_thick", 0.4)
        self.guide_offset = entry_row("Guide offset (mm)", "guide_offset", 0.0,
                                      "gap from the card")
        # Duplex drift means the back's guides never land exactly where the
        # front's do, so a second set that disagrees with the one you are
        # cutting to is worse than none. Reported by someone printing duplex.
        self.back_guides = ctk.CTkSwitch(
            left, text="Cut guides on backs too",
            font=(UI, theme.TYPE["small"]), command=self._refresh_preview)
        if s.get("back_guides", True):
            self.back_guides.select()
        self.back_guides.grid(row=self._r, column=0, columnspan=2, sticky="w",
                              padx=12, pady=(2, 4))
        self._r += 1

        self.reg_marks = ctk.CTkSwitch(
            left, text="Registration marks", command=self._refresh_preview)
        if s.get("reg_marks"):
            self.reg_marks.select()
        self.reg_marks.grid(row=self._r, column=0, columnspan=2, sticky="w",
                            padx=12, pady=(4, 2))
        self._r += 1
        self.reg_hint = ctk.CTkLabel(
            left, text="", text_color=MUTED, font=(UI, 11),
            wraplength=400, justify="left")
        self.reg_hint.grid(row=self._r, column=0, columnspan=2, sticky="w",
                           padx=12)
        self._r += 1
        self.reg_pattern = row("Mark pattern", print_sheet.REG_PATTERNS,
                               s.get("reg_pattern", print_sheet.REG_PATTERNS[0]))
        self.reg_inset = entry_row(
            "Mark inset (mm)", "reg_inset", print_sheet.REG_INSET_DEFAULT_MM,
            "min 10 = Studio's")
        self.reg_length = entry_row("Mark length (mm)", "reg_length",
                                    print_sheet.REG_LENGTH_DEFAULT_MM,
                                    "5–20 · 8.89 = Studio's")
        self.reg_thick = entry_row("Mark thickness (mm)", "reg_thick", 1.0,
                                   "0.5–1")

        tab("Image")
        # Format first: it decides what the rest of this tab even applies to.
        # Photo labs generally refuse PDF, which is the whole reason the 4x6
        # page size is worth having, so PNG/JPEG are a first-class output and
        # not an afterthought.
        self.out_format = row("Output format", list(OUTPUT_FORMATS.keys()),
                              s.get("out_format", OUTPUT_FORMAT_DEFAULT))
        self.out_dpi = row("Image DPI", OUTPUT_DPI_CHOICES,
                           s.get("out_dpi", OUTPUT_DPI_DEFAULT))
        self.quality = row("Quality", list(PDF_QUALITY_MODES.keys()),
                           s.get("quality", PDF_DEFAULT_QUALITY))
        self.profile = row("Color profile", profile_labels, saved_profile)
        self.sharpen = row("Sharpening", list(SHARPEN_MODES.keys()),
                           s.get("sharpen", SHARPEN_DEFAULT))
        self.shadow = row("Shadow lift", list(SHADOW_LIFTS.keys()),
                          s.get("shadow", SHADOW_DEFAULT))
        self.border = row("Deepen black border", BORDER_MODES,
                          border_mode(s.get("border")))
        srcfr = ctk.CTkFrame(left, fg_color="transparent")
        srcfr.grid(row=self._r, column=0, columnspan=2, sticky="w",
                   padx=(12, 8), pady=(0, 4))
        self._r += 1
        ctk.CTkLabel(srcfr, text="Apply to", anchor="w", text_color=TEXT_DIM,
                     font=(UI, theme.TYPE["small"])).grid(
            row=0, column=0, sticky="nw", padx=(0, 8), pady=(2, 0))
        saved_srcs = s.get("border_sources") or {}
        self.border_srcs = {}
        # Three per row: all six on one line ran past the panel and clipped
        # the last checkbox.
        for i, (key, label) in enumerate(
                (("scryfall", "Scryfall"), ("gatherer", "Gatherer"),
                 ("mpc", "MPC"), ("pokemon", "Pokémon"),
                 ("ygo", "Yu-Gi-Oh"), ("file", "Uploads"),
                 ("back", "Backs"))):
            var = ctk.BooleanVar(
                value=bool(saved_srcs.get(key, BORDER_SOURCES.get(key, True))))
            ctk.CTkCheckBox(srcfr, text=label, variable=var, width=20,
                            height=18, checkbox_width=16, checkbox_height=16,
                            corner_radius=3, font=(UI, theme.TYPE["caption"]),
                            fg_color=GOLD, hover_color=GOLD_HOVER,
                            text_color=TEXT_DIM,
                            command=self._refresh_preview).grid(
                row=i // 3, column=1 + (i % 3), sticky="w",
                padx=(0, 12), pady=1)
            self.border_srcs[key] = var

        # Edge contrast and Edge brightness used to be typed in here and are
        # gone on purpose. Measured across their whole range on a real card,
        # contrast moved the treated band by 0.04 levels and brightness by
        # 0.03: the treatment pushes dark pixels to pure black, and a frame
        # pixel is already there at the lowest setting either offers. Leaving
        # controls that cannot change the result is worse than not having
        # them, because moving one and seeing nothing reads as the whole
        # feature being broken. The constants they set are still in
        # print_sheet.
        def slider_row(label, key, default, to, unit, fmt="{:.0f}",
                       from_=0):
            ctk.CTkLabel(left, text=label, anchor="w", text_color=TEXT_DIM,
                         font=(UI, theme.TYPE["small"])).grid(
                row=self._r, column=0, sticky="w", padx=(12, 8), pady=5)
            fr = ctk.CTkFrame(left, fg_color="transparent")
            fr.grid(row=self._r, column=1, sticky="w", pady=4)
            val = ctk.CTkLabel(fr, text="", width=54, text_color=MUTED,
                               font=(UI, 11))
            sl = ctk.CTkSlider(fr, from_=from_, to=to, width=175,
                               button_color=GOLD, progress_color=GOLD_HOVER,
                               command=lambda v: (
                                   val.configure(text=fmt.format(v) + unit),
                                   self._refresh_preview()))
            sl.set(float(s.get(key, default)))
            val.configure(text=fmt.format(sl.get()) + unit)
            sl.pack(side="left")
            val.pack(side="left", padx=(6, 0))
            self._r += 1
            # let presets set the slider AND refresh its numeric label
            self._slider_setters[key] = lambda v, sl=sl, val=val: (
                sl.set(v), val.configure(text=fmt.format(v) + unit))
            return sl

        # The two that actually move the result. Strength is linear across its
        # range; depth runs 0.5 to 50, since 0 would mean no band at all.
        self.border_amount = slider_row("Strength", "border_amount",
                                        BORDER_AMOUNT_DEFAULT, 100, "%")
        self.edge_width = slider_row(
            "How far in", "edge_width",
            round(print_sheet.CONTRAST_EDGE_WIDTH * 100, 1),
            50, "%", "{:.1f}", from_=0.5)
        self.border_width = slider_row("Manual width (forced cards)",
                                       "border_width", BORDER_WIDTH_DEFAULT,
                                       12, "%", "{:.1f}")
        self._edge_strip = self._build_edge_strip(left)

        tab("Backs")
        self.backs = row("Card backs", BACKS_MODES,
                         s.get("backs", BACKS_MODES[0]))

        # chosen card back for every non-DFC card (DFCs keep their own back)
        ctk.CTkLabel(left, text="Back image", anchor="w").grid(
            row=self._r, column=0, sticky="w", padx=(12, 8), pady=4)
        backfr = ctk.CTkFrame(left, fg_color="transparent")
        backfr.grid(row=self._r, column=1, sticky="w", pady=4)
        self._r += 1
        self.back_lbl = ctk.CTkLabel(backfr, text=self._back_label(),
                                     text_color=MUTED, font=(UI, 11),
                                     width=110, anchor="w")
        self.back_lbl.pack(side="left")
        ctk.CTkButton(backfr, text="File…", width=52, height=26,
                      fg_color=GRAY_BTN, hover_color=GRAY_HOVER,
                      command=self._choose_back_file).pack(side="left", padx=2)
        ctk.CTkButton(backfr, text="MPC…", width=52, height=26,
                      fg_color=GRAY_BTN, hover_color=GRAY_HOVER,
                      command=self._choose_back_mpc).pack(side="left", padx=2)

        self.back_dx = entry_row("Back offset X (mm)", "back_dx", 0.0)
        self.back_dy = entry_row("Back offset Y (mm)", "back_dy", 0.0)
        self.back_rot = entry_row("Back rotation (°)", "back_rot", 0.0,
                                  "corrects angular drift")
        self.back_bleed = entry_row("Back bleed (mm)", "back_bleed", 1.5,
                                    "covers duplex drift")

        tab("Tests")
        tests = ctk.CTkFrame(left, fg_color="transparent")
        tests.grid(row=self._r, column=0, columnspan=2, sticky="w",
                   padx=12, pady=4)
        self._r += 1
        self.cal_btn = ctk.CTkButton(
            tests, text="Calibration...", width=120,
            fg_color=GRAY_BTN, hover_color=GRAY_HOVER,
            command=self._calibration)
        self.cal_btn.pack(side="left", padx=(0, 8))
        self.shadow_btn = ctk.CTkButton(
            tests, text="Shadow test...", width=120,
            fg_color=GRAY_BTN, hover_color=GRAY_HOVER,
            command=self._shadow_test)
        self.shadow_btn.pack(side="left")
        self.duplex_btn = ctk.CTkButton(
            tests, text="Duplex align...", width=120,
            fg_color=GRAY_BTN, hover_color=GRAY_HOVER,
            command=self._duplex_test)
        self.duplex_btn.pack(side="left", padx=(8, 0))

        # ------------------------------------------------ right: preview
        right = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=12)
        right.grid(row=1, column=1, sticky="nsew", padx=(8, 16), pady=8)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(right, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10,
                  pady=(10, 2))
        head.grid_columnconfigure(2, weight=1)
        self.prev_page_btn = ctk.CTkButton(head, text="◀", width=30, height=24,
                                           fg_color=GRAY_BTN, hover_color=GRAY_HOVER,
                                           command=lambda: self._flip_page(-1))
        self.prev_page_btn.grid(row=0, column=0, sticky="w")
        # Undo sits with the page nav rather than the export buttons: it acts
        # on the sheet, and the sheet is what you are looking at.
        hist = ctk.CTkFrame(head, fg_color="transparent")
        hist.grid(row=0, column=1, sticky="w", padx=(10, 0))
        self.undo_btn = ctk.CTkButton(hist, text="↶", width=30, height=24,
                                      font=(UI, 14), state="disabled",
                                      fg_color=GRAY_BTN, hover_color=GRAY_HOVER,
                                      command=self._undo)
        self.undo_btn.pack(side="left")
        self.redo_btn = ctk.CTkButton(hist, text="↷", width=30, height=24,
                                      font=(UI, 14), state="disabled",
                                      fg_color=GRAY_BTN, hover_color=GRAY_HOVER,
                                      command=self._redo)
        self.redo_btn.pack(side="left", padx=(4, 0))
        self.preview_title = ctk.CTkLabel(head, text="Preview",
                                          text_color=MUTED, font=(UI, 12))
        self.preview_title.grid(row=0, column=2)
        self.next_page_btn = ctk.CTkButton(head, text="▶", width=30, height=24,
                                           fg_color=GRAY_BTN, hover_color=GRAY_HOVER,
                                           command=lambda: self._flip_page(1))
        self.next_page_btn.grid(row=0, column=3, sticky="e")
        self.side_btn = ctk.CTkSegmentedButton(
            head, values=["Fronts", "Backs"], height=24,
            font=(UI, 11), command=lambda _v: self._draw_preview(),
            fg_color=BG, unselected_color=BG, unselected_hover_color=GRAY_HOVER,
            selected_color=GOLD, selected_hover_color=GOLD_HOVER,
            text_color="#d7dbe4")
        self.side_btn.set("Fronts")
        self.side_btn.grid(row=0, column=4, sticky="e", padx=(8, 0))
        self.canvas = tk.Canvas(right, bg=PANEL, highlightthickness=0, bd=0)
        self.canvas.grid(row=1, column=0, sticky="nsew", padx=(10, 0),
                         pady=(0, 6))
        self.vbar = ctk.CTkScrollbar(right, command=self.canvas.yview)
        self.vbar.grid(row=1, column=1, sticky="ns", padx=(2, 8), pady=(0, 6))
        self.canvas.configure(yscrollcommand=self._on_yscroll)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        # Tk dispatches only the most specific binding, so these take the click
        # instead of the plain handler rather than as well as it.
        self.canvas.bind("<Control-ButtonRelease-1>", self._on_ctrl_release)
        self.canvas.bind("<Alt-ButtonRelease-1>", self._on_alt_release)
        self.canvas.bind("<Shift-ButtonRelease-1>", self._on_shift_release)
        self.bind("<Escape>", self._clear_selection)
        self.canvas.bind("<Button-3>", self._preview_rclick)
        self.canvas.bind("<Motion>", self._preview_motion)
        self.canvas.bind("<Leave>", self._preview_leave)
        self.canvas.bind("<MouseWheel>",
                         lambda e: self.canvas.yview_scroll(
                             int(-e.delta / 120), "units"))
        self.canvas.bind("<Configure>", self._recenter_preview)
        for seq in ("<Control-z>", "<Control-Z>"):
            self.bind(seq, self._undo)
        for seq in ("<Control-y>", "<Control-Y>", "<Control-Shift-Z>"):
            self.bind(seq, self._redo)
        ctk.CTkLabel(right, text="Drag a card to reorder, onto any sheet · "
                     "click selects, shift+click adds to the selection · "
                     "Ctrl+click adds a copy · Alt+click removes · "
                     "right-click for more · Ctrl+Z undoes",
                     text_color=MUTED, font=(UI, 11),
                     wraplength=self._PREVIEW_BOX[0], justify="center").grid(
            row=2, column=0, columnspan=2, sticky="ew", padx=10, pady=(0, 8))

        # ------------------------------------------------ bottom buttons
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=2, column=0, columnspan=2, sticky="e",
                  padx=20, pady=(0, 14))
        # "Close", not "Cancel". Export no longer closes the dialog, so this
        # is the only way out and it has nothing left to cancel - and after an
        # export that has already been written, "Cancel" reads like it might
        # undo it.
        ctk.CTkButton(btns, text="Close", width=88, height=theme.H_BUTTON,
                      corner_radius=theme.RADIUS_SM,
                      font=(UI, theme.TYPE["body"]),
                      fg_color="transparent", hover_color=GRAY_HOVER,
                      border_width=1, border_color=BORDER_STRONG,
                      text_color=TEXT_DIM, command=self.destroy).pack(
            side="left", padx=6)
        ctk.CTkButton(btns, text="Add cards…", width=110,
                      height=theme.H_BUTTON, corner_radius=theme.RADIUS_SM,
                      font=(UI, theme.TYPE["body"]),
                      fg_color=CONTROL_ALT, hover_color=GRAY_HOVER,
                      text_color=TEXT, command=self._add_cards).pack(
            side="left", padx=6)
        self.export_btn = ctk.CTkButton(btns, text="Export", width=132,
                                        height=theme.H_BUTTON_LG,
                                        corner_radius=theme.RADIUS_SM,
                                        fg_color=GOLD, hover_color=GOLD_HOVER,
                                        text_color=GOLD_TEXT,
                                        font=(UI, theme.TYPE["subtitle"], "bold"),
                                        command=self._export)
        self.export_btn.pack(side="left")

        self._shield_entries()
        self._update_history()
        self._draw_preview()
        threading.Thread(target=self._load_thumbs, daemon=True).start()

    # ------------------------------------------------------------- values
    def _profile_id(self):
        label = self.profile.get()
        for pid, prof in CALIBRATION_PROFILES.items():
            if prof[0] == label:
                return pid
        return 1

    def _float(self, widget, default=0.0, lo=None, hi=None):
        try:
            v = float(widget.get())
        except ValueError:
            return default
        if lo is not None:
            v = max(lo, v)
        if hi is not None:
            v = min(hi, v)
        return v

    def _offsets(self):
        return (self._float(self.back_dx), self._float(self.back_dy))

    def _shift(self):
        return self._float(self.shift_down, 0.0, -100.0, 100.0)

    def _shift_x(self):
        return self._float(self.shift_right, 0.0, -100.0, 100.0)

    def _shifted(self):
        return bool(self._shift() or self._shift_x())

    def _bleed(self):
        return self._float(self.back_bleed, 1.5, 0.0, 3.0)

    def _edge_bleed(self):
        return self._float(self.edge_bleed, 0.0, 0.0, 2.0)

    def _back_rot(self):
        return self._float(self.back_rot, 0.0, -5.0, 5.0)

    def _guide_len(self):
        return self._float(self.guide_len, 4.0, 0.0, 20.0)

    def _guide_thick(self):
        return self._float(self.guide_thick, 0.4, 0.1, 3.0)

    def _guide_offset(self):
        return self._float(self.guide_offset, 0.0, 0.0, 10.0)

    def _corner_radius(self):
        return self._float(self.corner_radius, 0.0, 0.0, 6.0)

    def _is_pdf(self):
        return OUTPUT_FORMATS.get(self.out_format.get()) is None

    def _out_dpi(self):
        try:
            return int(self.out_dpi.get())
        except (TypeError, ValueError):
            return int(OUTPUT_DPI_DEFAULT)

    def _pick_card_size(self, name):
        """Same editor as the main window, so either place can define one."""
        if name != CUSTOM_SIZE_EDIT:
            self._refresh_preview()
            return
        label = ask_custom_card_size(self)
        self.card_size.configure(values=card_size_options())
        self.card_size.set(label or load_settings().get("card_size",
                                                        CARD_SIZE_DEFAULT))
        self._refresh_preview()

    def _card_mm(self):
        return card_size_mm(self.card_size.get())

    def _path_for(self, key):
        """The image a preview key stands for. Front keys are card ids; back
        keys are already paths, and so is anything unknown."""
        for c in self._order:
            if c.uid == key:
                return str(c.path)
        return key

    def _mode_for(self, path):
        """Per-image border mode: an explicit override wins, then the source
        rule, then 'auto' (follow the global switch).

        Keyed by path, not by copy, because build_pdf's border_modes is keyed
        by path - two copies of one card cannot be treated differently, and
        pretending otherwise in the preview would lie about the export."""
        override = self._border_modes.get(path)
        if override:
            return override
        src = self.card_sources.get(str(path))
        if src is not None:
            var = self.border_srcs.get(src)
            if var is not None and not var.get():
                return "off"
        return "auto"

    def _effective_border_modes(self):
        # the working set, not the dialog's opening arguments: cards added
        # through "Add cards…" have a source rule too
        keys = set(self._border_modes) | {str(c.path) for c in self._order}
        return {k: self._mode_for(k) for k in keys}

    def _border_style(self):
        """Which of the two border algorithms the mode picker selected."""
        if self.border.get() == BORDER_MODES[2]:
            return print_sheet.BORDER_STYLE_AUTO
        return print_sheet.BORDER_STYLE_CONTRAST

    # -------------------------------------------------- border before/after
    # The treatment lives in the outer few percent of the card, and the sheet
    # preview draws a card about 120 px wide. At that size the change is two
    # or three pixels and simply cannot be seen, which is why the controls
    # felt inert even where they were not. This shows one corner at a usable
    # size, untreated beside treated, right under the sliders that cause it.
    _STRIP = (250, 104)         # canvas size: two corners plus the divider

    def _build_edge_strip(self, parent):
        ctk.CTkLabel(parent, text="Border, before and after",
                     anchor="w", text_color=TEXT_DIM,
                     font=(UI, theme.TYPE["small"])).grid(
            row=self._r, column=0, columnspan=2, sticky="w",
            padx=(12, 8), pady=(10, 2))
        self._r += 1
        cv = tk.Canvas(parent, width=self._STRIP[0], height=self._STRIP[1],
                       bg=ROW, highlightthickness=1,
                       highlightbackground=BORDER, bd=0)
        cv.grid(row=self._r, column=0, columnspan=2, sticky="w",
                padx=12, pady=(0, 8))
        self._r += 1
        return cv

    def _draw_edge_strip(self):
        """Repaint the before/after corners from the first card on the sheet."""
        cv = getattr(self, "_edge_strip", None)
        if cv is None or not cv.winfo_exists():
            return
        cv.delete("all")
        pair = next((self._thumbs_raw.get(str(c.path)) for c in self._order
                     if str(c.path) in self._thumbs_raw), None)
        if pair is None:
            cv.create_text(self._STRIP[0] // 2, self._STRIP[1] // 2,
                           text="loading…", fill=MUTED, font=(UI, 10))
            return
        work = pair[0]
        w, h = self._STRIP[0] // 2 - 2, self._STRIP[1] - 4
        # A corner, because that is where two treated edges meet and the
        # effect is at its most obvious.
        # Crop tight enough that the treated band is a large share of what is
        # shown, and tie it to the band's own width so it keeps that share as
        # the slider moves. Taking a fixed half of the card puts the band back
        # to a few pixels on screen, which is the problem this strip exists to
        # solve.
        edge_px = self._edge_width() * min(work.width, work.height)
        side = int(min(max(edge_px * 2.6, work.width * 0.14), work.width * 0.6))
        box = (0, 0, side, side)
        before = work.crop(box).resize((w, h))
        treated = print_sheet._contrast_edges(
            work, None, self.border_amount.get() / 100.0,
            self._edge_width(), self._edge_contrast(), self._edge_brightness())
        after = treated.crop(box).resize((w, h))
        strip = PILImage.new("RGB", self._STRIP, (20, 24, 30))
        strip.paste(before, (2, 2))
        strip.paste(after, (self._STRIP[0] // 2 + 1, 2))
        self._edgephoto = PILImageTk.PhotoImage(strip)
        cv.create_image(0, 0, anchor="nw", image=self._edgephoto)
        mid = self._STRIP[0] // 2
        cv.create_line(mid, 0, mid, self._STRIP[1], fill=theme.ACCENT, width=1)
        cv.create_text(6, 8, anchor="w", text="off", fill="#d7dbe4",
                       font=(UI, 9, "bold"))
        cv.create_text(mid + 6, 8, anchor="w", text="on", fill=theme.ACCENT,
                       font=(UI, 9, "bold"))

    def _edge_width(self):
        return float(self.edge_width.get()) / 100.0

    # Fixed now rather than typed in. Both saturate immediately: a frame pixel
    # reaches pure black at the lowest setting either used to offer, so their
    # whole range moved the result by hundredths of a level. See the note
    # beside the sliders.
    def _edge_contrast(self):
        return print_sheet.CONTRAST_CONTRAST

    def _edge_brightness(self):
        return print_sheet.CONTRAST_BRIGHTNESS

    def _reg_inset(self):
        return self._float(self.reg_inset, print_sheet.REG_INSET_DEFAULT_MM,
                           print_sheet.REG_INSET_MIN_MM, 86.0)

    def _reg_length(self):
        return self._float(self.reg_length, 20.0,
                           print_sheet.REG_LENGTH_MIN_MM,
                           print_sheet.REG_LENGTH_MAX_MM)

    def _reg_thick(self):
        return self._float(self.reg_thick, 1.0,
                           print_sheet.REG_THICK_MIN_MM,
                           print_sheet.REG_THICK_MAX_MM)

    def _sheets_sel(self):
        """Parse the Sheets box ('' / '1' / '1-3' / '1,3,5' / '2-') into a set
        of 0-based sheet indices, or None for all sheets. Input is 1-based."""
        txt = self.sheets_sel.get().strip()
        if not txt:
            return None
        out = set()
        for part in txt.replace(" ", "").split(","):
            if not part:
                continue
            if "-" in part:
                a, _, b = part.partition("-")
                try:
                    lo = int(a) if a else 1
                    hi = int(b) if b else 9999
                except ValueError:
                    continue
                out.update(n - 1 for n in range(lo, hi + 1))
            else:
                try:
                    out.add(int(part) - 1)
                except ValueError:
                    continue
        return out or None

    def _collect_settings(self) -> dict:
        """Every export control as a flat dict - used both to persist the
        last-used values and to save/load named presets."""
        dx, dy = self._offsets()
        return {
            "card_size": self.card_size.get(),
            "reg_marks": bool(self.reg_marks.get()),
            "reg_pattern": self.reg_pattern.get(),
            "reg_inset": self._reg_inset(),
            "reg_length": self._reg_length(),
            "reg_thick": self._reg_thick(),
            "layout": self.layout.get(),
            "page": self.page.get(),
            "quality": self.quality.get(),
            "out_format": self.out_format.get(),
            "out_dpi": self.out_dpi.get(),
            "split": self.split.get(),
            "profile": self._profile_id(),
            "sharpen": self.sharpen.get(),
            "shadow": self.shadow.get(),
            "border": self.border.get(),
            "border_amount": round(self.border_amount.get(), 1),
            "border_width": round(self.border_width.get(), 1),
            "border_sources": {k: bool(v.get())
                               for k, v in self.border_srcs.items()},
            "edge_width": round(self._edge_width() * 100, 1),
            "backs": self.backs.get(),
            "back_dx": dx,
            "back_dy": dy,
            "back_rot": self._back_rot(),
            "back_bleed": self._bleed(),
            "edge_bleed": self._edge_bleed(),
            "bleed_color": self.bleed_color.get(),
            "guides": self.guides.get(),
            "back_guides": bool(self.back_guides.get()),
            "guide_style": self.guide_style.get(),
            "guide_len": self._guide_len(),
            "guide_thick": self._guide_thick(),
            "guide_offset": self._guide_offset(),
            "corner_radius": self._corner_radius(),
            "shift_down": self._shift(),
            "shift_right": self._shift_x(),
        }

    def _apply_settings(self, d: dict):
        """Push a settings dict (a preset) back into every widget."""
        def om(w, key):
            if key in d:
                try:
                    w.set(d[key])
                except Exception:
                    pass
        om(self.layout, "layout"); om(self.page, "page"); om(self.split, "split")
        om(self.card_size, "card_size"); om(self.reg_pattern, "reg_pattern")
        if "reg_marks" in d:
            (self.reg_marks.select if d["reg_marks"] else
             self.reg_marks.deselect)()
        if "back_guides" in d:
            (self.back_guides.select if d["back_guides"] else
             self.back_guides.deselect)()
        om(self.bleed_color, "bleed_color"); om(self.guides, "guides")
        om(self.guide_style, "guide_style"); om(self.quality, "quality")
        om(self.sharpen, "sharpen"); om(self.shadow, "shadow")
        om(self.out_format, "out_format"); om(self.out_dpi, "out_dpi")
        om(self.border, "border"); om(self.backs, "backs")
        if "profile" in d:
            prof = CALIBRATION_PROFILES.get(d["profile"])
            if prof:
                self.profile.set(prof[0])
        for e, key in ((self.edge_bleed, "edge_bleed"),
                       (self.shift_down, "shift_down"),
                       (self.shift_right, "shift_right"),
                       (self.guide_len, "guide_len"),
                       (self.guide_thick, "guide_thick"),
                       (self.guide_offset, "guide_offset"),
                       (self.corner_radius, "corner_radius"),
                       (self.reg_inset, "reg_inset"),
                       (self.reg_length, "reg_length"),
                       (self.reg_thick, "reg_thick"),
                       (self.back_dx, "back_dx"), (self.back_dy, "back_dy"),
                       (self.back_rot, "back_rot"), (self.back_bleed, "back_bleed")):
            if key in d:
                e.delete(0, "end"); e.insert(0, str(d[key]))
        for key in ("border_amount", "border_width", "edge_width"):
            if key in d and key in self._slider_setters:
                self._slider_setters[key](float(d[key]))
        self.back_lbl.configure(text=self._back_label())
        threading.Thread(target=self._load_thumbs, daemon=True).start()
        self._draw_preview()

    def _persist(self):
        s = load_settings()
        s.update(self._collect_settings())
        save_settings(s)
        # keep the main window's copy of the shared card-size setting in step
        menu = getattr(self.master, "card_size_menu", None)
        if menu is not None:
            try:
                menu.set(self.card_size.get())
            except Exception:
                pass

    # ---------------------------------------------------------- presets
    _PRESET_NONE = "(presets)"

    def _preset_names(self):
        presets = load_settings().get("export_presets", {})
        return [self._PRESET_NONE] + sorted(presets)

    def _apply_preset(self, name):
        if name == self._PRESET_NONE:
            return
        d = load_settings().get("export_presets", {}).get(name)
        if d:
            self._apply_settings(d)

    def _save_preset(self):
        dlg = ctk.CTkInputDialog(text="Preset name:", title="Save export preset")
        name = (dlg.get_input() or "").strip()
        if not name:
            return
        s = load_settings()
        presets = s.get("export_presets", {})
        presets[name] = self._collect_settings()
        s["export_presets"] = presets
        save_settings(s)
        self.preset_menu.configure(values=self._preset_names())
        self.preset_menu.set(name)

    def _delete_preset(self):
        name = self.preset_menu.get()
        if name == self._PRESET_NONE:
            return
        s = load_settings()
        presets = s.get("export_presets", {})
        if presets.pop(name, None) is not None:
            s["export_presets"] = presets
            save_settings(s)
        self.preset_menu.configure(values=self._preset_names())
        self.preset_menu.set(self._PRESET_NONE)

    def _ui(self, fn, *args):
        """Marshal a call onto the Tk main thread (no-op if window is gone).

        The same helper App has. This dialog does its own background work now
        (the back-face lookup, changing a card's art) and was calling a method
        it did not own: the thread died on the AttributeError with nothing to
        show for it, so a new art downloaded and upscaled and then never
        reached the sheet.
        """
        try:
            self.after(0, lambda: fn(*args))
        except RuntimeError:
            pass

    def _set_status(self, text):
        self.after(0, lambda: self.status.configure(text=text))

    # ------------------------------------------------------------ undo/redo
    # Everything the user can do to the working set lives in four containers,
    # so a snapshot is a shallow copy of those and nothing has to know how to
    # invert itself. _Card instances are immutable in practice (path and uid
    # never change), which is what makes the shallow copy safe.
    _UNDO_DEPTH = 50

    def _snapshot(self):
        return (list(self._order), set(self._excluded),
                dict(self._back_of), dict(self._border_modes))

    def _restore(self, snap):
        order, excluded, back_of, modes = snap
        self._order = list(order)
        self._excluded = set(excluded)
        self._back_of = dict(back_of)
        self._border_modes = dict(modes)

    def _push_undo(self, label):
        """Record the state as it is *now*, before `label` changes it."""
        self._undo_stack.append((label, self._snapshot()))
        del self._undo_stack[:-self._UNDO_DEPTH]
        self._redo_stack.clear()
        self._update_history()

    def _drop_history(self):
        """Forget both stacks. For actions that cannot be taken back - undoing
        past a deleted file would restore cards pointing at nothing."""
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._update_history()

    def _undo(self, _event=None):
        if not self._undo_stack:
            return "break"
        label, snap = self._undo_stack.pop()
        self._redo_stack.append((label, self._snapshot()))
        self._restore(snap)
        self._history_changed(f"Undid: {label}")
        return "break"

    def _redo(self, _event=None):
        if not self._redo_stack:
            return "break"
        label, snap = self._redo_stack.pop()
        self._undo_stack.append((label, self._snapshot()))
        self._restore(snap)
        self._history_changed(f"Redid: {label}")
        return "break"

    def _history_changed(self, note):
        # redoing an undone "Add cards…" brings back cards whose thumbnails
        # were never loaded, so the loader runs again; it only ever adds
        threading.Thread(target=self._load_thumbs, daemon=True).start()
        self._draw_preview()
        self._update_history()
        self._set_status(note)

    def _update_history(self):
        """Buttons say what they would take back, not just that they exist."""
        for btn, stack, verb in ((self.undo_btn, self._undo_stack, "Undo"),
                                 (self.redo_btn, self._redo_stack, "Redo")):
            if stack:
                btn.configure(state="normal")
                _tooltip(btn, f"{verb} {stack[-1][0]}")
            else:
                btn.configure(state="disabled")
                _tooltip(btn, f"Nothing to {verb.lower()}")

    def _shield_entries(self, parent=None):
        """Ctrl+Z inside a text field belongs to the text field.

        Bound on the entry itself, which consumes the event before it reaches
        the dialog: Tk runs the widget's own bindings ahead of the toplevel's,
        so returning "break" there stops it. Asking who has focus instead was
        unreliable - CustomTkinter entries are composites, and focus_get()
        answers about the wrapper, not the Tk entry inside it."""
        for child in (parent or self).winfo_children():
            if isinstance(child, (tk.Entry, tk.Text)):
                for seq in ("<Control-z>", "<Control-Z>", "<Control-y>",
                            "<Control-Y>", "<Control-Shift-Z>"):
                    child.bind(seq, lambda _e: "break")
            self._shield_entries(child)

    # ------------------------------------------------------------- preview
    _PREVIEW_BOX = (470, 560)   # max preview pixels (w, h)

    def _sheet_images(self, drop_excluded=True):
        """
        What goes on the sheets: (fronts, backs). Fronts are _Card instances,
        backs are image paths (or None when duplex is off) - a back is not
        something the user reorders, so it needs no identity of its own. In
        duplex a card's own back face stops being a front. A chosen card back
        overrides back.png. When drop_excluded is True the cards the user
        right-clicked out are removed (the export view); when False they are
        kept so the preview can still show and restore them.
        """
        def keep(c):
            return not drop_excluded or c.uid not in self._excluded

        fronts = [c for c in self._order if keep(c)]
        if self.backs.get() != BACKS_MODES[0]:
            # A card chosen as the back applies to everything. Otherwise each
            # card asks for the back of its own game, so a sheet mixing Magic
            # and Pokemon stops printing one back over both.
            def default_for(card):
                if self._custom_back:
                    return self._custom_back
                return find_back_image(self.card_sources.get(str(card.path)))

            backs = [self._back_of.get(c.uid) or default_for(c) for c in fronts]
            # Backs go through the same flatten path as fronts, so they need
            # a source too or the "Backs" checkbox would control nothing.
            for b in backs:
                if b is not None:
                    self.card_sources.setdefault(str(b), "back")
            return fronts, backs
        return fronts, None

    def _load_thumbs(self):
        self._loading = True
        fronts, backs = self._sheet_images()
        # by path: copies of one card share a thumbnail
        wanted = [c.path for c in fronts] + [b for b in (backs or []) if b]
        for p in wanted:
            key = str(p)
            if key in self._thumbs:
                continue
            try:
                src = PILImage.open(p).convert("RGBA")
                # Working copy is deliberately larger than the preview: the
                # detector behaves like it will at print resolution, and the
                # loupe has real detail to magnify.
                mid = src.resize(WORK_SIZE)
                flat = PILImage.new("RGB", mid.size, (0, 0, 0))
                flat.paste(mid, mask=mid.split()[3])
                opaque = np.asarray(mid.split()[3]) > 250
                self._thumbs_raw[key] = (flat, opaque)
                self._thumbs[key] = flat.resize(THUMB_SIZE)
            except (OSError, ValueError):
                continue
        self._loading = False
        try:
            self.after(0, self._draw_preview)
        except RuntimeError:
            pass

    def _treated_thumb(self, key):
        """Working-size treated copy (cached for the loupe) plus its thumb.
        Built on demand - only for cards actually painted on a visible sheet."""
        if key in self._thumbs_b:
            return self._thumbs_b[key]
        pair = self._thumbs_raw.get(key)
        if not pair:
            return None
        flat, opaque = pair
        work = print_sheet._deepen_black_border(
            flat, opaque, amount=self.border_amount.get() / 100.0,
            manual_width=0.0)
        self._work_b[key] = work
        thumb = work.resize(THUMB_SIZE)
        self._thumbs_b[key] = thumb
        return thumb

    def _refresh_preview(self, *_):
        if self._prev_job:
            try:
                self.after_cancel(self._prev_job)
            except Exception:
                pass
        # sliders change the treated look: drop the cached treated copies so
        # only the sheets actually on screen pay to rebuild them (lazy).
        self._thumbs_b.clear()
        self._work_b.clear()
        threading.Thread(target=self._load_thumbs, daemon=True).start()
        self._prev_job = self.after(200, self._draw_preview)

    _SHEET_GAP = 34             # vertical space between stacked sheets

    def _draw_preview(self):
        # a slider can leave a redraw queued; the dialog may be gone by then
        if not self.winfo_exists():
            return
        self._draw_edge_strip()
        cols, rows, landscape = print_sheet.LAYOUTS.get(
            self.layout.get(), print_sheet.LAYOUTS[print_sheet.DEFAULT_LAYOUT])
        pw, ph = _PAGE_MM.get(self.page.get(), _PAGE_MM["A4"])
        if landscape:
            pw, ph = ph, pw
        s = min(self._PREVIEW_BOX[0] / pw, self._PREVIEW_BOX[1] / ph)
        W, H = int(pw * s), int(ph * s)

        per_page = cols * rows
        CW, CH = self._card_mm()          # card size in mm for this TCG
        border_on = self.border.get() != BORDER_MODES[0]
        # preview keeps excluded cards visible (shown crossed out); the export
        # count below uses the dropped-excluded list
        fronts, backs = self._sheet_images(drop_excluded=False)
        exp_fronts, _ = self._sheet_images(drop_excluded=True)
        duplex = backs is not None
        showing_backs = duplex and self.side_btn.get() == "Backs"
        self._showing_backs = showing_backs
        # Two identities per slot. `keys` address the copy (hit-boxes, drag,
        # exclusion), `paths` address the image (thumbnail, border treatment).
        # They differ only on the fronts, where two copies share one path;
        # a back is addressed by its path either way.
        if showing_backs:
            page_keys = [str(b) if b else None for b in backs]
            page_paths = list(page_keys)
        else:
            page_keys = [c.uid for c in fronts]
            page_paths = [str(c.path) for c in fronts]
        # A back page prints offset and rotated to cancel duplex drift. Showing
        # it square was how a wrong offset stayed invisible until the cut.
        # The PDF's y runs up and the preview's runs down, so dy flips.
        boff = self._offsets() if showing_backs else (0.0, 0.0)
        brot = self._back_rot() if showing_backs else 0.0
        bdx, bdy = boff[0], -boff[1]
        eb = self._edge_bleed()
        g = 2 * eb
        bw = cols * CW + (cols - 1) * g
        bh = rows * CH + (rows - 1) * g
        # with registration marks the cutter aligns to the marks, so the page
        # shift is ignored (see build_pdf) - keep the preview in step
        reg_on = bool(self.reg_marks.get())
        # Placement comes from print_sheet rather than being recomputed here,
        # so the preview cannot disagree with the export about where a shift
        # lands - including when it is clamped at the paper edge.
        left, top = print_sheet.block_origin_mm(
            pw, ph, bw, bh,
            0.0 if reg_on else self._shift_x(),
            0.0 if reg_on else self._shift())

        def X(v):
            return int(v * s)

        bleed_fill = {"Black": (10, 10, 10), "White": (250, 250, 250)}.get(
            self.bleed_color.get(), (10, 10, 10))
        gc = {"White": (255, 255, 255), "Black": (0, 0, 0),
              "Gray": (120, 120, 120), "None": None}.get(self.guides.get())
        cw, ch = X(left + CW) - X(left), X(top + CH) - X(top)

        guide_len = self._guide_len()
        guide_style = self.guide_style.get()
        guide_offset = self._guide_offset()
        corner_r = self._corner_radius()
        corner_mask = None
        if corner_r > 0:
            r = max(1, int(corner_r * cw / CW))
            corner_mask = PILImage.new("L", (cw, ch), 0)
            PILDraw.Draw(corner_mask).rounded_rectangle(
                [0, 0, cw - 1, ch - 1], radius=r, fill=255)

        # Slot positions come from the same helper the PDF uses (it is unit
        # agnostic), in mm with a bottom-left origin; the preview flips y.
        reg_four = self.reg_pattern.get() == print_sheet.REG_PATTERNS[1]
        reg_args = (self._reg_inset(), self._reg_length(), self._reg_thick())
        oy_mm = ph - top - bh
        all_pos = print_sheet.layout_positions(
            self.layout.get(), left, oy_mm, bh, g, cols, rows, CW, CH)
        if reg_on:
            blocked = print_sheet._reg_blocked_slots(
                [(x * mm_pt, y * mm_pt) for x, y in all_pos],
                CW * mm_pt, CH * mm_pt, pw * mm_pt, ph * mm_pt,
                *reg_args, reg_four)
        else:
            blocked = set()
        usable = [p for i, p in enumerate(all_pos) if i not in blocked]
        per_sheet = len(usable) or 1
        sheets = max(1, -(-len(fronts) // per_sheet))
        self._page = max(0, min(self._page, sheets - 1))

        # Room to move: the shift is measured from centre, so each axis can
        # give away half its margin before hitting the printable edge.
        room_x = max(0.0, (pw - bw) / 2 - 3.0)
        room_y = max(0.0, (ph - bh) / 2 - 3.0)
        want_x, want_y = self._shift_x(), self._shift()
        if reg_on and self._shifted():
            self.shift_hint.configure(
                text="Ignored while registration marks are on: the cutter "
                     "aligns to the marks.", text_color=MUTED)
        elif abs(want_x) > room_x + 0.05 or abs(want_y) > room_y + 0.05:
            self.shift_hint.configure(
                text=f"⚠ Clamped to the paper. This grid leaves "
                     f"±{room_x:.1f} mm across and ±{room_y:.1f} mm "
                     f"down - a smaller grid or a bigger page gives more.",
                text_color="#e0b050")
        else:
            self.shift_hint.configure(
                text=f"Room to move: ±{room_x:.1f} mm across, "
                     f"±{room_y:.1f} mm down.", text_color=MUTED)

        if not reg_on:
            self.reg_hint.configure(
                text="Off - cards use every slot.", text_color=MUTED)
        elif blocked:
            # What blocks a slot is a CORNER mark landing on a CORNER card, so
            # the fix is usually to move the marks outward - often by half a
            # millimetre. Name the exact inset that works instead of leaving
            # the user to hunt for it; fall back to naming a layout that fits.
            fix_inset = print_sheet.best_inset(
                self.page.get(), CW * mm_pt, CH * mm_pt, self.layout.get(),
                reg_args[1], reg_args[2], reg_four, start_mm=reg_args[0])
            clean = [n for n in print_sheet.clean_layouts(
                self.page.get(), CW * mm_pt, CH * mm_pt, *reg_args, reg_four)
                if n != self.layout.get()]

            if fix_inset is not None:
                fix = (f" Mark inset {fix_inset:g} mm keeps all "
                       f"{len(all_pos)}.")
            elif clean:
                fix = f" {' or '.join(clean)} keeps every slot on this page."
            else:
                fix = (" No inset or layout keeps them all on this page - "
                       "A3, Legal or Tabloid has the margin for it.")
            n = len(blocked)
            lost = (f"{n} sits under a corner mark and stays empty "
                    "(that card moves to the next sheet)" if n == 1 else
                    f"{n} sit under a corner mark and stay empty "
                    "(those cards move to the next sheet)")
            self.reg_hint.configure(
                text=f"⚠ {len(usable)} of {len(all_pos)} slots usable - "
                     f"{lost}.{fix}",
                text_color="#e0b050")
        else:
            shift_note = (" The page shift is ignored: the cutter aligns to "
                          "the marks." if self._shifted() else "")
            self.reg_hint.configure(
                text=f"✓ All {len(all_pos)} slots usable with these marks." + shift_note,
                text_color="#7cc47c")

        def render_sheet(page):
            """One sheet as a (W,H) image plus its local card hit-boxes."""
            img = PILImage.new("RGB", (W, H), (255, 255, 255))
            # Cards and cut guides move together: the offset is what makes the
            # back's ink land where the front's did, so a guide left behind
            # would mark a cut that is not there. Composing them on their own
            # layer moves the lot as one, the way the PDF's transform does.
            # Registration marks and the page edge are drawn on `img` after,
            # because those stay square to the paper.
            moved = showing_backs and (bdx or bdy or brot)
            surf = PILImage.new("RGBA", (W, H), (0, 0, 0, 0)) if moved else img
            d = PILDraw.Draw(surf)
            slots = []
            for k, (px, py) in enumerate(usable):
                slot = page * per_sheet + k
                # backs print mirrored so they land behind their front
                x = print_sheet.mirror_x(px, left, bw, CW) if showing_backs else px
                y = ph - py - CH          # bottom-left origin -> preview's top
                if slot >= len(page_keys):
                    continue
                if eb > 0:
                    d.rectangle([X(x - eb), X(y - eb),
                                 X(x + CW + eb), X(y + CH + eb)],
                                fill=bleed_fill, outline=(210, 210, 215))
                key = page_keys[slot]
                path = page_paths[slot]
                mode = self._mode_for(path)
                treated = mode == "on" or (mode == "auto" and border_on)
                if path:
                    t = self._treated_thumb(path) if treated else None
                    t = t or self._thumbs.get(path)
                else:
                    t = None
                if t:
                    surf.paste(t.resize((cw, ch)), (X(x), X(y)), corner_mask)
                    slots.append((X(x), X(y), X(x + CW), X(y + CH), key))
                    if key in self._selected:
                        # A ring rather than a tint: the point of selecting a
                        # card here is to look at it, so nothing may sit on
                        # top of the art.
                        for i in range(3):
                            d.rectangle([X(x) + i, X(y) + i,
                                         X(x + CW) - 1 - i, X(y + CH) - 1 - i],
                                        outline=theme.ACCENT)
                    if key in self._excluded:
                        ov = PILImage.new("RGBA", (cw, ch), (20, 20, 25, 150))
                        surf.paste(ov, (X(x), X(y)), ov)
                        d.line([X(x), X(y), X(x + CW), X(y + CH)],
                               fill=(220, 70, 70), width=3)
                        d.line([X(x + CW), X(y), X(x), X(y + CH)],
                               fill=(220, 70, 70), width=3)
                    elif mode != "auto":
                        bc = (90, 190, 110) if mode == "on" else (210, 110, 110)
                        d.rectangle([X(x) + 3, X(y) + 3, X(x) + 36, X(y) + 18],
                                    fill=bc)
                        d.text((X(x) + 8, X(y) + 5),
                               "ON" if mode == "on" else "OFF", fill=(15, 15, 20))
                else:
                    d.rectangle([X(x), X(y), X(x + CW), X(y + CH)],
                                fill=(55, 60, 76))
                    if showing_backs and not path:
                        d.text((X(x) + cw // 2 - 26, X(y) + ch // 2),
                               "back.png\nmissing", fill=(190, 120, 120))

            xs, ys = set(), set()
            for c_ in range(cols):
                xs.add(left + c_ * (CW + g)); xs.add(left + c_ * (CW + g) + CW)
            for c_ in range(rows):
                ys.add(top + c_ * (CH + g)); ys.add(top + c_ * (CH + g) + CH)
            if gc:
                if guide_offset > 0:
                    gap = guide_offset
                else:
                    gap = 0.9 if guide_style == "Corner" else 0.0
                for x in xs:
                    for y in ys:
                        d.line([X(x), X(min(y + gap, top + bh)),
                                X(x), X(min(y + guide_len, top + bh))],
                               fill=gc, width=1)
                        d.line([X(x), X(max(y - gap, top)),
                                X(x), X(max(y - guide_len, top))],
                               fill=gc, width=1)
                        d.line([X(min(x + gap, left + bw)), X(y),
                                X(min(x + guide_len, left + bw)), X(y)],
                               fill=gc, width=1)
                        d.line([X(max(x - gap, left)), X(y),
                                X(max(x - guide_len, left)), X(y)],
                               fill=gc, width=1)
            for x in xs:
                d.line([X(x), X(top - 5), X(x), X(top - 1)], fill=(120, 125, 135))
                d.line([X(x), X(top + bh + 1), X(x), X(top + bh + 5)],
                       fill=(120, 125, 135))
            for y in ys:
                d.line([X(left - 5), X(y), X(left - 1), X(y)], fill=(120, 125, 135))
                d.line([X(left + bw + 1), X(y), X(left + bw + 5), X(y)],
                       fill=(120, 125, 135))
            if moved:
                if brot:
                    surf = surf.rotate(brot, resample=PILImage.BICUBIC,
                                       center=(W / 2, H / 2))
                img.paste(surf, (X(bdx), X(bdy)), surf)
                d = PILDraw.Draw(img)
            if reg_on:
                # same rects the PDF draws, converted from points back to mm
                rects, _ = print_sheet._reg_geometry(
                    pw * mm_pt, ph * mm_pt, *reg_args, reg_four)
                for x0, y0, x1, y1 in rects:
                    # PDF origin is bottom-left, the preview's is top-left
                    d.rectangle([X(x0 / mm_pt), X(ph - y1 / mm_pt),
                                 X(x1 / mm_pt), X(ph - y0 / mm_pt)],
                                fill=(0, 0, 0))
            d.rectangle([0, 0, W - 1, H - 1], outline=(185, 190, 200))
            return img, slots

        # Lazy multi-sheet canvas: only sheets near the viewport are painted
        # (see _render_visible). Hit-boxes for every card are cheap, so they
        # are all computed here for drag / loupe / right-click.
        gap = self._SHEET_GAP
        total_h = sheets * H + (sheets + 1) * gap
        side = "fronts"
        if showing_backs:
            # name the correction on the caption: it is the difference between
            # "the preview looks crooked" and "my offset is crooked"
            side = "backs, mirrored"
            if boff[0] or boff[1]:
                side += f" · offset {boff[0]:+g}/{boff[1]:+g} mm"
            if brot:
                side += f" · rotated {brot:+g}°"
        self._sheet_tops = [gap + p * (H + gap) for p in range(sheets)]

        self._slots = []
        # Drop targets cover EVERY usable slot, not just the filled ones: the
        # first empty slot after the last card is where "put it at the end"
        # lives, and without it a sheet with room offers nowhere to aim.
        self._drops = []
        for p in range(sheets):
            st = self._sheet_tops[p]
            for k, (px, py) in enumerate(usable):
                slot = p * per_sheet + k
                key = page_keys[slot] if slot < len(page_keys) else None
                # the hit-box follows the drawn card, so hover and right-click
                # keep landing on an offset back page
                x = (print_sheet.mirror_x(px, left, bw, CW) + bdx
                     if showing_backs else px)
                y = ph - py - CH + bdy
                box = (X(x), st + X(y), X(x + CW), st + X(y + CH))
                if key:
                    self._slots.append((*box, key))
                if not showing_backs and slot <= len(page_keys):
                    self._drops.append((*box, key))

        self._render_sheet = lambda p: render_sheet(p)[0]
        self._sheet_geom = (W, H, gap, sheets)
        self._tall_w, self._tall_h = W, total_h

        sel = self._sheets_sel()
        canvas_w = self.canvas.winfo_width()
        self._img_xoff = max(0, (canvas_w - W) // 2)
        self.canvas.delete("all")
        self._sheet_cache = {}
        self._loupe_item = self._drag_item = None
        for p in range(sheets):
            skipped = sel is not None and p not in sel
            cap = f"Sheet {p + 1} of {sheets} - {side}"
            if skipped:
                cap += "   (not printed)"
            self.canvas.create_text(
                self._img_xoff + 4, self._sheet_tops[p] - 8, anchor="w",
                text=cap, fill="#5c6270" if skipped else "#969caa",
                font=(UI, 8), tags="cap")
        self.canvas.configure(scrollregion=(0, 0, max(W, canvas_w), total_h))
        self._render_visible()

        # A raster export has no pages: every sheet is its own file, so
        # counting "PDF pages" there would name something that never exists.
        pages = sheets * 2 if duplex else sheets
        unit = "PDF page" if self._is_pdf() else "file"
        self.preview_title.configure(
            text=f"{sheets} sheet(s) · {pages} {unit}(s)")
        self._update_nav(sheets)
        # Calibration and the shadow test render a real card through the
        # pipeline, and Export has nothing to lay out: all three need the sheet
        # to be non-empty, which it no longer always is.
        has_cards = bool(self._order)
        for _b in (self.export_btn, self.cal_btn, self.shadow_btn):
            _b.configure(state="normal" if has_cards else "disabled")
        self.side_btn.configure(state="normal" if duplex else "disabled")
        if not duplex:
            self.side_btn.set("Fronts")

        # export counts use the dropped-excluded list
        exp_sheets = max(1, -(-len(exp_fronts) // per_sheet)) if exp_fronts else 0
        if sel is not None:
            exp_sheets = sum(1 for i in range(exp_sheets) if i in sel)
        exp_pages = exp_sheets * 2 if duplex else exp_sheets
        dropped = len(fronts) - len(exp_fronts)
        drop = f", {dropped} dropped" if dropped else ""
        if not self._order:
            self.summary.configure(
                # Short on purpose: this label shares its row with the
                # status text and a long string runs under it.
                text="No cards yet - set the sheet up, or "
                     "“Add cards…”")
        elif self._started_empty:
            self.summary.configure(
                text=f"{len(exp_fronts)} card(s) added{drop} -> "
                     f"{exp_sheets} sheet(s), {exp_pages} {unit}(s)")
        else:
            self.summary.configure(
                text=f"{len(exp_fronts)} card(s) from the {self.source}{drop} "
                     f"-> {exp_sheets} sheet(s), {exp_pages} {unit}(s)")

    def destroy(self):
        for job in (self._prev_job, self._spin_job, self._scroll_job):
            if job:
                try:
                    self.after_cancel(job)
                except Exception:
                    pass
        self._prev_job = self._spin_job = self._scroll_job = None
        super().destroy()

    def _on_yscroll(self, first, last):
        """Canvas view changed (drag, wheel, programmatic): keep the scrollbar
        in sync and paint any sheet that just scrolled into view."""
        self.vbar.set(first, last)
        self._render_visible()

    def _render_visible(self):
        """Paint only the sheets whose rows intersect the viewport (+margin).
        Each rendered sheet is cached, so scrolling back is instant and a
        100-card deck never rebuilds every sheet on a slider tweak."""
        if self._sheet_geom is None or not self.winfo_exists():
            return
        W, H, gap, sheets = self._sheet_geom
        top = self.canvas.canvasy(0)
        bot = top + self.canvas.winfo_height()
        margin = H  # one sheet of look-ahead in each direction
        for p in range(sheets):
            sy = self._sheet_tops[p]
            if sy + H < top - margin or sy > bot + margin:
                continue
            if p in self._sheet_cache:
                continue
            img = self._render_sheet(p)
            photo = PILImageTk.PhotoImage(img)
            item = self.canvas.create_image(self._img_xoff, sy, anchor="nw",
                                            image=photo, tags="sheet")
            self.canvas.tag_lower(item)          # stay under loupe / ghost
            self._sheet_cache[p] = (photo, item)
        self._update_spinners(top, bot)

    def _update_spinners(self, top=None, bot=None):
        """Put an animated spinner on every visible card whose thumbnail is
        still loading, so a grey slot reads as 'loading', not an error."""
        self.canvas.delete("spin")
        self._spin_items = []
        if self._sheet_geom is None or not self._loading:
            if self._spin_job:
                self.after_cancel(self._spin_job)
                self._spin_job = None
            return
        if top is None:
            top = self.canvas.canvasy(0)
            bot = top + self.canvas.winfo_height()
        _, H, _, _ = self._sheet_geom
        frame = SPINNER_FRAMES[self._spin_frame]
        for x0, y0, x1, y1, key in self._slots:
            if key in self._thumbs:          # already loaded -> real image
                continue
            if y1 < top - H or y0 > bot + H:
                continue
            it = self.canvas.create_text(
                self._img_xoff + (x0 + x1) // 2, (y0 + y1) // 2,
                text=frame, fill="#c9cfdb", font=(UI, 20), tags="spin")
            self._spin_items.append(it)
        if self._spin_items and not self._spin_job:
            self._spin_job = self.after(120, self._animate_spinners)

    def _animate_spinners(self):
        self._spin_job = None
        if not self._spin_items or not self.winfo_exists():
            return
        self._spin_frame = (self._spin_frame + 1) % len(SPINNER_FRAMES)
        ch = SPINNER_FRAMES[self._spin_frame]
        for it in self._spin_items:
            try:
                self.canvas.itemconfigure(it, text=ch)
            except Exception:
                pass
        self._spin_job = self.after(120, self._animate_spinners)

    def _recenter_preview(self, _event=None):
        """Keep the sheets horizontally centred when the canvas resizes."""
        if self._sheet_geom is None:
            return
        W, H, gap, sheets = self._sheet_geom
        cw = self.canvas.winfo_width()
        xoff = max(0, (cw - W) // 2)
        if xoff != self._img_xoff:
            self.canvas.move("sheet", xoff - self._img_xoff, 0)
            self.canvas.move("cap", xoff - self._img_xoff, 0)
            self._img_xoff = xoff
        self.canvas.configure(scrollregion=(0, 0, max(W, cw), self._tall_h))
        self._render_visible()

    def _event_xy(self, event):
        """Cursor position in sheet coordinates (scroll- and centre-aware)."""
        return (self.canvas.canvasx(event.x) - self._img_xoff,
                self.canvas.canvasy(event.y))

    def _key_at(self, cx, cy):
        for x0, y0, x1, y1, key in self._slots:
            if key and x0 <= cx <= x1 and y0 <= cy <= y1:
                return key
        return None

    def _loupe(self, px, py):
        """Magnified crop of the card under the cursor, plus where to paste."""
        for x0, y0, x1, y1, key in self._slots:
            if not (key and x0 <= px <= x1 and y0 <= py <= y1):
                continue
            path = self._path_for(key)
            mode = self._mode_for(path)
            treated = mode == "on" or (
                mode == "auto" and self.border.get() != BORDER_MODES[0])
            src = (self._work_b if treated else {}).get(path)
            if src is None:
                pair = self._thumbs_raw.get(path)
                src = pair[0] if pair else None
            if src is None:
                return None
            # cursor position as a fraction of the card, then in source pixels
            fx = (px - x0) / max(1, x1 - x0)
            fy = (py - y0) / max(1, y1 - y0)
            sw, sh = src.size
            half = int(sw * (LOUPE_MM / 63.0) / 2)
            cx = min(max(int(fx * sw), half), sw - half)
            cy = min(max(int(fy * sh), half), sh - half)
            crop = src.crop((cx - half, cy - half, cx + half, cy + half))
            lens = crop.resize((LOUPE_PX, LOUPE_PX), PILImage.NEAREST)
            d = PILDraw.Draw(lens)
            d.rectangle([0, 0, LOUPE_PX - 1, LOUPE_PX - 1],
                        outline=(212, 160, 23), width=2)
            d.line([LOUPE_PX // 2 - 6, LOUPE_PX // 2, LOUPE_PX // 2 + 6,
                    LOUPE_PX // 2], fill=(212, 160, 23))
            d.line([LOUPE_PX // 2, LOUPE_PX // 2 - 6, LOUPE_PX // 2,
                    LOUPE_PX // 2 + 6], fill=(212, 160, 23))
            # place it clear of the cursor, kept inside the stacked sheets
            W, H = self._tall_w, self._tall_h
            lx = px + 18 if px < W // 2 else px - LOUPE_PX - 18
            ly = py + 18
            lx = min(max(lx, 0), W - LOUPE_PX)
            ly = min(max(ly, 0), H - LOUPE_PX)
            return lens, (lx, ly)
        return None

    def _preview_motion(self, event):
        if self._drag:                       # dragging a card, no magnifier
            return
        cx, cy = self._event_xy(event)
        lens = self._loupe(cx, cy)
        self.canvas.delete("loupe")
        self._loupe_item = None
        if lens is None:
            self._loupephoto = None
            return
        img, (lx, ly) = lens
        self._loupephoto = PILImageTk.PhotoImage(img)
        self._loupe_item = self.canvas.create_image(
            lx + self._img_xoff, ly, anchor="nw", image=self._loupephoto,
            tags="loupe")

    def _preview_leave(self, _event=None):
        self.canvas.delete("loupe")
        self._loupe_item = None
        self._loupephoto = None

    def _back_label(self):
        if self._custom_back:
            return Path(self._custom_back).name[:16]
        # Say when it is picking per game, so a mixed sheet does not look like
        # it is about to print one back over everything.
        games = {self.card_sources.get(str(c.path)) for c in self._order}
        per_game = {g for g in games if find_back_image(g) is not None
                    and g in GAME_BACKS}
        if len(per_game) > 1:
            return f"per game ({len(per_game)})"
        return "back.png (default)" if find_back_image() else "none set"

    def _choose_back_file(self):
        f = filedialog.askopenfilename(
            parent=self, title="Choose a card back image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")])
        if f:
            self._custom_back = f
            self._after_back_change()

    def _choose_back_mpc(self):
        CardSearchDialog(self, on_pick=self._back_from_mpc)

    def _back_from_mpc(self, card):
        # download the chosen MPC image now so it can be used as the back
        try:
            dest = scryfall.TEMP_FOLDER / "_chosen_back.png"
            mpcfill.download(card, dest)
            self._custom_back = str(dest)
            self._after_back_change()
        except Exception as e:
            messagebox.showerror("Card back", str(e), parent=self)

    def _after_back_change(self):
        self.back_lbl.configure(text=self._back_label())
        if self.backs.get() == BACKS_MODES[0]:      # turn duplex on for them
            self.backs.set(BACKS_MODES[1])
        threading.Thread(target=self._load_thumbs, daemon=True).start()
        self._draw_preview()

    def _update_nav(self, sheets):
        self._page = max(0, min(self._page, sheets - 1))
        self.prev_page_btn.configure(
            state="normal" if self._page > 0 else "disabled")
        self.next_page_btn.configure(
            state="normal" if self._page < sheets - 1 else "disabled")

    def _flip_page(self, delta):
        """Scroll the canvas so the previous/next sheet lands at the top."""
        if not self._sheet_tops or not self._tall_h:
            return
        self._page = max(0, min(self._page + delta, len(self._sheet_tops) - 1))
        y = self._sheet_tops[self._page] - self._SHEET_GAP
        self.canvas.yview_moveto(max(0, y) / max(1, self._tall_h))
        self._update_nav(len(self._sheet_tops))

    # ---------------------------------------------------- drag to reorder
    _DRAG_THRESH = 6
    _DROPBAR_W = 3          # px; the insertion line drawn between slots

    def _drop_at(self, cx, cy):
        """Where a drop here would insert. Returns (index, x, y0, y1) or None.

        The slot is split down the middle: the left half means "before this
        card", the right half "after it". That is what makes the indicator
        honest, because the line is drawn on the edge the card will land
        against rather than always on the leading edge.
        """
        for x0, y0, x1, y1, key in self._drops:
            if not (x0 <= cx <= x1 and y0 <= cy <= y1):
                continue
            if key is None:                       # empty slot: append
                return len(self._order), x0, y0, y1
            idx = next((i for i, c in enumerate(self._order)
                        if c.uid == key), None)
            if idx is None:
                return None
            if cx < (x0 + x1) / 2:
                return idx, x0, y0, y1
            return idx + 1, x1, y0, y1
        return None

    def _show_dropbar(self, drop, src_key):
        """Draw the insertion line, or clear it when the drop changes nothing."""
        self.canvas.delete("dropbar")
        self._dropbar = None
        if not drop:
            return
        idx, x, y0, y1 = drop
        # A drop either side of the card being dragged puts it back where it
        # started. Showing a line there would promise a move that will not
        # happen, so nothing is drawn and the gesture reads as cancelled.
        src = next((i for i, c in enumerate(self._order)
                    if c.uid == src_key), None)
        if src is not None and idx in (src, src + 1):
            return
        x += self._img_xoff
        self._dropbar = self.canvas.create_rectangle(
            x - self._DROPBAR_W // 2, y0, x + self._DROPBAR_W // 2, y1,
            fill=theme.ACCENT, outline="", tags="dropbar")

    def _on_press(self, event):
        self._drag = None
        cx, cy = self._event_xy(event)
        key = self._key_at(cx, cy)
        if key:
            self._drag = {"key": key, "x": event.x, "y": event.y, "moved": False}

    def _on_drag(self, event):
        d = self._drag
        if not d:
            return
        if not d["moved"]:
            if abs(event.x - d["x"]) + abs(event.y - d["y"]) < self._DRAG_THRESH:
                return
            if self._showing_backs:      # reordering is a fronts-view action
                self._drag = None
                return
            d["moved"] = True
            self.canvas.delete("loupe")
            self._start_drag_ghost(d["key"])
        self._drag_pos = (event.x, event.y)
        self._drag_refresh()
        self._autoscroll()

    # Edge auto-scroll. Every sheet is stacked in one canvas, so a card can be
    # dragged to any of them, but only if the view follows. This used to scroll
    # one notch per motion event, which meant holding still at the edge did
    # nothing and crossing a single sheet took about ten deliberate wiggles
    # inside a 24 px band. A timer does it instead, so resting at the edge is
    # the gesture.
    _EDGE_BAND = 40         # px from the top/bottom edge that starts scrolling
    _EDGE_TICK = 30         # ms between scroll steps
    _EDGE_MIN, _EDGE_MAX = 5, 24    # px per step, by how deep into the band

    def _autoscroll(self):
        """Start, keep or stop the edge scroll based on where the cursor is."""
        if not self._drag or not self._drag_pos:
            return self._stop_autoscroll()
        _, y = self._drag_pos
        h = self.canvas.winfo_height()
        if y < self._EDGE_BAND:
            depth = (self._EDGE_BAND - y) / self._EDGE_BAND
            self._scroll_dir = -1
        elif y > h - self._EDGE_BAND:
            depth = (y - (h - self._EDGE_BAND)) / self._EDGE_BAND
            self._scroll_dir = 1
        else:
            return self._stop_autoscroll()
        depth = min(max(depth, 0.0), 1.0)
        self._scroll_step = (self._EDGE_MIN
                             + depth * (self._EDGE_MAX - self._EDGE_MIN))
        if self._scroll_job is None:
            self._scroll_job = self.after(self._EDGE_TICK, self._autoscroll_tick)

    def _stop_autoscroll(self):
        if self._scroll_job is not None:
            try:
                self.after_cancel(self._scroll_job)
            except Exception:
                pass
            self._scroll_job = None

    def _autoscroll_tick(self):
        self._scroll_job = None
        if not self._drag or not self._drag_pos or not self._tall_h:
            return
        top = self.canvas.canvasy(0) + self._scroll_dir * self._scroll_step
        top = min(max(top, 0), max(0, self._tall_h - self.canvas.winfo_height()))
        self.canvas.yview_moveto(top / self._tall_h)
        # the sheets moved under a cursor that did not, so the ghost and the
        # insertion line have to be recomputed or they lag a scroll behind
        self._drag_refresh()
        self._autoscroll()

    def _drag_refresh(self):
        """Put the ghost under the cursor and redraw the insertion line."""
        if not self._drag or not self._drag_pos:
            return
        x, y = self._drag_pos
        if self._drag_item is not None:
            self.canvas.coords(self._drag_item,
                               self.canvas.canvasx(x) + 12,
                               self.canvas.canvasy(y) + 12)
        cx = self.canvas.canvasx(x) - self._img_xoff
        cy = self.canvas.canvasy(y)
        self._show_dropbar(self._drop_at(cx, cy), self._drag["key"])
        self.canvas.tag_raise("ghost")

    def _start_drag_ghost(self, key):
        thumb = self._thumbs.get(key)
        if thumb is None:
            return
        ghost = thumb.resize((thumb.size[0] // 2, thumb.size[1] // 2))
        self._ghostphoto = PILImageTk.PhotoImage(ghost)
        self._drag_item = self.canvas.create_image(
            0, 0, anchor="nw", image=self._ghostphoto, tags="ghost")

    # ---------------------------------------------------------- selection
    # With quantity and change-art now living on a card, doing either to
    # twenty of them was twenty trips through the menu. A plain click selects,
    # which is what a click means everywhere else; the black-border cycle it
    # used to do has moved into the right-click menu, where it can at least
    # say which of its three states the card is in.

    def _select_only(self, key):
        self._selected = {key} if key else set()
        self._draw_preview()

    def _toggle_selected(self, key):
        if not key:
            return
        self._selected.symmetric_difference_update({key})
        self._draw_preview()

    def _clear_selection(self, _event=None):
        if self._selected:
            self._selected.clear()
            self._draw_preview()
        return "break"

    def _targets(self, key):
        """Cards an action on `key` should apply to.

        Acting on the selection only when the clicked card is part of it: a
        right-click on some other card is about that card, and silently
        applying to a selection elsewhere on the sheet would be a nasty
        surprise.
        """
        if key in self._selected and len(self._selected) > 1:
            # in sheet order, so copies and undo labels read predictably
            return [c.uid for c in self._order if c.uid in self._selected]
        return [key]

    def _on_shift_release(self, event):
        """Shift+click adds or removes one card from the selection."""
        d = self._end_drag()
        if not d:
            return
        if d["moved"]:
            return self._drop_here(d, event)
        self._toggle_selected(d["key"])

    def _end_drag(self):
        """Tear down the drag visuals and hand back what was being dragged."""
        d = self._drag
        self._drag = None
        self._drag_pos = None
        self._stop_autoscroll()
        self.canvas.delete("ghost")
        self.canvas.delete("dropbar")
        self._drag_item = None
        self._dropbar = None
        return d

    def _on_ctrl_release(self, event):
        """Ctrl+click a card: one more of it. Ctrl+drag still reorders."""
        d = self._end_drag()
        if not d:
            return
        if d["moved"]:
            return self._drop_here(d, event)
        self._add_copies_to(self._targets(d["key"]), 1)

    def _on_alt_release(self, event):
        """Alt+click a card: take it off the sheet."""
        d = self._end_drag()
        if not d:
            return
        if d["moved"]:
            return self._drop_here(d, event)
        self._remove_cards(self._targets(d["key"]))

    def _drop_here(self, d, event):
        cx, cy = self._event_xy(event)
        drop = self._drop_at(cx, cy)
        if drop:
            self._reorder(d["key"], drop[0])

    def _on_release(self, event):
        d = self._end_drag()
        if not d:
            return
        if not d["moved"]:
            self._select_only(d["key"])
            return
        self._drop_here(d, event)

    def _cycle_border(self, key):
        """Step this card's black-border treatment: auto -> off -> on.

        This used to be what a plain left-click did, with no indicator of
        which state a card was in and nothing to suggest a click would do
        anything. Undo covers it either way, but a stray click quietly
        retreating a border was never a good trade for the convenience.
        """
        path = self._path_for(key)
        nxt = {"auto": "off", "off": "on", "on": "auto"}
        self._push_undo("border change")
        self._border_modes[path] = nxt[self._border_modes.get(path, "auto")]
        self._draw_preview()

    def _reorder(self, src_key, index):
        """Move a card so it lands at `index` in the print order.

        `index` is a position in the CURRENT list, the same one the insertion
        line was drawn from. Pulling the card out first shifts everything after
        it down one, so a target beyond the card's own position has to come
        back by one or the card lands a slot late.
        """
        order = list(self._order)
        src = next((i for i, c in enumerate(order) if c.uid == src_key), None)
        if src is None or index in (src, src + 1):
            return                      # dropped back where it already was
        self._push_undo("move card")
        card = order.pop(src)
        order.insert(index - 1 if index > src else index, card)
        self._order = order
        self._draw_preview()

    def _preview_rclick(self, event):
        """Right-click a card: remove it from the PDF, or delete its file."""
        cx, cy = self._event_xy(event)
        key = self._key_at(cx, cy)
        if not key:
            return
        keys = self._targets(key)
        many = len(keys) > 1
        have = self._copies_of(key)
        mode = self._mode_for(self._path_for(key))
        menu = tk.Menu(self, tearoff=0)
        menu.add_command(
            label=(f"{many and len(keys) or have} cards selected" if many
                   else f"On the sheet {have}x"), state="disabled")
        menu.add_separator()
        # The accelerators are spelled out here because the menu is the only
        # place anyone will discover them.
        menu.add_command(label="Add 1 copy" + (" each" if many else ""),
                         accelerator="" if many else "Ctrl+Click",
                         command=lambda k=keys: self._add_copies_to(k, 1))
        menu.add_command(label="Add 3 copies" + (" each" if many else ""),
                         command=lambda k=keys: self._add_copies_to(k, 3))
        if not many:
            menu.add_command(label="Add copies…",
                             command=lambda k=key: self._ask_copies(k))
        menu.add_separator()
        # Moved off the plain left-click, so it needs to say where it stands.
        menu.add_command(label=f"Black border: {mode}  (click to cycle)",
                         command=lambda k=key: self._cycle_border(k))
        menu.add_separator()
        if not many:
            menu.add_command(label="Change art…",
                             command=lambda k=key: self._change_art(k, False))
            if have > 1:
                # Both are offered because both are wanted: fixing a playset
                # you picked the wrong printing for, and giving four basics
                # four different arts. Guessing which one someone meant would
                # be wrong half the time.
                menu.add_command(label=f"Change art for all {have} copies…",
                                 command=lambda k=key: self._change_art(k, True))
            menu.add_separator()
        menu.add_command(
            label="Remove from PDF" + (f" ({len(keys)} cards)" if many else ""),
            accelerator="" if many else "Alt+Click",
            command=lambda k=keys: self._remove_cards(k))
        if not many:
            menu.add_command(label="Delete from output folder…",
                             command=lambda k=key: self._delete_card_file(k))
        if self._selected:
            menu.add_separator()
            menu.add_command(label="Clear selection", accelerator="Esc",
                             command=self._clear_selection)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    _MAX_COPIES = 99          # a sheet holds 16; past this it is a typo

    def _add_copies(self, key, n=1, record=True):
        """Add `n` more of this card, right after it. Nothing is written to
        disk: a copy is another _Card pointing at the same image.

        They go in as one undo step. Asking for four and taking four presses of
        Ctrl+Z to take it back would make undo feel broken.
        """
        idx = next((i for i, c in enumerate(self._order) if c.uid == key), None)
        if idx is None or n < 1:
            return
        n = min(n, self._MAX_COPIES)
        if record:
            self._push_undo(f"add {n} cop{'y' if n == 1 else 'ies'}")
        src = self._order[idx]
        for offset in range(n):
            dup = _Card(src.path)
            self._order.insert(idx + 1 + offset, dup)
            self._back_of[dup.uid] = self._back_of.get(src.uid)
        self._draw_preview()

    # ------------------------------------------------------------ change art
    # Seeing the wrong printing used to mean cancelling the whole dialog,
    # fixing the queue and starting the sheet again. The gallery already exists
    # and so does the upscale pipeline; what was missing was reaching them from
    # here.

    def _change_art(self, key, all_copies):
        """Pick a different printing for this card, or for every copy of it."""
        card = next((c for c in self._order if c.uid == key), None)
        if card is None:
            return
        n = self._copies_of(key) if all_copies else 1
        CardSearchDialog(
            self,
            on_pick=lambda pick: self._apply_new_art(key, all_copies, pick),
            backend=sources.SCRYFALL,
            title=f"Change art{f' ({n} copies)' if n > 1 else ''}",
            placeholder=sources.SCRYFALL.PLACEHOLDER,
            empty_msg=sources.SCRYFALL.EMPTY,
            switchable=sources.ALL,
            query=card.path.stem.split("-")[0])

    def _art_settings(self):
        """The queue's own processing settings, so a card changed here comes
        out of the same pipeline as one added the usual way. Most live in
        settings.json; the model and fit-to-card switches live on the main
        window, and are read defensively because this dialog can outlive it."""
        app = self.master
        s = load_settings()
        return {
            "model": (app.model_menu.get()
                      if hasattr(app, "model_menu") else DEFAULT_MODEL),
            "fit": (bool(app.fit_switch.get())
                    if hasattr(app, "fit_switch") else FIT_TO_CARD_DEFAULT),
            "trim": bleed_mode_code(s.get("bleed_mode")),
            "card_size": s.get("card_size", CARD_SIZE_DEFAULT),
            "lang": card_lang_code(s.get("card_lang")),
            "best_scan": bool(s.get("best_scan", BEST_SCAN_DEFAULT)),
            "ai": getattr(app, "ai_ok", False),
        }

    def _fetch_art(self, pick, cfg):
        """Download a gallery pick and upscale it. Returns [front, back?].

        The two branches mirror App._add_source_card: some catalogues hand back
        a direct image url, others a reference for scryfall.fetch to resolve,
        which is also what turns a double-faced card into two files.
        """
        src = sources.by_id(pick.get("_source", "scryfall"))
        ref = pick.get("ref") if src.ADD_KIND == "scryfall" else None
        if ref is None and src.ID == "scryfall" and pick.get("identifier"):
            # The gallery's download url points at the FRONT face only, so a
            # double-faced card picked here would arrive as half a card. The
            # pick carries the Scryfall id too, and resolving that returns
            # every face. Both the exact printing and its language survive:
            # an api url counts as naming a printing, so best_scan and the
            # language preference leave it alone.
            ref = f"{scryfall.SCRYFALL_API}/cards/{pick['identifier']}"

        if ref:
            paths, _meta = scryfall.fetch(
                ref, status_callback=self._set_status,
                lang=cfg["lang"], best_scan=cfg["best_scan"])
            targets = [str(p) for p in paths]
        else:
            base = re.sub(r'[<>:"/\\|?*]', "",
                          f"{pick['name']}  [{pick.get('source') or src.LABEL}]")
            ident = re.sub(r"[^A-Za-z0-9_-]", "",
                           str(pick.get("identifier") or ""))[:10]
            if ident:
                base = f"{base} {ident}"
            self._set_status("Downloading…")
            targets = [str(scryfall.download_to_temp(base, pick["download"]))]

        out = []
        for t in targets:
            self._set_status(f"Upscaling {Path(t).stem[:28]}…")
            out.append(Path(upscale(
                t, model_label=cfg["model"], fit_to_card=cfg["fit"],
                rename=False, ai=cfg["ai"],
                trim_bleed=cfg["trim"] if src.ID in ("mpc",) else "never",
                card_size=cfg["card_size"])))
        # remember where it came from, or the border rules treat it as Scryfall
        for p in out:
            self.card_sources[str(p)] = src.ID
        return out

    def _apply_new_art(self, key, all_copies, pick):
        threading.Thread(target=self._art_worker,
                         args=(key, all_copies, pick), daemon=True).start()

    def _art_worker(self, key, all_copies, pick):
        try:
            cfg = self._art_settings()
            paths = self._fetch_art(pick, cfg)
        except Exception as e:
            applog.log.error("Changing art failed for %r", pick.get("name"),
                             exc_info=True)
            self._ui(messagebox.showerror, "Could not change the art", str(e))
            self._set_status("")
            return
        self._ui(self._swap_art, key, all_copies, paths)

    def _swap_art(self, key, all_copies, paths):
        """Point the card at its new image. Runs on the UI thread.

        A _Card is replaced rather than edited: undo snapshots the order with a
        shallow copy, on the understanding that a card's path never changes
        under it. Mutating one here would rewrite history as well as the sheet.
        """
        target = next((c for c in self._order if c.uid == key), None)
        if target is None:
            return
        front, back = paths[0], (paths[1] if len(paths) > 1 else None)
        changing = ([c for c in self._order if c.path == target.path]
                    if all_copies else [target])
        self._push_undo("change art" if len(changing) == 1
                        else f"change art on {len(changing)} copies")
        for old in changing:
            new = _Card(front)
            self._order[self._order.index(old)] = new
            self._back_of[new.uid] = back or self._back_of.get(old.uid)
            self._back_of.pop(old.uid, None)
        self._set_status("")
        threading.Thread(target=self._load_thumbs, daemon=True).start()
        self._draw_preview()

    def _add_copies_to(self, keys, n):
        """Add n copies to each of `keys`, as one undo step."""
        if not keys:
            return
        label = (f"add {n} cop{'y' if n == 1 else 'ies'}"
                 if len(keys) == 1 else
                 f"add {n} to {len(keys)} cards")
        self._push_undo(label)
        for k in keys:
            self._add_copies(k, n, record=False)

    def _remove_cards(self, keys):
        if not keys:
            return
        self._push_undo("remove card" if len(keys) == 1
                        else f"remove {len(keys)} cards")
        for k in keys:
            self._remove_card(k, record=False)
        self._selected.difference_update(keys)

    def _copies_of(self, key):
        """How many of this card are on the sheet, counting the one clicked."""
        card = next((c for c in self._order if c.uid == key), None)
        if card is None:
            return 0
        return sum(1 for c in self._order if c.path == card.path)

    def _ask_copies(self, key):
        """Add an arbitrary number of copies."""
        have = self._copies_of(key)
        dlg = ctk.CTkInputDialog(
            title="Add copies",
            text=f"How many more copies?  (this card is on the sheet {have}x)",
            fg_color=PANEL, button_fg_color=GOLD, button_hover_color=GOLD_HOVER,
            button_text_color=GOLD_TEXT, entry_fg_color=SURFACE_INPUT,
            entry_border_color=BORDER_STRONG, entry_text_color=TEXT,
            text_color=TEXT)
        raw = dlg.get_input()
        if raw is None:
            return
        try:
            n = int(raw.strip())
        except ValueError:
            messagebox.showinfo("Add copies",
                                f"'{raw}' is not a number.", parent=self)
            return
        self._add_copies(key, n)

    def _remove_card(self, key, record=True):
        """Take the card out of the working set entirely (the sheets recompact);
        the file on disk is untouched. Add it back later with 'Add cards…'.

        record=False is for callers that have already dealt with the history:
        deleting a file removes several cards at once and cannot be undone."""
        if record:
            self._push_undo("remove card")
        self._order = [c for c in self._order if c.uid != key]
        self._excluded.discard(key)
        self._selected.discard(key)
        self._back_of.pop(key, None)
        threading.Thread(target=self._load_thumbs, daemon=True).start()
        self._draw_preview()

    def _delete_card_file(self, key):
        """Permanently delete the card's PNG (and its DFC back, if any) from the
        output folder, then drop it from the PDF. Asks first."""
        front = next((c for c in self._order if c.uid == key), None)
        if front is None:
            return
        files = [front.path]
        back = self._back_of.get(key)
        if back:
            files.append(Path(back))
        names = "\n".join(f.name for f in files)
        # Every copy of the card points at the file being deleted, so they all
        # go - leaving one behind would put a missing image on the sheet.
        copies = [c for c in self._order if c.path == front.path]
        extra = (f"\n\n{len(copies)} copies of this card are on the sheet; "
                 "all of them will be removed." if len(copies) > 1 else "")
        if not messagebox.askyesno(
                "Delete from output folder",
                f"Permanently delete from disk?\n\n{names}{extra}", parent=self):
            return
        for f in files:
            try:
                f.unlink()
            except OSError:
                pass
        # The file is gone, so no earlier state is reachable any more: undoing
        # into one would put cards on the sheet pointing at nothing.
        self._drop_history()
        for c in copies:
            self._remove_card(c.uid, record=False)

    def _add_cards(self):
        """Append more already-upscaled cards to the current PDF set. Picking a
        card that is already in the set adds another copy of it, so 'Add cards…'
        doubles as another way to duplicate."""
        files = filedialog.askopenfilenames(
            parent=self, title="Add cards to the PDF",
            initialdir=OUTPUT_FOLDER,
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")])
        if not files:
            return
        self._push_undo("add cards")
        present = {str(c.path): c for c in self._order}
        added = False
        for f in files:
            p = Path(f)
            card = _Card(p)
            self._order.append(card)
            # a second copy inherits the first one's back; a new card has none
            twin = present.get(str(p))
            self._back_of[card.uid] = self._back_of.get(twin.uid) if twin else None
            added = True
        if added:
            threading.Thread(target=self._load_thumbs, daemon=True).start()
            self._draw_preview()

    # ------------------------------------------------------------- actions
    def _export(self):
        fmt = OUTPUT_FORMATS.get(self.out_format.get())
        ext = {None: ".pdf", "PNG": ".png", "JPEG": ".jpg"}[fmt]
        label = self.out_format.get()
        target = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=ext,
            initialdir=OUTPUT_FOLDER,
            initialfile=f"print-sheet{ext}",
            filetypes=[(label, f"*{ext}")])
        if not target:
            return

        self._persist()
        self.export_btn.configure(state="disabled", text="Exporting...")

        # honours dropped cards, the chosen card back and DFC pairing.
        # build_pdf takes paths and caches its flattens by path, so a card
        # listed n times is flattened once and printed n times.
        fronts, backs = self._sheet_images(drop_excluded=True)
        images = [c.path for c in fronts]
        if not images:
            self.export_btn.configure(state="normal", text="Export")
            messagebox.showwarning("Nothing to export",
                                   "Every card is dropped.", parent=self)
            return

        args = dict(
            layout=self.layout.get(),
            page_name=self.page.get(),
            quality=self.quality.get(),
            sharpen_name=self.sharpen.get(),
            profile_id=self._profile_id(),
            shadow_name=self.shadow.get(),
            deepen_border=self.border.get() != BORDER_MODES[0],
            border_modes=self._effective_border_modes(),
            border_amount=self.border_amount.get() / 100.0,
            border_width=self.border_width.get() / 100.0,
            border_style=self._border_style(),
            edge_width=self._edge_width(),
            edge_contrast=self._edge_contrast(),
            edge_brightness=self._edge_brightness(),
            sheets_sel=self._sheets_sel(),
            card_size_mm=self._card_mm(),
            reg_marks=bool(self.reg_marks.get()),
            reg_pattern=self.reg_pattern.get(),
            reg_inset_mm=self._reg_inset(),
            reg_length_mm=self._reg_length(),
            reg_thick_mm=self._reg_thick(),
            pages_per_file=PAGES_PER_FILE.get(self.split.get(), 0),
            image_format=fmt,
            image_dpi=self._out_dpi(),
            backs=backs,
            back_offset=self._offsets(),
            back_bleed_mm=self._bleed(),
            back_rotation_deg=self._back_rot(),
            edge_bleed_mm=self._edge_bleed(),
            bleed_color=self.bleed_color.get(),
            guide_color=self.guides.get(),
            back_guides=bool(self.back_guides.get()),
            guide_len_mm=self._guide_len(),
            guide_thick=self._guide_thick(),
            guide_style=self.guide_style.get(),
            guide_offset_mm=self._guide_offset(),
            corner_radius_mm=self._corner_radius(),
            shift_down_mm=self._shift(),
            shift_right_mm=self._shift_x(),
        )

        def build():
            try:
                files = print_sheet.build_pdf(
                    images, target,
                    status_callback=self._set_status, **args)
                self.after(0, lambda: self._done(files))
            except Exception as e:
                self.after(0, lambda err=e: self._failed(err))

        threading.Thread(target=build, daemon=True).start()

    _FRONT_RE = re.compile(r"-front( \(\d+\))?$")
    _BACK_RE = re.compile(r"-back( \(\d+\))?$")

    def _pairs(self):
        """Pair DFC faces: returns (fronts, backs) where backs[i] is the
        card's own back face, or None -> use the shared back.png."""
        paths = [Path(p) for p in self.images]
        stems = {p.stem: p for p in paths}
        fronts, backs = [], []
        for p in paths:
            st = p.stem
            if self._BACK_RE.search(st) and \
                    self._BACK_RE.sub(r"-front\1", st) in stems:
                continue
            b = None
            if self._FRONT_RE.search(st):
                b = stems.get(self._FRONT_RE.sub(r"-back\1", st))
            fronts.append(p)
            backs.append(b)
        return fronts, backs

    def _done(self, files):
        total_mb = sum(Path(f).stat().st_size for f in files) / 1e6
        names = "\n".join(Path(f).name for f in files[:8])
        if len(files) > 8:
            names += f"\n... (+{len(files) - 8} more)"
        # Stays open. This dialog is a workspace - order, copies, per-card art
        # and border modes, none of it saved anywhere - and closing on a
        # successful export threw all of it away. Reprinting one sheet with a
        # single card moved meant rebuilding the arrangement from scratch.
        self.export_btn.configure(state="normal", text="Export")
        self._set_status("")
        messagebox.showinfo(
            f"{self.out_format.get()} ready",
            f"{len(self._order)} card(s) -> {len(files)} file(s), "
            f"{total_mb:.0f} MB total:\n\n{names}", parent=self)

    def _failed(self, e):
        self.export_btn.configure(state="normal", text="Export")
        messagebox.showerror("Export failed", str(e), parent=self)

    def _calibration(self):
        target = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".pdf",
            initialdir=OUTPUT_FOLDER,
            initialfile="calibration.pdf",
            filetypes=[("PDF", "*.pdf")])
        if not target:
            return
        self.cal_btn.configure(state="disabled", text="Building...")
        card = self._order[0].path
        page = self.page.get()
        shift, shift_x = self._shift(), self._shift_x()

        def build():
            try:
                print_sheet.build_calibration(
                    card, target, page, shift_down_mm=shift,
                    shift_right_mm=shift_x,
                    status_callback=self._set_status)
                self.after(0, lambda: self._cal_done(target))
            except Exception as e:
                self.after(0, lambda err=e: self._failed_cal(err))

        threading.Thread(target=build, daemon=True).start()

    def _cal_done(self, target):
        self.cal_btn.configure(state="normal", text="Calibration...")
        self._set_status("")
        messagebox.showinfo(
            "Calibration sheet ready",
            "Print it at 100% scale with printer color correction OFF.\n"
            "Compare the 9 numbered variants against a real card, then pick "
            f"that number in 'Color profile'.\n\n{target}", parent=self)

    def _failed_cal(self, e):
        self.cal_btn.configure(state="normal", text="Calibration...")
        messagebox.showerror("Calibration failed", str(e), parent=self)

    def _shadow_test(self):
        target = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".pdf",
            initialdir=OUTPUT_FOLDER,
            initialfile="shadow-test.pdf",
            filetypes=[("PDF", "*.pdf")])
        if not target:
            return
        self.shadow_btn.configure(state="disabled", text="Building...")
        card = self._order[0].path
        page = self.page.get()
        profile = self._profile_id()
        shift, shift_x = self._shift(), self._shift_x()

        def build():
            try:
                print_sheet.build_shadow_test(
                    card, target, page, profile, shift_down_mm=shift,
                    shift_right_mm=shift_x,
                    status_callback=self._set_status)
                self.after(0, lambda: self._shadow_done(target))
            except Exception as e:
                self.after(0, lambda err=e: self._shadow_failed(err))

        threading.Thread(target=build, daemon=True).start()

    def _shadow_done(self, target):
        self.shadow_btn.configure(state="normal", text="Shadow test...")
        self._set_status("")
        messagebox.showinfo(
            "Shadow test ready",
            "Print AND laminate it like a real order, then look at the "
            "darkest details (artist signature, shadow texture).\n\n"
            "Pick the lowest +N where they become visible and set it in "
            f"'Shadow lift'.\n\n{target}", parent=self)

    def _shadow_failed(self, e):
        self.shadow_btn.configure(state="normal", text="Shadow test...")
        messagebox.showerror("Shadow test failed", str(e), parent=self)

    def _duplex_test(self):
        target = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".pdf",
            initialdir=OUTPUT_FOLDER,
            initialfile="duplex-align.pdf",
            filetypes=[("PDF", "*.pdf")])
        if not target:
            return
        self.duplex_btn.configure(state="disabled", text="Building...")
        args = dict(
            page_name=self.page.get(),
            layout=self.layout.get(),
            back_offset=self._offsets(),
            back_rotation_deg=self._back_rot(),
            edge_bleed_mm=self._edge_bleed(),
            shift_down_mm=self._shift(),
            shift_right_mm=self._shift_x(),
        )

        def build():
            try:
                print_sheet.build_duplex_test(
                    target, status_callback=self._set_status, **args)
                self.after(0, lambda: self._duplex_done(target))
            except Exception as e:
                self.after(0, lambda err=e: self._duplex_failed(err))

        threading.Thread(target=build, daemon=True).start()

    def _duplex_done(self, target):
        self.duplex_btn.configure(state="normal", text="Duplex align...")
        self._set_status("")
        messagebox.showinfo(
            "Duplex alignment test ready",
            "Print it DOUBLE-SIDED at 100% scale, then hold the page to the "
            "light. Where the back grid doesn't sit on top of the front grid, "
            "adjust 'Back offset X/Y' and 'Back rotation' and print again.\n\n"
            f"{target}", parent=self)

    def _duplex_failed(self, e):
        self.duplex_btn.configure(state="normal", text="Duplex align...")
        messagebox.showerror("Duplex test failed", str(e), parent=self)


# --------------------------------------------------------------------------
# first-run setup: download engine + models, probe GPU
# --------------------------------------------------------------------------
class SetupDialog(ctk.CTkToplevel):
    def __init__(self, master):
        super().__init__(master)
        self.master_app = master
        self.title("First-run setup")
        self.geometry("520x300")
        self.transient(master)
        self.after(60, self.grab_set)
        self.configure(fg_color=BG)
        self.protocol("WM_DELETE_WINDOW", lambda: None)  # not closable mid-setup

        ctk.CTkLabel(self, text="Setting up the AI engine",
                     font=(UI, theme.TYPE["title"], "bold"), text_color=TEXT).pack(
            anchor="w", padx=24, pady=(20, 4))
        ctk.CTkLabel(
            self,
            text="This app downloads its AI engine and models from their\n"
                 "official sources on first run (~110 MB total):\n"
                 "  •  Real-ESRGAN engine + base models (BSD license)\n"
                 "  •  UltraSharp / High Fidelity models (Upscayl project)\n\n"
                 "This happens only once.",
            justify="left", text_color=MUTED,
            font=(UI, 12)).pack(anchor="w", padx=24)

        self.bar = ctk.CTkProgressBar(self, width=460, height=6,
                                      corner_radius=3, fg_color=ROW,
                                      progress_color=GOLD)
        self.bar.set(0)
        self.bar.pack(padx=24, pady=(16, 4))
        self.status = ctk.CTkLabel(self, text="Starting…", text_color=MUTED,
                                   font=(UI, 11))
        self.status.pack(anchor="w", padx=24)

        threading.Thread(target=self._run, daemon=True).start()

    def _progress(self, text, frac):
        self.after(0, lambda: (self.status.configure(text=text),
                               self.bar.set(frac)))

    def _run(self):
        try:
            bootstrap.download_all(self._progress)
            self._progress("Detecting GPU…", 0.99)
            ok, name = bootstrap.probe_gpu()
            self.master_app.ai_ok = ok
            self.after(0, lambda: self._finish(ok, name))
        except Exception as e:
            self.after(0, lambda err=e: self._fail(err))

    def _finish(self, ok, name):
        self.grab_release()
        self.destroy()
        if ok:
            messagebox.showinfo(
                "Ready",
                f"Setup complete.\nGPU detected: {name}\n\n"
                "AI upscaling is fully enabled.")
        else:
            messagebox.showwarning(
                "Ready (no GPU)",
                f"Setup complete, but no Vulkan-compatible GPU was found "
                f"({name}).\n\nThe app will work with plain high-quality "
                "resizing instead of AI upscaling.")

    def _fail(self, e):
        self.grab_release()
        self.destroy()
        messagebox.showerror(
            "Setup failed",
            f"Could not download required components:\n\n{e}\n\n"
            "Check your internet connection and restart the app to retry.")


# --------------------------------------------------------------------------
# MPC Autofill search dialog
# --------------------------------------------------------------------------
class CardSearchDialog(ctk.CTkToplevel):
    """Search a card catalogue and pick a version to add to the queue.

    `backend` is any module exposing search(query) -> [card dict] and
    fetch_thumb(url) -> bytes, where a card dict carries name / source / dpi /
    thumb / download / identifier. Both mpcfill and ygoprodeck match that."""

    COLS = 4
    THUMB = (150, 209)

    # Spacing the grid is actually built with. Named because the window width
    # is derived from them below rather than typed once and left to rot: at
    # 720 px the fourth column was clipped, cutting the card art and the set
    # line in half.
    _TILE_PAD = 6       # padx inside a tile, around the thumbnail
    _TILE_GAP = 6       # padx between tiles
    _FRAME_PAD = 16     # the scrollable frame's own margin
    # Scrollbar plus the frame's internal chrome. Measured, not guessed: the
    # columns share a weight, so a window even five pixels short does not clip
    # the edge, it quietly squeezes the last columns and crops the art inside
    # them. A few spare pixels cost nothing; being short does not.
    _SCROLLBAR = 30

    @classmethod
    def _grid_width(cls):
        """Width the tile grid needs, so the last column is never cut off."""
        tile = cls.THUMB[0] + 2 * cls._TILE_PAD
        return (cls.COLS * (tile + 2 * cls._TILE_GAP)
                + 2 * cls._FRAME_PAD + cls._SCROLLBAR)

    def __init__(self, master, on_pick, backend=mpcfill,
                 title="Search MPC Autofill",
                 placeholder="Card name (e.g. Sol Ring)",
                 empty_msg="No matches on MPC Autofill.", note=None,
                 switchable=None, query=None):
        super().__init__(master)
        self.on_pick = on_pick
        self.backend = backend
        # `switchable` is a list of source classes the user can flip between
        # without leaving the dialog; the same card, different catalogues.
        self.switchable = switchable or []
        self.empty_msg = empty_msg
        self.title(title)
        self.geometry(f"{self._grid_width()}x640")
        self.minsize(self._grid_width(), 420)
        self.transient(master)
        self.after(60, self.grab_set)
        self.configure(fg_color=BG)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._thumbs = {}          # keep CTkImage refs alive
        self._token = 0            # ignore stale search threads

        ctk.CTkLabel(self, text=title,
                     font=(UI, theme.TYPE["title"], "bold"), text_color=TEXT).grid(
            row=0, column=0, sticky="w", padx=20, pady=(16, 2))
        if note:
            ctk.CTkLabel(self, text=note, text_color=MUTED,
                         font=(UI, 11)).grid(
                row=0, column=0, sticky="e", padx=20, pady=(20, 2))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=16, pady=6)
        bar.grid_columnconfigure(0, weight=1)
        self.entry = ctk.CTkEntry(bar, height=theme.H_INPUT, fg_color=SURFACE_INPUT,
                                  border_color=BORDER_STRONG,
                                  corner_radius=theme.RADIUS_SM,
                                  font=(UI, theme.TYPE["body"]),
                                  text_color=TEXT,
                                  placeholder_text=placeholder)
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.entry.bind("<Return>", lambda e: self._search())
        self.search_btn = ctk.CTkButton(bar, text="Search", width=96,
                                        height=theme.H_INPUT,
                                        corner_radius=theme.RADIUS_SM,
                                        fg_color=GOLD, hover_color=GOLD_HOVER,
                                        text_color=GOLD_TEXT,
                                        font=(UI, theme.TYPE["body"], "bold"),
                                        command=self._search)
        self.search_btn.grid(row=0, column=1)

        if self.switchable:
            srcbar = ctk.CTkFrame(self, fg_color="transparent")
            srcbar.grid(row=2, column=0, sticky="w", padx=16, pady=(0, 2))
            ctk.CTkLabel(srcbar, text="Source", font=(UI, theme.TYPE["small"]),
                         text_color=TEXT_DIM).pack(side="left", padx=(0, 8))
            self.source_btn = ctk.CTkSegmentedButton(
                srcbar, values=[s.LABEL for s in self.switchable],
                font=(UI, theme.TYPE["small"]),
                fg_color=BG, unselected_color=BG,
                unselected_hover_color=GRAY_HOVER,
                selected_color=GOLD, selected_hover_color=GOLD_HOVER,
                text_color="#d7dbe4", command=self._switch_source)
            self.source_btn.set(backend.LABEL)
            self.source_btn.pack(side="left")
            self.grid_rowconfigure(2, weight=0)
            self.grid_rowconfigure(3, weight=1)

        grid_row = 3 if self.switchable else 2
        self.grid_frame = ctk.CTkScrollableFrame(self, fg_color=PANEL,
                                                 corner_radius=theme.RADIUS_LG)
        self.grid_frame.grid(row=grid_row, column=0, sticky="nsew",
                             padx=16, pady=8)
        for c in range(self.COLS):
            self.grid_frame.grid_columnconfigure(c, weight=1)

        self.status = ctk.CTkLabel(self, text="Type a card name and hit Search.",
                                   text_color=MUTED, font=(UI, 12))
        self.status.grid(row=grid_row + 1, column=0, sticky="w",
                         padx=20, pady=(0, 12))

        # Opened from the main search box: run the query straight away
        # instead of making the user retype what they just typed.
        if query:
            self.entry.insert(0, query)
            self.after(120, self._search)

    def _switch_source(self, label):
        """Same query, different catalogue - the point of the switcher."""
        for s in self.switchable:
            if s.LABEL == label:
                self.backend = s
                break
        self.empty_msg = getattr(self.backend, "EMPTY", self.empty_msg)
        if self.entry.get().strip():
            self._search()

    def _search(self):
        query = self.entry.get().strip()
        if not query:
            return
        self._token += 1
        token = self._token
        for w in self.grid_frame.winfo_children():
            w.destroy()
        self._thumbs.clear()
        self.status.configure(text=f"Searching “{query}”…", text_color=MUTED)
        self.search_btn.configure(state="disabled")

        def work():
            try:
                cards = self.backend.search(query)
                self.after(0, lambda: self._show(cards, token))
            except Exception as e:
                self.after(0, lambda err=e: self._failed(err))

        threading.Thread(target=work, daemon=True).start()

    def _failed(self, e):
        applog.log.error("Card search failed on %s",
                         getattr(self.backend, "LABEL", "?"), exc_info=e)
        self.search_btn.configure(state="normal")
        self.status.configure(text=f"Search failed: {e}", text_color="#fca5a5")

    def _show(self, cards, token):
        if token != self._token:
            return
        self.search_btn.configure(state="normal")
        if not cards:
            self.status.configure(text=self.empty_msg,
                                  text_color="#fca5a5")
            return
        msg = f"{len(cards)} version(s). Click one to add it to the queue."
        note = getattr(self.backend, "NOTE", None)
        self.status.configure(text=f"{msg}  {note}" if note else msg,
                              text_color=MUTED)
        for i, card in enumerate(cards):
            self._card_tile(card, i // self.COLS, i % self.COLS, token)

    def _card_tile(self, card, r, c, token):
        tile = ctk.CTkFrame(self.grid_frame, fg_color=ROW,
                            corner_radius=theme.RADIUS_MD,
                            border_width=1, border_color=BORDER)
        tile.grid(row=r, column=c, padx=6, pady=6, sticky="n")
        ph = ctk.CTkLabel(tile, text="…", width=self.THUMB[0],
                          height=self.THUMB[1], text_color=MUTED)
        ph.pack(padx=6, pady=(6, 2))
        name = card["name"]
        short = name if len(name) <= 26 else name[:25] + "…"
        ctk.CTkLabel(tile, text=short, font=(UI, 11),
                     wraplength=self.THUMB[0]).pack(padx=6)
        sub = card["source"] or ""
        if card.get("dpi"):                  # YGOPRODeck doesn't report DPI
            sub = f"{sub} · {card['dpi']}dpi" if sub else f"{card['dpi']}dpi"
        # Wrapped like the name above it. Without this the set-and-artist line
        # sets the tile's width, so "SLD #2560 · Brandon L. Hunt" made its own
        # column wide and Tk squeezed the rest of the row, cropping their art.
        ctk.CTkLabel(tile, text=sub, font=(UI, 10), text_color=MUTED,
                     wraplength=self.THUMB[0], justify="center").pack(padx=6)
        add = ctk.CTkButton(tile, text="Add", width=72, height=28,
                            corner_radius=theme.RADIUS_SM,
                            fg_color=GOLD, hover_color=GOLD_HOVER,
                            text_color=GOLD_TEXT,
                            font=(UI, theme.TYPE["caption"], "bold"),
                            command=lambda ca=card: self._pick(ca))
        add.pack(padx=6, pady=(2, 8))

        def load():
            data = self.backend.fetch_thumb(card["thumb"])
            if not data or token != self._token:
                return
            try:
                im = PILImage.open(io.BytesIO(data)).convert("RGB").resize(
                    self.THUMB)
                cimg = ctk.CTkImage(light_image=im, dark_image=im,
                                    size=self.THUMB)
                self._thumbs[id(tile)] = cimg
                self.after(0, lambda: ph.winfo_exists()
                           and ph.configure(image=cimg, text=""))
            except (OSError, ValueError, RuntimeError):
                pass

        threading.Thread(target=load, daemon=True).start()

    def _pick(self, card):
        # Tell the handler which catalogue this came from - with the source
        # switcher the dialog is no longer tied to one backend.
        card = {**card, "_source": getattr(self.backend, "ID", "mpc")}
        self.on_pick(card)
        self.status.configure(text=f"Added: {card['name']}", text_color=GOLD)


# --------------------------------------------------------------------------
# Help: FAQ + About
# --------------------------------------------------------------------------

# Written from the questions people actually asked after the public release,
# not from what seemed likely to be asked. Most entries here cost someone a
# confused hour or a wasted sheet of cardstock.
FAQ = [
    ("My antivirus flags Cardwright as a trojan. Is it infected?",
     "No, and here is how to check rather than take my word for it.\n\n"
     "Windows Defender reports it as Trojan:Win32/Wacatac.C!ml. The \"!ml\" "
     "suffix means a machine-learning guess about the file's shape and "
     "behaviour, not a match against a known virus. Wacatac is Defender's "
     "catch-all for packed executables, and Cardwright is a packed "
     "executable that legitimately does three things malware also does:\n\n"
     "  - it is one self-extracting file (PyInstaller), the same packaging "
     "malware uses to hide in\n"
     "  - it downloads and then runs another executable, the Real-ESRGAN AI "
     "engine, on first run\n"
     "  - it replaces its own .exe when you accept an update\n\n"
     "Every one of those is visible in the source, which is public at "
     "github.com/Boffo90/cardwright.\n\n"
     "To verify what you downloaded: every release lists the SHA-256 of both "
     "files. Run\n"
     "    certutil -hashfile Cardwright.exe SHA256\n"
     "and compare it with the release page. If they match, you have exactly "
     "the file that was published.\n\n"
     "The real fix is a code-signing certificate, which is being worked on. "
     "Until then, reporting the file to Microsoft as a false positive is what "
     "clears it, and that is done for each release."),

    ("How do I set the card back, and can I mix games on one sheet?",
     "Cardwright does not ship card backs. A Magic back belongs to Wizards and "
     "a Pokemon one to Nintendo, and putting their artwork inside a download "
     "is not the same as a website showing it. So you supply the image once "
     "and it is used from then on.\n\n"
     "Drop a file named back.png (or .jpg) in the Cardwright folder and every "
     "single-faced card uses it.\n\n"
     "Mixing games on one sheet? Name them per game instead and each card "
     "takes the right one automatically:\n\n"
     "    back-mtg.png       Magic, from Scryfall, Gatherer or MPC\n"
     "    back-pokemon.png   Pokemon\n"
     "    back-yugioh.png    Yu-Gi-Oh\n\n"
     "Anything without a matching file falls back to back.png, so you can add "
     "just the ones you need. A card that has its own second face, like a "
     "transforming card, always uses that instead.\n\n"
     "To override everything for one print run, use \"Choose…\" beside Card "
     "back in the export dialog."),

    ("My printer says \"insufficient memory\" or spits out an error page.",
     "A print sheet is a real 1200 DPI page - lossless, that is around 217 MB - "
     "and a home printer has to rasterise the whole thing in its own RAM. Most "
     "do not have it. The Brother 3240 CDW, where this was first reported, "
     "ships with 128 MB.\n\n"
     "Make the PC do the rasterising instead: in Adobe Reader, "
     "Print > Advanced > tick \"Print as Image\". The printer then receives "
     "finished pixels rather than a document it has to render.\n\n"
     "That dialog has its own resolution dropdown, and it often defaults to "
     "300 dpi. Set it to the highest your printer offers - 600 or 1200 - or "
     "you will have thrown away the resolution you came here for.\n\n"
     "Still choking? Lower PDF quality to JPEG q97: near-lossless, roughly a "
     "third the size. File split (one page per PDF) helps too, since the "
     "printer then only ever holds one sheet."),

    ("Registration marks are eating my card slots. Why?",
     "The marks are corner brackets, so what blocks a slot is a mark landing "
     "on a CORNER card. Moving the marks outward frees them: on A4 3x3, "
     "lowering Mark inset from 10 mm to 6 mm takes you from 6 usable cards "
     "back to 9.\n\n"
     "When marks do cost you slots, the hint under the preview names the exact "
     "inset that keeps them all. The floor is 3.5 mm - below that most inkjets "
     "cannot print, and the mark is simply clipped off."),

    ("How do I get one exact printing instead of whatever it picks?",
     "Type the card the way a decklist writes it: the name, the set code in "
     "brackets, then the collector number.\n\n"
     "    Sol Ring (SLD) 2560\n\n"
     "That fetches exactly that printing. A bare name does not choose one, so "
     "the app picks for you, which is usually not the art you had in mind.\n\n"
     "The line is forgiving. A quantity in front works (\"3x Sol Ring (SLD) "
     "2560\"), the set code is case-insensitive, and a trailing marker like "
     "[matte] or *F* is ignored. It is the same format Moxfield, Archidekt and "
     "most deckbuilders export, so a whole decklist pastes straight in, one "
     "card per line.\n\n"
     "A link pins the printing just as firmly: paste a scryfall.com or "
     "gatherer.wizards.com card URL. If the link names a language, that is "
     "respected too.\n\n"
     "If you would rather choose by eye, the search button opens a gallery of "
     "every printing with thumbnails, and \"Change art\" on a card in the "
     "export preview opens that same gallery."),

    ("Can I print a card size that is not in the list?",
     "Yes. Pick \"Custom size...\" in the Card size dropdown and enter the "
     "printed width and height in millimetres, 20-200 mm a side. It is "
     "remembered and appears in the list from then on.\n\n"
     "The size drives the upscale target as well as the sheet, so set it "
     "before running the cards, not after. If the grid you picked will not "
     "fit on the page at that size, the export says so - use a bigger paper "
     "or a smaller grid."),

    ("My print shop is cheapest on 4x6 photo prints, and will not take a PDF.",
     "Set Page size to \"4x6 photo\" and Card grid to \"2x1 landscape\": that "
     "is two cards per print, which in some countries costs a fraction of "
     "nine cards on A4 or Letter.\n\n"
     "Then set Output format on the Image tab to PNG or JPEG - photo labs "
     "usually accept nothing else. Each sheet comes out as its own numbered "
     "file, so File split does not apply.\n\n"
     "Image DPI decides the size: 300 gives 1800x1200 pixels, which is what "
     "most labs print at natively, and 600 and 1200 are there for the ones "
     "that take more. Ask yours what it accepts - sending more pixels than it "
     "wants is harmless, sending fewer is not."),

    ("My printer's rear feed leaves roller marks, or loses part of the page.",
     "Move the whole layout away from the edge it cannot use. *Shift down* and "
     "*Shift right* on the Layout tab both take negative numbers, so the block "
     "goes up, down, left or right - shift down -8 moves it 8 mm toward the "
     "top of the page.\n\n"
     "Guides and margin ticks move with the cards, so what you cut to is still "
     "correct. The preview shows the result, and the line under the two "
     "entries says how far you can actually go on this page and grid.\n\n"
     "If the room is smaller than what your printer wastes, no shift will fix "
     "it: the cards simply do not fit clear of the dead zone. A rear top "
     "loader that eats 0.8 in leaves Letter 3x3 no way out - drop to 4x2 "
     "landscape, or move to Legal, A3 or Tabloid.\n\n"
     "With registration marks on, the shift is ignored on purpose: the cutter "
     "finds the marks wherever the paper actually fed and cuts relative to "
     "them, so it already compensates."),

    ("Which paper and layout should I use with a cutting machine?",
     "A3 or Tabloid, if your printer takes them. At the default mark geometry "
     "every layout keeps every slot on those, including 4x4 - sixteen cards a "
     "sheet with nothing lost to the marks. The bigger margin is what does it: "
     "the marks stop competing with the card grid.\n\n"
     "On Legal, 3x3 keeps all nine. On A4, use 4x2 landscape (8) or the 7-card "
     "Silhouette layout (7) - A4 3x3 drops to 6. On Letter no layout keeps "
     "every slot at the defaults; lower the mark inset a little and the hint "
     "under the preview will tell you the value that works.\n\n"
     "The 7-card layout exists for exactly this: it clears both left corners, "
     "where a Cameo's key marks sit."),

    ("My marks do not line up with a Silhouette Studio template.",
     "Mark geometry follows Studio's published figures: 0.394 in inset, "
     "0.350 in (8.89 mm) length, 0.039 in thickness. If your template was "
     "built around different numbers, set them to match in Export > Cutting.\n\n"
     "A template made in Studio also assumes a particular grid, so matching "
     "the marks but not the layout will still misalign."),

    ("Why is a Pokemon card less sharp than a Magic card?",
     "Every Pokemon catalogue tops out at 600x825, against Scryfall's 745x1040 "
     "for Magic. That is a limit of the source data, not of this app - no "
     "Pokemon API has anything better.\n\n"
     "Small sources are resized to the right size BEFORE the AI pass, so it "
     "reconstructs at the target instead of stretching afterwards. That "
     "recovers a good part of the difference."),

    ("I chose a language but some cards came back in English.",
     "Not every card was printed in every language. Promos, Secret Lairs and "
     "older sets are frequently English-only.\n\n"
     "Those cards are added in English and listed separately after the import, "
     "so you know which ones rather than wondering why the deck came out "
     "mixed. It is not a failure."),

    ("I imported with Gatherer and some cards came from Scryfall.",
     "Gatherer has no entry for Secret Lairs, promos, or any foil printing. "
     "Scryfall numbers foils with a star - 198 is the normal card, 198* is the "
     "foil - and gives the starred one no Gatherer id, because Gatherer never "
     "catalogued foils separately.\\n\\n"
     "Rather than drop those, the import falls back to the Scryfall image and "
     "lists which ones. You still get the whole deck; only those cards come "
     "from the other source."),

    ("What does Best scan actually do?",
     "When you type a bare card name, it compares that card's printings and "
     "picks the sharpest image, keeping the same artwork.\n\n"
     "It never swaps the art for a different one, and it never overrides a "
     "link or a decklist line - those already name a printing you chose."),

    ("Which black border mode should I use?",
     "Contrast edges (the default) pushes the dark pixels inside a fixed band "
     "at the card's edge. It detects nothing, so there is no judgement to get "
     "wrong on artwork that reaches the cut edge.\n\n"
     "Auto-detect measures how deep the frame runs and snaps it to black. It "
     "is crisper on a normal black-bordered scan but can misjudge full-art "
     "cards. Both take a per-card override: left-click a card in the preview."),

    ("A card came out cropped, or kept a bleed edge it should not have.",
     "Bleed detection works by aspect ratio, which is a good guess but still a "
     "guess. Set MPC bleed to Assume none for an image wrongly flagged, or "
     "Assume bleed for one carrying bleed the proportions hide.\n\n"
     "It only ever runs on MPC picks and local files - cards from Scryfall, "
     "Gatherer, Pokemon and Yu-Gi-Oh are never touched."),

    ("The two sides do not line up when I print double-sided.",
     "Use Export > Tests > duplex alignment sheet. Print it double-sided, hold "
     "it up to the light, and dial in Back offset and Back rotation from what "
     "you actually see. Guessing those numbers rarely works.\n\n"
     "Back bleed helps the cut survive whatever drift is left."),

    ("Windows says unknown publisher. Is that a problem?",
     "The app is not code-signed yet - a signing certificate is a recurring "
     "cost this project has not taken on. SmartScreen flags any unsigned "
     "executable regardless of what it does.\n\n"
     "The source is published so anyone can read exactly what it does, and the "
     "releases on GitHub are the only official builds."),

    ("What does it download on first run?",
     "The Real-ESRGAN engine and the AI models, once, from their official "
     "sources - about 110 MB. After that the upscaling runs entirely on your "
     "machine and needs no connection.\n\n"
     "Card images are fetched only when you ask for a specific card."),

    ("Something went wrong and the message was not enough.",
     "The Log button in the header opens a log file with the full details of "
     "any failure, including what was being fetched when it broke.\n\n"
     "Attach it to a bug report on GitHub - it is the difference between a "
     "guess and a fix."),

    ("Is printing proxies allowed?",
     "This is an unofficial fan project. It ships no publisher artwork: card "
     "images are fetched from public APIs when you ask for them.\n\n"
     "Proxies are for personal playtesting. Selling them, or passing them off "
     "as real cards, is not what this tool is for, and what you do with the "
     "output is your responsibility."),
]


class HelpDialog(ctk.CTkToplevel):
    """FAQ and About, in one window reachable from the header."""

    def __init__(self, master):
        super().__init__(master)
        self.title(f"{APP_NAME} - Help")
        self.geometry("720x640")
        self.transient(master)
        self.after(60, self.grab_set)
        self.configure(fg_color=BG)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Help",
                     font=(UI, theme.TYPE["title"], "bold"),
                     text_color=TEXT).grid(row=0, column=0, sticky="w",
                                           padx=20, pady=(16, 4))

        tabs = ctk.CTkTabview(self, fg_color=PANEL,
                              segmented_button_selected_color=GOLD,
                              segmented_button_selected_hover_color=GOLD_HOVER,
                              text_color=TEXT)
        tabs.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
        tabs.add("FAQ")
        tabs.add("About")

        self._build_faq(tabs.tab("FAQ"))
        self._build_about(tabs.tab("About"))

        ctk.CTkButton(self, text="Close", width=96, height=theme.H_BUTTON,
                      corner_radius=theme.RADIUS_SM, fg_color=CONTROL_ALT,
                      hover_color=GRAY_HOVER, text_color=TEXT,
                      command=self.destroy).grid(row=2, column=0, sticky="e",
                                                 padx=20, pady=(0, 14))

    def _build_faq(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)
        box = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        box.grid(row=0, column=0, sticky="nsew")
        box.grid_columnconfigure(0, weight=1)

        for i, (q, a) in enumerate(FAQ):
            ctk.CTkLabel(box, text=q, font=(UI, theme.TYPE["body"], "bold"),
                         text_color=TEXT, justify="left", anchor="w",
                         wraplength=590).grid(row=i * 2, column=0, sticky="ew",
                                              padx=6, pady=(14 if i else 2, 2))
            ctk.CTkLabel(box, text=a, font=(UI, theme.TYPE["small"]),
                         text_color=TEXT_DIM, justify="left", anchor="w",
                         wraplength=590).grid(row=i * 2 + 1, column=0,
                                              sticky="ew", padx=6, pady=(0, 2))

    def _build_about(self, parent):
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(0, weight=1)
        box = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        box.grid(row=0, column=0, sticky="nsew")
        box.grid_columnconfigure(0, weight=1)

        def para(text, bold=False, muted=False, pad=(8, 2)):
            ctk.CTkLabel(
                box, text=text,
                font=(UI, theme.TYPE["body"], "bold") if bold
                else (UI, theme.TYPE["small"]),
                text_color=TEXT if bold else (MUTED if muted else TEXT_DIM),
                justify="left", anchor="w", wraplength=590).pack(
                anchor="w", padx=6, pady=pad)

        def link(text, url):
            ctk.CTkButton(box, text=text, height=26, anchor="w", width=260,
                          fg_color="transparent", hover_color=GRAY_HOVER,
                          text_color=GOLD, font=(UI, theme.TYPE["small"]),
                          command=lambda u=url: webbrowser.open(u)).pack(
                anchor="w", padx=2, pady=1)

        para(f"{APP_NAME} {APP_VERSION}", bold=True, pad=(10, 0))
        para("Turns card images into true 1200 DPI print-ready proxies using "
             "AI upscaling on your own GPU, then builds print-ready sheets. "
             "Free, and offline once it has downloaded its engine.")

        para("Links", bold=True)
        link("Releases and source", f"https://github.com/{GITHUB_REPO}")
        link("Report a bug", f"https://github.com/{GITHUB_REPO}/issues")
        # Separate from the bug link on purpose. A user with a five-line gripe
        # about their printer went to Reddit rather than file an issue, and
        # that report only arrived because somebody happened to be reading.
        # Issues is a high bar for "is this supposed to work like this?".
        link("Ask or suggest something",
             f"https://github.com/{GITHUB_REPO}/discussions")
        link("Donate", DONATE_URL)

        para("Licence", bold=True)
        para("Free to use, but not open source. The code is published so "
             "anyone can read and audit what the app does. You may study it "
             "and build it for your own use; you may not redistribute it, "
             "publish a rebranded version, or sell it.")

        para("Card data and images", bold=True)
        para("Magic card data and images courtesy of Scryfall. Yu-Gi-Oh from "
             "YGOPRODeck and Pokemon from TCGdex - images are downloaded to "
             "your machine rather than hotlinked, per their terms. MPC "
             "Autofill art comes from the community database.\n\n"
             "This is an unofficial fan project, not affiliated with or "
             "endorsed by Wizards of the Coast or any other publisher, and it "
             "ships no publisher artwork.")

        para("Built on", bold=True)
        para("Real-ESRGAN (BSD-3) for the upscaling engine, with the "
             "UltraSharp and High Fidelity community models fetched from the "
             "Upscayl project. Registration-mark geometry follows the spec "
             "used by silhouette-card-maker; the 7-card arrangement matches "
             "ProxySheet's SevenCard template; the contrast-edges border "
             "treatment is a reimplementation of the approach Proxxied uses. "
             "No code from those projects is used.")

        para("Intended for personal playtesting. What you do with the output "
             "is your responsibility.", muted=True, pad=(10, 12))


def ask_custom_card_size(master):
    """Ask for a card size in mm. Returns the new picker label, or None.

    One saved size rather than a list: the ask was "can I set my own", and a
    managed list of named sizes is a lot of interface for a need nobody has
    described yet.
    """
    current = custom_card_size() or (63.0, 88.0)

    win = ctk.CTkToplevel(master)
    win.title("Custom card size")
    win.geometry("360x210")
    win.transient(master)
    win.configure(fg_color=BG)
    win.resizable(False, False)
    win.after(60, win.grab_set)

    ctk.CTkLabel(win, text="Card size in millimetres",
                 font=(UI, theme.TYPE["body"], "bold"),
                 text_color=TEXT).pack(anchor="w", padx=20, pady=(16, 2))
    ctk.CTkLabel(win, text=f"The printed size of one card, "
                           f"{CUSTOM_SIZE_MIN_MM:g}-{CUSTOM_SIZE_MAX_MM:g} mm "
                           f"a side.",
                 font=(UI, theme.TYPE["small"]), text_color=MUTED,
                 justify="left", wraplength=310).pack(anchor="w", padx=20)

    row = ctk.CTkFrame(win, fg_color="transparent")
    row.pack(anchor="w", padx=20, pady=(12, 0))

    def field(label, value):
        ctk.CTkLabel(row, text=label, font=(UI, theme.TYPE["small"]),
                     text_color=TEXT_DIM).pack(side="left", padx=(0, 6))
        e = ctk.CTkEntry(row, width=76, height=theme.H_INPUT,
                         fg_color=SURFACE_INPUT, border_color=BORDER_STRONG,
                         corner_radius=theme.RADIUS_SM,
                         font=(UI, theme.TYPE["body"]), text_color=TEXT)
        e.insert(0, f"{value:g}")
        e.pack(side="left", padx=(0, 16))
        return e

    w_entry = field("Width", current[0])
    h_entry = field("Height", current[1])

    err = ctk.CTkLabel(win, text="", font=(UI, theme.TYPE["small"]),
                       text_color="#fca5a5", justify="left", wraplength=310)
    err.pack(anchor="w", padx=20, pady=(6, 0))

    result = {}

    def save():
        try:
            w = float(w_entry.get().replace(",", "."))
            h = float(h_entry.get().replace(",", "."))
        except ValueError:
            err.configure(text="Both values have to be numbers.")
            return
        lo, hi = CUSTOM_SIZE_MIN_MM, CUSTOM_SIZE_MAX_MM
        if not (lo <= w <= hi and lo <= h <= hi):
            err.configure(text=f"Keep each side between {lo:g} and {hi:g} mm.")
            return
        result["label"] = save_custom_card_size(w, h)
        win.destroy()

    btns = ctk.CTkFrame(win, fg_color="transparent")
    btns.pack(fill="x", padx=20, pady=(10, 14))
    ctk.CTkButton(btns, text="Cancel", width=90, height=theme.H_BUTTON,
                  corner_radius=theme.RADIUS_SM, fg_color=CONTROL_ALT,
                  hover_color=GRAY_HOVER, text_color=TEXT,
                  command=win.destroy).pack(side="right", padx=(8, 0))
    ctk.CTkButton(btns, text="Save", width=90, height=theme.H_BUTTON,
                  corner_radius=theme.RADIUS_SM, fg_color=GOLD,
                  hover_color=GOLD_HOVER, text_color=GOLD_TEXT,
                  font=(UI, theme.TYPE["body"], "bold"),
                  command=save).pack(side="right")

    w_entry.bind("<Return>", lambda _: save())
    h_entry.bind("<Return>", lambda _: save())
    master.wait_window(win)
    return result.get("label")
