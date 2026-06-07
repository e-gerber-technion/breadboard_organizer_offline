# components.py  – component type definitions and pin-out data
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List

# ── Pin types ─────────────────────────────────────────────────────────────────
PT_IO      = "io"
PT_GND     = "gnd"
PT_POWER   = "power"
PT_DIGITAL = "digital"
PT_ANALOG  = "analog"
PT_PWM     = "pwm"
PT_I2C_SCL = "i2c_scl"
PT_I2C_SDA = "i2c_sda"

GND_PIN_TYPES  = {PT_GND}
PWR_PIN_TYPES  = {PT_POWER}


@dataclass
class PinDef:
    name: str
    ptype: str = PT_IO
    note: str  = ""


def P(name: str, ptype: str = PT_IO, note: str = "") -> PinDef:
    return PinDef(name, ptype, note)


@dataclass
class ComponentDef:
    """Definition of a component *type* (shared, never mutated)."""
    type_name:   str
    category:    str   # "controller" | "display" | "input" | "led" | "audio"
    color:       str   # hex fill colour for body
    # Pins in the *left* column (top→bottom). For single-sided components,
    # put all pins here; right_pins stays empty.
    left_pins:   List[PinDef] = field(default_factory=list)
    # Pins in the *right* column (top→bottom). Non-empty ⇒ straddles the gap.
    right_pins:  List[PinDef] = field(default_factory=list)
    description: str = ""

    # ── derived helpers ───────────────────────────────────────────────────────
    @property
    def is_dip(self) -> bool:
        """True when component has pins on both sides (straddles the gap)."""
        return bool(self.right_pins)

    @property
    def height_in_rows(self) -> int:
        return max(len(self.left_pins), len(self.right_pins), 1)

    @property
    def all_pins(self) -> List[PinDef]:
        return self.left_pins + self.right_pins

    def gnd_pins(self) -> List[PinDef]:
        return [p for p in self.all_pins if p.ptype in GND_PIN_TYPES]


# ═══════════════════════════════════════════════════════════════════════════════
#  CONTROLLERS
# ═══════════════════════════════════════════════════════════════════════════════

ARDUINO_UNO_R3 = ComponentDef(
    type_name = "Arduino UNO R3",
    category  = "controller",
    color     = "#1565C0",
    left_pins = [
        P("IOREF",    PT_POWER),
        P("RESET"),
        P("3.3V",     PT_POWER),
        P("5V",       PT_POWER),
        P("GND",      PT_GND),
        P("GND",      PT_GND),
        P("VIN",      PT_POWER),
        P("A0",       PT_ANALOG),
        P("A1",       PT_ANALOG),
        P("A2",       PT_ANALOG),
        P("A3",       PT_ANALOG),
        P("A4/SDA",   PT_I2C_SDA),
        P("A5/SCL",   PT_I2C_SCL),
    ],
    right_pins = [
        P("SCL",        PT_I2C_SCL),
        P("SDA",        PT_I2C_SDA),
        P("AREF"),
        P("GND",        PT_GND),
        P("D13/SCK",    PT_DIGITAL),
        P("D12/MISO",   PT_DIGITAL),
        P("D11/MOSI",   PT_PWM),
        P("D10/SS",     PT_PWM),
        P("D9",         PT_PWM),
        P("D8",         PT_DIGITAL),
        P("D7",         PT_DIGITAL),
        P("D6",         PT_PWM),
        P("D5",         PT_PWM),
        P("D4",         PT_DIGITAL),
        P("D3",         PT_PWM),
        P("D2",         PT_DIGITAL),
        P("D1/TX",      PT_DIGITAL),
        P("D0/RX",      PT_DIGITAL),
    ],
    description = "Arduino UNO R3 – 5 V, AVR ATmega328P",
)

ESP32_WROOM = ComponentDef(
    type_name = "ESP-WROOM-32",
    category  = "controller",
    color     = "#2E7D32",
    left_pins = [
        P("GND",          PT_GND),
        P("3V3",          PT_POWER),
        P("EN"),
        P("GPIO36/VP",    PT_ANALOG),
        P("GPIO39/VN",    PT_ANALOG),
        P("GPIO34",       PT_ANALOG),
        P("GPIO35",       PT_ANALOG),
        P("GPIO32",       PT_IO),
        P("GPIO33",       PT_IO),
        P("GPIO25/DAC1",  PT_IO),
        P("GPIO26/DAC2",  PT_IO),
        P("GPIO27",       PT_IO),
        P("GPIO14",       PT_IO),
        P("GPIO12",       PT_IO),
        P("GND",          PT_GND),
        P("GPIO13",       PT_IO),
        P("GPIO9/SD2",    PT_IO),
        P("GPIO10/SD3",   PT_IO),
        P("GPIO11/CMD",   PT_IO),
    ],
    right_pins = [
        P("VIN",          PT_POWER),
        P("GND",          PT_GND),
        P("GPIO23",       PT_IO),
        P("GPIO22/SCL",   PT_I2C_SCL),
        P("GPIO1/TX",     PT_DIGITAL),
        P("GPIO0/RX",     PT_DIGITAL),
        P("GPIO21/SDA",   PT_I2C_SDA),
        P("GND",          PT_GND),
        P("GPIO19/MISO",  PT_IO),
        P("GPIO18/SCK",   PT_IO),
        P("GPIO5/SS",     PT_IO),
        P("GPIO17",       PT_IO),
        P("GPIO16",       PT_IO),
        P("GPIO4",        PT_IO),
        P("GPIO0/BOOT",   PT_IO),
        P("GPIO2",        PT_IO),
        P("GPIO15",       PT_IO),
        P("GPIO8/SD1",    PT_IO),
        P("GPIO7/SD0",    PT_IO),
    ],
    description = "ESP-WROOM-32 – Wi-Fi/BT, 3.3 V",
)

