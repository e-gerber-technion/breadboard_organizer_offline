# main.py  – application window, toolbar, sidebar and JSON export
from __future__ import annotations

import json
import os
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Optional

from components import ALL_COMPONENTS, CONTROLLERS, NON_CONTROLLERS, ComponentDef
from constants import (
    MODE_SELECT, MODE_PLACE, MODE_WIRE, MODE_DELETE, MODE_DIVIDER, MODE_PAN,
    C_WIRE_PALETTE, ALL_RAILS,
    RAIL_LEFT_MINUS, RAIL_LEFT_PLUS, RAIL_RIGHT_PLUS, RAIL_RIGHT_MINUS,
)
from model import BoardState, PT_GND
from canvas import BreadboardCanvas


# ═══════════════════════════════════════════════════════════════════════════════
#  Export
# ═══════════════════════════════════════════════════════════════════════════════


# ═══════════════════════════════════════════════════════════════════════════════
#  ToolTip
# ═══════════════════════════════════════════════════════════════════════════════

class ToolTip:
    """Lightweight hover tooltip for any tkinter widget."""
    def __init__(self, widget: tk.Widget, text: str, delay: int = 600):
        self.widget = widget
        self.text   = text
        self.delay  = delay
        self._job   = None
        self._tip   = None
        widget.bind("<Enter>",       self._schedule, add="+")
        widget.bind("<Leave>",       self._cancel,   add="+")
        widget.bind("<ButtonPress>", self._cancel,   add="+")

    def _schedule(self, _e=None):
        self._cancel()
        self._job = self.widget.after(self.delay, self._show)

    def _cancel(self, _e=None):
        if self._job:
            self.widget.after_cancel(self._job)
            self._job = None
        if self._tip:
            self._tip.destroy()
            self._tip = None

    def _show(self):
        x = self.widget.winfo_rootx() + self.widget.winfo_width() // 2
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self._tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        tk.Label(tw, text=self.text, justify=tk.LEFT,
                 background="#FFFFCC", foreground="#333333",
                 relief=tk.SOLID, borderwidth=1,
                 font=("Helvetica", 9), padx=6, pady=3).pack()


# (Export section follows)
# ═══════════════════════════════════════════════════════════════════════════════
#  Export (original)
# ═══════════════════════════════════════════════════════════════════════════════

