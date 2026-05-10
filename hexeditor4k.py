#!/usr/bin/env python3.14
"""
ac's hex editor0.1
Supports: Atari 2600/7800, NES, SNES, N64, GBA, NDS, Nintendo Switch ROM formats
60 FPS refresh | tkinter GUI | 600x400 window
"""

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog
import struct
import os
import time

# ─── Platform signature database ─────────────────────────────────────────────
PLATFORM_SIGNATURES = {
    # Atari
    "Atari 2600 (2K/4K ROM)": {
        "check": lambda d: len(d) <= 0x1000 and len(d) >= 0x800,
        "extensions": [".bin", ".a26"],
    },
    "Atari 7800": {
        "check": lambda d: d[:2] == b'A7' or d[:7] == b'ATARI7X',
        "extensions": [".a78"],
    },
    # Nintendo
    "NES (iNES)": {
        "check": lambda d: d[:4] == b'\x4E\x45\x53\x1A',
        "extensions": [".nes"],
    },
    "SNES": {
        "check": lambda d: len(d) in [0x200000, 0x400000, 0x80000, 0x100000] or d[:3] == b'SMC',
        "extensions": [".smc", ".sfc"],
    },
    "Game Boy": {
        "check": lambda d: d[0x104:0x107] in [b'\xCE\xED\x66\x66', b'\xC3\x00\xC3'],
        "extensions": [".gb", ".gbc"],
    },
    "GBA": {
        "check": lambda d: d[0xB2:0xBC] == b'\x96' * 1 or len(d) > 0x200 and d[0x4:0x8] == b'\x24\xAE\x51\x24' or True,
        "extensions": [".gba"],
    },
    "Nintendo 64": {
        "check": lambda d: d[:4] in [b'\x80\x37\x12\x40', b'\x37\x80\x40\x12'],
        "extensions": [".n64", ".z64", ".v64"],
    },
    "Nintendo DS": {
        "check": lambda d: d[:4] == b'\xAC\x84\x24\xFF' or d[:4] == b'\xCF\x56\x23\xBE',
        "extensions": [".nds"],
    },
    "Nintendo Switch (NSP)": {
        "check": lambda d: d[:4] == b'PFS0',
        "extensions": [".nsp"],
    },
    "Nintendo Switch (XCI)": {
        "check": lambda d: d[:4] == b'HEAD',
        "extensions": [".xci"],
    },
    "Nintendo Switch (NCA)": {
        "check": lambda d: len(d) >= 0x200 and d[0x200:0x204] == b'NCA3' or d[0x200:0x204] == b'NCA2',
        "extensions": [".nca"],
    },
    "Nintendo Switch (NSO)": {
        "check": lambda d: d[:4] == b'NSO0',
        "extensions": [".nso"],
    },
    "GameCube / Wii": {
        "check": lambda d: d[:4] == b'\xC2\x33\x9F\x3D' or d[:4] == b'\x5D\x1C\x9E\xA3',
        "extensions": [".iso", ".gcm"],
    },
    "Atari Jaguar": {
        "check": lambda d: len(d) >= 0x2000 and d[:3] == b'Jag',
        "extensions": [".jag", ".j64"],
    },
}


