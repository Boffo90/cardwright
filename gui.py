import io
import os
import re
import shutil
import threading
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import numpy as np
from PIL import Image as PILImage, ImageDraw as PILDraw, ImageTk as PILImageTk

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
    PARALLEL_JOBS,
    PDF_PAGE_SIZES,
    PDF_DEFAULT_PAGE,
    PDF_QUALITY_MODES,
    PDF_DEFAULT_QUALITY,
    PAGES_PER_FILE,
    PAGES_PER_FILE_DEFAULT,
    SHARPEN_MODES,
    SHARPEN_DEFAULT,
    SHADOW_LIFTS,
    SHADOW_DEFAULT,
    BORDER_MODES,
    BORDER_DEFAULT,
    BORDER_AMOUNT_DEFAULT,
    BORDER_WIDTH_DEFAULT,
    CALIBRATION_PROFILES,
    BACKS_MODES,
    find_back_image,
    ICON_FILE,
    load_settings,
    save_settings,
)
from upscale import upscale
import scryfall
import mpcfill
import print_sheet
import bootstrap
import update as app_update
from version import APP_NAME, APP_VERSION, DONATE_URL


ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# ---- palette: dark arena + MTG gold accent -------------------------------
BG        = "#101218"   # window
PANEL     = "#181b24"   # bars / frames
ROW       = "#1f2330"   # queue rows
GOLD      = "#d4a017"
GOLD_HOVER = "#b8860b"
GOLD_TEXT = "#171003"   # text on gold buttons
BLUE      = "#2c5f8a"   # secondary actions (import / export)
BLUE_HOVER = "#24486a"
GRAY_BTN  = "#2a2e3a"
GRAY_HOVER = "#39404f"
MUTED     = "#8a92a6"