def build_export(state: BoardState) -> dict:
    """Build a JSON-serialisable dict describing the full board state."""
    nets     = state.compute_nets()
    gnd_ids  = state.gnd_net_ids(nets)

    # Run safety checks
    issues = state.analyze_safety()
    safety_data = []
    for issue in issues:
        safety_data.append({
            "severity": issue.severity,
            "message":  issue.message,
            "net_id":   issue.net_id,
            "comp_id":  issue.comp_id
        })

    # Helper: find net id for a CP
    def net_of(cp):
        for nid, cps in nets.items():
            if cp in cps:
                return nid
        return None

    # Build net descriptions
    net_descriptions = {}
    for nid, cps in nets.items():
        node_list = []
        for cp in cps:
            if cp[0] == "hole":
                node_list.append({"type": "hole", "row": cp[1], "col": cp[2]})
            elif cp[0] == "rail":
                node_list.append({"type": "rail", "rail": cp[1], "idx": cp[2]})
            elif cp[0] == "pin":
                inst_id  = cp[1]
                pin_key  = cp[2]
                pin_name = pin_key.split("__", 1)[-1] if "__" in pin_key else pin_key
                pc = state.get_component(inst_id)
                cname = pc.comp_def.type_name if pc else "?"
                node_list.append({"type": "pin", "component": cname,
                                  "instance": inst_id, "pin": pin_name})
        net_descriptions[str(nid)] = {
            "is_gnd": nid in gnd_ids,
            "nodes": node_list,
        }

    # Controller connections
    ctrl = state.controller()
    ctrl_connections = []
    if ctrl:
        for i, (label, cp) in enumerate(ctrl.connection_points()):
            nid = net_of(cp)
            if nid is None:
                continue
            # Find all non-controller pins in this net
            partners = []
            for cp2 in nets[nid]:
                if cp2 == cp:
                    continue
                if cp2[0] == "pin":
                    other_id = cp2[1]
                    other_pc = state.get_component(other_id)
                    if other_pc and other_pc.inst_id != ctrl.inst_id:
                        pin_key2 = cp2[2]
                        pname2   = pin_key2.split("__", 1)[-1] if "__" in pin_key2 else pin_key2
                        partners.append({
                            "component": other_pc.comp_def.type_name,
                            "instance":  other_id,
                            "pin":       pname2,
                        })
                elif cp2[0] == "hole":
                    # Check if any on-board component pin is at this hole
                    r, c = cp2[1], cp2[2]
                    for other_pc in state.components:
                        if other_pc.inst_id == ctrl.inst_id:
                            continue
                        for j, (lbl2, cp3) in enumerate(other_pc.connection_points()):
                            if cp3 == cp2:
                                partners.append({
                                    "component": other_pc.comp_def.type_name,
                                    "instance":  other_pc.inst_id,
                                    "pin":       lbl2,
                                })
            ctrl_pin_info = ctrl.comp_def.all_pins[i] if i < len(ctrl.comp_def.all_pins) else None
            ctrl_connections.append({
                "controller_pin": label,
                "pin_type":       ctrl_pin_info.ptype if ctrl_pin_info else "io",
                "net":            nid,
                "is_gnd":         nid in gnd_ids,
                "connected_to":   partners,
            })

    # Component list with GND-connection check
    component_list = []
    for pc in state.components:
        if pc.comp_def.category == "controller":
            continue
        pins_info = []
        for i, (label, cp) in enumerate(pc.connection_points()):
            nid     = net_of(cp)
            is_gnd  = (nid in gnd_ids) if nid is not None else False
            pd      = pc.comp_def.all_pins[i] if i < len(pc.comp_def.all_pins) else None
            pins_info.append({
                "pin":          label,
                "pin_type":     pd.ptype if pd else "io",
                "net":          nid,
                "gnd_connected": is_gnd,
                "note":         pd.note if pd else "",
            })
        # GND warning
        expects_gnd   = any(pd.ptype == PT_GND for pd in pc.comp_def.all_pins)
        gnd_pins_ok   = all(
            p["gnd_connected"] for p in pins_info if p["pin_type"] == PT_GND
        ) if expects_gnd else True

        component_list.append({
            "type":         pc.comp_def.type_name,
            "instance":     pc.inst_id,
            "category":     pc.comp_def.category,
            "on_board":     pc.on_board,
            "anchor_row":   pc.anchor_row if pc.on_board else None,
            "anchor_col":   pc.anchor_col if pc.on_board else None,
            "rotated":      getattr(pc, "rotated", False),
            "flipped":      getattr(pc, "flipped", False),
            "gnd_warning":  expects_gnd and not gnd_pins_ok,
            "pins":         pins_info,
        })

    return {
        "board": {
            "num_rows":        state.num_rows,
            "rails_visible":   state.rails_visible,
            "dividers_after_rows": sorted(state.dividers),
        },
        "controller": {
            "type":        ctrl.comp_def.type_name if ctrl else None,
            "instance":    ctrl.inst_id            if ctrl else None,
            "connections": ctrl_connections,
        },
        "components": component_list,
        "nets":        net_descriptions,
        "safety_issues": safety_data,
    }


# ═══════════════════════════════════════════════════════════════════════════════
#  Controller selection dialog
# ═══════════════════════════════════════════════════════════════════════════════

class ControllerDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("Select Controller")
        self.resizable(False, False)
        self.grab_set()
        self.result: Optional[ComponentDef] = None

        tk.Label(self, text="Choose your microcontroller:",
                 font=("Helvetica", 11)).pack(padx=20, pady=(16, 8))

        self._var = tk.StringVar(value=CONTROLLERS[0].type_name)
        for cd in CONTROLLERS:
            frm = tk.Frame(self)
            frm.pack(fill=tk.X, padx=20, pady=2)
            tk.Radiobutton(frm, text=cd.type_name,
                           variable=self._var, value=cd.type_name,
                           font=("Helvetica", 10),
                           width=26, anchor="w").pack(side=tk.LEFT)
            tk.Label(frm, text=cd.description,
                     font=("Helvetica", 8), fg="#666666",
                     wraplength=300, justify=tk.LEFT).pack(side=tk.LEFT, padx=6)

        btn_frm = tk.Frame(self)
        btn_frm.pack(pady=14)
        tk.Button(btn_frm, text="OK", width=10, command=self._ok,
                  font=("Helvetica", 10, "bold")).pack(side=tk.LEFT, padx=6)
        tk.Button(btn_frm, text="No controller yet", width=16,
                  command=self.destroy,
                  font=("Helvetica", 9)).pack(side=tk.LEFT, padx=6)

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.wait_window(self)

    def _ok(self):
        from components import COMPONENT_BY_NAME
        self.result = COMPONENT_BY_NAME.get(self._var.get())
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════════
#  Board-settings dialog
# ═══════════════════════════════════════════════════════════════════════════════

