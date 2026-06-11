# canvas.py  – BreadboardCanvas widget: drawing + all mouse interaction
from __future__ import annotations

import tkinter as tk
from tkinter import colorchooser
from typing import Callable, Dict, List, Optional, Tuple

from constants import *
from model import BoardState, PlacedComponent, Wire, CP, hole_cp, rail_cp, pin_cp


# ── Colour utilities ───────────────────────────────────────────────────────────

def contrast_color(hex_color: str) -> str:
    """Return '#000000' or '#FFFFFF' whichever contrasts better with hex_color."""
    h = hex_color.lstrip('#')
    if len(h) < 6:
        return '#000000'
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    luminance = 0.299 * r + 0.587 * g + 0.114 * b
    return '#FFFFFF' if luminance < 140 else '#000000'


def _label_color_for(bg_hex: str) -> str:
    """Alias kept for clarity – same as contrast_color."""
    return contrast_color(bg_hex)


# ── Layout ─────────────────────────────────────────────────────────────────────

class Layout:
    """
    Translates logical board positions to canvas pixel coordinates.
    All output values are screen-space pixels that incorporate zoom and the
    current board-origin offset (board_ox, board_oy).

    Rail layout (left to right):
      [board_ox]
        [−left]  [+left]  [row_label]  [a…e  gap  f…j]  [row_label]  [+right]  [−right]
      [board_right]
    """

    def __init__(self, num_rows: int, rails_visible: Dict[str, bool],
                 zoom: float = 1.0,
                 board_ox: float = 80.0, board_oy: float = 50.0):
        self.num_rows       = num_rows
        self.rails_visible  = dict(rails_visible)
        self.zoom           = zoom
        self.board_ox       = board_ox
        self.board_oy       = board_oy
        self._recompute()

    def update(self, num_rows: int, rails_visible: Dict[str, bool],
               zoom: float = None, board_ox: float = None,
               board_oy: float = None) -> None:
        self.num_rows      = num_rows
        self.rails_visible = dict(rails_visible)
        if zoom     is not None: self.zoom     = zoom
        if board_ox is not None: self.board_ox = board_ox
        if board_oy is not None: self.board_oy = board_oy
        self._recompute()

    def _recompute(self) -> None:
        z  = self.zoom
        hs = HOLE_SPACING * z        # scaled hole spacing
        bx = self.board_ox
        by = self.board_oy

        # ── X positions (left → right) ────────────────────────────────────────
        # Left rails: minus (outer) then plus (inner)
        self._left_minus_x      = bx + hs * 0.5
        self._left_plus_x       = bx + hs * 1.5

        # Row-label column between left-plus rail and col 'a'
        self._row_label_left_x  = bx + hs * 2.0 + RAIL_TO_GRID_GAP * z + ROW_LABEL_W * z * 0.5

        # Main grid: col 'a' starts here
        self.grid_x0            = bx + hs * 2.0 + RAIL_TO_GRID_GAP * z + ROW_LABEL_W * z

        # Right side mirrors left
        grid_right              = self.grid_x0 + 11 * hs   # centre of col 'j'
        self._row_label_right_x = grid_right + ROW_LABEL_W * z * 0.5
        self._right_plus_x      = grid_right + ROW_LABEL_W * z + RAIL_TO_GRID_GAP * z + hs * 0.5
        self._right_minus_x     = self._right_plus_x + hs

        self.board_left         = bx
        self.board_right        = self._right_minus_x + hs * 0.5

        # ── Y positions ───────────────────────────────────────────────────────
        self.board_top          = by
        self.grid_y0            = by + COL_LABEL_H * z + hs * 0.4
        self.board_bottom       = self.grid_y0 + (self.num_rows - 1) * hs + hs * 0.5

        # Convenience cache
        self._hs = hs
        self._hr = max(1.5, HOLE_RADIUS * z)   # scaled hole radius

    # ── Coordinate helpers ────────────────────────────────────────────────────

    def hole_xy(self, row: int, col: str) -> Tuple[float, float]:
        hs = self._hs
        return (self.grid_x0 + COL_X_IDX[col] * hs,
                self.grid_y0  + (row - 1) * hs)

    def rail_xy(self, rail_id: str, idx: int) -> Tuple[float, float]:
        """idx is 0-based row index (0 = row 1 of the main grid)."""
        y = self.grid_y0 + idx * self._hs
        x = {
            RAIL_LEFT_MINUS:  self._left_minus_x,
            RAIL_LEFT_PLUS:   self._left_plus_x,
            RAIL_RIGHT_PLUS:  self._right_plus_x,
            RAIL_RIGHT_MINUS: self._right_minus_x,
        }.get(rail_id, 0)
        return x, y

    def nearest_hole(self, px: float, py: float,
                     occupied: Dict = None) -> Optional[Tuple[int, str]]:
        hs      = self._hs
        snap_r  = hs * 0.65

        # 1. Row math - snap directly to closest row
        row = round((py - self.grid_y0) / hs) + 1
        if not (1 <= row <= self.num_rows):
            return None

        cy = self.grid_y0 + (row - 1) * hs
        dy = cy - py
        if abs(dy) > snap_r:
            return None

        best_d  = snap_r
        best    = None
        # 2. Check 10 columns only
        for col in ALL_COLS:
            cx = self.grid_x0 + COL_X_IDX[col] * hs
            dx = cx - px
            d  = (dx * dx + dy * dy) ** 0.5
            if d < best_d:
                best_d = d
                best   = (row, col)
        return best

    def nearest_rail_hole(self, px: float, py: float
                          ) -> Optional[Tuple[str, int]]:
        hs     = self._hs
        snap_r = hs * 0.65
        x_map  = {
            RAIL_LEFT_MINUS:  self._left_minus_x,
            RAIL_LEFT_PLUS:   self._left_plus_x,
            RAIL_RIGHT_PLUS:  self._right_plus_x,
            RAIL_RIGHT_MINUS: self._right_minus_x,
        }

        # 1. Row index math
        idx = round((py - self.grid_y0) / hs)
        if not (0 <= idx < self.num_rows):
            return None

        ry = self.grid_y0 + idx * hs
        dy = ry - py
        if abs(dy) > snap_r:
            return None

        best_d = snap_r
        best   = None
        for rail_id, rx in x_map.items():
            if not self.rails_visible.get(rail_id, True):
                continue
            dx = rx - px
            d  = (dx * dx + dy * dy) ** 0.5
            if d < best_d:
                best_d = d
                best   = (rail_id, idx)
        return best

    def board_hit(self, px: float, py: float) -> bool:
        return (self.board_left <= px <= self.board_right and
                self.board_top  <= py <= self.board_bottom)

    # ── World ↔ screen coordinate helpers ────────────────────────────────────

    def to_screen(self, wx: float, wy: float) -> Tuple[float, float]:
        """Convert world-space coords to canvas screen coords (zoom + pan)."""
        return (self.board_ox + wx * self.zoom,
                self.board_oy + wy * self.zoom)

    def to_world(self, sx: float, sy: float) -> Tuple[float, float]:
        """Convert canvas screen coords back to world-space coords."""
        return ((sx - self.board_ox) / self.zoom,
                (sy - self.board_oy) / self.zoom)

    def offboard_default_world_x(self) -> float:
        """World-space x for the default off-board placement zone."""
        board_right_world = (self.board_right - self.board_ox) / self.zoom
        return board_right_world + OFFBOARD_ZONE_X_PAD


