# Electronics Board Organiser (Breadboard Simulator)

An interactive, Tkinter-based desktop simulator for visually organizing electronics components on a breadboard. It allows you to model your breadboard circuit layout and export the connection data into a clean JSON netlist, which can be fed to AI agents/compilers downstream for programming microcontrollers.

---

## Features

- **Interactive Breadboard Layout**: Move components, draw wires, toggle power rail dividers, and visualize connections.
- **Microcontrollers (Controllers)**: Built-in support for popular microcontrollers like **Arduino Uno R3**, **ESP-WROOM-32**, and **Teensy 4.0**.
- **Visual Microcontroller Flipping**: Toggle physical pin alignment (DIP layout) both on-board and off-board to match your physical setup.
- **Automatic Netlist Logic**: Tracks electrical connections across grid holes, power rails, and off-board pinouts.
- **GND Connectivity Check**: Warns you if required ground pins are disconnected before exporting.
- **Export to JSON**: Generates a standard JSON representation of the board state for automated code-generation agents.

---

## Installation & Running

This project uses standard Python GUI libraries (`tkinter`), requiring no external dependencies.

```bash
python main.py
```

### Controls

- **Left-Click**: Select, drag, place components, and start/end wires.
- **Right-Click**: Open context menu to delete items, change colors, or flip microcontrollers.
- **Ctrl + Scroll / Zoom Buttons**: Zoom in and out of the board layout.
- **Escape**: Cancel current placing/wiring operation.

---

## JSON Netlist Export

The exported JSON structure describes:
- **Board Configuration**: Row count, rails visible, and divider points.
- **Microcontroller Connections**: Pin-by-pin breakdown of what other component pins are connected to each controller pin.
- **Component Definitions**: List of placed components, categories, positions, and GND status.
- **Netlist**: Computed list of connected nodes across the breadboard.