TEENSY_40 = ComponentDef(
    type_name = "Teensy 4.0",
    category  = "controller",
    color     = "#6A1B9A",
    left_pins = [
        P("GND",         PT_GND),
        P("D0/RX1",      PT_DIGITAL),
        P("D1/TX1",      PT_DIGITAL),
        P("D2",          PT_DIGITAL),
        P("D3",          PT_PWM),
        P("D4",          PT_PWM),
        P("D5",          PT_PWM),
        P("D6",          PT_PWM),
        P("D7/RX2",      PT_DIGITAL),
        P("D8/TX2",      PT_DIGITAL),
        P("D9",          PT_PWM),
        P("D10",         PT_PWM),
        P("D11/MOSI",    PT_IO),
        P("D12/MISO",    PT_IO),
        P("D13/SCK/LED", PT_IO),
        P("3.3V",        PT_POWER),
        P("A0/D14",      PT_ANALOG),
        P("A1/D15",      PT_ANALOG),
        P("A2/D16",      PT_ANALOG),
        P("A3/D17",      PT_ANALOG),
        P("A4/D18/SDA",  PT_I2C_SDA),
        P("A5/D19/SCL",  PT_I2C_SCL),
        P("A6/D20",      PT_ANALOG),
        P("A7/D21",      PT_ANALOG),
    ],
    right_pins = [
        P("VIN",         PT_POWER),
        P("AGND",        PT_GND),
        P("3.3V",        PT_POWER),
        P("A9/D23",      PT_ANALOG),
        P("A8/D22",      PT_ANALOG),
        P("D21",         PT_IO),
        P("D20",         PT_IO),
        P("D19/SCL",     PT_I2C_SCL),
        P("D18/SDA",     PT_I2C_SDA),
        P("D17",         PT_IO),
        P("D16",         PT_IO),
        P("D15",         PT_IO),
        P("D14",         PT_IO),
        P("GND",         PT_GND),
        P("D24/TX6",     PT_DIGITAL),
        P("D25/RX6",     PT_DIGITAL),
        P("D26",         PT_DIGITAL),
        P("D27",         PT_DIGITAL),
        P("D28/RX7",     PT_DIGITAL),
        P("D29/TX7",     PT_DIGITAL),
        P("D30",         PT_DIGITAL),
        P("D31",         PT_DIGITAL),
        P("D32",         PT_DIGITAL),
        P("GND",         PT_GND),
    ],
    description = "Teensy 4.0 – ARM Cortex-M7, 3.3 V",
)

# ═══════════════════════════════════════════════════════════════════════════════
#  OTHER COMPONENTS
# ═══════════════════════════════════════════════════════════════════════════════

OLED_JMD096D1 = ComponentDef(
    type_name = "JMD0.96D-1 OLED",
    category  = "display",
    color     = "#37474F",
    left_pins = [
        P("GND", PT_GND),
        P("VCC", PT_POWER),
        P("SCL", PT_I2C_SCL),
        P("SDA", PT_I2C_SDA),
    ],
    description = "0.96\" 128×64 I²C OLED display",
)

PUSHBUTTON_4PIN = ComponentDef(
    type_name = "4-Pin Button",
    category  = "input",
    color     = "#F57F17",
    left_pins = [
        P("A1", note="Side A – connected to A2"),
        P("A2", note="Side A – connected to A1"),
    ],
    right_pins = [
        P("B1", note="Side B – connected to B2"),
        P("B2", note="Side B – connected to B1"),
    ],
    description = "Tactile 6×6 mm pushbutton. A1↔A2 always connected; B1↔B2 always connected; press bridges A↔B.",
)

LED_BLUE = ComponentDef(
    type_name = "Blue LED",
    category  = "led",
    color     = "#1E88E5",
    left_pins = [
        P("Anode (+)",   note="Long leg"),
        P("Cathode (−)", PT_GND, note="Short leg"),
    ],
    description = "Blue LED – forward voltage ≈ 3.0 V",
)

LED_RED = ComponentDef(
    type_name = "Red LED",
    category  = "led",
    color     = "#E53935",
    left_pins = [
        P("Anode (+)",   note="Long leg"),
        P("Cathode (−)", PT_GND, note="Short leg"),
    ],
    description = "Red LED – forward voltage ≈ 2.0 V",
)

BUZZER_TMB12A03 = ComponentDef(
    type_name = "TMB12A03 Buzzer",
    category  = "audio",
    color     = "#4E342E",
    left_pins = [
        P("VCC (+)", PT_POWER),
        P("GND (−)", PT_GND),
    ],
    description = "TMB12A03 active buzzer – 3 V, 12 mm",
)

# ═══════════════════════════════════════════════════════════════════════════════
#  Registry
# ═══════════════════════════════════════════════════════════════════════════════

ALL_COMPONENTS: List[ComponentDef] = [
    ARDUINO_UNO_R3,
    ESP32_WROOM,
    TEENSY_40,
    OLED_JMD096D1,
    PUSHBUTTON_4PIN,
    LED_BLUE,
    LED_RED,
    BUZZER_TMB12A03,
]

CONTROLLERS    = [c for c in ALL_COMPONENTS if c.category == "controller"]
NON_CONTROLLERS = [c for c in ALL_COMPONENTS if c.category != "controller"]

COMPONENT_BY_NAME = {c.type_name: c for c in ALL_COMPONENTS}
