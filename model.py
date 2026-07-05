# model.py  – board state, placed components, wires and netlist
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple

from components import ComponentDef, PinDef, PT_GND, PT_POWER
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


@dataclass
class SafetyIssue:
    severity: str  # "critical" | "warning"
    message: str
    comp_id: Optional[str] = None
    net_id: Optional[int] = None


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
    rotated:    bool = False  # rotate 90 degrees (essential for button placement on same side)

    # Off-board placement (canvas world coordinates, top-left of the component box)
    x: float = 200.0
    y: float = 200.0

    resistance: float = 220.0

    # ── derived pin→hole mapping (populated by compute_pin_holes) ─────────────
    # pin_holes[pin_name_unique_key] = (row, col)  or None for off-board pins
    pin_holes: Dict[str, Optional[Tuple[int, str]]] = field(default_factory=dict)

    def pin_key(self, pin_index: int) -> str:
        """A stable key for a pin based on its index in all_pins."""
        return f"{self.inst_id}__{pin_index}"

    def get_right_column(self, l_col: str) -> str:
        return MIRROR_COL.get(l_col, l_col)

    def compute_pin_holes(self) -> None:
        """Populate self.pin_holes based on placement position."""
        self.pin_holes.clear()
        if not self.on_board:
            return

        cd = self.comp_def
        l_col = self.anchor_col
        r_col = self.get_right_column(l_col)

        # Determine which side goes where when flipped
        if self.flipped and cd.is_dip:
            l_col, r_col = r_col, l_col

        if self.rotated:
            if cd.type_name == "4-Pin Button":
                try:
                    start_idx = ALL_COLS.index(l_col)
                    same_side_col = ALL_COLS[min(start_idx + 2, len(ALL_COLS) - 1)]
                except ValueError:
                    same_side_col = l_col
                # Rotated pushbutton spans rows:
                # Side A (pins 0, 1) are at anchor_row, in l_col and r_col
                # Side B (pins 2, 3) are at anchor_row + 2, in l_col and r_col
                self.pin_holes[self.pin_key(0)] = (self.anchor_row, l_col)
                self.pin_holes[self.pin_key(1)] = (self.anchor_row, same_side_col)
                self.pin_holes[self.pin_key(2)] = (self.anchor_row + 2, l_col)
                self.pin_holes[self.pin_key(3)] = (self.anchor_row + 2, same_side_col)
            else:
                # Place all pins horizontally starting from anchor_col
                try:
                    start_idx = ALL_COLS.index(l_col)
                except ValueError:
                    start_idx = 0
                for i, pin in enumerate(cd.all_pins):
                    col_idx = min(start_idx + i, len(ALL_COLS) - 1)
                    col = ALL_COLS[col_idx]
                    key = self.pin_key(i)
                    self.pin_holes[key] = (self.anchor_row, col)
        else:
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
                      x: float = 200, y: float = 200,
                      rotated: bool = False) -> PlacedComponent:
        inst_id = self.new_comp_id()
        pc = PlacedComponent(
            inst_id=inst_id, comp_def=comp_def,
            on_board=on_board, anchor_row=anchor_row, anchor_col=anchor_col,
            x=x, y=y, rotated=rotated
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

    def _pin_index_from_key(self, pin_key: str) -> Optional[int]:
        idx_str = pin_key.split("__", 1)[0]
        return int(idx_str) if idx_str.isdigit() else None

    def pin_refs_at_cp(self, cp: CP) -> List[Tuple[PlacedComponent, PinDef, str]]:
        refs: List[Tuple[PlacedComponent, PinDef, str]] = []
        if cp[0] == "pin":
            pc = self.get_component(cp[1])
            pin_idx = self._pin_index_from_key(cp[2])
            if pc is not None and pin_idx is not None and pin_idx < len(pc.comp_def.all_pins):
                pin_def = pc.comp_def.all_pins[pin_idx]
                refs.append((pc, pin_def, pin_def.name))
            return refs

        if cp[0] != "hole":
            return refs

        for pc in self.components:
            if not pc.on_board:
                continue
            for i, (label, cp_pin) in enumerate(pc.connection_points()):
                if cp_pin == cp and i < len(pc.comp_def.all_pins):
                    refs.append((pc, pc.comp_def.all_pins[i], label))
        return refs

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
            cps = pc.connection_points()
            for _label, cp in cps:
                ensure(cp)

            if pc.comp_def.type_name == "4-Pin Button" and len(cps) >= 4:
                union(cps[0][1], cps[1][1])
                union(cps[2][1], cps[3][1])

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
        for _label, cp in ctrl.connection_points():
            if any(pc.inst_id == ctrl.inst_id and pin_def.ptype == PT_GND
                   for pc, pin_def, _pin_name in self.pin_refs_at_cp(cp)):
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

        self.dividers = {dv for dv in self.dividers if 1 <= dv < num_rows}

        invalid_wires = []
        for wire in self.wires:
            if self._cp_out_of_range(wire.start) or self._cp_out_of_range(wire.end):
                invalid_wires.append(wire.wire_id)
        for wire_id in invalid_wires:
            self.remove_wire(wire_id)

    def _cp_out_of_range(self, cp: CP) -> bool:
        if cp[0] == "hole":
            return not (1 <= cp[1] <= self.num_rows)
        if cp[0] == "rail":
            return not (0 <= cp[2] < self.num_rows)
        return False

    def analyze_safety(self) -> List[SafetyIssue]:
        issues: List[SafetyIssue] = []
        nets = self.compute_nets()

        # Map each connection point (CP) to its net ID
        cp_to_net: Dict[CP, int] = {}
        for nid, cps in nets.items():
            for cp in cps:
                cp_to_net[cp] = nid

        # ── 1. Direct Short Circuits & Power Conflicts ────────────────────────
        # Group each net's microcontroller pins by type and name
        for nid, cps in sorted(nets.items()):
            gnd_pins = []
            power_pins = []
            io_pins = []

            for cp in cps:
                for pc, pin_def, _pin_name in self.pin_refs_at_cp(cp):
                    if pc.comp_def.category != "controller":
                        continue
                    if pin_def.ptype == PT_GND:
                        gnd_pins.append((pc, pin_def))
                    elif pin_def.ptype == PT_POWER:
                        power_pins.append((pc, pin_def))
                    else:
                        io_pins.append((pc, pin_def))

            # Rules for direct short-circuit:
            if gnd_pins and power_pins:
                power_labels = ", ".join(f"{pc.comp_def.type_name} {pin.name}" for pc, pin in power_pins)
                gnd_labels = ", ".join(f"{pc.comp_def.type_name} {pin.name}" for pc, pin in gnd_pins)
                issues.append(SafetyIssue(
                    severity="critical",
                    message=f"Direct Short Circuit in Net {nid}! Power ({power_labels}) is connected directly to Ground ({gnd_labels}).",
                    net_id=nid
                ))

            # Rule for power supply voltage conflicts:
            if len(power_pins) > 1:
                # Group power pins by normalized voltage
                # (e.g. 5V -> 5.0, 3.3V/3V3 -> 3.3, VIN -> 9.0)
                voltage_groups = {}
                for pc, pin in power_pins:
                    name = pin.name.upper()
                    if "5V" in name:
                        voltage = 5.0
                    elif "3.3V" in name or "3V3" in name:
                        voltage = 3.3
                    elif "VIN" in name:
                        voltage = 9.0
                    else:
                        voltage = 5.0  # default assumption
                    voltage_groups.setdefault(voltage, []).append((pc, pin))

                if len(voltage_groups) > 1:
                    conflict_desc = []
                    for volt, list_pins in sorted(voltage_groups.items()):
                        pins_desc = ", ".join(f"{pc.comp_def.type_name} {p.name}" for pc, p in list_pins)
                        conflict_desc.append(f"{volt}V ({pins_desc})")
                    issues.append(SafetyIssue(
                        severity="critical",
                        message=f"Power Rail Conflict in Net {nid}! Different voltages are connected together: {'; '.join(conflict_desc)}.",
                        net_id=nid
                    ))

        # ── 2. LED Overload Verification (Series Resistor Check) ──────────────
        # Build adjacency list for nets connected via Resistors
        # Adjacency list format: net_id -> list of (neighbor_net_id, resistance)
        resistors = [pc for pc in self.components if pc.comp_def.type_name == "Resistor"]
        adj: Dict[int, List[Tuple[int, float]]] = {}
        for r in resistors:
            rcps = r.connection_points()
            if len(rcps) >= 2:
                cp0, cp1 = rcps[0][1], rcps[1][1]
                n0 = cp_to_net.get(cp0)
                n1 = cp_to_net.get(cp1)
                r_val = getattr(r, "resistance", 220.0)
                if n0 is not None and n1 is not None and n0 != n1:
                    adj.setdefault(n0, []).append((n1, r_val))
                    adj.setdefault(n1, []).append((n0, r_val))

        # Helper to find minimum resistor distance/resistance to other nets (Dijkstra)
        def find_path_resistance(start_nid: int) -> Dict[int, float]:
            import heapq
            queue = [(0.0, start_nid)]
            visited = {start_nid: 0.0}
            while queue:
                r_sum, curr = heapq.heappop(queue)
                if r_sum > visited.get(curr, float('inf')):
                    continue
                for neighbor, res_val in adj.get(curr, []):
                    new_r = r_sum + res_val
                    if new_r < visited.get(neighbor, float('inf')):
                        visited[neighbor] = new_r
                        heapq.heappush(queue, (new_r, neighbor))
            return visited

        # Check each LED
        leds = [pc for pc in self.components if pc.comp_def.category == "led"]
        for led in leds:
            lcps = led.connection_points()
            if len(lcps) < 2:
                continue
            anode_cp, cathode_cp = lcps[0][1], lcps[1][1]
            anode_net = cp_to_net.get(anode_cp)
            cathode_net = cp_to_net.get(cathode_cp)

            if anode_net is None or cathode_net is None:
                # LED is disconnected on one or both sides
                continue

            # Find all nets reachable via resistors from anode and cathode
            anode_res = find_path_resistance(anode_net)
            cathode_res = find_path_resistance(cathode_net)

            # Check if there is any power source (or GPIO pin) connected to the anode/cathode side,
            # and any ground (or GPIO pin) connected to the cathode/anode side.
            correct_power = []
            correct_gnd = []
            reverse_power = []
            reverse_gnd = []

            # Search all nets in the system
            for nid, cps in nets.items():
                has_power = False
                has_gnd = False
                for cp in cps:
                    for pc, pin_def, _pin_name in self.pin_refs_at_cp(cp):
                        if pc.comp_def.category != "controller":
                            continue
                        if pin_def.ptype == PT_POWER:
                            has_power = True
                        elif pin_def.ptype == PT_GND:
                            has_gnd = True
                        else:
                            has_power = True
                            has_gnd = True

                if has_power:
                    if nid in anode_res:
                        correct_power.append((nid, anode_res[nid]))
                    if nid in cathode_res:
                        reverse_power.append((nid, cathode_res[nid]))
                if has_gnd:
                    if nid in cathode_res:
                        correct_gnd.append((nid, cathode_res[nid]))
                    if nid in anode_res:
                        reverse_gnd.append((nid, anode_res[nid]))

            if correct_power and correct_gnd:
                # Find minimum resistance over all power/GND path pairs
                min_res_val = min(
                    p_res + g_res for _, p_res in correct_power for _, g_res in correct_gnd
                )
                if min_res_val < 100.0:
                    if min_res_val == 0.0:
                        issues.append(SafetyIssue(
                            severity="warning",
                            message=f"Overload Hazard! LED '{led.comp_def.type_name}' ({led.inst_id}) is connected directly between power/GPIO and ground without a current-limiting series resistor.",
                            comp_id=led.inst_id
                        ))
                    else:
                        issues.append(SafetyIssue(
                            severity="warning",
                            message=f"Overload Hazard! LED '{led.comp_def.type_name}' ({led.inst_id}) series resistance is too low ({min_res_val:g} Ω). Use at least 100 Ω.",
                            comp_id=led.inst_id
                        ))
                elif min_res_val > 10000.0:
                    issues.append(SafetyIssue(
                        severity="warning",
                        message=f"Practicality Warning: LED '{led.comp_def.type_name}' ({led.inst_id}) series resistance is too high ({min_res_val/1000.0:g} kΩ). LED will be very dim or off.",
                        comp_id=led.inst_id
                    ))
            elif reverse_power and reverse_gnd:
                issues.append(SafetyIssue(
                    severity="warning",
                    message=f"Reverse Polarity Warning! LED '{led.comp_def.type_name}' ({led.inst_id}) is connected with reverse polarity (Cathode is connected to Power/GPIO, Anode is connected to Ground/GPIO). The LED will not light up.",
                    comp_id=led.inst_id
                ))

        # ── 3. Pushbutton Short Circuit on Press Check ────────────────────────
        buttons = [pc for pc in self.components if pc.comp_def.type_name == "4-Pin Button"]
        for btn in buttons:
            bcps = btn.connection_points()
            # Side A is index 0 and 1 (A1, A2)
            # Side B is index 2 and 3 (B1, B2)
            if len(bcps) >= 4:
                # We can check side A nets and side B nets
                side_A_nets = set(cp_to_net.get(bcps[i][1]) for i in (0, 1) if cp_to_net.get(bcps[i][1]) is not None)
                side_B_nets = set(cp_to_net.get(bcps[i][1]) for i in (2, 3) if cp_to_net.get(bcps[i][1]) is not None)

                if side_A_nets and side_B_nets:
                    # Find all power/GND sources reachable via resistors from Side A and Side B
                    side_A_power = False
                    side_A_gnd = False
                    side_B_power = False
                    side_B_gnd = False

                    # Run BFS/Dijkstra from any of Side A nets
                    side_A_dists = {}
                    for san in side_A_nets:
                        side_A_dists.update(find_path_resistance(san))
                    side_B_dists = {}
                    for sbn in side_B_nets:
                        side_B_dists.update(find_path_resistance(sbn))

                    # We check if Side A can reach power with 0 ohms, and Side B can reach GND with 0 ohms (or vice versa)
                    # Let's inspect each net for sources:
                    for nid, cps in nets.items():
                        has_power = False
                        has_gnd = False
                        for cp in cps:
                            for pc, pin_def, _pin_name in self.pin_refs_at_cp(cp):
                                if pc.comp_def.category != "controller":
                                    continue
                                if pin_def.ptype == PT_POWER:
                                    has_power = True
                                elif pin_def.ptype == PT_GND:
                                    has_gnd = True

                        if has_power:
                            if nid in side_A_dists and side_A_dists[nid] < 100.0:
                                side_A_power = True
                            if nid in side_B_dists and side_B_dists[nid] < 100.0:
                                side_B_power = True
                        if has_gnd:
                            if nid in side_A_dists and side_A_dists[nid] < 100.0:
                                side_A_gnd = True
                            if nid in side_B_dists and side_B_dists[nid] < 100.0:
                                side_B_gnd = True

                    # Short hazard exists if:
                    # (Side A has Power with 0 resistors AND Side B has GND with 0 resistors) OR
                    # (Side A has GND with 0 resistors AND Side B has Power with 0 resistors)
                    if (side_A_power and side_B_gnd) or (side_A_gnd and side_B_power):
                        issues.append(SafetyIssue(
                            severity="critical",
                            message=f"Short Circuit Hazard! Pushbutton '{btn.comp_def.type_name}' ({btn.inst_id}) connects Power directly to Ground with no resistor when pressed.",
                            comp_id=btn.inst_id
                        ))

        # ── 4. Logic Level Voltage Mismatch Check ─────────────────────────────
        net_signal_pins = {}
        for nid, cps in nets.items():
            net_signal_pins[nid] = []
            for cp in cps:
                for pc, pin_def, pin_name in self.pin_refs_at_cp(cp):
                    if pc.comp_def.category not in {"passive", "led"} and pc.comp_def.type_name != "4-Pin Button":
                        if pin_def.ptype not in (PT_GND, PT_POWER) and pin_def.ptype in {
                            "io", "digital", "analog", "pwm", "i2c_scl", "i2c_sda"
                        }:
                            net_signal_pins[nid].append((pc, pin_def, pin_name))

        for nid, sig_pins in net_signal_pins.items():
            voltages = {}
            for pc, pin_def, pin_name in sig_pins:
                v = getattr(pc.comp_def, "logic_voltage", 3.3)
                voltages.setdefault(v, []).append((pc, pin_name))
            if len(voltages) > 1:
                conflict_desc = []
                for volt, list_pins in sorted(voltages.items()):
                    pins_desc = ", ".join(f"{pc.comp_def.type_name} {name}" for pc, name in list_pins)
                    conflict_desc.append(f"{volt}V ({pins_desc})")
                issues.append(SafetyIssue(
                    severity="warning",
                    message=f"Logic Level Mismatch on Net {nid}! Different signal voltages are connected directly together: {'; '.join(conflict_desc)}. Connecting 5V signals directly to 3.3V pins can damage components.",
                    net_id=nid
                ))

        # ── 5. GPIO Output Short Hazard (GPIO Output Pin Conflicts) ───────────
        for nid, sig_pins in net_signal_pins.items():
            ctrl_io_pins = []
            for pc, pin_def, pin_name in sig_pins:
                if pc.comp_def.category == "controller" and pin_def.ptype in {"io", "digital", "pwm"}:
                    ctrl_io_pins.append((pc, pin_name))
            if len(ctrl_io_pins) > 1:
                pins_desc = ", ".join(f"{pc.comp_def.type_name} {name}" for pc, name in ctrl_io_pins)
                issues.append(SafetyIssue(
                    severity="warning",
                    message=f"GPIO Conflict Hazard on Net {nid}! Multiple configurable output pins ({pins_desc}) are connected directly. If one is driven HIGH and another LOW in software, it will create a short circuit.",
                    net_id=nid
                ))

        # ── 6. Floating Inputs (Pushbutton Pull-up/Pull-down Check) ───────────
        buttons = [pc for pc in self.components if pc.comp_def.type_name == "4-Pin Button"]
        for btn in buttons:
            bcps = btn.connection_points()
            if len(bcps) < 4:
                continue
            nets_A = set(cp_to_net.get(cp) for label, cp in bcps[:2] if cp_to_net.get(cp) is not None)
            nets_B = set(cp_to_net.get(cp) for label, cp in bcps[2:] if cp_to_net.get(cp) is not None)
            
            for side_nets, side_label in [(nets_A, "Side A"), (nets_B, "Side B")]:
                for nid in side_nets:
                    for pc, pin_def, pin_name in net_signal_pins.get(nid, []):
                        if pc.comp_def.category == "controller" and pin_def.ptype in {"io", "digital", "pwm", "analog"}:
                            paths = find_path_resistance(nid)
                            has_pull_resistor = False
                            for path_nid, path_res in paths.items():
                                if path_res <= 0:
                                    continue
                                for cp in nets.get(path_nid, []):
                                    if any(pin_def.ptype in {PT_POWER, PT_GND}
                                           for _c_pc, pin_def, _pin_name in self.pin_refs_at_cp(cp)):
                                        has_pull_resistor = True
                                        break
                                if has_pull_resistor:
                                    break
                            if not has_pull_resistor:
                                issues.append(SafetyIssue(
                                    severity="warning",
                                    message=f"Floating Input Warning! Pin '{pc.comp_def.type_name} {pin_name}' is connected to pushbutton '{btn.inst_id}' ({side_label}) but its net lacks a pull-up/pull-down resistor. If the button is open, the input will float. Enable the internal pull-up in code (e.g. `INPUT_PULLUP`) or add a resistor.",
                                    comp_id=btn.inst_id
                                ))

        # ── 7. Missing I2C Pull-ups Check ─────────────────────────────────────
        for nid, cps in nets.items():
            i2c_pins = []
            for cp in cps:
                for c_pc, p_def, _pin_name in self.pin_refs_at_cp(cp):
                    if p_def.ptype in {"i2c_sda", "i2c_scl"}:
                        i2c_pins.append((c_pc, p_def))

            if i2c_pins and len(cps) > 1:
                paths = find_path_resistance(nid)
                has_pullup = False
                for path_nid, path_res in paths.items():
                    if not (1000.0 <= path_res <= 10000.0):
                        continue
                    for cp in nets.get(path_nid, []):
                        if any(pin_def.ptype == PT_POWER
                               for _c_pc, pin_def, _pin_name in self.pin_refs_at_cp(cp)):
                            has_pullup = True
                            break
                    if has_pullup:
                        break
                if not has_pullup:
                    pins_desc = ", ".join(f"{pc.comp_def.type_name} {pin.name}" for pc, pin in i2c_pins)
                    issues.append(SafetyIssue(
                        severity="warning",
                        message=f"Missing I2C Pull-up! I2C net {nid} ({pins_desc}) lacks a pull-up resistor to a power rail (VCC/3.3V/5V). Open-drain I2C lines require pull-up resistors (typically 4.7k Ω) to pull the lines high.",
                        net_id=nid
                    ))

        # ── 8. Overvoltage & Direct Power Connection to Signal Check ─────────
        for nid, cps in nets.items():
            power_pins_in_net = []
            signal_pins_in_net = []
            for cp in cps:
                for c_pc, p_def, _pin_name in self.pin_refs_at_cp(cp):
                    if p_def.ptype == PT_POWER:
                        power_pins_in_net.append((c_pc, p_def))
                    elif p_def.ptype in {"io", "digital", "analog", "pwm", "i2c_scl", "i2c_sda"}:
                        if c_pc.comp_def.category not in {"passive", "led"} and c_pc.comp_def.type_name != "4-Pin Button":
                            signal_pins_in_net.append((c_pc, p_def))

            if power_pins_in_net and signal_pins_in_net:
                for s_pc, s_pin in signal_pins_in_net:
                    s_volt = getattr(s_pc.comp_def, "logic_voltage", 3.3)
                    for p_pc, p_pin in power_pins_in_net:
                        p_name = p_pin.name.upper()
                        if "5V" in p_name:
                            p_volt = 5.0
                        elif "3.3V" in p_name or "3V3" in p_name:
                            p_volt = 3.3
                        elif "VIN" in p_name:
                            p_volt = 9.0
                        else:
                            p_volt = getattr(p_pc.comp_def, "logic_voltage", 3.3)

                        if p_volt > s_volt:
                            issues.append(SafetyIssue(
                                severity="critical",
                                message=f"Overvoltage Hazard! GPIO Pin '{s_pc.comp_def.type_name} {s_pin.name}' ({s_volt}V logic) is connected directly to Power Pin '{p_pc.comp_def.type_name} {p_pin.name}' ({p_volt}V). This will damage the pin.",
                                comp_id=s_pc.inst_id,
                                net_id=nid
                            ))
                        else:
                            issues.append(SafetyIssue(
                                severity="warning",
                                message=f"Direct Power Connection Warning! GPIO Pin '{s_pc.comp_def.type_name} {s_pin.name}' is connected directly to Power Pin '{p_pc.comp_def.type_name} {p_pin.name}'. If the pin is configured as output driven LOW in code, it will cause a short circuit. Use a pull-up resistor instead.",
                                comp_id=s_pc.inst_id,
                                net_id=nid
                            ))

        return issues

