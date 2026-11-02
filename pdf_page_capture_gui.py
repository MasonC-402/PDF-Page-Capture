#!/usr/bin/env python3
"""
pdf_page_capture_gui.py - Windowed front end for pdf_page_capture.py.

Same capture engine as the command-line version, but every option is a button,
checkbox or field, so no terminal is needed. This is the file that gets packaged
into the Windows .exe.

Run from source:
    pip install pyautogui pillow
    python pdf_page_capture_gui.py
"""

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

# Without DPI awareness, Windows display scaling (125%/150%) makes the mouse
# coordinates and the screenshot pixels disagree. Must run before Tk starts.
if sys.platform == "win32":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass

import pyautogui

from pdf_page_capture import run_capture

SETTINGS_FILE = Path.home() / ".pdf_page_capture.json"
DEFAULT_OUT = Path.home() / "Documents" / "PDF Page Capture"
HOVER_WAIT = 5  # seconds to hover when recording a position
START_WAIT = 5  # seconds between minimizing the window and the first screenshot
KEYS = ["right", "pagedown", "down", "space"]
_DONE = object()  # queue sentinel: capture thread finished


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("PDF Page Capture")
        root.resizable(False, True)

        self.mode = tk.StringVar(value="click")
        self.key = tk.StringVar(value=KEYS[0])
        self.reveal = tk.BooleanVar(value=False)
        self.full_screen = tk.BooleanVar(value=False)
        self.delay = tk.StringVar(value="1.5")
        self.max_pages = tk.StringVar(value="1000")
        self.reveal_delay = tk.StringVar(value="1.0")
        self.tolerance = tk.StringVar(value="10")
        self.park_mouse = tk.BooleanVar(value=True)
        self.make_pdf = tk.BooleanVar(value=True)
        self.out_dir = tk.StringVar(value=str(DEFAULT_OUT))

        self.next_pos: tuple[int, int] | None = None
        self.reveal_pos: tuple[int, int] | None = None
        self.region: tuple[int, int, int, int] | None = None

        self.log_queue: queue.Queue = queue.Queue()
        self.stop_event = threading.Event()
        self.worker: threading.Thread | None = None
        self.saved_count = 0

        self._load_settings()
        self._build()
        self._refresh()

    # --- Layout -------------------------------------------------------------

    def _build(self) -> None:
        pad = {"padx": 8, "pady": 4}
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill="both", expand=True)

        # Step 1: how to turn the page
        adv = ttk.LabelFrame(main, text="1. How to turn the page", padding=6)
        adv.pack(fill="x", **pad)
        ttk.Radiobutton(adv, text="Click the viewer's Next button", variable=self.mode,
                        value="click", command=self._refresh).grid(row=0, column=0, sticky="w")
        self.next_btn = ttk.Button(adv, text="Set Next button", command=self._pick_next)
        self.next_btn.grid(row=0, column=1, padx=6)
        self.next_lbl = ttk.Label(adv, width=22)
        self.next_lbl.grid(row=0, column=2, sticky="w")
        ttk.Radiobutton(adv, text="Press a key", variable=self.mode,
                        value="key", command=self._refresh).grid(row=1, column=0, sticky="w")
        self.key_box = ttk.Combobox(adv, textvariable=self.key, values=KEYS, width=12, state="readonly")
        self.key_box.grid(row=1, column=1, padx=6, sticky="w")

        # Step 2: what to capture
        cap = ttk.LabelFrame(main, text="2. What to capture", padding=6)
        cap.pack(fill="x", **pad)
        self.area_btn = ttk.Button(cap, text="Set capture area", command=self._pick_area)
        self.area_btn.grid(row=0, column=0, sticky="w")
        self.area_lbl = ttk.Label(cap, width=30)
        self.area_lbl.grid(row=0, column=1, padx=6, sticky="w")
        ttk.Checkbutton(cap, text="Whole screen instead", variable=self.full_screen,
                        command=self._refresh).grid(row=1, column=0, columnspan=2, sticky="w")

        # Optional reveal click
        rev = ttk.LabelFrame(main, text="Optional: 'Click to display content' spot", padding=6)
        rev.pack(fill="x", **pad)
        ttk.Checkbutton(rev, text="Click this spot before each page", variable=self.reveal,
                        command=self._refresh).grid(row=0, column=0, sticky="w")
        self.reveal_btn = ttk.Button(rev, text="Set spot", command=self._pick_reveal)
        self.reveal_btn.grid(row=0, column=1, padx=6)
        self.reveal_lbl = ttk.Label(rev, width=16)
        self.reveal_lbl.grid(row=0, column=2, sticky="w")

        # Options
        opt = ttk.LabelFrame(main, text="Options", padding=6)
        opt.pack(fill="x", **pad)
        fields = [
            ("Seconds to wait for each page", self.delay),
            ("Maximum pages", self.max_pages),
            ("Seconds to wait after reveal click", self.reveal_delay),
            ("Change sensitivity (0-255, lower = stricter)", self.tolerance),
        ]
        for i, (label, var) in enumerate(fields):
            ttk.Label(opt, text=label).grid(row=i, column=0, sticky="w")
            ttk.Entry(opt, textvariable=var, width=8).grid(row=i, column=1, sticky="w", padx=6)
        ttk.Checkbutton(opt, text="Move mouse out of the way before each screenshot",
                        variable=self.park_mouse).grid(row=4, column=0, columnspan=2, sticky="w")
        ttk.Checkbutton(opt, text="Also combine all pages into one PDF",
                        variable=self.make_pdf).grid(row=5, column=0, columnspan=2, sticky="w")

        # Output folder
        out = ttk.LabelFrame(main, text="Save to", padding=6)
        out.pack(fill="x", **pad)
        ttk.Entry(out, textvariable=self.out_dir, width=45).grid(row=0, column=0, sticky="we")
        ttk.Button(out, text="Browse...", command=self._browse).grid(row=0, column=1, padx=6)
        ttk.Button(out, text="Open", command=self._open_folder).grid(row=0, column=2)

        # Start / Stop
        run = ttk.Frame(main)
        run.pack(fill="x", **pad)
        self.start_btn = ttk.Button(run, text="Start", command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(run, text="Stop", command=self._stop, state="disabled")
        self.stop_btn.pack(side="left", padx=6)
        self.status = ttk.Label(run, text="", foreground="#0a5")
        self.status.pack(side="left", padx=6)

        ttk.Label(main, foreground="#666", wraplength=440, text=(
            "Tip: put the PDF on page 1 before pressing Start. To stop early, slam the "
            "mouse into any corner of the screen.")).pack(fill="x", **pad)

        self.log = ScrolledText(main, height=10, width=60, state="disabled")
        self.log.pack(fill="both", expand=True, **pad)

    def _refresh(self) -> None:
        click = self.mode.get() == "click"
        self.next_btn.configure(state="normal" if click else "disabled")
        self.key_box.configure(state="readonly" if not click else "disabled")
        self.area_btn.configure(state="disabled" if self.full_screen.get() else "normal")
        self.reveal_btn.configure(state="normal" if self.reveal.get() else "disabled")
        self.next_lbl.configure(text=self._fmt_point(self.next_pos))
        self.reveal_lbl.configure(text=self._fmt_point(self.reveal_pos))
        if self.region:
            l, t, w, h = self.region
            self.area_lbl.configure(text=f"✓ {w}x{h} at ({l}, {t})")
        else:
            self.area_lbl.configure(text="not set")

    @staticmethod
    def _fmt_point(pos: tuple[int, int] | None) -> str:
        return f"✓ ({pos[0]}, {pos[1]})" if pos else "not set"

    # --- Recording positions ------------------------------------------------

    def _countdown_then(self, msg: str, seconds: int, callback) -> None:
        """Show a countdown in the status label without freezing the window."""
        if seconds > 0:
            self.status.configure(text=f"{msg} in {seconds}...")
            self.root.after(1000, self._countdown_then, msg, seconds - 1, callback)
        else:
            self.status.configure(text="")
            callback()

    def _pick_point(self, what: str, callback) -> None:
        self._set_busy(True)
        self._log(f"Hover the mouse over the {what} and hold still...")

        def done() -> None:
            pos = pyautogui.position()
            self._set_busy(False)
            callback((pos.x, pos.y))  # may start another pick (capture area)
            self._refresh()

        self._countdown_then(f"Recording {what}", HOVER_WAIT, done)

    def _pick_next(self) -> None:
        def got(pos):
            self.next_pos = pos
            self._log(f"Next button set to {pos}")
        self._pick_point("NEXT PAGE button", got)

    def _pick_reveal(self) -> None:
        def got(pos):
            self.reveal_pos = pos
            self._log(f"Reveal spot set to {pos}")
        self._pick_point("'display content' spot", got)

    def _pick_area(self) -> None:
        def got_tl(tl):
            def got_br(br):
                left, top = min(tl[0], br[0]), min(tl[1], br[1])
                self.region = (left, top, abs(br[0] - tl[0]), abs(br[1] - tl[1]))
                self._log(f"Capture area set to {self.region[2]}x{self.region[3]} at ({left}, {top})")
            self._pick_point("BOTTOM-RIGHT corner of the page", got_br)
        self._pick_point("TOP-LEFT corner of the page", got_tl)

    # --- Running ------------------------------------------------------------

    def _set_busy(self, busy: bool) -> None:
        self.start_btn.configure(state="disabled" if busy else "normal")
        if busy:
            for btn in (self.next_btn, self.area_btn, self.reveal_btn):
                btn.configure(state="disabled")
        else:
            self._refresh()

    def _read_options(self) -> dict | None:
        try:
            opts = {
                "delay": float(self.delay.get()),
                "max_pages": int(self.max_pages.get()),
                "reveal_delay": float(self.reveal_delay.get()),
                "tolerance": int(self.tolerance.get()),
            }
        except ValueError:
            messagebox.showerror("PDF Page Capture", "Please enter numbers in the Options boxes.")
            return None
        if self.mode.get() == "click" and not self.next_pos:
            messagebox.showerror("PDF Page Capture", "Click 'Set Next button' first (step 1).")
            return None
        if not self.full_screen.get() and not self.region:
            messagebox.showerror("PDF Page Capture",
                                 "Click 'Set capture area' first (step 2), or tick 'Whole screen instead'.")
            return None
        if self.reveal.get() and not self.reveal_pos:
            messagebox.showerror("PDF Page Capture", "Click 'Set spot' for the reveal click, or untick it.")
            return None
        if not self.out_dir.get().strip():
            messagebox.showerror("PDF Page Capture", "Choose a folder to save to.")
            return None
        return opts

    def _start(self) -> None:
        opts = self._read_options()
        if opts is None:
            return
        self._save_settings()
        out = Path(self.out_dir.get().strip()).expanduser()
        if out.exists() and any(out.glob("page_*.png")):
            if not messagebox.askyesno(
                    "PDF Page Capture",
                    f"{out} already has captured pages. They will be overwritten. Continue?"):
                return

        kwargs = dict(
            out=out,
            next_pos=self.next_pos if self.mode.get() == "click" else None,
            key=self.key.get() if self.mode.get() == "key" else None,
            region=None if self.full_screen.get() else self.region,
            reveal_pos=self.reveal_pos if self.reveal.get() else None,
            park_mouse=self.park_mouse.get(),
            make_pdf=self.make_pdf.get(),
            log=self.log_queue.put,
            stop_event=self.stop_event,
            **opts,
        )
        self.stop_event.clear()
        self.saved_count = 0
        self._set_busy(True)
        self.stop_btn.configure(state="normal")
        self._log(f"Starting in {START_WAIT} seconds. Click on the PDF viewer if it isn't in front.")
        self.root.iconify()
        self.root.after(START_WAIT * 1000, self._launch, kwargs)
        self.root.after(100, self._poll)

    def _launch(self, kwargs: dict) -> None:
        if self.stop_event.is_set():
            self.log_queue.put("Stopped by user.")
            self.log_queue.put(_DONE)
            return

        def work() -> None:
            try:
                saved = run_capture(**kwargs)
                self.saved_count = len(saved)
            except Exception as e:  # surface errors in the window instead of dying silently
                self.log_queue.put(f"Error: {e}")
            finally:
                self.log_queue.put(_DONE)

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _poll(self) -> None:
        try:
            while True:
                item = self.log_queue.get_nowait()
                if item is _DONE:
                    self._finished()
                    return
                self._log(str(item).strip())
        except queue.Empty:
            pass
        self.root.after(100, self._poll)

    def _finished(self) -> None:
        self.worker = None
        self.stop_btn.configure(state="disabled")
        self._set_busy(False)
        self.root.deiconify()
        self.root.lift()
        if self.saved_count and messagebox.askyesno(
                "PDF Page Capture", f"Done! Saved {self.saved_count} pages.\n\nOpen the folder?"):
            self._open_folder()

    def _stop(self) -> None:
        self.stop_event.set()
        self._log("Stopping after the current page...")

    # --- Helpers ------------------------------------------------------------

    def _log(self, msg: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _browse(self) -> None:
        folder = filedialog.askdirectory(initialdir=self.out_dir.get() or str(Path.home()))
        if folder:
            self.out_dir.set(folder)

    def _open_folder(self) -> None:
        folder = Path(self.out_dir.get().strip()).expanduser()
        folder.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])

    def _load_settings(self) -> None:
        try:
            data = json.loads(SETTINGS_FILE.read_text())
        except (OSError, ValueError):
            return
        for name in ("mode", "key", "reveal", "full_screen", "delay", "max_pages",
                     "reveal_delay", "tolerance", "park_mouse", "make_pdf", "out_dir"):
            if name in data:
                try:
                    getattr(self, name).set(data[name])
                except tk.TclError:
                    pass
        for name in ("next_pos", "reveal_pos", "region"):
            if data.get(name):
                setattr(self, name, tuple(data[name]))

    def _save_settings(self) -> None:
        data = {name: getattr(self, name).get() for name in (
            "mode", "key", "reveal", "full_screen", "delay", "max_pages",
            "reveal_delay", "tolerance", "park_mouse", "make_pdf", "out_dir")}
        data.update(next_pos=self.next_pos, reveal_pos=self.reveal_pos, region=self.region)
        try:
            SETTINGS_FILE.write_text(json.dumps(data, indent=2))
        except OSError:
            pass


def main() -> None:
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
