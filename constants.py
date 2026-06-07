# constants.py  – layout, colour, and mode constants

# ── Breadboard grid ───────────────────────────────────────────────────────────
HOLE_SPACING  = 22      # px between adjacent holes (at zoom = 1.0)
HOLE_RADIUS   = 3.8     # px – drawn hole circle radius

# Margins & label areas
BOARD_MARGIN_X = 30
BOARD_MARGIN_Y = 20
ROW_LABEL_W    = 26     # px reserved for row-number labels on each side
COL_LABEL_H    = 16     # px reserved for column-letter labels at top

# Power-rail geometry (vertical strips along the long side of the board)
RAIL_TO_GRID_GAP = 6    # px gap between inner rail column and row-label area

# Off-board workspace
OFFBOARD_ZONE_X_PAD = 80   # initial gap (px) between board right edge and off-board zone

# ── Column definitions ────────────────────────────────────────────────────────
ALL_COLS   = ['a', 'b', 'c', 'd', 'e', 'f', 'g', 'h', 'i', 'j']
LEFT_COLS  = ['a', 'b', 'c', 'd', 'e']
RIGHT_COLS = ['f', 'g', 'h', 'i', 'j']

# x-index for each column (gap of 2 units between 'e' and 'f')
COL_X_IDX = {
    'a': 0, 'b': 1, 'c': 2, 'd': 3, 'e': 4,
    'f': 7, 'g': 8, 'h': 9, 'i': 10, 'j': 11
}
BOARD_WIDTH_UNITS = 12   # 5 + 2-gap + 5 (column indices 0–11)

# Mirror a column across the central gap
MIRROR_COL = {
    'a': 'j', 'b': 'i', 'c': 'h', 'd': 'g', 'e': 'f',
    'f': 'e', 'g': 'd', 'h': 'c', 'i': 'b', 'j': 'a'
}

# ── Rail IDs  (vertical strips running along the long side of the board) ──────
# Left side : MINUS is outermost, PLUS is innermost (closest to the main grid)
# Right side: PLUS is innermost, MINUS is outermost
RAIL_LEFT_MINUS  = "left_minus"
RAIL_LEFT_PLUS   = "left_plus"
RAIL_RIGHT_PLUS  = "right_plus"
RAIL_RIGHT_MINUS = "right_minus"
ALL_RAILS = [RAIL_LEFT_MINUS, RAIL_LEFT_PLUS, RAIL_RIGHT_PLUS, RAIL_RIGHT_MINUS]

# ── Zoom ──────────────────────────────────────────────────────────────────────
ZOOM_MIN  = 0.25
ZOOM_MAX  = 4.0
ZOOM_STEP = 1.15   # multiply/divide per Ctrl+scroll tick

# ── Colours ───────────────────────────────────────────────────────────────────
C_CANVAS_BG      = "#2E2E2E"   # dark workspace background
C_BOARD          = "#FFFDE7"
C_BOARD_BORDER   = "#BDBDBD"
C_HOLE           = "#2A2A2A"
C_HOLE_HOVER     = "#FF8C00"
C_HOLE_OCCUPIED  = "#555555"
C_RAIL_PLUS_BG   = "#FFEBEE"
C_RAIL_MINUS_BG  = "#E3F2FD"
C_RAIL_DOT_PLUS  = "#C62828"
C_RAIL_DOT_MINUS = "#1565C0"
C_RAIL_BORDER    = "#9E9E9E"
C_DIVIDER        = "#E53935"
C_DIVIDER_LABEL  = "#B71C1C"
C_GHOST_FILL     = "#90CAF9"
C_GHOST_OUTLINE  = "#1565C0"
C_SELECTION      = "#FF6F00"
C_COMP_OUTLINE   = "#212121"
C_PIN_DOT        = "#EEEEEE"
C_PIN_HOVER      = "#FFCC02"
C_WIRE_PALETTE   = [
    "#E53935",  # red
    "#1E88E5",  # blue
    "#43A047",  # green
    "#FB8C00",  # orange
    "#8E24AA",  # purple
    "#00ACC1",  # cyan
    "#F9A825",  # yellow
    "#6D4C41",  # brown
]

# ── Off-board component visuals ───────────────────────────────────────────────
OFFBOARD_PIN_SPACING = 20   # px between consecutive pins on a side
OFFBOARD_PADDING_X   = 10
OFFBOARD_PADDING_Y   = 8
OFFBOARD_MIN_WIDTH   = 110

# ── Interaction modes ─────────────────────────────────────────────────────────
MODE_SELECT   = "select"
MODE_PLACE    = "place"
MODE_WIRE     = "wire"
MODE_DELETE   = "delete"
MODE_DIVIDER  = "divider"
MODE_PAN      = "pan"       # drag the board within the canvas workspace