# ═══════════════════════════════════════════════════════════════════════════════
#  BreadboardCanvas
# ═══════════════════════════════════════════════════════════════════════════════

class BreadboardCanvas(tk.Frame):
    """
    The main scrollable canvas.  All drawing and user interaction lives here.
    """

    def __init__(self, parent, state: BoardState,
                 on_status: Callable[[str], None] = None,
                 on_change: Callable[[], None] = None, **kw):
        super().__init__(parent, **kw)
        self.state     = state
        self.on_status = on_status or (lambda s: None)
        self.on_change = on_change or (lambda: None)

        # Zoom & board position
        self._zoom      = 1.0
        self._board_ox  = 100.0
        self._board_oy  = 60.0
        self._initialized = False

        # Interaction state
        self._mode:               str  = MODE_SELECT
        self._placing_def                = None
        self._wire_start: Optional[CP]   = None
        self._wire_color: str            = C_WIRE_PALETTE[0]
        self._wire_color_idx: int        = 0
        self._drag_comp: Optional[str]   = None
        self._drag_off:  Tuple           = (0.0, 0.0)
        self._selected_comp: Optional[str] = None
        self._selected_wire: Optional[str] = None

        # Board-pan drag state  (MODE_PAN)
        self._pan_anchor: Optional[Tuple] = None   # (cx, cy, board_ox, board_oy)

        # Viewport-pan via middle-click
        self._vp_anchor: Optional[Tuple]  = None   # (ex, ey, xview, yview)

        self.layout = Layout(state.num_rows, state.rails_visible,
                             zoom=self._zoom,
                             board_ox=self._board_ox, board_oy=self._board_oy)

        self._build_widgets()
        self._bind_events()

    # ── Widget construction ───────────────────────────────────────────────────

    def _build_widgets(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        self._canvas = tk.Canvas(
            self, bg=C_CANVAS_BG,
            scrollregion=(0, 0, 2400, 1600),
        )
        vsb = tk.Scrollbar(self, orient=tk.VERTICAL,   command=self._canvas.yview)
        hsb = tk.Scrollbar(self, orient=tk.HORIZONTAL, command=self._canvas.xview)
        self._canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self._canvas.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")

    def _bind_events(self) -> None:
        c = self._canvas
        c.bind("<ButtonPress-1>",   self._on_left_press)
        c.bind("<B1-Motion>",       self._on_left_drag)
        c.bind("<ButtonRelease-1>", self._on_left_release)
        c.bind("<Motion>",          self._on_motion)
        c.bind("<Button-3>",        self._on_right_click)
        c.bind("<Escape>",          self._on_escape)
        c.bind("<Delete>",          self._on_delete_key)
        c.bind("<Key-r>",           self._on_rotate_key)
        c.bind("<Key-R>",           self._on_rotate_key)
        c.bind("<space>",           self._on_rotate_key)
        # Ctrl+scroll → zoom
        c.bind("<Control-MouseWheel>", self._on_zoom_scroll)
        c.bind("<Control-Button-4>",   self._on_zoom_scroll)
        c.bind("<Control-Button-5>",   self._on_zoom_scroll)
        # Plain scroll → viewport pan
        c.bind("<MouseWheel>",         self._on_scroll_y)
        c.bind("<Shift-MouseWheel>",   self._on_scroll_x)
        c.bind("<Button-4>",           self._on_scroll_y)
        c.bind("<Button-5>",           self._on_scroll_y)
        # Middle-click drag → viewport pan
        c.bind("<ButtonPress-2>",      self._on_vp_pan_start)
        c.bind("<B2-Motion>",          self._on_vp_pan_drag)
        c.bind("<ButtonRelease-2>",    self._on_vp_pan_end)
        c.focus_set()

    # ── Public API ────────────────────────────────────────────────────────────

    def set_mode(self, mode: str, placing_def=None) -> None:
        self._mode        = mode
        self._placing_def = placing_def
        self._placing_rotated = False
        self._wire_start  = None
        self._drag_comp   = None
        cursor_map = {
            MODE_SELECT:  "arrow",
            MODE_PLACE:   "crosshair",
            MODE_WIRE:    "pencil",
            MODE_DELETE:  "X_cursor",
            MODE_DIVIDER: "sb_v_double_arrow",
            MODE_PAN:     "fleur",
        }
        self._canvas.configure(cursor=cursor_map.get(mode, "arrow"))
        if mode not in (MODE_WIRE, MODE_PLACE):
            self._canvas.delete("ghost")
            self._canvas.delete("ghost_wire")
        self.redraw()

    def set_wire_color(self, color: str) -> None:
        self._wire_color = color

    def next_wire_color(self) -> str:
        self._wire_color_idx = (self._wire_color_idx + 1) % len(C_WIRE_PALETTE)
        self._wire_color = C_WIRE_PALETTE[self._wire_color_idx]
        return self._wire_color

    def zoom_in(self) -> None:
        self._apply_zoom(self._zoom * ZOOM_STEP)

    def zoom_out(self) -> None:
        self._apply_zoom(self._zoom / ZOOM_STEP)

    def zoom_reset(self) -> None:
        self._apply_zoom(1.0)

    def _apply_zoom(self, new_zoom: float) -> None:
        self._zoom = max(ZOOM_MIN, min(ZOOM_MAX, new_zoom))
        self.refresh_layout()
        self.on_status(f"Zoom: {self._zoom:.0%}")

    def refresh_layout(self) -> None:
        self.layout.update(self.state.num_rows, self.state.rails_visible,
                           zoom=self._zoom,
                           board_ox=self._board_ox, board_oy=self._board_oy)
        self.redraw(full=True)

    def redraw(self, full: bool = False) -> None:
        if not self._initialized or full:
            self._canvas.delete("all")
            self._draw_board()
            self._initialized = True
        else:
            self._canvas.delete("comp")
            self._canvas.delete("wire")
            self._canvas.delete("pin_dot")
            self._canvas.delete("hole_pin")
            self._canvas.delete("ghost")
            self._canvas.delete("ghost_wire")
            
            # Update grid occupied holes using itemconfig (extremely fast)
            self._canvas.itemconfig("hole", fill=C_HOLE)
            occ = self.state.occupied_holes()
            for row, col in occ:
                self._canvas.itemconfig(f"hole_{row}_{col}", fill=C_HOLE_OCCUPIED)

        self._draw_components()
        self._draw_wires()
        # Update scroll region to encompass everything
        rw = max(self.layout.board_right + 600, 1200)
        rh = max(self.layout.board_bottom + 400, 800)
        for pc in self.state.components:
            if not pc.on_board:
                sx, sy = self.layout.to_screen(pc.x, pc.y)
                rw = max(rw, sx + 400)
                rh = max(rh, sy + 300)
        self._canvas.configure(scrollregion=(0, 0, rw, rh))

    def _label_color(self, tx: float, ty: float) -> str:
        """
        Return the best readable text colour for a label drawn at canvas
        coordinates (tx, ty).  Checks whether that point sits over the
        board surface or the dark workspace canvas.
        """
        if self.layout.board_hit(tx, ty):
            return contrast_color(C_BOARD)      # board is light → dark text
        return contrast_color(C_CANVAS_BG)      # canvas is dark  → light text

    # ── Drawing: board ────────────────────────────────────────────────────────

    def _draw_board(self) -> None:
        c   = self._canvas
        lay = self.layout
        occ = self.state.occupied_holes()
        z   = lay.zoom
        hs  = lay._hs
        hr  = lay._hr

        # Board body fill
        c.create_rectangle(lay.board_left, lay.board_top,
                           lay.board_right, lay.board_bottom,
                           fill=C_BOARD, outline=C_BOARD_BORDER, width=2,
                           tags="bg_board")

        # ── Vertical rail strips ──────────────────────────────────────────────
        rail_x_map = {
            RAIL_LEFT_MINUS:  lay._left_minus_x,
            RAIL_LEFT_PLUS:   lay._left_plus_x,
            RAIL_RIGHT_PLUS:  lay._right_plus_x,
            RAIL_RIGHT_MINUS: lay._right_minus_x,
        }
        for rail_id, rx in rail_x_map.items():
            if not self.state.rails_visible.get(rail_id, True):
                continue
            is_plus = "plus" in rail_id
            bg_col  = C_RAIL_PLUS_BG  if is_plus else C_RAIL_MINUS_BG
            dot_col = C_RAIL_DOT_PLUS if is_plus else C_RAIL_DOT_MINUS
            sym     = "+" if is_plus else "−"

            # Strip background (vertical)
            sy0 = lay.grid_y0 - hs * 0.5
            sy1 = lay.grid_y0 + (lay.num_rows - 1) * hs + hs * 0.5
            c.create_rectangle(rx - hs * 0.42, sy0,
                               rx + hs * 0.42, sy1,
                               fill=bg_col, outline=C_RAIL_BORDER, width=1,
                               tags="rail_bg")

            # + / − label at top (and bottom)
            lbl_font = ("Helvetica", max(7, int(9 * z)), "bold")
            c.create_text(rx, sy0 - hs * 0.5,
                          text=sym, font=lbl_font, fill=dot_col, tags="rail_lbl")
            c.create_text(rx, sy1 + hs * 0.5,
                          text=sym, font=lbl_font, fill=dot_col, tags="rail_lbl")

            # Individual holes
            for idx in range(lay.num_rows):
                rx2, ry = lay.rail_xy(rail_id, idx)
                c.create_oval(rx2 - hr, ry - hr, rx2 + hr, ry + hr,
                              fill=dot_col, outline="",
                              tags=("rail_hole", f"rail_{rail_id}_{idx}"))

            # Dividers within this rail strip
            for dv in sorted(self.state.dividers):
                if 1 <= dv < lay.num_rows:
                    _, yd1 = lay.rail_xy(rail_id, dv - 1)
                    _, yd2 = lay.rail_xy(rail_id, dv)
                    yd = (yd1 + yd2) / 2
                    c.create_line(rx - hs * 0.45, yd, rx + hs * 0.45, yd,
                                  fill=C_DIVIDER, width=max(2, int(2 * z)),
                                  tags="divider_rail")

        # ── Main grid ─────────────────────────────────────────────────────────
        # Central gap dashed line
        gap_x = (lay.hole_xy(1, 'e')[0] + lay.hole_xy(1, 'f')[0]) / 2
        gy0   = lay.grid_y0 - hs * 0.5
        gy1   = lay.grid_y0 + (lay.num_rows - 1) * hs + hs * 0.5
        c.create_line(gap_x, gy0, gap_x, gy1,
                      fill=C_BOARD_BORDER, width=max(1, int(2 * z)),
                      dash=(4, 4), tags="bg_gap")

        # Column labels
        fnt_col = ("Helvetica", max(7, int(8 * z)), "bold")
        for col in ALL_COLS:
            cx, _ = lay.hole_xy(1, col)
            c.create_text(cx, lay.grid_y0 - hs * 0.75,
                          text=col, font=fnt_col, fill="#888888", tags="col_lbl")

        # Row labels + holes
        fnt_row = ("Helvetica", max(5, int(7 * z)))
        for row in range(1, lay.num_rows + 1):
            _, ry = lay.hole_xy(row, 'a')
            c.create_text(lay._row_label_left_x, ry,
                          text=str(row), font=fnt_row, fill="#888888", tags="row_lbl")
            c.create_text(lay._row_label_right_x, ry,
                          text=str(row), font=fnt_row, fill="#888888", tags="row_lbl")

            for col in ALL_COLS:
                cx, cy = lay.hole_xy(row, col)
                fill   = C_HOLE_OCCUPIED if (row, col) in occ else C_HOLE
                c.create_oval(cx - hr, cy - hr, cx + hr, cy + hr,
                              fill=fill, outline="",
                              tags=("hole", f"hole_{row}_{col}"))

        # Main-grid divider lines (horizontal, across all columns)
        for dv in sorted(self.state.dividers):
            if 1 <= dv < lay.num_rows:
                _, yd1 = lay.hole_xy(dv,     'a')
                _, yd2 = lay.hole_xy(dv + 1, 'a')
                yd  = (yd1 + yd2) / 2
                x0d = lay.hole_xy(dv, 'a')[0] - hs * 0.5
                x1d = lay.hole_xy(dv, 'j')[0] + hs * 0.5
                c.create_line(x0d, yd, x1d, yd,
                              fill=C_DIVIDER, width=max(1, int(2 * z)),
                              dash=(6, 3), tags=("divider", f"div_{dv}"))
                c.create_text(x0d - hs * 0.6, yd,
                              text="÷", font=("Helvetica", max(8, int(10 * z)), "bold"),
                              fill=C_DIVIDER_LABEL, tags="divider")

    # ── Drawing: components ───────────────────────────────────────────────────

    def _draw_components(self) -> None:
        for pc in self.state.components:
            if pc.on_board:
                self._draw_onboard_component(pc)
            else:
                self._draw_offboard_component(pc)

    def _draw_onboard_component(self, pc: PlacedComponent) -> None:
        c   = self._canvas
        lay = self.layout
        cd  = pc.comp_def
        z   = lay.zoom
        hs  = lay._hs
        sel = (pc.inst_id == self._selected_comp)
        tc  = contrast_color(cd.color)          # text ON the component fill

        if not cd.is_dip:
            holes = pc.all_occupied_holes()
            if not holes:
                return
            xs = [lay.hole_xy(r, col)[0] for r, col in holes]
            ys = [lay.hole_xy(r, col)[1] for r, col in holes]
            x0 = min(xs) - hs * 0.4;  y0 = min(ys) - hs * 0.4
            x1 = max(xs) + hs * 0.4;  y1 = max(ys) + hs * 0.4
            ow = 3 if sel else 1
            oc = C_SELECTION if sel else C_COMP_OUTLINE
            c.create_rectangle(x0, y0, x1, y1,
                                fill=cd.color, outline=oc, width=ow,
                                tags=("comp", f"comp_{pc.inst_id}"))
            c.create_text((x0 + x1) / 2, (y0 + y1) / 2,
                          text=cd.type_name.split()[0],
                          font=("Helvetica", max(6, int(7 * z))), fill=tc,
                          tags=("comp", f"comp_{pc.inst_id}"))
            # Pin dots + labels – labels float above the hole ON THE BOARD SURFACE
            lbl_fnt = ("Helvetica", max(6, int(7 * z)))
            for i, (label, cp) in enumerate(pc.connection_points()):
                if cp[0] == "hole":
                    hx, hy = lay.hole_xy(cp[1], cp[2])
                    hr = lay._hr
                    c.create_oval(hx - hr - 1, hy - hr - 1,
                                  hx + hr + 1, hy + hr + 1,
                                  fill=C_PIN_DOT, outline=cd.color,
                                  tags=("hole_pin", f"hp_{pc.inst_id}_{i}"))
                    # Label sits above hole on whatever surface is there
                    lty = hy - hs * 0.65
                    ltx = hx
                    c.create_text(ltx, lty, text=label, font=lbl_fnt,
                                  fill=self._label_color(ltx, lty),
                                  tags=("comp", f"comp_{pc.inst_id}"))
        else:
            # ── DIP: straddles the centre gap ─────────────────────────────────
            rotated = getattr(pc, "rotated", False)
            if rotated:
                holes = pc.all_occupied_holes()
                if not holes:
                    return
                xs = [lay.hole_xy(r, col)[0] for r, col in holes]
                ys = [lay.hole_xy(r, col)[1] for r, col in holes]
                pad = hs * 0.45
                bx0, by0 = min(xs) - pad, min(ys) - pad
                bx1, by1 = max(xs) + pad, max(ys) + pad
                mid_x = (bx0 + bx1) / 2
            else:
                n_rows = cd.height_in_rows
                lx, ly = lay.hole_xy(pc.anchor_row, pc.anchor_col)
                rc      = MIRROR_COL[pc.anchor_col]
                rx, _   = lay.hole_xy(pc.anchor_row, rc)
                y1      = lay.hole_xy(pc.anchor_row + n_rows - 1, pc.anchor_col)[1]
                pad     = hs * 0.45
                bx0, by0 = min(lx, rx) - pad, ly - pad
                bx1, by1 = max(lx, rx) + pad, y1 + pad
                mid_x    = (bx0 + bx1) / 2

            ow = 3 if sel else 1
            oc = C_SELECTION if sel else C_COMP_OUTLINE
            c.create_rectangle(bx0, by0, bx1, by1,
                                fill=cd.color, outline=oc, width=ow,
                                tags=("comp", f"comp_{pc.inst_id}"))
            c.create_text(mid_x, (by0 + by1) / 2,
                          text=cd.type_name,
                          font=("Helvetica", max(7, int(8 * z)), "bold"),
                          fill=tc, width=bx1 - bx0 - 8,
                          tags=("comp", f"comp_{pc.inst_id}"))

            # ── Pin-1 gold stripe ─────────────────────────────────────────────
            # Drawn on whichever column pin[0] occupies after flip.
            pin0_hole = pc.pin_holes.get(pc.pin_key(0))
            if pin0_hole and not rotated:
                _, p0_col = pin0_hole
                sw = max(3.0, hs * 0.14)   # stripe width
                if p0_col in LEFT_COLS:
                    c.create_rectangle(bx0, by0, bx0 + sw, by1,
                                       fill="#FFD700", outline="",
                                       tags=("comp", f"comp_{pc.inst_id}"))
                else:
                    c.create_rectangle(bx1 - sw, by0, bx1, by1,
                                       fill="#FFD700", outline="",
                                       tags=("comp", f"comp_{pc.inst_id}"))

            # ── Pin dots + labels ─────────────────────────────────────────────
            lbl_fnt = ("Helvetica", max(6, int(7 * z)))
            left_tx  = bx0 + hs * 0.55    # left-side  labels start here →
            right_tx = bx1 - hs * 0.55    # right-side labels end   here ←
            top_ty    = by0 + hs * 0.55
            bottom_ty = by1 - hs * 0.55

            for i, (label, cp) in enumerate(pc.connection_points()):
                if cp[0] != "hole":
                    continue
                hx, hy = lay.hole_xy(cp[1], cp[2])
                hr = lay._hr
                c.create_oval(hx - hr - 1, hy - hr - 1,
                              hx + hr + 1, hy + hr + 1,
                              fill=C_PIN_DOT, outline=cd.color,
                              tags=("hole_pin", f"hp_{pc.inst_id}_{i}"))
                
                if rotated:
                    if cp[1] == pc.anchor_row:
                        c.create_text(hx, top_ty, text=label, font=lbl_fnt,
                                      fill=tc, anchor="n",
                                      tags=("comp", f"comp_{pc.inst_id}"))
                    else:
                        c.create_text(hx, bottom_ty, text=label, font=lbl_fnt,
                                      fill=tc, anchor="s",
                                      tags=("comp", f"comp_{pc.inst_id}"))
                else:
                    # Choose side based on which column the hole is in RIGHT NOW
                    # (reflects flip correctly without any extra state check)
                    if cp[2] in LEFT_COLS:
                        c.create_text(left_tx, hy, text=label, font=lbl_fnt,
                                      fill=tc, anchor="w",
                                      tags=("comp", f"comp_{pc.inst_id}"))
                    else:
                        c.create_text(right_tx, hy, text=label, font=lbl_fnt,
                                      fill=tc, anchor="e",
                                      tags=("comp", f"comp_{pc.inst_id}"))

    def _draw_offboard_component(self, pc: PlacedComponent) -> None:
        c   = self._canvas
        cd  = pc.comp_def
        sel = (pc.inst_id == self._selected_comp)
        tc  = contrast_color(cd.color)           # text ON the component fill
        lay = self.layout
        z   = lay.zoom

        # All sizes scale with zoom; position is stored in world coords
        ps    = OFFBOARD_PIN_SPACING * z
        pad_x = OFFBOARD_PADDING_X * z
        pad_y = OFFBOARD_PADDING_Y * z
        dot_r = max(4, int(5 * z))

        n_left  = len(cd.left_pins)
        n_right = len(cd.right_pins)
        n_rows  = max(n_left, n_right, 1)

        body_w = max(OFFBOARD_MIN_WIDTH * z,
                     90 * z * (1 + cd.is_dip) + pad_x * 2)
        body_h = n_rows * ps + pad_y * 2

        # World → screen
        x0, y0 = lay.to_screen(pc.x, pc.y)
        x1, y1 = x0 + body_w, y0 + body_h

        ow = 3 if sel else 1
        oc = C_SELECTION if sel else C_COMP_OUTLINE
        c.create_rectangle(x0, y0, x1, y1,
                           fill=cd.color, outline=oc, width=ow,
                           tags=("comp", "offboard", f"comp_{pc.inst_id}"))

        # ── Pin-1 gold stripe (for off-board DIP components) ─────────────────
        if cd.is_dip:
            sw = max(3.0, 3 * z)
            if not pc.flipped:
                c.create_rectangle(x0, y0, x0 + sw, y1,
                                   fill="#FFD700", outline="",
                                   tags=("comp", f"comp_{pc.inst_id}"))
            else:
                c.create_rectangle(x1 - sw, y0, x1, y1,
                                   fill="#FFD700", outline="",
                                   tags=("comp", f"comp_{pc.inst_id}"))

        c.create_text((x0 + x1) / 2, (y0 + y1) / 2,
                      text=cd.type_name,
                      font=("Helvetica", max(7, int(8 * z)), "bold"),
                      fill=tc, width=body_w - 4,
                      tags=("comp", f"comp_{pc.inst_id}"))

        # Pin circles with labels
        offset = len(cd.left_pins)
        pc._bbox          = (x0, y0, x1, y1)   # type: ignore[attr-defined]
        pc._pin_positions = {}                   # type: ignore[attr-defined]

        fnt = ("Helvetica", max(6, int(7 * z)))

        # Determine pin lists and their original indices in cd.all_pins
        left_draw = []   # list of (original_index, pin)
        right_draw = []  # list of (original_index, pin)

        if pc.flipped and cd.is_dip:
            # Left visual side draws right_pins (original indices starting at offset)
            for i, pin in enumerate(cd.right_pins):
                left_draw.append((offset + i, pin))
            # Right visual side draws left_pins (original indices starting at 0)
            for i, pin in enumerate(cd.left_pins):
                right_draw.append((i, pin))
        else:
            # Left visual side draws left_pins (original indices starting at 0)
            for i, pin in enumerate(cd.left_pins):
                left_draw.append((i, pin))
            # Right visual side draws right_pins (original indices starting at offset)
            for i, pin in enumerate(cd.right_pins):
                right_draw.append((offset + i, pin))

        for idx, (orig_idx, pin) in enumerate(left_draw):
            py_pin = y0 + pad_y + idx * ps + ps / 2
            tag_id = f"pin_{pc.inst_id}_{orig_idx}"
            c.create_oval(x0 - dot_r, py_pin - dot_r,
                          x0 + dot_r, py_pin + dot_r,
                          fill=C_PIN_HOVER, outline=C_COMP_OUTLINE,
                          tags=("pin_dot", tag_id, f"comp_{pc.inst_id}"))
            # Label sits outside-left of the body – detect what's there
            ltx = x0 - dot_r - 3
            c.create_text(ltx, py_pin,
                          text=pin.name, font=fnt,
                          anchor="e", fill=self._label_color(ltx, py_pin),
                          tags=("comp", f"comp_{pc.inst_id}"))
            pc._pin_positions[orig_idx] = (x0, py_pin)    # type: ignore[attr-defined]

        for idx, (orig_idx, pin) in enumerate(right_draw):
            py_pin = y0 + pad_y + idx * ps + ps / 2
            tag_id = f"pin_{pc.inst_id}_{orig_idx}"
            c.create_oval(x1 - dot_r, py_pin - dot_r,
                          x1 + dot_r, py_pin + dot_r,
                          fill=C_PIN_HOVER, outline=C_COMP_OUTLINE,
                          tags=("pin_dot", tag_id, f"comp_{pc.inst_id}"))
            ltx = x1 + dot_r + 3
            c.create_text(ltx, py_pin,
                          text=pin.name, font=fnt,
                          anchor="w", fill=self._label_color(ltx, py_pin),
                          tags=("comp", f"comp_{pc.inst_id}"))
            pc._pin_positions[orig_idx] = (x1, py_pin)   # type: ignore[attr-defined]


    # ── Drawing: wires ────────────────────────────────────────────────────────

    def _draw_wires(self) -> None:
        for w in self.state.wires:
            p1 = self._cp_to_pixel(w.start)
            p2 = self._cp_to_pixel(w.end)
            if p1 and p2:
                sel   = (w.wire_id == self._selected_wire)
                width = max(2, int(3 * self._zoom)) if sel else max(1, int(2 * self._zoom))
                self._canvas.create_line(
                    p1[0], p1[1], p2[0], p2[1],
                    fill=w.color, width=width, capstyle=tk.ROUND,
                    tags=("wire", f"wire_{w.wire_id}"))
                dot_r = max(2, int(3 * self._zoom))
                for px, py in (p1, p2):
                    self._canvas.create_oval(
                        px - dot_r, py - dot_r, px + dot_r, py + dot_r,
                        fill=w.color, outline="", tags="wire")

    # ── Connection-point utilities ────────────────────────────────────────────

    def _cp_to_pixel(self, cp: CP) -> Optional[Tuple[float, float]]:
        lay = self.layout
        if cp[0] == "hole":
            _, row, col = cp
            if 1 <= row <= lay.num_rows and col in ALL_COLS:
                return lay.hole_xy(row, col)
        elif cp[0] == "rail":
            _, rail_id, idx = cp
            if self.state.rails_visible.get(rail_id, True):
                return lay.rail_xy(rail_id, idx)
        elif cp[0] == "pin":
            _, inst_id, pin_key = cp
            pc = self.state.get_component(inst_id)
            if pc and not pc.on_board:
                pin_idx  = int(pin_key.split("__")[0])
                pos_map  = getattr(pc, "_pin_positions", {})
                return pos_map.get(pin_idx)
        return None

    def _hit_test_connection(self, px: float, py: float) -> Optional[CP]:
        lay = self.layout
        snap = lay.nearest_hole(px, py)
        if snap:
            return hole_cp(*snap)
        rsnap = lay.nearest_rail_hole(px, py)
        if rsnap:
            rail_id, idx = rsnap
            return rail_cp(rail_id, idx)
        for pc in self.state.components:
            if pc.on_board:
                continue
            pos_map = getattr(pc, "_pin_positions", {})
            for pin_idx, (ppx, ppy) in pos_map.items():
                if ((ppx - px) ** 2 + (ppy - py) ** 2) ** 0.5 < 10:
                    all_pins = pc.comp_def.all_pins
                    pname    = all_pins[pin_idx].name
                    return pin_cp(pc.inst_id, f"{pin_idx}__{pname}")
        return None

    def _hit_test_component(self, px: float, py: float
                            ) -> Optional[PlacedComponent]:
        lay = self.layout
        hs  = lay._hs
        for pc in reversed(self.state.components):
            if pc.on_board:
                holes = pc.all_occupied_holes()
                if not holes:
                    continue
                xs  = [lay.hole_xy(r, col)[0] for r, col in holes]
                ys  = [lay.hole_xy(r, col)[1] for r, col in holes]
                pad = hs * 0.5
                if (min(xs) - pad <= px <= max(xs) + pad and
                        min(ys) - pad <= py <= max(ys) + pad):
                    return pc
            else:
                bbox = getattr(pc, "_bbox", None)
                if bbox and bbox[0] <= px <= bbox[2] and bbox[1] <= py <= bbox[3]:
                    return pc
        return None

    def _hit_test_wire(self, px: float, py: float) -> Optional[Wire]:
        THRESHOLD = max(4, int(5 * self._zoom))
        for w in reversed(self.state.wires):
            p1 = self._cp_to_pixel(w.start)
            p2 = self._cp_to_pixel(w.end)
            if not p1 or not p2:
                continue
            dx, dy = p2[0] - p1[0], p2[1] - p1[1]
            ln2 = dx * dx + dy * dy
            if ln2 == 0:
                dist = ((px - p1[0]) ** 2 + (py - p1[1]) ** 2) ** 0.5
            else:
                t    = max(0, min(1, ((px - p1[0]) * dx + (py - p1[1]) * dy) / ln2))
                dist = ((px - p1[0] - t * dx) ** 2 + (py - p1[1] - t * dy) ** 2) ** 0.5
            if dist < THRESHOLD:
                return w
        return None

    def _canvas_xy(self, event) -> Tuple[float, float]:
        return (self._canvas.canvasx(event.x),
                self._canvas.canvasy(event.y))

    # ── Mouse event handlers ──────────────────────────────────────────────────

    def _on_left_press(self, event) -> None:
        cx, cy = self._canvas_xy(event)
        self._canvas.focus_set()

        if self._mode == MODE_SELECT:
            self._handle_select_press(cx, cy)
        elif self._mode == MODE_PLACE:
            self._handle_place(cx, cy)
        elif self._mode == MODE_WIRE:
            self._handle_wire_click(cx, cy)
        elif self._mode == MODE_DELETE:
            self._handle_delete_click(cx, cy)
        elif self._mode == MODE_DIVIDER:
            self._handle_divider_click(cx, cy)
        elif self._mode == MODE_PAN:
            self._pan_anchor = (cx, cy, self._board_ox, self._board_oy)

    def _on_left_drag(self, event) -> None:
        cx, cy = self._canvas_xy(event)
        if self._mode == MODE_PLACE:
            self._draw_ghost(cx, cy)
        elif self._mode == MODE_SELECT and self._drag_comp:
            self._handle_comp_drag(cx, cy)
        elif self._mode == MODE_WIRE and self._wire_start:
            self._update_ghost_wire(cx, cy)
        elif self._mode == MODE_PAN and self._pan_anchor:
            ax, ay, ox, oy = self._pan_anchor
            self._board_ox = ox + (cx - ax)
            self._board_oy = oy + (cy - ay)
            self.refresh_layout()

    def _on_left_release(self, event) -> None:
        cx, cy = self._canvas_xy(event)
        if self._mode == MODE_SELECT and self._drag_comp:
            self._handle_comp_drop(cx, cy)
        self._drag_comp  = None
        self._pan_anchor = None

    def _on_motion(self, event) -> None:
        cx, cy = self._canvas_xy(event)
        if self._mode == MODE_PLACE:
            self._draw_ghost(cx, cy)
        elif self._mode == MODE_WIRE and self._wire_start:
            self._update_ghost_wire(cx, cy)

    def _on_right_click(self, event) -> None:
        cx, cy = self._canvas_xy(event)
        if self._mode in (MODE_WIRE, MODE_PLACE, MODE_PAN):
            self._cancel_action()
        else:
            self._show_context_menu(event, cx, cy)

    def _on_escape(self, event) -> None:
        self._cancel_action()

    def _on_delete_key(self, event) -> None:
        if self._selected_comp:
            self.state.remove_component(self._selected_comp)
            self._selected_comp = None
            self.redraw()
            self.on_change()
        elif self._selected_wire:
            self.state.remove_wire(self._selected_wire)
            self._selected_wire = None
            self.redraw()
            self.on_change()

    def _on_zoom_scroll(self, event) -> None:
        if event.num == 4 or event.delta > 0:
            self._apply_zoom(self._zoom * ZOOM_STEP)
        else:
            self._apply_zoom(self._zoom / ZOOM_STEP)

    def _on_scroll_y(self, event) -> None:
        # Don't scroll when Ctrl is held (that's zoom)
        if event.state & 0x0004:
            return
        if event.num == 4:
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._canvas.yview_scroll(1, "units")
        else:
            self._canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _on_scroll_x(self, event) -> None:
        self._canvas.xview_scroll(-1 if event.delta > 0 else 1, "units")

    def _on_vp_pan_start(self, event) -> None:
        self._vp_anchor = (event.x, event.y,
                           self._canvas.xview()[0],
                           self._canvas.yview()[0])
        self._canvas.configure(cursor="fleur")

    def _on_vp_pan_drag(self, event) -> None:
        if not self._vp_anchor:
            return
        x0, y0, xv0, yv0 = self._vp_anchor
        sr = self._canvas.cget("scrollregion")
        if sr:
            parts = [float(v) for v in sr.split()]
            w, h  = parts[2] - parts[0], parts[3] - parts[1]
        else:
            w, h = 2400, 1600
        dx = (x0 - event.x) / w
        dy = (y0 - event.y) / h
        self._canvas.xview_moveto(max(0.0, min(1.0, xv0 + dx)))
        self._canvas.yview_moveto(max(0.0, min(1.0, yv0 + dy)))

    def _on_vp_pan_end(self, event) -> None:
        self._vp_anchor = None
        cursor_map = {
            MODE_SELECT: "arrow", MODE_PLACE: "crosshair",
            MODE_WIRE: "pencil", MODE_DELETE: "X_cursor",
            MODE_DIVIDER: "sb_v_double_arrow", MODE_PAN: "fleur",
        }
        self._canvas.configure(cursor=cursor_map.get(self._mode, "arrow"))

    # ── Action handlers ───────────────────────────────────────────────────────

    def _handle_select_press(self, cx: float, cy: float) -> None:
        comp = self._hit_test_component(cx, cy)
        if comp:
            self._selected_comp = comp.inst_id
            self._selected_wire = None
            self._drag_comp     = comp.inst_id
            if comp.on_board:
                ax, ay = self.layout.hole_xy(comp.anchor_row, comp.anchor_col)
                self._drag_off = (cx - ax, cy - ay)
            else:
                # Drag offset in canvas coords relative to component screen origin
                sx, sy = self.layout.to_screen(comp.x, comp.y)
                self._drag_off = (cx - sx, cy - sy)
            self.redraw()
            return
        wire = self._hit_test_wire(cx, cy)
        if wire:
            self._selected_wire = wire.wire_id
            self._selected_comp = None
            self.redraw()
            return
        self._selected_comp = None
        self._selected_wire = None
        self.redraw()

    def _handle_comp_drag(self, cx: float, cy: float) -> None:
        pc = self.state.get_component(self._drag_comp)
        if not pc:
            return
        lay = self.layout
        tx  = cx - self._drag_off[0]
        ty  = cy - self._drag_off[1]

        snap = lay.nearest_hole(tx, ty)
        if snap and lay.board_hit(cx, cy):
            new_row, new_col = snap
            if pc.comp_def.category == "controller" and new_col in RIGHT_COLS:
                new_col = MIRROR_COL[new_col]
            pc.on_board = True
            pc.anchor_row = new_row
            pc.anchor_col = new_col
            pc.compute_pin_holes()
        else:
            pc.on_board = False
            wx, wy = lay.to_world(tx, ty)
            pc.x = wx
            pc.y = wy
            pc.compute_pin_holes()
        self.redraw()

    def _handle_comp_drop(self, cx: float, cy: float) -> None:
        pc  = self.state.get_component(self._drag_comp)
        if not pc:
            return
        pc.compute_pin_holes()
        self.redraw()
        self.on_change()

    def _handle_place(self, cx: float, cy: float) -> None:
        if self._placing_def is None:
            return
        lay = self.layout
        occ = self.state.occupied_holes()
        cd  = self._placing_def
        rotated = getattr(self, "_placing_rotated", False)

        if lay.board_hit(cx, cy):
            snap = lay.nearest_hole(cx, cy)
            if snap:
                row, col = snap
                if cd.category == "controller" and col in RIGHT_COLS:
                    col = MIRROR_COL[col]
                test_pc = PlacedComponent("_test", cd, on_board=True,
                                         anchor_row=row, anchor_col=col, rotated=rotated)
                test_pc.compute_pin_holes()
                candidate = test_pc.all_occupied_holes()
                if all(h not in occ and 1 <= h[0] <= lay.num_rows
                       and h[1] in ALL_COLS for h in candidate):
                    self.state.add_component(cd, on_board=True,
                                             anchor_row=row, anchor_col=col, rotated=rotated)
                    self.on_change()
                    self.on_status(f"Placed {cd.type_name} at row {row}, col {col}")
                else:
                    self.on_status("Cannot place here – holes occupied or out of range")
        else:
            # Convert canvas click to world coords for off-board placement
            wx, wy = lay.to_world(cx - 60, cy - 30)
            min_wx = lay.offboard_default_world_x()
            wx = max(wx, min_wx)
            self.state.add_component(cd, on_board=False, x=wx, y=wy, rotated=rotated)
            self.on_change()
            self.on_status(f"Placed {cd.type_name} off-board")

        self._canvas.delete("ghost")
        self.redraw()

    def _handle_wire_click(self, cx: float, cy: float) -> None:
        cp = self._hit_test_connection(cx, cy)
        if cp is None:
            return
        if self._wire_start is None:
            self._wire_start = cp
            self.on_status(f"Wire start set – click an endpoint to complete")
        else:
            if cp != self._wire_start:
                self.state.add_wire(self._wire_start, cp, color=self._wire_color)
                self.on_change()
                self.on_status("Wire added")
                self._wire_color = self.next_wire_color()
            self._wire_start = None
            self._canvas.delete("ghost_wire")
            self.redraw()

    def _update_ghost_wire(self, cx: float, cy: float) -> None:
        self._canvas.delete("ghost_wire")
        if not self._wire_start:
            return
        p1 = self._cp_to_pixel(self._wire_start)
        if not p1:
            return
        self._canvas.create_line(p1[0], p1[1], cx, cy,
                                  fill=self._wire_color,
                                  width=max(1, int(2 * self._zoom)),
                                  dash=(4, 3), tags="ghost_wire")

    def _handle_delete_click(self, cx: float, cy: float) -> None:
        wire = self._hit_test_wire(cx, cy)
        if wire:
            self.state.remove_wire(wire.wire_id)
            self.on_status(f"Deleted wire {wire.wire_id}")
            self.redraw()
            self.on_change()
            return
        comp = self._hit_test_component(cx, cy)
        if comp:
            self.state.remove_component(comp.inst_id)
            self.on_status(f"Deleted {comp.comp_def.type_name}")
            self.redraw()
            self.on_change()

    def _handle_divider_click(self, cx: float, cy: float) -> None:
        lay = self.layout
        hs  = lay._hs
        best_dist = hs
        best_row  = None
        for row in range(1, lay.num_rows):
            _, y1 = lay.hole_xy(row, 'a')
            _, y2 = lay.hole_xy(row + 1, 'a')
            yd = (y1 + y2) / 2
            d  = abs(cy - yd)
            if d < best_dist:
                best_dist = d
                best_row  = row
        if best_row:
            if best_row in self.state.dividers:
                self.state.dividers.remove(best_row)
                self.on_status(f"Removed divider after row {best_row}")
            else:
                self.state.dividers.add(best_row)
                self.on_status(f"Added divider after row {best_row}")
            self.redraw(full=True)
            self.on_change()

    def _cancel_action(self) -> None:
        self._wire_start  = None
        self._placing_def = None
        self._pan_anchor  = None
        self._canvas.delete("ghost")
        self._canvas.delete("ghost_wire")
        self._mode = MODE_SELECT
        self._canvas.configure(cursor="arrow")
        self.on_status("Action cancelled")

    # ── Ghost (placement preview) ─────────────────────────────────────────────

    def _draw_ghost(self, px: float, py: float) -> None:
        self._canvas.delete("ghost")
        if self._placing_def is None:
            return
        cd  = self._placing_def
        lay = self.layout
        occ = self.state.occupied_holes()
        hs  = lay._hs

        snap = lay.nearest_hole(px, py)
        if not snap:
            return
        row, col = snap
        rotated = getattr(self, "_placing_rotated", False)
        if cd.category == "controller" and col in RIGHT_COLS:
            col = MIRROR_COL[col]
        temp_pc = PlacedComponent("_temp", cd, on_board=True, anchor_row=row, anchor_col=col, rotated=rotated)
        temp_pc.compute_pin_holes()
        ghost_holes = temp_pc.all_occupied_holes()
        valid = all(
            h not in occ and 1 <= h[0] <= lay.num_rows and h[1] in ALL_COLS
            for h in ghost_holes
        )
        fill    = C_GHOST_FILL if valid else "#FFAAAA"
        outline = C_GHOST_OUTLINE if valid else "#CC0000"

        if not ghost_holes:
            return
        xs = [lay.hole_xy(r, c)[0] for r, c in ghost_holes]
        ys = [lay.hole_xy(r, c)[1] for r, c in ghost_holes]
        x0 = min(xs) - hs * 0.45;  y0 = min(ys) - hs * 0.45
        x1 = max(xs) + hs * 0.45;  y1 = max(ys) + hs * 0.45
        self._canvas.create_rectangle(x0, y0, x1, y1,
                                      fill=fill, outline=outline,
                                      width=2, stipple="gray50", tags="ghost")
        tc = contrast_color(fill)
        for i, pin in enumerate(cd.left_pins + cd.right_pins):
            if i < len(ghost_holes):
                gx, gy = lay.hole_xy(*ghost_holes[i])
                self._canvas.create_text(gx, gy, text=pin.name,
                                         font=("Helvetica", max(5, int(6 * lay.zoom))),
                                         fill=tc, tags="ghost")

    # ── Context menu ──────────────────────────────────────────────────────────

    def _show_context_menu(self, event, cx: float, cy: float) -> None:
        comp = self._hit_test_component(cx, cy)
        wire = self._hit_test_wire(cx, cy)
        menu = tk.Menu(self, tearoff=0)
        if comp:
            menu.add_command(label=f"Delete  {comp.comp_def.type_name}",
                             command=lambda: self._ctx_delete_comp(comp.inst_id))
            if comp.comp_def.is_dip:
                menu.add_command(label="Flip left ↔ right",
                                 command=lambda: self._ctx_flip(comp.inst_id))
            if comp.comp_def.category != "controller":
                menu.add_command(label="Rotate 90°",
                                 command=lambda: self._ctx_rotate(comp.inst_id))
            menu.add_separator()
            menu.add_command(label="Move off-board",
                             command=lambda: self._ctx_move_off(comp.inst_id))
        elif wire:
            menu.add_command(label="Delete wire",
                             command=lambda: self._ctx_delete_wire(wire.wire_id))
            menu.add_command(label="Change wire colour…",
                             command=lambda: self._ctx_wire_color(wire.wire_id))
        else:
            menu.add_command(label="Cancel / deselect",
                             command=self._cancel_action)
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    def _ctx_delete_comp(self, inst_id: str) -> None:
        self.state.remove_component(inst_id)
        if self._selected_comp == inst_id:
            self._selected_comp = None
        self.redraw()
        self.on_change()

    def _ctx_flip(self, inst_id: str) -> None:
        pc = self.state.get_component(inst_id)
        if pc:
            pc.flipped = not pc.flipped
            pc.compute_pin_holes()
            self.redraw()
            self.on_change()

    def _ctx_move_off(self, inst_id: str) -> None:
        pc = self.state.get_component(inst_id)
        if pc:
            lay = self.layout
            wx = lay.offboard_default_world_x()
            wy = lay.to_world(0, lay.board_oy + 20)[1]
            self.state.move_component_off_board(inst_id, wx, wy)
            self.redraw()
            self.on_change()

    def _ctx_delete_wire(self, wire_id: str) -> None:
        self.state.remove_wire(wire_id)
        if self._selected_wire == wire_id:
            self._selected_wire = None
        self.redraw()
        self.on_change()

    def _ctx_wire_color(self, wire_id: str) -> None:
        w = self.state._wire_by_id.get(wire_id)
        if not w:
            return
        color = colorchooser.askcolor(color=w.color, title="Wire colour")[1]
        if color:
            w.color = color
            self.redraw()

    def _ctx_rotate(self, inst_id: str) -> None:
        pc = self.state.get_component(inst_id)
        if pc:
            pc.rotated = not getattr(pc, "rotated", False)
            pc.compute_pin_holes()
            self.redraw()
            self.on_change()

    def _on_rotate_key(self, event) -> None:
        if self._mode == MODE_PLACE:
            self._placing_rotated = not getattr(self, "_placing_rotated", False)
            try:
                raw_x = self._canvas.winfo_pointerx() - self._canvas.winfo_rootx()
                raw_y = self._canvas.winfo_pointery() - self._canvas.winfo_rooty()
                cx = self._canvas.canvasx(raw_x)
                cy = self._canvas.canvasy(raw_y)
                self._draw_ghost(cx, cy)
            except Exception:
                pass
        elif self._mode == MODE_SELECT and self._selected_comp:
            pc = self.state.get_component(self._selected_comp)
            if pc and pc.comp_def.category != "controller":
                pc.rotated = not getattr(pc, "rotated", False)
                pc.compute_pin_holes()
                self.redraw()
                self.on_change()