class BoardSettingsDialog(tk.Toplevel):
    def __init__(self, parent, state: BoardState):
        super().__init__(parent)
        self.title("Board Settings")
        self.resizable(False, False)
        self.grab_set()
        self.state  = state
        self.ok_pressed = False

        tk.Label(self, text="Number of rows:", font=("Helvetica", 10)).grid(
            row=0, column=0, padx=16, pady=(14, 4), sticky="e")
        self._rows_var = tk.IntVar(value=state.num_rows)
        sb = tk.Spinbox(self, from_=10, to=200, textvariable=self._rows_var, width=6,
                        font=("Helvetica", 10))
        sb.grid(row=0, column=1, padx=8, pady=(14, 4), sticky="w")

        tk.Label(self, text="Power rails:", font=("Helvetica", 10)).grid(
            row=1, column=0, padx=16, pady=4, sticky="e")
        rail_frame = tk.Frame(self)
        rail_frame.grid(row=1, column=1, padx=8, pady=4, sticky="w")
        self._rail_vars: dict[str, tk.BooleanVar] = {}
        labels = {
            RAIL_LEFT_MINUS:  "Left  −  (outer)",
            RAIL_LEFT_PLUS:   "Left  +  (inner)",
            RAIL_RIGHT_PLUS:  "Right +  (inner)",
            RAIL_RIGHT_MINUS: "Right −  (outer)",
        }
        for i, rail_id in enumerate(ALL_RAILS):
            v = tk.BooleanVar(value=state.rails_visible.get(rail_id, True))
            self._rail_vars[rail_id] = v
            tk.Checkbutton(rail_frame, text=labels[rail_id], variable=v,
                           font=("Helvetica", 9)).grid(
                row=i // 2, column=i % 2, sticky="w", padx=4)

        btn_frm = tk.Frame(self)
        btn_frm.grid(row=2, column=0, columnspan=2, pady=12)
        tk.Button(btn_frm, text="Apply", width=9, command=self._apply,
                  font=("Helvetica", 10, "bold")).pack(side=tk.LEFT, padx=6)
        tk.Button(btn_frm, text="Cancel", width=9, command=self.destroy,
                  font=("Helvetica", 9)).pack(side=tk.LEFT, padx=6)

        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self.wait_window(self)

    def _apply(self) -> None:
        new_rows = self._rows_var.get()
        self.state.resize(new_rows)
        for rail_id, var in self._rail_vars.items():
            self.state.rails_visible[rail_id] = var.get()
        self.ok_pressed = True
        self.destroy()


# ═══════════════════════════════════════════════════════════════════════════════
#  Main Application
# ═══════════════════════════════════════════════════════════════════════════════

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Electronics Board Organiser")
        self.geometry("1300x780")
        self.minsize(900, 600)

        self.state = BoardState(num_rows=30)

        self._build_ui()
        self._set_mode(MODE_SELECT)   # initialise button highlight state
        self._refresh_netlist()
        self._ask_controller()

    # ── UI construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Top toolbar
        toolbar = tk.Frame(self, bd=1, relief=tk.RAISED)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        self._build_toolbar(toolbar)

        # Paned layout: left sidebar | canvas | right panel
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashwidth=4,
                                sashrelief=tk.RAISED)
        paned.pack(fill=tk.BOTH, expand=True)

        left = tk.Frame(paned, width=210)
        left.pack_propagate(False)
        paned.add(left, minsize=160)
        self._build_sidebar(left)

        self._bcanvas = BreadboardCanvas(paned, self.state,
                                          on_status=self._set_status,
                                          on_change=self._refresh_netlist)
        paned.add(self._bcanvas, minsize=600)

        right = tk.Frame(paned, width=220)
        right.pack_propagate(False)
        paned.add(right, minsize=180)
        self._build_right_panel(right)

        # Status bar
        self._status_var = tk.StringVar(value="Ready")
        tk.Label(self, textvariable=self._status_var, anchor="w",
                 font=("Helvetica", 9), bd=1, relief=tk.SUNKEN).pack(
            side=tk.BOTTOM, fill=tk.X, ipady=2)

    def _build_toolbar(self, parent) -> None:
           self._mode_buttons: dict = {}   # mode_key → (widget, normal_bg)

           def mbtn(text, cmd, tip="", bg="#E0E0E0", fg="#212121", bold=False,
                    mode_key=None):
              font = ("Helvetica", 9, "bold") if bold else ("Helvetica", 9)
              b = tk.Button(parent, text=text, command=cmd,
                         font=font, relief=tk.FLAT, bg=bg, fg=fg,
                         activebackground="#BDBDBD",
                         padx=7, pady=3, cursor="hand2")
              b.pack(side=tk.LEFT, padx=2, pady=3)
              if tip:
                 ToolTip(b, tip)
              if mode_key is not None:
                 self._mode_buttons[mode_key] = (b, bg)
              return b

           def sep():
              tk.Frame(parent, width=1, bg="#BDBDBD").pack(
                 side=tk.LEFT, fill=tk.Y, padx=5, pady=3)

           # ── Edit modes ────────────────────────────────────────────────────────
           mbtn("⬡  Select",    lambda: self._set_mode(MODE_SELECT),
               tip="Select / move components and wires  (Esc to cancel)",
               bg="#E3F2FD", fg="#0D47A1", mode_key=MODE_SELECT)
           mbtn("〰  Wire",      lambda: self._set_mode(MODE_WIRE),
               tip="Draw a wire between two connection points",
               bg="#E8F5E9", fg="#1B5E20", mode_key=MODE_WIRE)
           mbtn("✂  Delete",    lambda: self._set_mode(MODE_DELETE),
               tip="Click a component or wire to delete it",
               bg="#FFEBEE", fg="#B71C1C", mode_key=MODE_DELETE)
           mbtn("╌  Divider",   lambda: self._set_mode(MODE_DIVIDER),
               tip="Click between two rows to toggle a rail divider",
               bg="#FFF8E1", fg="#E65100", mode_key=MODE_DIVIDER)
           mbtn("✥  Move Board", lambda: self._set_mode(MODE_PAN),
               tip="Drag to reposition the breadboard in the workspace  (middle-drag pans the view)",
               bg="#F3E5F5", fg="#4A148C", mode_key=MODE_PAN)

           sep()

           # ── Zoom ──────────────────────────────────────────────────────────────
           mbtn("🔍+", self._zoom_in,
               tip="Zoom in  (Ctrl + scroll up)",    bg="#ECEFF1")
           mbtn("🔍−", self._zoom_out,
               tip="Zoom out  (Ctrl + scroll down)", bg="#ECEFF1")
           mbtn("1:1", self._zoom_reset,
               tip="Reset zoom to 100 %",            bg="#ECEFF1")

           sep()

           # ── Settings & export ─────────────────────────────────────────────────
           mbtn("⚙  Board…",        self._board_settings,
               tip="Configure number of rows and visible power rails")
           mbtn("🎨  Wire colour…", self._pick_wire_color,
               tip="Choose colour for the next wire drawn")

           sep()

           mbtn("💾  Export JSON…", self._export_json,
               tip="Export board connections to a JSON file for downstream agents",
               bg="#C8E6C9", fg="#1B5E20", bold=True)

           # Mode indicator (right-aligned)
           self._mode_label = tk.Label(parent, text="Mode: SELECT",
                                 font=("Helvetica", 9, "bold"),
                                 fg="#1565C0", bg=parent.cget("bg"))
           self._mode_label.pack(side=tk.RIGHT, padx=12)

    def _build_sidebar(self, parent) -> None:
        tk.Label(parent, text="Components", font=("Helvetica", 10, "bold"),
                 bg="#ECEFF1").pack(fill=tk.X, ipady=4)

        # Search box
        search_var = tk.StringVar()
        search_var.trace_add("write", lambda *_: self._filter_list(search_var.get()))
        tk.Entry(parent, textvariable=search_var, font=("Helvetica", 9)).pack(
            fill=tk.X, padx=6, pady=(4, 2))

        frm = tk.Frame(parent)
        frm.pack(fill=tk.BOTH, expand=True, padx=4, pady=2)

        vsb = tk.Scrollbar(frm, orient=tk.VERTICAL)
        self._comp_list = tk.Listbox(frm, font=("Helvetica", 9),
                                      yscrollcommand=vsb.set,
                                      selectmode=tk.SINGLE, activestyle="none",
                                      exportselection=False)
        vsb.configure(command=self._comp_list.yview)
        self._comp_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        self._comp_list.bind("<<ListboxSelect>>", self._on_comp_select)
        self._comp_list.bind("<Double-Button-1>", self._on_comp_double)

        # Hint label
        tk.Label(parent, text="Click to select, then click\nboard/workspace to place.",
                 font=("Helvetica", 8), fg="#666666", justify=tk.LEFT).pack(
            pady=4, padx=6, anchor="w")

        # Place button
        self._place_btn = tk.Button(parent, text="Place selected ▶",
                                     font=("Helvetica", 9, "bold"),
                                     command=self._place_selected, state=tk.DISABLED)
        self._place_btn.pack(fill=tk.X, padx=6, pady=4)

        self._filter_list("")

    def _build_right_panel(self, parent) -> None:
        tk.Label(parent, text="Info / Rules / Nets", font=("Helvetica", 10, "bold"),
                 bg="#ECEFF1").pack(fill=tk.X, ipady=4)
        self._info_text = tk.Text(parent, font=("Helvetica", 8), state=tk.DISABLED,
                                   wrap=tk.WORD, bg="#FAFAFA")
        self._info_text.tag_configure("critical", foreground="#D32F2F", font=("Helvetica", 8, "bold"))
        self._info_text.tag_configure("warning", foreground="#F57C00", font=("Helvetica", 8, "bold"))
        self._info_text.tag_configure("ok", foreground="#388E3C", font=("Helvetica", 8, "bold"))
        self._info_text.tag_configure("header", font=("Helvetica", 9, "bold"))

        vsb = tk.Scrollbar(parent, command=self._info_text.yview)
        self._info_text.configure(yscrollcommand=vsb.set)
        self._info_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(4, 0), pady=4)
        vsb.pack(side=tk.RIGHT, fill=tk.Y, pady=4)

        tk.Button(parent, text="Refresh netlist",
                  font=("Helvetica", 8), command=self._refresh_netlist).pack(
            side=tk.BOTTOM, fill=tk.X, padx=4, pady=4)

    # ── Component list ────────────────────────────────────────────────────────

    def _filter_list(self, query: str) -> None:
        self._comp_list.delete(0, tk.END)
        q = query.lower()
        self._filtered: list[ComponentDef] = []
        for cd in ALL_COMPONENTS:
            if q in cd.type_name.lower() or q in cd.category.lower():
                self._comp_list.insert(tk.END, f"  {cd.type_name}")
                self._filtered.append(cd)
        self._place_btn.configure(state=tk.DISABLED)

    def _on_comp_select(self, _event) -> None:
        sel = self._comp_list.curselection()
        self._place_btn.configure(state=tk.NORMAL if sel else tk.DISABLED)

    def _on_comp_double(self, _event) -> None:
        self._place_selected()

    def _place_selected(self) -> None:
        sel = self._comp_list.curselection()
        if not sel:
            return
        cd = self._filtered[sel[0]]
        # If user tries to place a second controller, warn
        if cd.category == "controller" and self.state.controller() is not None:
            if not messagebox.askyesno(
                    "Replace controller?",
                    "A controller is already on the board. Replace it?"):
                return
            old = self.state.controller()
            if old:
                self.state.remove_component(old.inst_id)
        self._set_mode(MODE_PLACE, placing_def=cd)

    # ── Mode & status ─────────────────────────────────────────────────────────

    def _set_mode(self, mode: str, placing_def=None) -> None:
        self._bcanvas.set_mode(mode, placing_def=placing_def)
        labels = {
            MODE_SELECT:  "SELECT",
            MODE_PLACE:   f"PLACE – {placing_def.type_name if placing_def else '?'}",
            MODE_WIRE:    "WIRE",
            MODE_DELETE:  "DELETE",
            MODE_DIVIDER: "DIVIDER",
            MODE_PAN:     "MOVE BOARD",
        }
        self._mode_label.configure(text=f"Mode: {labels.get(mode, mode.upper())}")
        # Highlight active mode button, reset all others
        for m, (btn, normal_bg) in self._mode_buttons.items():
            if m == mode:
                btn.configure(relief=tk.SUNKEN, bg="#FFD54F")   # amber = active
            else:
                btn.configure(relief=tk.FLAT, bg=normal_bg)

    def _set_status(self, msg: str) -> None:
        self._status_var.set(msg)

    # ── Controller helper ─────────────────────────────────────────────────────

    def _ask_controller(self) -> None:
        dlg = ControllerDialog(self)
        if dlg.result:
            self._set_mode(MODE_PLACE, placing_def=dlg.result)
            self._set_status(
                f"Click the board to place {dlg.result.type_name}  "
                "(left side anchor = first left pin)")

    # ── Zoom helpers ──────────────────────────────────────────────────────────

    def _zoom_in(self)    -> None: self._bcanvas.zoom_in()
    def _zoom_out(self)   -> None: self._bcanvas.zoom_out()
    def _zoom_reset(self) -> None: self._bcanvas.zoom_reset()

    # ── Board settings ────────────────────────────────────────────────────────

    def _board_settings(self) -> None:
        dlg = BoardSettingsDialog(self, self.state)
        if dlg.ok_pressed:
            self._bcanvas.refresh_layout()

    # ── Wire colour ───────────────────────────────────────────────────────────

    def _pick_wire_color(self) -> None:
        from tkinter import colorchooser
        color = colorchooser.askcolor(
            color=self._bcanvas._wire_color, title="Next wire colour")[1]
        if color:
            self._bcanvas.set_wire_color(color)
            self._set_status(f"Next wire colour: {color}")

    # ── Netlist panel ─────────────────────────────────────────────────────────

    def _refresh_netlist(self) -> None:
        self._info_text.configure(state=tk.NORMAL)
        self._info_text.delete("1.0", tk.END)

        # ── 1. Safety analysis ────────────────────────────────────────────────
        self._info_text.insert(tk.END, "=== SAFETY RULES ===\n", "header")
        issues = self.state.analyze_safety()
        if not issues:
            self._info_text.insert(tk.END, "✔ All checks passed. No issues detected.\n\n", "ok")
        else:
            for issue in issues:
                prefix = "⚠ CRITICAL: " if issue.severity == "critical" else "⚠ WARNING: "
                tag = issue.severity
                self._info_text.insert(tk.END, f"{prefix}{issue.message}\n\n", tag)

        # ── 2. Netlist ────────────────────────────────────────────────────────
        self._info_text.insert(tk.END, "=== NETS & CONNECTIONS ===\n", "header")
        nets    = self.state.compute_nets()
        gnd_ids = self.state.gnd_net_ids(nets)
        lines   = []

        ctrl = self.state.controller()
        if ctrl:
            lines.append(f"Controller: {ctrl.comp_def.type_name}\n")
        else:
            lines.append("No controller placed.\n")

        for nid, cps in sorted(nets.items()):
            # Only show non-trivial nets (>1 node, or containing a pin)
            has_pin = any(cp[0] == "pin" for cp in cps)
            if len(cps) <= 6 and not has_pin:
                continue
            tag = " [GND]" if nid in gnd_ids else ""
            lines.append(f"Net {nid}{tag}:")
            for cp in sorted(cps, key=str):
                if cp[0] == "pin":
                    pc = self.state.get_component(cp[1])
                    cname = pc.comp_def.type_name if pc else "?"
                    lines.append(f"  {cname} · {cp[2].split('__',1)[-1]}")
            lines.append("")

        text = "\n".join(lines) if lines else "No notable nets yet."
        self._info_text.insert(tk.END, text)
        self._info_text.configure(state=tk.DISABLED)

    # ── Export ────────────────────────────────────────────────────────────────

    def _export_json(self) -> None:
        if not self.state.components:
            messagebox.showinfo("Nothing to export",
                                "Place at least one component first.")
            return

        # Safety validation checks before exporting
        issues = self.state.analyze_safety()
        if issues:
            critical_msgs = [f"  • {i.message}" for i in issues if i.severity == "critical"]
            warning_msgs  = [f"  • {i.message}" for i in issues if i.severity == "warning"]

            err_msg = ""
            if critical_msgs:
                err_msg += "CRITICAL SAFETY ERRORS:\n" + "\n".join(critical_msgs) + "\n\n"
            if warning_msgs:
                err_msg += "SAFETY WARNINGS:\n" + "\n".join(warning_msgs) + "\n\n"

            err_msg += "Do you want to proceed with the export anyway?"
            if not messagebox.askyesno("Safety Validation Failed", err_msg):
                return

        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
            title="Export board data",
        )
        if not path:
            return
        data = build_export(self.state)
        # GND warnings
        warnings = [
            f"  • {c['type']} ({c['instance']})"
            for c in data["components"] if c.get("gnd_warning")
        ]
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        msg = f"Exported to:\n{os.path.basename(path)}"
        if warnings:
            msg += "\n\n⚠ GND not connected for:\n" + "\n".join(warnings)
        messagebox.showinfo("Export complete", msg)
        self._set_status(f"Exported → {path}")



# ═══════════════════════════════════════════════════════════════════════════════
#  Entry point
# ═══════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    app = App()
    app.mainloop()
