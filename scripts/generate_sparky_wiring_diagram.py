#!/usr/bin/env python3
"""
One-off generator for docs/sparky_wiring_diagram.png - the breadboard wiring
plan for Sparky's electronics (ESP32-WROOM + INMP441 mic + MAX98357A amp +
speaker + MAX7219 dot matrix + WS2812B accent LED).

Laid out as four self-contained per-component panels (each showing exactly
which ESP32 pin feeds which component pin) rather than one full-board
diagram with long crossing wires - far easier to read at a glance and to
build from. Every pin name matches the wiring spec given alongside this
diagram exactly.

Not part of the running app; run manually when the wiring changes:
    python scripts/generate_sparky_wiring_diagram.py
"""
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

RED = "#c0392b"
ORANGE = "#d68910"
BLACK = "#222222"
BLUE = "#2874a6"
GRAY = "#666666"

COLOR_FOR = {"5V": RED, "3.3V": ORANGE, "GND": BLACK}


def draw_panel(ax, title, subtitle, rows):
    """rows: list of (esp32_pin_label, component_pin_label, rail_or_signal)
    rail_or_signal is one of "5V", "3.3V", "GND", or "SIG" (a GPIO signal)."""
    ax.set_xlim(0, 10)
    ax.set_ylim(0, len(rows) + 2)
    ax.axis("off")
    ax.set_title(title, fontsize=13, fontweight="bold", color="#0d2436", loc="left")
    if subtitle:
        ax.text(0, len(rows) + 1.35, subtitle, fontsize=8.5, color=GRAY, va="top")

    left_x, right_x = 2.6, 6.8
    for i, (esp_pin, comp_pin, kind) in enumerate(rows):
        y = len(rows) - i
        color = COLOR_FOR.get(kind, BLUE)
        ax.text(left_x - 0.15, y, esp_pin, ha="right", va="center", fontsize=9)
        ax.text(right_x + 0.15, y, comp_pin, ha="left", va="center", fontsize=9)
        ax.plot([left_x, right_x], [y, y], color=color, linewidth=2)
        ax.plot(left_x, y, "o", color=color, markersize=4)
        ax.plot(right_x, y, "o", color=color, markersize=4)

    ax.add_patch(FancyBboxPatch((0.1, 0.3), left_x - 0.5, len(rows) + 0.6,
                                 boxstyle="round,pad=0.05", linewidth=1.3,
                                 edgecolor="#0d2436", facecolor="#eef3f6"))
    ax.text(0.1 + (left_x - 0.5) / 2, len(rows) + 0.55, "ESP32-WROOM",
            ha="center", va="bottom", fontsize=9, fontweight="bold", color="#0d2436")

    ax.add_patch(FancyBboxPatch((right_x + 1.0, 0.3), 10 - (right_x + 1.3), len(rows) + 0.6,
                                 boxstyle="round,pad=0.05", linewidth=1.3,
                                 edgecolor="#0d2436", facecolor="#fdeee1"))


fig, axes = plt.subplots(2, 2, figsize=(15, 11))
fig.suptitle("Sparky Wiring Diagram - per-component pin connections (v2, includes push-to-talk button)",
             fontsize=15, fontweight="bold")

draw_panel(
    axes[0, 0],
    "INMP441 Microphone",
    "3.3V rail ONLY - connecting VDD to 5V will destroy the chip",
    [
        ("3V3", "VDD", "3.3V"),
        ("GND", "GND", "GND"),
        ("GND", "L/R (channel select)", "GND"),
        ("GPIO 32", "SCK (bit clock)", "SIG"),
        ("GPIO 25", "WS (word select)", "SIG"),
        ("GPIO 33", "SD (data out)", "SIG"),
    ],
)

draw_panel(
    axes[0, 1],
    "MAX98357A Amp + Speaker",
    "5V rail. SD now GPIO-controlled (mute) - see build sequence notes",
    [
        ("5V / VIN", "VIN", "5V"),
        ("GND", "GND", "GND"),
        ("GND", "GAIN (if broken out)", "GND"),
        ("GPIO 21", "SD (mute control)", "SIG"),
        ("GPIO 27", "BCLK", "SIG"),
        ("GPIO 26", "LRC", "SIG"),
        ("GPIO 22", "DIN", "SIG"),
        ("(speaker wires)", "SPEAKER +/-", "GND"),
    ],
)

draw_panel(
    axes[1, 0],
    "MAX7219 Dot Matrix (32x8)",
    "5V rail - if display is flaky, power from 3.3V instead or add a level shifter",
    [
        ("5V / VIN", "VCC", "5V"),
        ("GND", "GND", "GND"),
        ("GPIO 18", "CLK", "SIG"),
        ("GPIO 23", "DIN", "SIG"),
        ("GPIO 5", "CS / LOAD", "SIG"),
    ],
)

draw_panel(
    axes[1, 1],
    "Accent LED + Touch Pad + Push-to-Talk Button",
    "LED: plain 5mm white, low-side switched - GPIO LOW = on, HIGH = off. Button: internal pull-up",
    [
        ("5V / VIN  (--180-220Ω--)", "LED anode (+)", "5V"),
        ("GPIO 4", "LED cathode (-)", "SIG"),
        ("GPIO 13", "(touch pad - exposed wire, no component)", "SIG"),
        ("GPIO 14", "Button leg 1", "SIG"),
        ("GND", "Button leg 2", "GND"),
    ],
)

legend_ax = fig.add_axes([0.35, 0.0, 0.3, 0.035])
legend_ax.axis("off")
lx = 0
for color, label in [(RED, "5V"), (ORANGE, "3.3V"), (BLACK, "GND"), (BLUE, "GPIO signal")]:
    legend_ax.plot([lx, lx + 0.06], [0.5, 0.5], color=color, linewidth=3, transform=legend_ax.transAxes)
    legend_ax.text(lx + 0.075, 0.5, label, va="center", fontsize=9, transform=legend_ax.transAxes)
    lx += 0.25

plt.tight_layout(rect=[0, 0.04, 1, 0.96])
plt.savefig("docs/sparky_wiring_diagram.png", dpi=150, bbox_inches="tight")
print("Wrote docs/sparky_wiring_diagram.png")