class HexEditor:
    """Main hex editor application."""

    # ── Colour / layout constants ────────────────────────────────────────
    BG           = "#0a0a0a"
    TEXT_BLUE    = "#00ccff"
    TEXT_ASCII   = "#4488ff"
    TEXT_OFFSET  = "#ff8800"
    TEXT_INFO    = "#00ff88"
    BTN_BG       = "#000000"
    BTN_FG       = "#0066ff"
    HIGHLIGHT_BG = "#1a1a3a"
    CURSOR_BG    = "#003388"
    SELECTED_BG  = "#003355"
    GRID_COLOR   = "#111122"
    FONT_HEX     = ("Consolas", 10)
    FONT_ASCII   = ("Consolas", 10)
    FONT_OFFSET  = ("Consolas", 10, "bold")
    FONT_BTN     = ("Consolas", 9, "bold")
    BYTES_PER_ROW = 16
    FPS           = 60

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("ac's hex editor0.1")
        self.root.geometry("600x400")
        self.root.resizable(True, True)
        self.root.configure(bg=self.BG)

        # ── Data ─────────────────────────────────────────────────────────
        self.data: bytearray = bytearray()
        self.filepath: str | None = None
        self.offset: int = 0
        self.cursor_pos: int = 0
        self.selected_start: int | None = None
        self.selected_end: int | None = None
        self.mode: str = "hex"  # "hex" or "ascii"
        self.nibble_high: bool = True  # high nibble active when editing
        self.search_matches: list[int] = []
        self.platform: str = "Unknown"
        self.edit_history: list[bytearray] = []
        self.modified: bool = False

        self._build_ui()
        self._bind_keys()
        self._tick()

    # ── UI Construction ──────────────────────────────────────────────────
    def _build_ui(self):
        # ─── Toolbar ─────────────────────────────────────────────────────
        toolbar = tk.Frame(self.root, bg=self.BTN_BG, bd=1, relief=tk.RAISED)
        toolbar.pack(fill=tk.X, side=tk.TOP)

        btn_defs = [
            ("Open",       self.open_file),
            ("Save",       self.save_file),
            ("Save As",    self.save_file_as),
            ("Go To",      self.goto_offset),
            ("Find",       self.find_bytes),
            ("Find Next",  self.find_next),
            ("Undo",       self.undo),
            ("Fill",       self.fill_range),
            ("Export",     self.export_selection),
            ("Info",       self.show_info),
        ]
        for label, cmd in btn_defs:
            b = tk.Button(
                toolbar, text=label, command=cmd,
                bg=self.BTN_BG, fg=self.BTN_FG,
                activebackground="#001144", activeforeground="#44aaff",
                font=self.FONT_BTN, bd=1, relief=tk.RIDGE, padx=4, pady=1,
            )
            b.pack(side=tk.LEFT, padx=1, pady=2)

        # ─── Status bar ──────────────────────────────────────────────────
        self.status_var = tk.StringVar(value="No file loaded")
        status_bar = tk.Label(
            self.root, textvariable=self.status_var,
            bg=self.BTN_BG, fg=self.TEXT_INFO,
            font=("Consolas", 9), anchor=tk.W, padx=6,
        )
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # ─── Platform label ──────────────────────────────────────────────
        self.platform_var = tk.StringVar(value="Platform: ---")
        platform_bar = tk.Label(
            self.root, textvariable=self.platform_var,
            bg=self.BTN_BG, fg="#ffcc00",
            font=("Consolas", 9, "bold"), anchor=tk.W, padx=6,
        )
        platform_bar.pack(fill=tk.X, side=tk.BOTTOM)

        # ─── Hex canvas ──────────────────────────────────────────────────
        canvas_frame = tk.Frame(self.root, bg=self.BG)
        canvas_frame.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(
            canvas_frame, bg=self.BG, highlightthickness=0,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # ─── Scrollbar ───────────────────────────────────────────────────
        self.scrollbar = tk.Scrollbar(
            self.root, orient=tk.VERTICAL, command=self._on_scroll,
            bg=self.BTN_BG, troughcolor=self.BG,
        )
        self.scrollbar.pack(fill=tk.Y, side=tk.RIGHT)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        # ─── Scroll bar (horizontal) ─────────────────────────────────────
        self.hscrollbar = tk.Scrollbar(
            self.root, orient=tk.HORIZONTAL, command=self._on_hscroll,
            bg=self.BTN_BG, troughcolor=self.BG,
        )
        # not packing by default, only if needed

    # ── Key bindings ─────────────────────────────────────────────────────
    def _bind_keys(self):
        self.root.bind("<Control-o>", lambda e: self.open_file())
        self.root.bind("<Control-s>", lambda e: self.save_file())
        self.root.bind("<Control-g>", lambda e: self.goto_offset())
        self.root.bind("<Control-f>", lambda e: self.find_bytes())
        self.root.bind("<F3>",        lambda e: self.find_next())
        self.root.bind("<Control-z>", lambda e: self.undo())
        self.root.bind("<Up>",        lambda e: self._move_cursor(-16))
        self.root.bind("<Down>",      lambda e: self._move_cursor(16))
        self.root.bind("<Left>",      lambda e: self._move_cursor(-1))
        self.root.bind("<Right>",     lambda e: self._move_cursor(1))
        self.root.bind("<Prior>",     lambda e: self._page_up())
        self.root.bind("<Next>",      lambda e: self._page_down())
        self.root.bind("<Home>",      lambda e: self._home())
        self.root.bind("<End>",       lambda e: self._end())
        self.root.bind("<Tab>",       lambda e: self._toggle_mode())
        self.root.bind("<Escape>",    lambda e: self._clear_selection())
        self.canvas.bind("<Button-1>", self._on_click)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", lambda e: self._scroll_up())
        self.canvas.bind("<Button-5>", lambda e: self._scroll_down())
        self.root.bind("<Key>", self._on_key)

    # ── 60 FPS render loop ───────────────────────────────────────────────
    def _tick(self):
        self._render()
        self.root.after(1000 // self.FPS, self._tick)

    # ── Rendering ────────────────────────────────────────────────────────
    def _render(self):
        self.canvas.delete("all")
        if not self.data:
            self.canvas.create_text(
                300, 180, text="ac's hex editor0.1\n\nCtrl+O to open a file",
                fill=self.TEXT_BLUE, font=("Consolas", 14), justify=tk.CENTER,
            )
            return

        w = self.canvas.winfo_width()
        h = self.canvas.winfo_height()
        if w < 10 or h < 10:
            return

        bpr = self.BYTES_PER_ROW
        row_h = 18
        total_rows = (len(self.data) + bpr - 1) // bpr

        # Compute visible rows
        visible_rows = h // row_h + 1
        start_row = self.offset // bpr
        end_row = min(start_row + visible_rows + 1, total_rows)

        # Update scrollbar
        if total_rows > 0:
            self.scrollbar.set(
                start_row / total_rows,
                min((start_row + visible_rows) / total_rows, 1.0),
            )

        # Column positions
        x_offset = 8
        x_hex = 80
        x_ascii = x_hex + bpr * 29 + 16
        y = 4

        for row in range(start_row, end_row):
            addr = row * bpr
            # Offset label
            self.canvas.create_text(
                x_offset, y, text=f"{addr:08X}", fill=self.TEXT_OFFSET,
                font=self.FONT_OFFSET, anchor=tk.NW,
            )

            # Hex bytes
            for col in range(bpr):
                pos = addr + col
                if pos >= len(self.data):
                    break

                byte = self.data[pos]
                hex_str = f"{byte:02X}"

                # Determine colour / background
                fg = self.TEXT_BLUE
                bg = None

                # Selection highlight
                if self.selected_start is not None and self.selected_end is not None:
                    sel_lo = min(self.selected_start, self.selected_end)
                    sel_hi = max(self.selected_start, self.selected_end)
                    if sel_lo <= pos <= sel_hi:
                        bg = self.SELECTED_BG

                # Search match highlight
                if pos in self.search_matches:
                    bg = "#2a1a00"
                    fg = "#ffcc00"

                # Cursor
                if pos == self.cursor_pos:
                    bg = self.CURSOR_BG
                    fg = "#ffffff"
                    if self.mode == "hex" and not self.nibble_high:
                        # Dim high nibble to show low-nibble editing
                        pass

                bx = x_hex + col * 29
                if bg:
                    self.canvas.create_rectangle(
                        bx - 2, y, bx + 23, y + row_h - 2,
                        fill=bg, outline="",
                    )
                self.canvas.create_text(
                    bx, y, text=hex_str, fill=fg,
                    font=self.FONT_HEX, anchor=tk.NW,
                )

            # ASCII column
            for col in range(bpr):
                pos = addr + col
                if pos >= len(self.data):
                    break

                byte = self.data[pos]
                ch = chr(byte) if 0x20 <= byte < 0x7F else "."

                fg = self.TEXT_ASCII
                bg = None

                if self.selected_start is not None and self.selected_end is not None:
                    sel_lo = min(self.selected_start, self.selected_end)
                    sel_hi = max(self.selected_start, self.selected_end)
                    if sel_lo <= pos <= sel_hi:
                        bg = self.SELECTED_BG

                if pos in self.search_matches:
                    bg = "#2a1a00"
                    fg = "#ffcc00"

                if pos == self.cursor_pos:
                    bg = self.CURSOR_BG
                    fg = "#ffffff"

                ax = x_ascii + col * 9
                if bg:
                    self.canvas.create_rectangle(
                        ax - 1, y, ax + 8, y + row_h - 2,
                        fill=bg, outline="",
                    )
                self.canvas.create_text(
                    ax, y, text=ch, fill=fg,
                    font=self.FONT_ASCII, anchor=tk.NW,
                )

            y += row_h

        # ─── Update status ───────────────────────────────────────────────
        self._update_status()

    # ── Status ───────────────────────────────────────────────────────────
    def _update_status(self):
        pos = self.cursor_pos
        if self.data and pos < len(self.data):
            b = self.data[pos]
            signed = b if b < 128 else b - 256
            sel_info = ""
            if self.selected_start is not None and self.selected_end is not None:
                lo = min(self.selected_start, self.selected_end)
                hi = max(self.selected_start, self.selected_end)
                sel_info = f" | Sel: {lo:08X}-{hi:08X} ({hi-lo+1} bytes)"
            self.status_var.set(
                f"Offset: {pos:08X}  |  "
                f"Hex: {b:02X}  Dec: {b}  Signed: {signed}  "
                f"Bin: {b:08b}  Char: {chr(b) if 0x20<=b<0x7F else '.'}  "
                f"Mode: {self.mode.upper()}"
                f"{sel_info}  |  "
                f"Size: {len(self.data):,} bytes"
                f"{'  [MODIFIED]' if self.modified else ''}"
            )
        else:
            self.status_var.set("No file loaded")

    # ── File operations ──────────────────────────────────────────────────
    def open_file(self):
        ftypes = [
            ("All files", "*.*"),
            ("Atari 2600", "*.bin *.a26"),
            ("Atari 7800", "*.a78"),
            ("NES ROM", "*.nes"),
            ("SNES ROM", "*.smc *.sfc"),
            ("Game Boy", "*.gb *.gbc"),
            ("GBA ROM", "*.gba"),
            ("N64 ROM", "*.n64 *.z64 *.v64"),
            ("NDS ROM", "*.nds"),
            ("Switch NSP", "*.nsp"),
            ("Switch XCI", "*.xci"),
            ("Switch NCA", "*.nca"),
            ("Switch NSO", "*.nso"),
            ("GameCube/Wii", "*.iso *.gcm"),
            ("Binary", "*.bin *.dat"),
        ]
        path = filedialog.askopenfilename(filetypes=ftypes)
        if not path:
            return
        try:
            with open(path, "rb") as f:
                self.data = bytearray(f.read())
            self.filepath = path
            self.offset = 0
            self.cursor_pos = 0
            self.selected_start = None
            self.selected_end = None
            self.search_matches = []
            self.edit_history = [bytearray(self.data)]
            self.modified = False
            self._detect_platform()
            messagebox.showinfo(
                "File Loaded",
                f"Loaded: {os.path.basename(path)}\n"
                f"Size: {len(self.data):,} bytes\n"
                f"Platform: {self.platform}",
            )
        except Exception as e:
            messagebox.showerror("Error", f"Cannot open file:\n{e}")

    def save_file(self):
        if not self.filepath:
            self.save_file_as()
            return
        try:
            with open(self.filepath, "wb") as f:
                f.write(self.data)
            self.modified = False
        except Exception as e:
            messagebox.showerror("Error", f"Cannot save:\n{e}")

    def save_file_as(self):
        if not self.data:
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".bin",
            filetypes=[("All files", "*.*"), ("Binary", "*.bin")],
        )
        if path:
            self.filepath = path
            self.save_file()

    # ── Platform detection ───────────────────────────────────────────────
    def _detect_platform(self):
        if not self.data:
            self.platform = "Unknown"
            self.platform_var.set("Platform: ---")
            return

        # Try by header signature first
        for name, sig in PLATFORM_SIGNATURES.items():
            try:
                if sig["check"](self.data):
                    self.platform = name
                    self.platform_var.set(f"Platform: {name}")
                    return
            except (IndexError, ValueError):
                continue

        # Fallback: try by extension
        if self.filepath:
            ext = os.path.splitext(self.filepath)[1].lower()
            for name, sig in PLATFORM_SIGNATURES.items():
                if ext in sig["extensions"]:
                    self.platform = f"{name} (by ext)"
                    self.platform_var.set(f"Platform: {self.platform}")
                    return

        self.platform = "Unknown / Raw Binary"
        self.platform_var.set(f"Platform: {self.platform}")

    # ── Navigation ───────────────────────────────────────────────────────
    def _move_cursor(self, delta: int):
        if not self.data:
            return
        self.cursor_pos = max(0, min(self.cursor_pos + delta, len(self.data) - 1))
        self.nibble_high = True
        self._ensure_cursor_visible()

    def _ensure_cursor_visible(self):
        bpr = self.BYTES_PER_ROW
        row = self.cursor_pos // bpr
        vis_start = self.offset // bpr
        vis_rows = max(self.canvas.winfo_height() // 18 - 1, 1)
        vis_end = vis_start + vis_rows
        if row < vis_start:
            self.offset = row * bpr
        elif row >= vis_end:
            self.offset = (row - vis_rows + 2) * bpr

    def _page_up(self):
        bpr = self.BYTES_PER_ROW
        vis_rows = max(self.canvas.winfo_height() // 18 - 1, 1)
        self.offset = max(0, self.offset - vis_rows * bpr)
        self._move_cursor(-vis_rows * bpr)

    def _page_down(self):
        bpr = self.BYTES_PER_ROW
        vis_rows = max(self.canvas.winfo_height() // 18 - 1, 1)
        self.offset = min(len(self.data) - 1, self.offset + vis_rows * bpr)
        self._move_cursor(vis_rows * bpr)

    def _home(self):
        self.cursor_pos = 0
        self.offset = 0
        self.nibble_high = True

    def _end(self):
        if self.data:
            self.cursor_pos = len(self.data) - 1
            self.nibble_high = True
            self._ensure_cursor_visible()

    def _toggle_mode(self):
        self.mode = "ascii" if self.mode == "hex" else "hex"
        self.nibble_high = True

    def _clear_selection(self):
        self.selected_start = None
        self.selected_end = None
        self.search_matches = []

    # ── Scroll handling ──────────────────────────────────────────────────
    def _on_scroll(self, action, value, *args):
        bpr = self.BYTES_PER_ROW
        if action == "moveto":
            total = (len(self.data) + bpr - 1) // bpr
            row = int(float(value) * total)
            self.offset = max(0, row * bpr)
        elif action == "scroll":
            delta = int(value) * bpr * 3
            self.offset = max(0, min(len(self.data) - 1, self.offset + delta))

    def _on_hscroll(self, *args):
        pass

    def _on_mousewheel(self, event):
        if event.delta > 0:
            self._scroll_up()
        else:
            self._scroll_down()

    def _scroll_up(self):
        bpr = self.BYTES_PER_ROW
        self.offset = max(0, self.offset - bpr * 3)

    def _scroll_down(self):
        bpr = self.BYTES_PER_ROW
        if self.data:
            self.offset = min(len(self.data) - 1, self.offset + bpr * 3)

    # ── Mouse interaction ────────────────────────────────────────────────
    def _on_click(self, event):
        if not self.data:
            return
        pos = self._canvas_to_pos(event.x, event.y)
        if pos is not None:
            self.cursor_pos = pos
            self.nibble_high = True
            self.selected_start = pos
            self.selected_end = pos

    def _on_drag(self, event):
        if not self.data:
            return
        pos = self._canvas_to_pos(event.x, event.y)
        if pos is not None:
            self.selected_end = pos
            self.cursor_pos = pos
            self._ensure_cursor_visible()

    def _canvas_to_pos(self, x, y) -> int | None:
        bpr = self.BYTES_PER_ROW
        row_h = 18
        x_hex = 80
        x_ascii = x_hex + bpr * 29 + 16

        row_idx = (y - 4) // row_h
        addr = (self.offset // bpr + row_idx) * bpr
        if addr < 0 or addr >= len(self.data):
            return None

        if x >= x_ascii:
            col = int((x - x_ascii) / 9)
            col = max(0, min(col, bpr - 1))
        elif x >= x_hex:
            col = int((x - x_hex) / 29)
            col = max(0, min(col, bpr - 1))
        else:
            col = 0

        pos = addr + col
        return max(0, min(pos, len(self.data) - 1))

    # ── Keyboard editing ─────────────────────────────────────────────────
    def _on_key(self, event):
        if not self.data or self.cursor_pos >= len(self.data):
            return

        if self.mode == "hex":
            self._hex_key(event)
        else:
            self._ascii_key(event)

    def _hex_key(self, event):
        ch = event.char.upper()
        if ch in "0123456789ABCDEF":
            nibble = int(ch, 16)
            self._push_history()
            if self.nibble_high:
                old = self.data[self.cursor_pos]
                self.data[self.cursor_pos] = (old & 0x0F) | (nibble << 4)
                self.nibble_high = False
            else:
                old = self.data[self.cursor_pos]
                self.data[self.cursor_pos] = (old & 0xF0) | nibble
                self.nibble_high = True
                self._move_cursor(1)
            self.modified = True

    def _ascii_key(self, event):
        if event.char and len(event.char) == 1 and ord(event.char) >= 0x20:
            self._push_history()
            self.data[self.cursor_pos] = ord(event.char)
            self._move_cursor(1)
            self.modified = True

    # ── Edit history ─────────────────────────────────────────────────────
    def _push_history(self):
        if len(self.edit_history) > 200:
            self.edit_history = self.edit_history[-100:]
        self.edit_history.append(bytearray(self.data))

    def undo(self):
        if len(self.edit_history) > 1:
            self.edit_history.pop()
            self.data = bytearray(self.edit_history[-1])
            self.modified = True

    # ── Tools ────────────────────────────────────────────────────────────
    def goto_offset(self):
        if not self.data:
            return
        result = simpledialog.askstring(
            "Go To Offset", "Enter hex offset:",
            parent=self.root,
        )
        if result:
            try:
                addr = int(result, 16)
                addr = max(0, min(addr, len(self.data) - 1))
                self.cursor_pos = addr
                self.offset = max(0, (addr // self.BYTES_PER_ROW - 5) * self.BYTES_PER_ROW)
                self.nibble_high = True
            except ValueError:
                messagebox.showerror("Error", "Invalid hex offset.")

    def find_bytes(self):
        if not self.data:
            return
        result = simpledialog.askstring(
            "Find", "Enter hex bytes (e.g. 4E45531A) or ASCII string:",
            parent=self.root,
        )
        if not result:
            return
        try:
            # Try hex interpretation first
            needle = bytes.fromhex(result.replace(" ", ""))
        except ValueError:
            needle = result.encode("ascii", errors="replace")

        self.search_matches = []
        start = 0
        while True:
            idx = self.data.find(needle, start)
            if idx == -1:
                break
            for i in range(len(needle)):
                self.search_matches.append(idx + i)
            start = idx + 1

        if self.search_matches:
            self.cursor_pos = self.search_matches[0]
            self._ensure_cursor_visible()
            messagebox.showinfo("Find", f"Found {len(self.search_matches) // len(needle)} match(es).")
        else:
            messagebox.showinfo("Find", "No matches found.")

    def find_next(self):
        if not self.search_matches or not self.data:
            self.find_bytes()
            return
        # Find next match block after cursor
        needle_len = 1
        for m in sorted(self.search_matches):
            if m > self.cursor_pos:
                self.cursor_pos = m
                self._ensure_cursor_visible()
                return
        # Wrap around
        self.cursor_pos = self.search_matches[0]
        self._ensure_cursor_visible()

    def fill_range(self):
        if not self.data:
            return
        if self.selected_start is None or self.selected_end is None:
            messagebox.showinfo("Fill", "Select a range first (click & drag).")
            return
        lo = min(self.selected_start, self.selected_end)
        hi = max(self.selected_start, self.selected_end)
        result = simpledialog.askstring(
            "Fill", f"Fill {lo:08X}-{hi:08X} with hex byte:",
            parent=self.root,
        )
        if result:
            try:
                fill_byte = int(result, 16) & 0xFF
                self._push_history()
                for i in range(lo, hi + 1):
                    self.data[i] = fill_byte
                self.modified = True
            except ValueError:
                messagebox.showerror("Error", "Invalid hex byte.")

    def export_selection(self):
        if not self.data or self.selected_start is None or self.selected_end is None:
            messagebox.showinfo("Export", "Select a range first.")
            return
        lo = min(self.selected_start, self.selected_end)
        hi = max(self.selected_start, self.selected_end)
        path = filedialog.asksaveasfilename(
            defaultextension=".bin",
            filetypes=[("Binary", "*.bin"), ("All", "*.*")],
        )
        if path:
            with open(path, "wb") as f:
                f.write(self.data[lo:hi + 1])
            messagebox.showinfo("Export", f"Exported {hi - lo + 1} bytes.")

    def show_info(self):
        if not self.data:
            return
        info = (
            f"═══ ac's hex editor0.1 ═══\n\n"
            f"File: {os.path.basename(self.filepath) if self.filepath else 'N/A'}\n"
            f"Path: {self.filepath or 'N/A'}\n"
            f"Size: {len(self.data):,} bytes ({len(self.data):#x})\n"
            f"Platform: {self.platform}\n\n"
            f"── Header (first 64 bytes) ──\n"
        )
        for row in range(4):
            addr = row * 16
            hex_part = " ".join(f"{self.data[addr+i]:02X}" for i in range(16) if addr + i < len(self.data))
            ascii_part = "".join(chr(self.data[addr+i]) if 0x20 <= self.data[addr+i] < 0x7F else "." for i in range(16) if addr + i < len(self.data))
            info += f"{addr:08X}  {hex_part:<48s}  {ascii_part}\n"

        # Checksums
        s = sum(self.data) & 0xFFFFFFFF
        info += f"\nSimple checksum: {s:08X}"
        messagebox.showinfo("File Info", info)


# ─── Entry point ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    root = tk.Tk()
    app = HexEditor(root)
    root.mainloop()
