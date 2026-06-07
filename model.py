# model.py  – board state, placed components, wires and netlist
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from components import ComponentDef, PinDef, PT_GND
from constants import (
    ALL_COLS, LEFT_COLS, RIGHT_COLS, MIRROR_COL,
    ALL_RAILS,
    RAIL_LEFT_MINUS, RAIL_LEFT_PLUS,
    RAIL_RIGHT_PLUS, RAIL_RIGHT_MINUS,
)

# ── Connection-point types ─────────────────────────────────────────────────────
# HoleCP  : ("hole",  row: int,  col: str)   e.g. ("hole", 5, "c")
# RailCP  : ("rail",  rail_id: str, seg: int) e.g. ("rail", "top_plus", 0)
# PinCP   : ("pin",   inst_id: str, pin_name: str)
CP = Tuple   # generic alias; actual tuples are one of the three shapes above


def hole_cp(row: int, col: str) -> CP:
    return ("hole", row, col)

def rail_cp(rail_id: str, seg: int) -> CP:
    return ("rail", rail_id, seg)

def pin_cp(inst_id: str, pin_name: str) -> CP:
    return ("pin", inst_id, pin_name)


# ═══════════════════════════════════════════════════════════════════════════════
#  PlacedComponent
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class PlacedComponent:
    """One instance of a ComponentDef placed in the workspace."""
    inst_id:    str          # unique identifier  e.g. "comp_3"
    comp_def:   ComponentDef

    # On-board placement
    on_board:   bool = False
    anchor_row: int  = 1     # row of first left pin (1-indexed)
    anchor_col: str  = 'b'   # column of first left pin
    flipped:    bool = False  # flip left↔right sides (only relevant for DIP)

    # Off-board placement (canvas world coordinates, top-left of the component box)
    x: float = 200.0
    y: float = 200.0

    # ── derived pin→hole mapping (populated by compute_pin_holes) ─────────────
    # pin_holes[pin_name_unique_key] = (row, col)  or None for off-board pins
    pin_holes: Dict[str, Optional[Tuple[int, str]]] = field(default_factory=dict)

    def pin_key(self, pin_index: int) -> str:
        """A stable key for a pin based on its index in all_pins."""
        return f"{self.inst_id}__{pin_index}"

    def compute_pin_holes(self) -> None:
        """Populate self.pin_holes based on placement position."""
        self.pin_holes.clear()
        if not self.on_board:
            return

        cd = self.comp_def
        l_col = self.anchor_col
        r_col = MIRROR_COL.get(l_col, l_col)

        # Determine which side goes where when flipped
        if self.flipped and cd.is_dip:
            l_col, r_col = r_col, l_col

        # Left-side pins
        for i, pin in enumerate(cd.left_pins):
            row = self.anchor_row + i
            key = self.pin_key(i)
            self.pin_holes[key] = (row, l_col)

        # Right-side pins
        offset = len(cd.left_pins)
        for i, pin in enumerate(cd.right_pins):
            row = self.anchor_row + i
            key = self.pin_key(offset + i)
            self.pin_holes[key] = (row, r_col)

    def all_occupied_holes(self) -> List[Tuple[int, str]]:
        """Return all (row, col) holes this component occupies."""
        return [h for h in self.pin_holes.values() if h is not None]

    def connection_points(self) -> List[Tuple[str, CP]]:
        """
        Return list of (label, CP) for all pins:
        • on-board pins  → HoleCP
        • off-board pins → PinCP
        """
        result = []
        cd = self.comp_def
        all_pins = cd.all_pins
        for i, pin in enumerate(all_pins):
            key = self.pin_key(i)
            if self.on_board and key in self.pin_holes and self.pin_holes[key]:
                row, col = self.pin_holes[key]
                cp = hole_cp(row, col)
            else:
                cp = pin_cp(self.inst_id, f"{i}__{pin.name}")
            result.append((pin.name, cp))
        return result


# ═══════════════════════════════════════════════════════════════════════════════
#  Wire
# ═══════════════════════════════════════════════════════════════════════════════

@dataclass
class Wire:
    wire_id: str
    start:   CP
    end:     CP
    color:   str = "#E53935"
    label:   str = ""