# WUBRG accent dots for the header
MANA_COLORS = ["#f5e7bd", "#2f76b5", "#6b6570", "#d3202a", "#00733e"]

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
    "pending":    ("#6b7280", "#9ca3af"),
    "processing": ("#3b82f6", "#93c5fd"),
    "done":       ("#22c55e", "#86efac"),
    "error":      ("#ef4444", "#fca5a5"),
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
class QueueItem(ctk.CTkFrame):
    def __init__(self, master, ref, kind, on_remove, downloads=None, label=None,
                 qty=1, released_at=None, set_code=None, on_status=None):
        super().__init__(master, corner_radius=10, fg_color=ROW)
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

        self.dot = ctk.CTkLabel(self, text="●", width=18,
                                text_color=STATUS_COLORS["pending"][0],
                                font=("Segoe UI", 16))
        self.dot.grid(row=0, column=0, padx=(12, 6), pady=8)

        if label is not None:
            pass
        elif kind == "file":
            label = Path(ref).name
        else:
            label = ref
        self.name = ctk.CTkLabel(self, text=self._trim(label), anchor="w",
                                 font=("Segoe UI", 13))
        self.name.grid(row=0, column=1, sticky="ew", pady=(8, 0))

        self.info = ctk.CTkLabel(self, text="Pending", anchor="w",
                                 text_color=STATUS_COLORS["pending"][1],
                                 font=("Segoe UI", 11))
        self.info.grid(row=1, column=1, sticky="ew", pady=(0, 8))

        self.model_menu = ctk.CTkOptionMenu(
            self, values=list(ROW_MODELS.keys()), width=104, height=26,
            font=("Segoe UI", 11), fg_color=GRAY_BTN, button_color=GRAY_HOVER,
            command=self._model_changed)
        self.model_menu.set("Auto")
        self.model_menu.grid(row=0, column=2, rowspan=2, padx=(4, 2))

        self.bar = ctk.CTkProgressBar(self, height=6, width=120)
        self.bar.set(0)
        self.bar.grid(row=0, column=3, rowspan=2, padx=8)

        self.remove_btn = ctk.CTkButton(self, text="✕", width=30, height=30,
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
                     font=("Georgia", 30, "bold"),
                     text_color=GOLD).pack(side="left")
        for color in MANA_COLORS:
            ctk.CTkLabel(header, text="●", font=("Segoe UI", 16),
                         text_color=color).pack(side="left", padx=2, pady=(12, 0))
        ctk.CTkLabel(header, text="  Scryfall · Gatherer → 1200 DPI print-ready cards",
                     font=("Segoe UI", 13),
                     text_color=MUTED).pack(side="left", pady=(14, 0))
        ctk.CTkLabel(header, text=f"v{APP_VERSION}", font=("Segoe UI", 11),
                     text_color=MUTED).pack(side="right", pady=(14, 0))
        ctk.CTkButton(header, text="♥ Donate", width=84, height=28,
                      fg_color="transparent", hover_color=GRAY_HOVER,
                      border_width=1, border_color=GOLD, text_color=GOLD,
                      font=("Segoe UI", 12),
                      command=lambda: webbrowser.open(DONATE_URL)).pack(
            side="right", padx=(4, 10), pady=(10, 0))

    # ---------------------------------------------------------------- inputs
    def _build_inputs(self):
        bar = ctk.CTkFrame(self, corner_radius=12, fg_color=PANEL)
        bar.grid(row=1, column=0, sticky="ew", padx=24, pady=8)
        bar.grid_columnconfigure(0, weight=1)

        self.ref_entry = ctk.CTkEntry(
            bar, height=40, fg_color=BG, border_color=GRAY_BTN,
            placeholder_text="Card name, Scryfall or Gatherer link  (e.g. Lightning Bolt, scryfall.com/card/…, gatherer.wizards.com/…)")
        self.ref_entry.grid(row=0, column=0, sticky="ew", padx=(12, 8), pady=12)
        self.ref_entry.bind("<Return>", lambda e: self._add_scryfall())

        ctk.CTkButton(bar, text="Add card", width=100, height=40,
                      fg_color=GOLD, hover_color=GOLD_HOVER, text_color=GOLD_TEXT,
                      font=("Segoe UI", 13, "bold"),
                      command=self._add_scryfall).grid(row=0, column=1, padx=4, pady=12)
        ctk.CTkButton(bar, text="Add files…", width=100, height=40,
                      fg_color=GRAY_BTN, hover_color=GRAY_HOVER,
                      command=self._add_files).grid(row=0, column=2, padx=4, pady=12)
        ctk.CTkButton(bar, text="Import list…", width=110, height=40,
                      fg_color=BLUE, hover_color=BLUE_HOVER,
                      command=self._open_import).grid(row=0, column=3, padx=4, pady=12)
        ctk.CTkButton(bar, text="MPC search…", width=110, height=40,
                      fg_color=BLUE, hover_color=BLUE_HOVER,
                      command=self._open_mpc).grid(row=0, column=4, padx=(4, 12), pady=12)

    # ----------------------------------------------------------------- queue
    def _build_queue(self):
        wrap = ctk.CTkFrame(self, corner_radius=12, fg_color=PANEL)
        wrap.grid(row=2, column=0, sticky="nsew", padx=24, pady=8)
        wrap.grid_columnconfigure(0, weight=1)
        wrap.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(wrap, fg_color="transparent")
        top.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 0))
        ctk.CTkLabel(top, text="Queue", text_color=GOLD,
                     font=("Segoe UI", 13, "bold")).pack(side="left")

        self.status_filter = "All"
        self.filter_btn = ctk.CTkSegmentedButton(
            top, values=["All", "Pending", "Processing", "Done", "Error"],
            command=self._set_filter, height=26,
            font=("Segoe UI", 11),
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
            text_color=MUTED, font=("Segoe UI", 14))
        self.empty_hint.grid(row=0, column=0, pady=40)

    # ---------------------------------------------------------------- footer
    def _build_footer(self):
        opts = ctk.CTkFrame(self, fg_color="transparent")
        opts.grid(row=3, column=0, sticky="ew", padx=24, pady=(4, 0))
        opts.grid_columnconfigure(4, weight=1)

        ctk.CTkLabel(opts, text="Model:").grid(row=0, column=0, padx=(0, 6))
        self.model_menu = ctk.CTkOptionMenu(
            opts, values=[AUTO_MODEL] + list(MODELS.keys()), width=250)
        self.model_menu.set(DEFAULT_MODEL)
        self.model_menu.grid(row=0, column=1, padx=(0, 16))

        self.fit_switch = ctk.CTkSwitch(opts, text="Fit to MTG card (1200 DPI)")
        if FIT_TO_CARD_DEFAULT:
            self.fit_switch.select()
        self.fit_switch.grid(row=0, column=2, padx=8)

        self.trim_switch = ctk.CTkSwitch(opts, text="Trim MPC bleed")
        if MPC_TRIM_DEFAULT:
            self.trim_switch.select()
        self.trim_switch.grid(row=0, column=3, padx=8)

        self.pdf_btn = ctk.CTkButton(opts, text="Export PDF…", width=120,
                                     fg_color=BLUE, hover_color=BLUE_HOVER,
                                     command=self._export_pdf)
        self.pdf_btn.grid(row=0, column=5, padx=2)

        ctk.CTkButton(opts, text="Open output folder", width=140,
                      fg_color=GRAY_BTN, hover_color=GRAY_HOVER,
                      command=self._open_output).grid(row=0, column=6, padx=(2, 0))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=4, column=0, sticky="ew", padx=24, pady=(8, 20))
        footer.grid_columnconfigure(0, weight=1)

        self.overall = ctk.CTkProgressBar(footer, height=12, progress_color=GOLD)
        self.overall.set(0)
        self.overall.grid(row=0, column=0, sticky="ew", padx=(0, 16))

        self.clear_btn = ctk.CTkButton(footer, text="Clear", width=90, height=44,
                                       fg_color=GRAY_BTN, hover_color=GRAY_HOVER,
                                       command=self._clear)
        self.clear_btn.grid(row=0, column=1, padx=4)

        self.start_btn = ctk.CTkButton(footer, text="UPSCALE ALL", width=180, height=44,
                                       font=("Segoe UI", 15, "bold"),
                                       fg_color=GOLD, hover_color=GOLD_HOVER,
                                       text_color=GOLD_TEXT,
                                       command=self._start)
        self.start_btn.grid(row=0, column=2)

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
                  released_at=None, set_code=None):
        item = QueueItem(self.queue_frame, ref, kind, self._remove_item,
                         downloads=downloads, label=label, qty=qty,
                         released_at=released_at, set_code=set_code,
                         on_status=self._apply_filter)
        item.grid(row=len(self.items) + 1, column=0, sticky="ew", padx=6, pady=4)
        self.items.append(item)
        self._apply_filter(item)
        self._refresh_empty()

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
        self._add_item(ref, "scryfall")
        self.ref_entry.delete(0, "end")

    def _open_import(self):
        if self.running:
            return
        ImportDialog(self, on_resolved=self._add_resolved_cards)

    def _open_mpc(self):
        if self.running:
            return
        MPCDialog(self, on_pick=self._add_mpc_card)

    def _add_mpc_card(self, card):
        # MPC images are Google-Drive downloads with a bleed edge; reuse the
        # "card" path (download then upscale), the bleed trim handles the edge
        base = f"{card['name']}  [{card['source']}]"
        safe = re.sub(r'[<>:"/\\|?*]', "", base)
        self._add_item(base, "card",
                       downloads=[(safe, card["download"])], label=base)

    def _add_resolved_cards(self, cards):
        for c in cards:
            self._add_item(c["display"], "card",
                           downloads=c["downloads"], label=c["display"],
                           qty=c["qty"], released_at=c.get("released_at"),
                           set_code=c.get("set"))

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
        os.startfile(OUTPUT_FOLDER)

    # ============================================================ pdf export
    def _export_images(self):
        """Cards to lay out: queue results first (order + copies), else
        everything in the output folder."""
        images = [p for it in self.items if it.status == "done"
                  for p in it.outputs if Path(p).exists()]
        source = "queue"
        if not images:
            images = sorted(OUTPUT_FOLDER.glob("*.png"))
            source = "output folder"
        return images, source

    def _export_pdf(self):
        if self.running:
            return
        images, source = self._export_images()
        if not images:
            messagebox.showerror("Nothing to export",
                                 "No upscaled cards found. Run UPSCALE ALL first.")
            return
        ExportDialog(self, images, source)

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
        trim = bool(self.trim_switch.get())
        pending = [it for it in self.items if it.status != "done"]
        total = len(pending)
        state = {"done": 0, "errors": 0}
        lock = threading.Lock()

        def process(item):
            try:
                self._process_item(item, model, fit, trim)
            except Exception as e:
                with lock:
                    state["errors"] += 1
                self._ui(item.set_status, "error", f"Error: {e}")
            finally:
                with lock:
                    state["done"] += 1
                    progress = state["done"] / total
                self._ui(self.overall.set, progress)

        with ThreadPoolExecutor(max_workers=PARALLEL_JOBS) as pool:
            list(pool.map(process, pending))

        self.after(0, lambda: self._finish(total, state["errors"]))

    def _process_item(self, item, model, fit, trim):
        self._ui(item.set_status, "processing", "Preparing…", 0)
        item.outputs = []

        # build the list of local files to upscale (2 for DFCs)
        if item.kind == "card":
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
                    it.set_status, "processing", t))
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
                trim_bleed=trim,
                progress_callback=lambda v, it=item: self._ui(
                    it.set_status, "processing", None, v),
                status_callback=lambda s, it=item: self._ui(
                    it.set_status, "processing", s),
            ))
            item.outputs.append(out)
            # one output file per requested copy (upscale once, copy)
            for n in range(2, item.qty + 1):
                copy = out.with_name(f"{out.stem} ({n}){out.suffix}")
                shutil.copy2(out, copy)
                item.outputs.append(copy)

        done_msg = f"Done ({item.qty} copies)" if item.qty > 1 else "Done"
        self._ui(item.set_status, "done", done_msg, 1)

    def _finish(self, total, errors):
        self.running = False
        self.start_btn.configure(state="normal", text="UPSCALE ALL")
        self.clear_btn.configure(state="normal")
        ok = total - errors
        if errors:
            failed = [it for it in self.items if it.status == "error"]
            names = "\n".join(
                f"  • {it.name.cget('text')} — {it.info.cget('text')}"
                for it in failed[:12])
            if len(failed) > 12:
                names += f"\n  … (+{len(failed) - 12} more)"
            messagebox.showwarning(
                "Finished with errors",
                f"{ok} succeeded, {errors} failed:\n\n{names}\n\n"
                f"Use the 'Error' filter above the queue to see them, "
                f"then UPSCALE ALL retries only the failed ones.")
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
    PLACEHOLDER = ("Paste a decklist or an Archidekt deck URL, e.g.\n\n"
                   "1 Winota, Joiner of Forces (PRM) 80807 [matte]\n"
                   "3 Plains (MSC) 866 [matte]\n"
                   "1 Ajani, Nacatl Pariah // Ajani, Nacatl Avenger (MH3) 442\n\n"
                   "https://archidekt.com/decks/1234567/my-deck\n\n"
                   "(Moxfield: use Export → copy the list and paste it here)")

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
                     font=("Georgia", 18, "bold"), text_color=GOLD).grid(
            row=0, column=0, sticky="w", padx=20, pady=(18, 4))

        self.textbox = ctk.CTkTextbox(self, font=("Consolas", 12), wrap="none",
                                      fg_color=PANEL, border_color=GRAY_BTN,
                                      border_width=1)
        self.textbox.grid(row=1, column=0, sticky="nsew", padx=20, pady=8)
        self.textbox.insert("1.0", self.PLACEHOLDER)
        self.textbox.bind("<FocusIn>", self._clear_placeholder)
        self._has_placeholder = True

        self.status = ctk.CTkLabel(self, text="Fetches the exact printing "
                                   "(set + number) from Scryfall.",
                                   text_color="#9ca3af", font=("Segoe UI", 12))
        self.status.grid(row=2, column=0, sticky="w", padx=20, pady=2)

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=3, column=0, sticky="e", padx=20, pady=(6, 16))
        ctk.CTkButton(btns, text="Cancel", width=90, fg_color=GRAY_BTN,
                      hover_color=GRAY_HOVER, command=self.destroy).pack(
            side="left", padx=6)
        self.import_btn = ctk.CTkButton(btns, text="Resolve & add", width=140,
                                        fg_color=GOLD, hover_color=GOLD_HOVER,
                                        text_color=GOLD_TEXT,
                                        font=("Segoe UI", 13, "bold"),
                                        command=self._do_import)
        self.import_btn.pack(side="left")

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
        threading.Thread(target=self._resolve, args=(text,), daemon=True).start()

    def _resolve(self, text):
        try:
            status = lambda s: self.after(
                0, lambda: self.status.configure(text=s, text_color="#9ca3af"))

            # deck site URLs
            kind = scryfall.deck_url_kind(text)
            if kind == "moxfield":
                raise scryfall.ScryfallError(
                    "Moxfield blocks external tools. In Moxfield use "
                    "Export → copy the decklist text and paste it here "
                    "instead — the format is supported directly.")
            if kind == "archidekt":
                text = scryfall.fetch_archidekt(text, status_callback=status)

            cards, not_found, bad = scryfall.resolve_decklist(
                text, status_callback=status)
            self.after(0, lambda: self._done(cards, not_found, bad))
        except Exception as e:
            self.after(0, lambda: self._failed(e))

    def _done(self, cards, not_found, bad):
        if cards:
            self.on_resolved(cards)

        problems = []
        if not_found:
            problems.append("Not found on Scryfall:\n  - " + "\n  - ".join(not_found))
        if bad:
            problems.append("Could not parse these lines:\n  - " + "\n  - ".join(bad))

        if problems:
            self.import_btn.configure(state="normal", text="Resolve & add")
            self.status.configure(
                text=f"Added {len(cards)}. {len(not_found)+len(bad)} issue(s) — see popup.",
                text_color="#fca5a5")
            messagebox.showwarning(
                "Imported with issues",
                f"Added {len(cards)} card(s) to the queue.\n\n" + "\n\n".join(problems),
                parent=self)
        else:
            self.destroy()

    def _failed(self, e):
        self.import_btn.configure(state="normal", text="Resolve & add")
        self.status.configure(text=f"Error: {e}", text_color="#fca5a5")