# ═══════════════════════════════════════════════════════════════════════════════
#  BoardState – the entire logical state of one project
# ═══════════════════════════════════════════════════════════════════════════════

class BoardState:
    def __init__(self, num_rows: int = 30):
        self.num_rows: int = num_rows

        # Power-rail visibility
        self.rails_visible: Dict[str, bool] = {r: True for r in ALL_RAILS}

        # Dividers: set of row numbers after which a divider is drawn.
        # A divider splits ONLY the power rails at that position.
        self.dividers: Set[int] = set()

        # Placed components (ordered insertion for z-order)
        self.components: List[PlacedComponent] = []
        self._comp_by_id: Dict[str, PlacedComponent] = {}

        # Wires
        self.wires: List[Wire] = []
        self._wire_by_id: Dict[str, Wire] = {}

        # Counters for unique IDs
        self._comp_counter: int = 0
        self._wire_counter: int = 0

    # ── Component management ──────────────────────────────────────────────────

    def new_comp_id(self) -> str:
        self._comp_counter += 1
        return f"comp_{self._comp_counter}"

    def add_component(self, comp_def: ComponentDef,
                      on_board: bool = False,
                      anchor_row: int = 1,
                      anchor_col: str = 'b',
                      x: float = 200, y: float = 200) -> PlacedComponent:
        inst_id = self.new_comp_id()
        pc = PlacedComponent(
            inst_id=inst_id, comp_def=comp_def,
            on_board=on_board, anchor_row=anchor_row, anchor_col=anchor_col,
            x=x, y=y,
        )
        pc.compute_pin_holes()
        self.components.append(pc)
        self._comp_by_id[inst_id] = pc
        return pc

    def remove_component(self, inst_id: str) -> None:
        pc = self._comp_by_id.pop(inst_id, None)
        if pc:
            self.components.remove(pc)
            # Remove any wires that reference this component's pins
            to_remove = [
                w for w in self.wires
                if (w.start[0] == "pin" and w.start[1] == inst_id) or
                   (w.end[0]   == "pin" and w.end[1]   == inst_id)
            ]
            for w in to_remove:
                self.remove_wire(w.wire_id)

    def get_component(self, inst_id: str) -> Optional[PlacedComponent]:
        return self._comp_by_id.get(inst_id)

    def move_component_on_board(self, inst_id: str,
                                 anchor_row: int, anchor_col: str) -> None:
        pc = self._comp_by_id.get(inst_id)
        if pc:
            pc.on_board   = True
            pc.anchor_row = anchor_row
            pc.anchor_col = anchor_col
            pc.compute_pin_holes()

    def move_component_off_board(self, inst_id: str, x: float, y: float) -> None:
        pc = self._comp_by_id.get(inst_id)
        if pc:
            pc.on_board = False
            pc.x        = x
            pc.y        = y
            pc.compute_pin_holes()

    def occupied_holes(self) -> Dict[Tuple[int, str], str]:
        """Returns {(row, col): inst_id} for every occupied hole."""
        result: Dict[Tuple[int, str], str] = {}
        for pc in self.components:
            for hole in pc.all_occupied_holes():
                result[hole] = pc.inst_id
        return result

    def controller(self) -> Optional[PlacedComponent]:
        """Return the first (and ideally only) controller component."""
        for pc in self.components:
            if pc.comp_def.category == "controller":
                return pc
        return None

    # ── Wire management ───────────────────────────────────────────────────────

    def new_wire_id(self) -> str:
        self._wire_counter += 1
        return f"wire_{self._wire_counter}"

    def add_wire(self, start: CP, end: CP, color: str = "#E53935") -> Wire:
        wid = self.new_wire_id()
        w = Wire(wire_id=wid, start=start, end=end, color=color)
        self.wires.append(w)
        self._wire_by_id[wid] = w
        return w

    def remove_wire(self, wire_id: str) -> None:
        w = self._wire_by_id.pop(wire_id, None)
        if w:
            self.wires.remove(w)

    # ── Netlist (union-find) ──────────────────────────────────────────────────

    def compute_nets(self) -> Dict[int, Set[CP]]:
        """
        Returns a dict  net_id → set[CP].
        All CPs in the same set are electrically connected.
        """
        # Union-Find with path compression
        parent: Dict[CP, CP] = {}

        def find(x: CP) -> CP:
            if parent.setdefault(x, x) != x:
                parent[x] = find(parent[x])
            return parent[x]

        def union(a: CP, b: CP) -> None:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[ra] = rb

        def ensure(x: CP) -> None:
            find(x)  # initialises parent[x] = x

        # 1. Breadboard row-group internal connections
        for r in range(1, self.num_rows + 1):
            for group in (LEFT_COLS, RIGHT_COLS):
                anchor = hole_cp(r, group[0])
                ensure(anchor)
                for col in group[1:]:
                    union(anchor, hole_cp(r, col))

        # 2. Power-rail internal connections (with divider splits)
        for rail_id in ALL_RAILS:
            if not self.rails_visible.get(rail_id, True):
                continue
            # Build segments: dividers split the rail
            sorted_divs = sorted(self.dividers)
            segments: List[List[int]] = []
            seg_start = 0
            for d in sorted_divs:
                segments.append(list(range(seg_start, d)))
                seg_start = d
            segments.append(list(range(seg_start, self.num_rows)))
            for seg_idx, seg in enumerate(segments):
                if not seg:
                    continue
                anchor = rail_cp(rail_id, seg[0])
                ensure(anchor)
                for idx in seg[1:]:
                    union(anchor, rail_cp(rail_id, idx))

        # 3. Component pin CPs (off-board only – on-board pins are just at holes)
        for pc in self.components:
            for _label, cp in pc.connection_points():
                ensure(cp)

        # 4. Wires merge nets
        for w in self.wires:
            ensure(w.start)
            ensure(w.end)
            union(w.start, w.end)

        # 5. Group by root
        nets: Dict[CP, Set[CP]] = {}
        all_cps = set(parent.keys())
        for cp in all_cps:
            root = find(cp)
            nets.setdefault(root, set()).add(cp)

        # Re-index by integer
        return {i: s for i, s in enumerate(nets.values())}

    # ── GND analysis ──────────────────────────────────────────────────────────

    def gnd_net_ids(self, nets: Dict[int, Set[CP]]) -> Set[int]:
        """Return net IDs that contain a controller GND pin."""
        ctrl = self.controller()
        if ctrl is None:
            return set()
        gnd_cps: Set[CP] = set()
        for label, cp in ctrl.connection_points():
            pin_idx = int(cp[2].split("__")[0]) if cp[0] == "pin" else -1
            # Check by ptype
            all_pins = ctrl.comp_def.all_pins
            idx = int(cp[2].split("__")[0]) if cp[0] == "pin" else None
            if cp[0] == "hole":
                # find which pin index maps to this hole
                for i, (lbl2, cp2) in enumerate(ctrl.connection_points()):
                    if cp2 == cp:
                        pd = all_pins[i]
                        if pd.ptype == PT_GND:
                            gnd_cps.add(cp)
                        break
            else:
                i_str = cp[2].split("__")[0]
                if i_str.isdigit():
                    pd = all_pins[int(i_str)]
                    if pd.ptype == PT_GND:
                        gnd_cps.add(cp)

        result = set()
        for net_id, cps in nets.items():
            if gnd_cps & cps:
                result.add(net_id)
        return result

    def is_gnd_connected(self, inst_id: str, pin_index: int,
                          nets: Dict[int, Set[CP]],
                          gnd_net_ids: Set[int]) -> bool:
        """True if the given pin index of inst_id is on a GND net."""
        pc = self._comp_by_id.get(inst_id)
        if pc is None:
            return False
        cps = pc.connection_points()
        if pin_index >= len(cps):
            return False
        _, cp = cps[pin_index]
        for net_id, net_cps in nets.items():
            if cp in net_cps:
                return net_id in gnd_net_ids
        return False

    # ── Board-size helper ─────────────────────────────────────────────────────

    def resize(self, num_rows: int) -> None:
        """Change board size; removes components/wires that fall out of range."""
        self.num_rows = num_rows
        # Remove on-board components that are now out of range
        to_remove = []
        for pc in self.components:
            if pc.on_board:
                max_row = pc.anchor_row + pc.comp_def.height_in_rows - 1
                if max_row > num_rows or pc.anchor_row < 1:
                    to_remove.append(pc.inst_id)
        for iid in to_remove:
            self.remove_component(iid)