# --------------------------------------------------------------------------
# PDF export dialog with live preview
# --------------------------------------------------------------------------
_PAGE_MM = {"Letter": (215.9, 279.4), "A4": (210.0, 297.0)}

# Cards are kept at WORK_SIZE in memory: big enough for the detector to
# behave as it will at print resolution and for the loupe to magnify, small
# enough to redraw the whole sheet instantly.
WORK_SIZE = (640, 896)
THUMB_SIZE = (200, 279)
LOUPE_PX = 148              # size of the magnifier window, in pixels
LOUPE_MM = 12               # how much of the card it shows (~6x zoom)

GUIDE_CHOICES = ["White", "Black", "Gray", "None"]
GUIDE_STYLE_CHOICES = ["Cross", "Corner"]
BLEED_COLOR_CHOICES = ["Black", "White"]


class ExportDialog(ctk.CTkToplevel):
    """Print-sheet export: layout, quality, color pipeline, duplex backs and
    a live preview of page 1. Choices persist in settings.json."""

    def __init__(self, master, images, source):
        super().__init__(master)
        self.images = images
        self.source = source
        self.title("Export print sheet")
        self.geometry("980x760")
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
        self._prev_job = None
        self._page = 0             # sheet the ◀▶ nav is pointing at
        self._excluded = set()     # paths dropped from the export
        self._custom_back = None   # chosen card back for non-DFC cards
        self._img_xoff = 0         # x offset of the sheets inside the canvas
        self._sheet_tops = []      # y of each sheet in canvas coordinates
        self._sheet_geom = None    # (W, H, gap, sheets) of the current layout
        self._sheet_cache = {}     # page -> (PhotoImage, canvas id); lazy
        self._render_sheet = None  # closure that paints one sheet on demand
        self._tall_w = 0           # sheet width / total stacked height, for
        self._tall_h = 0           #   loupe clamping and scroll math
        self._drag = None          # in-progress card drag
        self._loupe_item = None    # canvas id of the magnifier overlay
        self._drag_item = None     # canvas id of the dragged thumbnail
        self._showing_backs = False

        # explicit print order (the source of truth for the PDF); backs follow
        # their front via _back_of. Drag-and-drop reorders _order.
        fronts0, backs0 = self._pairs()
        self._order = list(fronts0)
        self._back_of = {f: b for f, b in zip(fronts0, backs0)}

        s = load_settings()

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(self, text="Export print sheet",
                     font=("Georgia", 18, "bold"), text_color=GOLD).grid(
            row=0, column=0, sticky="w", padx=20, pady=(16, 2))
        self.summary = ctk.CTkLabel(self, text="", text_color=MUTED,
                                    font=("Segoe UI", 12))
        self.summary.grid(row=0, column=1, sticky="w", padx=8, pady=(20, 2))

        # ------------------------------------------------ left: controls
        left = ctk.CTkScrollableFrame(self, width=430, fg_color=PANEL,
                                      corner_radius=12)
        left.grid(row=1, column=0, sticky="nsw", padx=(16, 8), pady=8)
        left.grid_columnconfigure(1, weight=1)
        self._r = 0

        def row(label, values, initial):
            ctk.CTkLabel(left, text=label, anchor="w").grid(
                row=self._r, column=0, sticky="w", padx=(12, 8), pady=4)
            menu = ctk.CTkOptionMenu(left, values=values, width=220,
                                     fg_color=GRAY_BTN, button_color=GRAY_HOVER,
                                     command=self._refresh_preview)
            menu.set(initial if initial in values else values[0])
            menu.grid(row=self._r, column=1, sticky="w", pady=4)
            self._r += 1
            return menu

        def entry_row(label, key, default, hint=""):
            ctk.CTkLabel(left, text=label, anchor="w").grid(
                row=self._r, column=0, sticky="w", padx=(12, 8), pady=4)
            fr = ctk.CTkFrame(left, fg_color="transparent")
            fr.grid(row=self._r, column=1, sticky="w", pady=4)
            e = ctk.CTkEntry(fr, width=56, fg_color=BG, border_color=GRAY_BTN)
            e.insert(0, str(s.get(key, default)))
            e.pack(side="left")
            e.bind("<KeyRelease>", self._refresh_preview)
            if hint:
                ctk.CTkLabel(fr, text=hint, text_color=MUTED,
                             font=("Segoe UI", 11)).pack(side="left", padx=6)
            self._r += 1
            return e

        def section(text):
            ctk.CTkLabel(left, text=text, text_color=GOLD,
                         font=("Segoe UI", 12, "bold")).grid(
                row=self._r, column=0, columnspan=2, sticky="w",
                padx=12, pady=(10, 2))
            self._r += 1

        profile_labels = [p[0] for p in CALIBRATION_PROFILES.values()]
        saved_profile = CALIBRATION_PROFILES.get(s.get("profile", 1),
                                                 CALIBRATION_PROFILES[1])[0]

        section("Presets")
        prow = ctk.CTkFrame(left, fg_color="transparent")
        prow.grid(row=self._r, column=0, columnspan=2, sticky="w",
                  padx=12, pady=4)
        self._r += 1
        self.preset_menu = ctk.CTkOptionMenu(
            prow, values=self._preset_names(), width=180,
            fg_color=GRAY_BTN, button_color=GRAY_HOVER,
            command=self._apply_preset)
        self.preset_menu.set(self._PRESET_NONE)
        self.preset_menu.pack(side="left")
        ctk.CTkButton(prow, text="Save…", width=52, height=28,
                      fg_color=GRAY_BTN, hover_color=GRAY_HOVER,
                      command=self._save_preset).pack(side="left", padx=(6, 2))
        ctk.CTkButton(prow, text="Delete", width=58, height=28,
                      fg_color=GRAY_BTN, hover_color=GRAY_HOVER,
                      command=self._delete_preset).pack(side="left")

        section("Layout")
        self.layout = row("Card grid", list(print_sheet.LAYOUTS.keys()),
                          s.get("layout", print_sheet.DEFAULT_LAYOUT))
        self.page = row("Page size", PDF_PAGE_SIZES,
                        s.get("page", PDF_DEFAULT_PAGE))
        self.split = row("File split", list(PAGES_PER_FILE.keys()),
                         s.get("split", PAGES_PER_FILE_DEFAULT))
        self.edge_bleed = entry_row("Edge bleed (mm)", "edge_bleed", 0.0,
                                    "0 = cards touching")
        self.bleed_color = row("Bleed color", BLEED_COLOR_CHOICES,
                               s.get("bleed_color", "Black"))
        self.guides = row("Cut guides", GUIDE_CHOICES,
                          s.get("guides", "White"))
        self.guide_style = row("Guide style", GUIDE_STYLE_CHOICES,
                               s.get("guide_style", "Cross"))
        self.guide_len = entry_row("Guide length (mm)", "guide_len", 4.0)
        self.guide_thick = entry_row("Guide thickness (pt)", "guide_thick", 0.4)
        self.guide_offset = entry_row("Guide offset (mm)", "guide_offset", 0.0,
                                      "gap from the card")
        self.corner_radius = entry_row("Corner radius (mm)", "corner_radius",
                                       0.0, "0 = square")
        self.shift_down = entry_row("Shift down (mm)", "shift_down", 0.0,
                                    "late paper feed")

        section("Image pipeline (PDF only, masters untouched)")
        self.quality = row("Quality", list(PDF_QUALITY_MODES.keys()),
                           s.get("quality", PDF_DEFAULT_QUALITY))
        self.profile = row("Color profile", profile_labels, saved_profile)
        self.sharpen = row("Sharpening", list(SHARPEN_MODES.keys()),
                           s.get("sharpen", SHARPEN_DEFAULT))
        self.shadow = row("Shadow lift", list(SHADOW_LIFTS.keys()),
                          s.get("shadow", SHADOW_DEFAULT))
        self.border = row("Deepen black border", BORDER_MODES,
                          s.get("border", BORDER_DEFAULT))

        def slider_row(label, key, default, to, unit, fmt="{:.0f}"):
            ctk.CTkLabel(left, text=label, anchor="w").grid(
                row=self._r, column=0, sticky="w", padx=(12, 8), pady=4)
            fr = ctk.CTkFrame(left, fg_color="transparent")
            fr.grid(row=self._r, column=1, sticky="w", pady=4)
            val = ctk.CTkLabel(fr, text="", width=54, text_color=MUTED,
                               font=("Segoe UI", 11))
            sl = ctk.CTkSlider(fr, from_=0, to=to, width=175,
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

        self.border_amount = slider_row("Amount", "border_amount",
                                        BORDER_AMOUNT_DEFAULT, 100, "%")
        self.border_width = slider_row("Manual width (forced cards)",
                                       "border_width", BORDER_WIDTH_DEFAULT,
                                       12, "%", "{:.1f}")

        section("Duplex backs")
        self.backs = row("Card backs", BACKS_MODES,
                         s.get("backs", BACKS_MODES[0]))

        # chosen card back for every non-DFC card (DFCs keep their own back)
        ctk.CTkLabel(left, text="Back image", anchor="w").grid(
            row=self._r, column=0, sticky="w", padx=(12, 8), pady=4)
        backfr = ctk.CTkFrame(left, fg_color="transparent")
        backfr.grid(row=self._r, column=1, sticky="w", pady=4)
        self._r += 1
        self.back_lbl = ctk.CTkLabel(backfr, text=self._back_label(),
                                     text_color=MUTED, font=("Segoe UI", 11),
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

        section("Test sheets")
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

        self.status = ctk.CTkLabel(left, text="", text_color=MUTED,
                                   font=("Segoe UI", 11))
        self.status.grid(row=self._r, column=0, columnspan=2, sticky="w",
                         padx=12, pady=(6, 8))
        self._r += 1

        # ------------------------------------------------ right: preview
        right = ctk.CTkFrame(self, fg_color=PANEL, corner_radius=12)
        right.grid(row=1, column=1, sticky="nsew", padx=(8, 16), pady=8)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)
        head = ctk.CTkFrame(right, fg_color="transparent")
        head.grid(row=0, column=0, columnspan=2, sticky="ew", padx=10,
                  pady=(10, 2))
        head.grid_columnconfigure(1, weight=1)
        self.prev_page_btn = ctk.CTkButton(head, text="◀", width=30, height=24,
                                           fg_color=GRAY_BTN, hover_color=GRAY_HOVER,
                                           command=lambda: self._flip_page(-1))
        self.prev_page_btn.grid(row=0, column=0, sticky="w")
        self.preview_title = ctk.CTkLabel(head, text="Preview",
                                          text_color=MUTED, font=("Segoe UI", 12))
        self.preview_title.grid(row=0, column=1)
        self.next_page_btn = ctk.CTkButton(head, text="▶", width=30, height=24,
                                           fg_color=GRAY_BTN, hover_color=GRAY_HOVER,
                                           command=lambda: self._flip_page(1))
        self.next_page_btn.grid(row=0, column=2, sticky="e")
        self.side_btn = ctk.CTkSegmentedButton(
            head, values=["Fronts", "Backs"], height=24,
            font=("Segoe UI", 11), command=lambda _v: self._draw_preview(),
            fg_color=BG, unselected_color=BG, unselected_hover_color=GRAY_HOVER,
            selected_color=GOLD, selected_hover_color=GOLD_HOVER,
            text_color="#d7dbe4")
        self.side_btn.set("Fronts")
        self.side_btn.grid(row=0, column=3, sticky="e", padx=(8, 0))
        self.canvas = tk.Canvas(right, bg=PANEL, highlightthickness=0, bd=0)
        self.canvas.grid(row=1, column=0, sticky="nsew", padx=(10, 0),
                         pady=(0, 6))
        self.vbar = ctk.CTkScrollbar(right, command=self.canvas.yview)
        self.vbar.grid(row=1, column=1, sticky="ns", padx=(2, 8), pady=(0, 6))
        self.canvas.configure(yscrollcommand=self._on_yscroll)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        self.canvas.bind("<Button-3>", self._preview_rclick)
        self.canvas.bind("<Motion>", self._preview_motion)
        self.canvas.bind("<Leave>", self._preview_leave)
        self.canvas.bind("<MouseWheel>",
                         lambda e: self.canvas.yview_scroll(
                             int(-e.delta / 120), "units"))
        self.canvas.bind("<Configure>", self._recenter_preview)
        ctk.CTkLabel(right, text="Scroll through every sheet · drag a card to "
                     "reorder · left-click cycles the black border · "
                     "right-click drops a card",
                     text_color=MUTED, font=("Segoe UI", 11)).grid(
            row=2, column=0, columnspan=2, pady=(0, 8))

        # ------------------------------------------------ bottom buttons
        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=2, column=0, columnspan=2, sticky="e",
                  padx=20, pady=(0, 14))
        ctk.CTkButton(btns, text="Cancel", width=90, fg_color=GRAY_BTN,
                      hover_color=GRAY_HOVER, command=self.destroy).pack(
            side="left", padx=6)
        self.export_btn = ctk.CTkButton(btns, text="Export", width=130,
                                        fg_color=GOLD, hover_color=GOLD_HOVER,
                                        text_color=GOLD_TEXT,
                                        font=("Segoe UI", 13, "bold"),
                                        command=self._export)
        self.export_btn.pack(side="left")

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
        return self._float(self.shift_down, 0.0, 0.0)

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

    def _collect_settings(self) -> dict:
        """Every export control as a flat dict — used both to persist the
        last-used values and to save/load named presets."""
        dx, dy = self._offsets()
        return {
            "layout": self.layout.get(),
            "page": self.page.get(),
            "quality": self.quality.get(),
            "split": self.split.get(),
            "profile": self._profile_id(),
            "sharpen": self.sharpen.get(),
            "shadow": self.shadow.get(),
            "border": self.border.get(),
            "border_amount": round(self.border_amount.get(), 1),
            "border_width": round(self.border_width.get(), 1),
            "backs": self.backs.get(),
            "back_dx": dx,
            "back_dy": dy,
            "back_rot": self._back_rot(),
            "back_bleed": self._bleed(),
            "edge_bleed": self._edge_bleed(),
            "bleed_color": self.bleed_color.get(),
            "guides": self.guides.get(),
            "guide_style": self.guide_style.get(),
            "guide_len": self._guide_len(),
            "guide_thick": self._guide_thick(),
            "guide_offset": self._guide_offset(),
            "corner_radius": self._corner_radius(),
            "shift_down": self._shift(),
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
        om(self.bleed_color, "bleed_color"); om(self.guides, "guides")
        om(self.guide_style, "guide_style"); om(self.quality, "quality")
        om(self.sharpen, "sharpen"); om(self.shadow, "shadow")
        om(self.border, "border"); om(self.backs, "backs")
        if "profile" in d:
            prof = CALIBRATION_PROFILES.get(d["profile"])
            if prof:
                self.profile.set(prof[0])
        for e, key in ((self.edge_bleed, "edge_bleed"),
                       (self.shift_down, "shift_down"),
                       (self.guide_len, "guide_len"),
                       (self.guide_thick, "guide_thick"),
                       (self.guide_offset, "guide_offset"),
                       (self.corner_radius, "corner_radius"),
                       (self.back_dx, "back_dx"), (self.back_dy, "back_dy"),
                       (self.back_rot, "back_rot"), (self.back_bleed, "back_bleed")):
            if key in d:
                e.delete(0, "end"); e.insert(0, str(d[key]))
        for key in ("border_amount", "border_width"):
            if key in d and key in self._slider_setters:
                self._slider_setters[key](float(d[key]))
        self.back_lbl.configure(text=self._back_label())
        threading.Thread(target=self._load_thumbs, daemon=True).start()
        self._draw_preview()

    def _persist(self):
        s = load_settings()
        s.update(self._collect_settings())
        save_settings(s)

    # ---------------------------------------------------------- presets
    _PRESET_NONE = "— presets —"

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

    def _set_status(self, text):
        self.after(0, lambda: self.status.configure(text=text))

    # ------------------------------------------------------------- preview
    _PREVIEW_BOX = (470, 560)   # max preview pixels (w, h)

    def _sheet_images(self, drop_excluded=True):
        """
        What goes on the sheets: (fronts, backs), backs=None when duplex is
        off. In duplex a card's own back face stops being a front. A chosen
        card back overrides back.png. When drop_excluded is True the cards the
        user right-clicked out are removed (the export view); when False they
        are kept so the preview can still show and restore them.
        """
        def keep(f):
            return not drop_excluded or str(f) not in self._excluded

        fronts = [f for f in self._order if keep(f)]
        if self.backs.get() != BACKS_MODES[0]:
            default = self._custom_back or find_back_image()
            backs = [self._back_of.get(f) or default for f in fronts]
            return fronts, backs
        return fronts, None

    def _load_thumbs(self):
        fronts, backs = self._sheet_images()
        wanted = list(fronts) + [b for b in (backs or []) if b]
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
        try:
            self.after(0, self._draw_preview)
        except RuntimeError:
            pass

    def _treated_thumb(self, key):
        """Working-size treated copy (cached for the loupe) plus its thumb.
        Built on demand — only for cards actually painted on a visible sheet."""
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
        cols, rows, landscape = print_sheet.LAYOUTS.get(
            self.layout.get(), print_sheet.LAYOUTS[print_sheet.DEFAULT_LAYOUT])
        pw, ph = _PAGE_MM.get(self.page.get(), _PAGE_MM["A4"])
        if landscape:
            pw, ph = ph, pw
        s = min(self._PREVIEW_BOX[0] / pw, self._PREVIEW_BOX[1] / ph)
        W, H = int(pw * s), int(ph * s)

        per_page = cols * rows
        border_on = self.border.get() != BORDER_MODES[0]
        # preview keeps excluded cards visible (shown crossed out); the export
        # count below uses the dropped-excluded list
        fronts, backs = self._sheet_images(drop_excluded=False)
        exp_fronts, _ = self._sheet_images(drop_excluded=True)
        duplex = backs is not None
        showing_backs = duplex and self.side_btn.get() == "Backs"
        self._showing_backs = showing_backs
        page_items = backs if showing_backs else fronts
        eb = self._edge_bleed()
        g = 2 * eb
        bw = cols * 63 + (cols - 1) * g
        bh = rows * 88 + (rows - 1) * g
        left = (pw - bw) / 2
        top = (ph - bh) / 2 + self._shift()
        if ph - top - bh < 3:
            top = ph - bh - 3

        def X(v):
            return int(v * s)

        bleed_fill = {"Black": (10, 10, 10), "White": (250, 250, 250)}.get(
            self.bleed_color.get(), (10, 10, 10))
        gc = {"White": (255, 255, 255), "Black": (0, 0, 0),
              "Gray": (120, 120, 120), "None": None}.get(self.guides.get())
        cw, ch = X(left + 63) - X(left), X(top + 88) - X(top)
        sheets = max(1, -(-len(fronts) // per_page))
        self._page = max(0, min(self._page, sheets - 1))

        guide_len = self._guide_len()
        guide_style = self.guide_style.get()
        guide_offset = self._guide_offset()
        corner_r = self._corner_radius()
        corner_mask = None
        if corner_r > 0:
            r = max(1, int(corner_r * cw / 63))
            corner_mask = PILImage.new("L", (cw, ch), 0)
            PILDraw.Draw(corner_mask).rounded_rectangle(
                [0, 0, cw - 1, ch - 1], radius=r, fill=255)

        def render_sheet(page):
            """One sheet as a (W,H) image plus its local card hit-boxes."""
            img = PILImage.new("RGB", (W, H), (255, 255, 255))
            d = PILDraw.Draw(img)
            slots = []
            base_i = page * per_page
            for idx in range(per_page):
                col, rw = idx % cols, idx // cols
                # backs print column-mirrored so they land behind their front
                local = rw * cols + (cols - 1 - col) if showing_backs else idx
                slot = base_i + local
                x = left + col * (63 + g)
                y = top + rw * (88 + g)
                if slot >= len(page_items):
                    continue
                if eb > 0:
                    d.rectangle([X(x - eb), X(y - eb),
                                 X(x + 63 + eb), X(y + 88 + eb)],
                                fill=bleed_fill, outline=(210, 210, 215))
                item = page_items[slot]
                key = str(item) if item else None
                mode = self._border_modes.get(key, "auto")
                treated = mode == "on" or (mode == "auto" and border_on)
                if key:
                    t = self._treated_thumb(key) if treated else None
                    t = t or self._thumbs.get(key)
                else:
                    t = None
                if t:
                    img.paste(t.resize((cw, ch)), (X(x), X(y)), corner_mask)
                    slots.append((X(x), X(y), X(x + 63), X(y + 88), key))
                    if key in self._excluded:
                        ov = PILImage.new("RGBA", (cw, ch), (20, 20, 25, 150))
                        img.paste(ov, (X(x), X(y)), ov)
                        d.line([X(x), X(y), X(x + 63), X(y + 88)],
                               fill=(220, 70, 70), width=3)
                        d.line([X(x + 63), X(y), X(x), X(y + 88)],
                               fill=(220, 70, 70), width=3)
                    elif mode != "auto":
                        bc = (90, 190, 110) if mode == "on" else (210, 110, 110)
                        d.rectangle([X(x) + 3, X(y) + 3, X(x) + 36, X(y) + 18],
                                    fill=bc)
                        d.text((X(x) + 8, X(y) + 5),
                               "ON" if mode == "on" else "OFF", fill=(15, 15, 20))
                else:
                    d.rectangle([X(x), X(y), X(x + 63), X(y + 88)],
                                fill=(55, 60, 76))
                    if showing_backs and not item:
                        d.text((X(x) + cw // 2 - 26, X(y) + ch // 2),
                               "back.png\nmissing", fill=(190, 120, 120))

            xs, ys = set(), set()
            for c_ in range(cols):
                xs.add(left + c_ * (63 + g)); xs.add(left + c_ * (63 + g) + 63)
            for c_ in range(rows):
                ys.add(top + c_ * (88 + g)); ys.add(top + c_ * (88 + g) + 88)
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
            d.rectangle([0, 0, W - 1, H - 1], outline=(185, 190, 200))
            return img, slots

        # Lazy multi-sheet canvas: only sheets near the viewport are painted
        # (see _render_visible). Hit-boxes for every card are cheap, so they
        # are all computed here for drag / loupe / right-click.
        gap = self._SHEET_GAP
        total_h = sheets * H + (sheets + 1) * gap
        side = "backs, mirrored" if showing_backs else "fronts"
        self._sheet_tops = [gap + p * (H + gap) for p in range(sheets)]

        self._slots = []
        for p in range(sheets):
            st = self._sheet_tops[p]
            for idx in range(per_page):
                col, rw = idx % cols, idx // cols
                local = rw * cols + (cols - 1 - col) if showing_backs else idx
                slot = p * per_page + local
                if slot >= len(page_items):
                    continue
                item = page_items[slot]
                if not item:
                    continue
                x = left + col * (63 + g)
                y = top + rw * (88 + g)
                self._slots.append((X(x), st + X(y),
                                    X(x + 63), st + X(y + 88), str(item)))

        self._render_sheet = lambda p: render_sheet(p)[0]
        self._sheet_geom = (W, H, gap, sheets)
        self._tall_w, self._tall_h = W, total_h

        canvas_w = self.canvas.winfo_width()
        self._img_xoff = max(0, (canvas_w - W) // 2)
        self.canvas.delete("all")
        self._sheet_cache = {}
        self._loupe_item = self._drag_item = None
        for p in range(sheets):
            self.canvas.create_text(
                self._img_xoff + 4, self._sheet_tops[p] - 8, anchor="w",
                text=f"Sheet {p + 1} of {sheets} — {side}",
                fill="#969caa", font=("Segoe UI", 8), tags="cap")
        self.canvas.configure(scrollregion=(0, 0, max(W, canvas_w), total_h))
        self._render_visible()

        pages = sheets * 2 if duplex else sheets      # PDF pages
        self.preview_title.configure(
            text=f"{sheets} sheet(s) · {pages} PDF page(s)")
        self._update_nav(sheets)
        self.side_btn.configure(state="normal" if duplex else "disabled")
        if not duplex:
            self.side_btn.set("Fronts")

        # export counts use the dropped-excluded list
        exp_sheets = max(1, -(-len(exp_fronts) // per_page)) if exp_fronts else 0
        exp_pages = exp_sheets * 2 if duplex else exp_sheets
        dropped = len(fronts) - len(exp_fronts)
        drop = f", {dropped} dropped" if dropped else ""
        self.summary.configure(
            text=f"{len(exp_fronts)} card(s) from the {self.source}{drop} -> "
                 f"{exp_sheets} sheet(s), {exp_pages} PDF page(s)")

    def destroy(self):
        if self._prev_job:
            try:
                self.after_cancel(self._prev_job)
            except Exception:
                pass
            self._prev_job = None
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
            mode = self._border_modes.get(key, "auto")
            treated = mode == "on" or (
                mode == "auto" and self.border.get() != BORDER_MODES[0])
            src = (self._work_b if treated else {}).get(key)
            if src is None:
                pair = self._thumbs_raw.get(key)
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
        return "back.png (default)" if find_back_image() else "none set"

    def _choose_back_file(self):
        f = filedialog.askopenfilename(
            parent=self, title="Choose a card back image",
            filetypes=[("Images", "*.png *.jpg *.jpeg *.webp")])
        if f:
            self._custom_back = f
            self._after_back_change()

    def _choose_back_mpc(self):
        MPCDialog(self, on_pick=self._back_from_mpc)

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
        if self._drag_item is not None:
            self.canvas.coords(self._drag_item,
                               self.canvas.canvasx(event.x) + 12,
                               self.canvas.canvasy(event.y) + 12)
        # let the user drag onto any sheet by auto-scrolling at the edges
        h = self.canvas.winfo_height()
        if event.y < 24:
            self.canvas.yview_scroll(-1, "units")
        elif event.y > h - 24:
            self.canvas.yview_scroll(1, "units")

    def _start_drag_ghost(self, key):
        thumb = self._thumbs.get(key)
        if thumb is None:
            return
        ghost = thumb.resize((thumb.size[0] // 2, thumb.size[1] // 2))
        self._ghostphoto = PILImageTk.PhotoImage(ghost)
        self._drag_item = self.canvas.create_image(
            0, 0, anchor="nw", image=self._ghostphoto, tags="ghost")

    def _on_release(self, event):
        d = self._drag
        self._drag = None
        self.canvas.delete("ghost")
        self._drag_item = None
        if not d:
            return
        if not d["moved"]:
            # a plain click cycles the black border: auto -> off -> on
            key = d["key"]
            nxt = {"auto": "off", "off": "on", "on": "auto"}
            self._border_modes[key] = nxt[self._border_modes.get(key, "auto")]
            self._draw_preview()
            return
        cx, cy = self._event_xy(event)
        self._reorder(d["key"], self._key_at(cx, cy))

    def _reorder(self, src_key, tgt_key):
        """Move the dragged card to sit just before the card it was dropped on."""
        if not tgt_key or tgt_key == src_key:
            return
        src = next((f for f in self._order if str(f) == src_key), None)
        tgt = next((f for f in self._order if str(f) == tgt_key), None)
        if src is None or tgt is None:
            return
        order = list(self._order)
        order.remove(src)
        order.insert(order.index(tgt), src)
        self._order = order
        self._draw_preview()

    def _preview_rclick(self, event):
        """Drop / restore the card under the cursor from the export."""
        cx, cy = self._event_xy(event)
        key = self._key_at(cx, cy)
        if not key:
            return
        if key in self._excluded:
            self._excluded.discard(key)
        else:
            self._excluded.add(key)
        threading.Thread(target=self._load_thumbs, daemon=True).start()
        self._draw_preview()

    # ------------------------------------------------------------- actions
    def _export(self):
        target = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".pdf",
            initialdir=OUTPUT_FOLDER,
            initialfile="print-sheet.pdf",
            filetypes=[("PDF", "*.pdf")])
        if not target:
            return

        self._persist()
        self.export_btn.configure(state="disabled", text="Exporting...")

        # honours dropped cards, the chosen card back and DFC pairing
        images, backs = self._sheet_images(drop_excluded=True)
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
            border_modes=dict(self._border_modes),
            border_amount=self.border_amount.get() / 100.0,
            border_width=self.border_width.get() / 100.0,
            pages_per_file=PAGES_PER_FILE.get(self.split.get(), 0),
            backs=backs,
            back_offset=self._offsets(),
            back_bleed_mm=self._bleed(),
            back_rotation_deg=self._back_rot(),
            edge_bleed_mm=self._edge_bleed(),
            bleed_color=self.bleed_color.get(),
            guide_color=self.guides.get(),
            guide_len_mm=self._guide_len(),
            guide_thick=self._guide_thick(),
            guide_style=self.guide_style.get(),
            guide_offset_mm=self._guide_offset(),
            corner_radius_mm=self._corner_radius(),
            shift_down_mm=self._shift(),
        )

        def build():
            try:
                files = print_sheet.build_pdf(
                    images, target,
                    status_callback=self._set_status, **args)
                self.after(0, lambda: self._done(files))
            except Exception as e:
                self.after(0, lambda: self._failed(e))

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
        messagebox.showinfo(
            "PDF ready",
            f"{len(self.images)} card(s) -> {len(files)} file(s), "
            f"{total_mb:.0f} MB total:\n\n{names}", parent=self)
        self.destroy()

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
        card = self.images[0]
        page = self.page.get()
        shift = self._shift()

        def build():
            try:
                print_sheet.build_calibration(
                    card, target, page, shift_down_mm=shift,
                    status_callback=self._set_status)
                self.after(0, lambda: self._cal_done(target))
            except Exception as e:
                self.after(0, lambda: self._failed_cal(e))

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
        card = self.images[0]
        page = self.page.get()
        profile = self._profile_id()
        shift = self._shift()

        def build():
            try:
                print_sheet.build_shadow_test(
                    card, target, page, profile, shift_down_mm=shift,
                    status_callback=self._set_status)
                self.after(0, lambda: self._shadow_done(target))
            except Exception as e:
                self.after(0, lambda: self._shadow_failed(e))

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
        )

        def build():
            try:
                print_sheet.build_duplex_test(
                    target, status_callback=self._set_status, **args)
                self.after(0, lambda: self._duplex_done(target))
            except Exception as e:
                self.after(0, lambda: self._duplex_failed(e))

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
                     font=("Georgia", 18, "bold"), text_color=GOLD).pack(
            anchor="w", padx=24, pady=(20, 4))
        ctk.CTkLabel(
            self,
            text="This app downloads its AI engine and models from their\n"
                 "official sources on first run (~110 MB total):\n"
                 "  •  Real-ESRGAN engine + base models (BSD license)\n"
                 "  •  UltraSharp / High Fidelity models (Upscayl project)\n\n"
                 "This happens only once.",
            justify="left", text_color=MUTED,
            font=("Segoe UI", 12)).pack(anchor="w", padx=24)

        self.bar = ctk.CTkProgressBar(self, width=460, progress_color=GOLD)
        self.bar.set(0)
        self.bar.pack(padx=24, pady=(16, 4))
        self.status = ctk.CTkLabel(self, text="Starting…", text_color=MUTED,
                                   font=("Segoe UI", 11))
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
            self.after(0, lambda: self._fail(e))

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
class MPCDialog(ctk.CTkToplevel):
    """Search mpcfill.com and pick a card version to add to the queue."""

    COLS = 4
    THUMB = (150, 209)

    def __init__(self, master, on_pick):
        super().__init__(master)
        self.on_pick = on_pick
        self.title("Search MPC Autofill")
        self.geometry("720x640")
        self.transient(master)
        self.after(60, self.grab_set)
        self.configure(fg_color=BG)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)
        self._thumbs = {}          # keep CTkImage refs alive
        self._token = 0            # ignore stale search threads

        ctk.CTkLabel(self, text="Search MPC Autofill",
                     font=("Georgia", 18, "bold"), text_color=GOLD).grid(
            row=0, column=0, sticky="w", padx=20, pady=(16, 2))

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.grid(row=1, column=0, sticky="ew", padx=16, pady=6)
        bar.grid_columnconfigure(0, weight=1)
        self.entry = ctk.CTkEntry(bar, height=38, fg_color=PANEL,
                                  border_color=GRAY_BTN,
                                  placeholder_text="Card name (e.g. Sol Ring)")
        self.entry.grid(row=0, column=0, sticky="ew", padx=(0, 8))
        self.entry.bind("<Return>", lambda e: self._search())
        self.search_btn = ctk.CTkButton(bar, text="Search", width=100, height=38,
                                        fg_color=GOLD, hover_color=GOLD_HOVER,
                                        text_color=GOLD_TEXT,
                                        font=("Segoe UI", 13, "bold"),
                                        command=self._search)
        self.search_btn.grid(row=0, column=1)

        self.grid_frame = ctk.CTkScrollableFrame(self, fg_color=PANEL,
                                                 corner_radius=10)
        self.grid_frame.grid(row=2, column=0, sticky="nsew", padx=16, pady=8)
        for c in range(self.COLS):
            self.grid_frame.grid_columnconfigure(c, weight=1)

        self.status = ctk.CTkLabel(self, text="Type a card name and hit Search.",
                                   text_color=MUTED, font=("Segoe UI", 12))
        self.status.grid(row=3, column=0, sticky="w", padx=20, pady=(0, 12))

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
                cards = mpcfill.search(query)
                self.after(0, lambda: self._show(cards, token))
            except Exception as e:
                self.after(0, lambda: self._failed(e))

        threading.Thread(target=work, daemon=True).start()

    def _failed(self, e):
        self.search_btn.configure(state="normal")
        self.status.configure(text=f"Search failed: {e}", text_color="#fca5a5")

    def _show(self, cards, token):
        if token != self._token:
            return
        self.search_btn.configure(state="normal")
        if not cards:
            self.status.configure(text="No matches on MPC Autofill.",
                                  text_color="#fca5a5")
            return
        self.status.configure(
            text=f"{len(cards)} version(s). Click one to add it to the queue.",
            text_color=MUTED)
        for i, card in enumerate(cards):
            self._card_tile(card, i // self.COLS, i % self.COLS, token)

    def _card_tile(self, card, r, c, token):
        tile = ctk.CTkFrame(self.grid_frame, fg_color=ROW, corner_radius=8)
        tile.grid(row=r, column=c, padx=6, pady=6, sticky="n")
        ph = ctk.CTkLabel(tile, text="…", width=self.THUMB[0],
                          height=self.THUMB[1], text_color=MUTED)
        ph.pack(padx=6, pady=(6, 2))
        name = card["name"]
        short = name if len(name) <= 26 else name[:25] + "…"
        ctk.CTkLabel(tile, text=short, font=("Segoe UI", 11),
                     wraplength=self.THUMB[0]).pack(padx=6)
        ctk.CTkLabel(tile, text=f"{card['source']} · {card['dpi']}dpi",
                     font=("Segoe UI", 10), text_color=MUTED).pack(padx=6)
        add = ctk.CTkButton(tile, text="Add", width=70, height=26,
                            fg_color=GOLD, hover_color=GOLD_HOVER,
                            text_color=GOLD_TEXT, font=("Segoe UI", 11, "bold"),
                            command=lambda ca=card: self._pick(ca))
        add.pack(padx=6, pady=(2, 8))

        def load():
            data = mpcfill.fetch_thumb(card["thumb"])
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
        self.on_pick(card)
        self.status.configure(text=f"Added: {card['name']}", text_color=GOLD)
