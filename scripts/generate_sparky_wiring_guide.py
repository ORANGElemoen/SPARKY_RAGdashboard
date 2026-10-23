#!/usr/bin/env python3
"""
Generator for Sparky's wiring guide (v3): docs/sparky_wiring_guide.pdf plus its two
figures, docs/images/sparky_pinout.png (also the report's wiring figure) and
docs/images/sparky_breadboard_layout.png.

v3 changes from the report's v2 diagram: the accent LED is a plain 5 mm white LED moved
from the 5 V rail to the 3.3 V rail (the report's identified risk: GPIO 4 could see more
than 3.6 V), the ESP32 sits off the breadboard on female-to-male jumpers (on a half breadboard it
would take half the rows, leaving too few for the parts), amp GAIN is optional.
Board: ESP-WROOM-32 on a 30-pin dev board (DOIT DevKit V1 layout; 5 V pin is VIN).

Pin map: report Table "ESP32 GPIO allocation" = firmware/sparky/config.h.
Not part of the running app; re-run when the wiring changes:
    python scripts/generate_sparky_wiring_guide.py
"""
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Circle, FancyBboxPatch, Rectangle

sys.path.insert(0, str(Path(__file__).resolve().parent))
from generate_sparky_build_guide import (BOX, CELL, GREY, H1, H2, H3, P, SMALL, bullets, image, sized,  # noqa: E402
                                         steps, table)
from reportlab.lib.pagesizes import A4  # noqa: E402
from reportlab.lib.units import mm  # noqa: E402
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "docs" / "images"
PINOUT = IMG / "sparky_pinout.png"
LAYOUT = IMG / "sparky_breadboard_layout.png"
OUT = ROOT / "docs" / "sparky_wiring_guide.pdf"

# ------------------------------------------------------------------ colours
V5, V33, GND = "#dc2626", "#f59e0b", "#111827"
COL = {"mic": "#7c3aed", "amp": "#059669", "matrix": "#2563eb", "button": "#ea580c",
       "led": "#db2777", "touch": "#0891b2", "5V": V5, "3V3": V33, "GND": GND}
INK, MUTED = "#0f172a", "#94a3b8"

# 30-pin ESP32 DevKit V1 (ESP-WROOM-32) header order, antenna end first.
# (printed label, used-for or None, colour key). Boards print D32, G32 or P32 - same pin.
J2 = [("EN", None, None), ("VP / 36", None, None), ("VN / 39", None, None), ("D34", None, None),
      ("D35", None, None), ("D32", "MIC SCK", "mic"), ("D33", "MIC SD", "mic"), ("D25", "MIC WS", "mic"),
      ("D26", "AMP LRC", "amp"), ("D27", "AMP BCLK", "amp"), ("D14", "BUTTON", "button"), ("D12", None, None),
      ("D13", "TOUCH PAD", "touch"), ("GND", "GND rail", "GND"), ("VIN", "5 V rail", "5V")]
J3 = [("D23", "MATRIX DIN", "matrix"), ("D22", "AMP DIN", "amp"), ("TX0 / 1", None, None), ("RX0 / 3", None, None),
      ("D21", "AMP SD (mute)", "amp"), ("D19", None, None), ("D18", "MATRIX CLK", "matrix"),
      ("D5", "MATRIX CS", "matrix"), ("TX2 / 17", None, None), ("RX2 / 16", None, None),
      ("D4", "LED (−) short leg", "led"), ("D2", None, None), ("D15", None, None), ("GND", None, None),
      ("3V3", "3.3 V rail", "3V3")]

# Every connection, in build order: (step, from, to, wire, colour key). Used for the checklist.
WIRES = [
    ("Power", "ESP32 VIN (= 5 V from USB)", "Top + rail (5 V)", "F-M jumper", "5V"),
    ("Power", "ESP32 3V3", "Bottom + rail (3.3 V)", "F-M jumper", "3V3"),
    ("Power", "ESP32 GND (either one)", "Top − rail (GND)", "F-M jumper", "GND"),
    ("Power", "Top − rail (GND)", "Bottom − rail (GND), at row 1", "M-M jumper", "GND"),
    ("Matrix", "Matrix VCC (IN end)", "Top + rail (5 V)", "Matrix cable + M-M pin", "5V"),
    ("Matrix", "Matrix GND", "Top − rail (GND)", "Matrix cable + M-M pin", "GND"),
    ("Matrix", "Matrix DIN", "ESP32 GPIO 23", "Matrix cable (F-F)", "matrix"),
    ("Matrix", "Matrix CS", "ESP32 GPIO 5", "Matrix cable (F-F)", "matrix"),
    ("Matrix", "Matrix CLK", "ESP32 GPIO 18", "Matrix cable (F-F)", "matrix"),
    ("Amp", "Amp VIN (row 15)", "Top + rail (5 V)", "M-M jumper", "5V"),
    ("Amp", "Amp GND (row 14)", "Top − rail (GND)", "M-M jumper", "GND"),
    ("Amp", "Amp LRC (row 9)", "ESP32 GPIO 26", "F-M jumper", "amp"),
    ("Amp", "Amp BCLK (row 10)", "ESP32 GPIO 27", "F-M jumper", "amp"),
    ("Amp", "Amp DIN (row 11)", "ESP32 GPIO 22", "F-M jumper", "amp"),
    ("Amp", "Amp SD (row 13)", "ESP32 GPIO 21", "F-M jumper", "amp"),
    ("Amp", "Amp GAIN (row 12)", "Nothing at first (9 dB). Louder: to GND (12 dB)", "-", "GND"),
    ("Amp", "Speaker red / black", "Amp screw terminal + / −", "Speaker's own wires", "amp"),
    ("Mic", "Mic VDD (row 4, bottom)", "Bottom + rail (3.3 V) - NEVER 5 V", "M-M jumper", "3V3"),
    ("Mic", "Mic GND (row 5, bottom)", "Bottom − rail (GND)", "M-M jumper", "GND"),
    ("Mic", "Mic L/R (row 3, top)", "Top − rail (GND) = left channel", "M-M jumper", "GND"),
    ("Mic", "Mic SD (row 3, bottom)", "ESP32 GPIO 33", "F-M jumper", "mic"),
    ("Mic", "Mic WS (row 4, top)", "ESP32 GPIO 25", "F-M jumper", "mic"),
    ("Mic", "Mic SCK (row 5, top)", "ESP32 GPIO 32", "F-M jumper", "mic"),
    ("Button", "Button leg, row 19 top", "ESP32 GPIO 14", "F-M jumper", "button"),
    ("Button", "Button leg, row 21 bottom (diagonal)", "Bottom − rail (GND)", "M-M jumper", "GND"),
    ("LED", "47 Ω resistor", "Bottom + rail (3.3 V) to row 24", "Resistor legs", "3V3"),
    ("LED", "LED long leg (+)", "Row 24 (with the resistor)", "LED leg", "led"),
    ("LED", "LED short leg (−, flat side)", "Row 26", "LED leg", "led"),
    ("LED", "Row 26", "ESP32 GPIO 4", "F-M jumper", "led"),
    ("Touch", "Row 29 top", "ESP32 GPIO 13", "F-M jumper", "touch"),
    ("Touch", "Row 29 top", "Loose jumper end = touch pad", "M-M jumper", "touch"),
]


# ------------------------------------------------------------------ figure 1: pinout
def tag(ax, x, y, text, colour, align):
    ax.text(x, y, text, ha=align, va="center", fontsize=8.6, color="white", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.28", fc=colour, ec="none"))


def module(ax, x, y, w, title, colour, lines, note=None):
    """A module box: title bar, then (pin, connects-to, colour key) lines."""
    h = 0.62 + 0.46 * len(lines) + (0.5 if note else 0)
    ax.add_patch(FancyBboxPatch((x, y - h), w, h, boxstyle="round,pad=0.04,rounding_size=0.18",
                                fc="white", ec=colour, lw=2))
    ax.add_patch(FancyBboxPatch((x, y - 0.52), w, 0.52, boxstyle="round,pad=0.04,rounding_size=0.18",
                                fc=colour, ec=colour, lw=2))
    ax.text(x + 0.2, y - 0.26, title, color="white", fontsize=10.5, fontweight="bold", va="center")
    for i, (pin, to, key) in enumerate(lines):
        yy = y - 0.88 - 0.46 * i
        ax.add_patch(Circle((x + 0.25, yy), 0.09, color=COL[key]))
        ax.text(x + 0.45, yy, pin, fontsize=8.8, va="center", fontweight="bold", color=INK)
        ax.text(x + w * 0.42, yy, "→  " + to, fontsize=8.6, va="center", color=COL[key] if key != "GND" else INK)
    if note:
        ax.text(x + 0.2, y - h + 0.25, note, fontsize=7.6, color="#b91c1c", va="center", style="italic")


def draw_pinout():
    fig, ax = plt.subplots(figsize=(16, 11.3))
    ax.set_xlim(-13.0, 13.0)
    ax.set_ylim(-7.3, 7.4)
    ax.axis("off")
    ax.text(0, 7.05, "Sparky - circuit pinout (v3)", ha="center", fontsize=19, fontweight="bold", color=INK)
    ax.text(0, 6.55, "30-pin ESP32 DevKit (ESP-WROOM-32) seen from the top (antenna up, USB down). Coloured tags = pins Sparky uses. "
            "Go by the labels printed on your boards.", ha="center", fontsize=9.5, color="#475569")

    # board
    pitch, top = 0.75, 5.6
    bx, bw = -1.9, 3.8
    ax.add_patch(FancyBboxPatch((bx, top - 14 * pitch - 0.55), bw, 14 * pitch + 1.1,
                                boxstyle="round,pad=0.05,rounding_size=0.25", fc="#1e293b", ec="#0f172a", lw=2))
    ax.add_patch(Rectangle((-0.55, top - 14 * pitch - 0.85), 1.1, 0.6, fc="#9ca3af", ec="#6b7280"))
    ax.text(0, top - 14 * pitch - 1.15, "USB", ha="center", fontsize=8.5, color="#475569")
    ax.text(0, top - 7 * pitch, "ESP32 DevKit 30-pin  ·  ESP-WROOM-32", rotation=90, ha="center", va="center",
            fontsize=10.5, color="#e2e8f0", fontweight="bold")
    for side, pins in ((-1, J2), (1, J3)):
        for i, (label, use, key) in enumerate(pins):
            y = top - i * pitch
            px = side * 1.55
            used = use is not None
            ax.add_patch(Circle((px, y), 0.13, fc=COL[key] if used else "#475569", ec="#e2e8f0", lw=1))
            ax.text(px - side * 0.3, y, label, ha="left" if side < 0 else "right", va="center", fontsize=8,
                    color="white" if used else "#94a3b8", fontweight="bold" if used else "normal")
            if used:
                ax.plot([px, side * 2.35], [y, y], color=COL[key], lw=2.2, solid_capstyle="round")
                tag(ax, side * 2.4, y, use, COL[key], "right" if side < 0 else "left")

    # modules, left column
    lx, rx, w = -12.9, 5.7, 7.2
    module(ax, lx, 6.1, w, "INMP441 microphone", COL["mic"],
           [("VDD", "3.3 V rail", "3V3"), ("GND", "GND", "GND"), ("L/R", "GND (left channel)", "GND"),
            ("SCK", "GPIO 32", "mic"), ("WS", "GPIO 25", "mic"), ("SD", "GPIO 33", "mic")],
           note="3.3 V ONLY - 5 V destroys the mic")
    module(ax, lx, 2.05, w, "MAX98357A amp + 3 W speaker", COL["amp"],
           [("VIN", "5 V rail", "5V"), ("GND", "GND", "GND"), ("LRC", "GPIO 26", "amp"),
            ("BCLK", "GPIO 27", "amp"), ("DIN", "GPIO 22", "amp"), ("SD", "GPIO 21 (LOW = mute)", "amp"),
            ("GAIN", "open = 9 dB, to GND = 12 dB", "GND"), ("+  /  −", "speaker red / black", "amp")])
    module(ax, lx, -2.85, w, "Push-to-talk button", COL["button"],
           [("leg 1", "GPIO 14 (internal pull-up)", "button"), ("leg 2", "GND", "GND")],
           note="Tactile: use DIAGONAL legs. Arcade: COM + NO")
    # right column
    module(ax, rx, 6.1, w, "MAX7219 LED matrix 32 x 8 (IN end)", COL["matrix"],
           [("VCC", "5 V rail", "5V"), ("GND", "GND", "GND"), ("DIN", "GPIO 23", "matrix"),
            ("CS", "GPIO 5", "matrix"), ("CLK", "GPIO 18", "matrix")],
           note="Use the IN end (DIN, not DOUT). Keep brightness low on USB.")
    module(ax, rx, 2.45, w, "Accent LED (white 5 mm, now on 3.3 V)", COL["led"],
           [("3.3 V rail", "47 Ω resistor", "3V3"), ("resistor", "LED long leg (+)", "led"),
            ("short leg (−)", "GPIO 4  (LOW = on)", "led")])
    module(ax, rx, 0.2, w, "Touch pad", COL["touch"],
           [("pad / wire", "GPIO 13 (touch T4)", "touch")],
           note="Bench: bare jumper end. In Sparky: copper tape pad")
    module(ax, rx, -1.65, w, "Power (USB 5 V into the ESP32)", "#334155",
           [("ESP32 VIN", "top + rail  = 5 V", "5V"), ("ESP32 3V3", "bottom + rail = 3.3 V", "3V3"),
            ("ESP32 GND", "both − rails (link them)", "GND")],
           note="Never feed 5 V into any GPIO or the 3V3 pin")

    # legend
    ly = -6.95
    for i, (k, label) in enumerate([("5V", "5 V"), ("3V3", "3.3 V"), ("GND", "GND"), ("mic", "mic"), ("amp", "amp"),
                                    ("matrix", "matrix"), ("button", "button"), ("led", "LED"), ("touch", "touch")]):
        x = -11.5 + i * 2.6
        ax.plot([x, x + 0.6], [ly, ly], color=COL[k], lw=4)
        ax.text(x + 0.75, ly, label, va="center", fontsize=9)
    fig.savefig(PINOUT, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ------------------------------------------------------------------ figure 2: breadboard layout
# Half breadboard, 30 rows left to right. Columns: j..f top half, e..a bottom half.
COLY = {c: y for c, y in zip("jihgf", [9.0, 8.0, 7.0, 6.0, 5.0])} | {c: y for c, y in zip("edcba", [2.0, 1.0, 0.0, -1.0, -2.0])}
RAIL = {"top-": 11.6, "top+": 10.7, "bot+": -3.7, "bot-": -4.6}


def hole(c, r):
    return (r, COLY[c] if c in COLY else RAIL[c])


def wire(ax, a, b, key, lw=3.2, z=5):
    ax.plot([a[0], b[0]], [a[1], b[1]], color=COL[key], lw=lw, solid_capstyle="round", zorder=z)
    for p in (a, b):
        ax.add_patch(Circle(p, 0.17, color=COL[key], zorder=z + 1))


def flag(ax, at, text, key, up):
    """A jumper going off the board to the ESP32 (or the matrix cable): line + label above/below."""
    y2 = 14.2 if up else -7.4
    ax.plot([at[0], at[0]], [at[1], y2], color=COL[key], lw=3, zorder=5, solid_capstyle="round")
    ax.add_patch(Circle(at, 0.17, color=COL[key], zorder=6))
    ax.text(at[0], y2 + (0.35 if up else -0.35), text, ha="center", va="bottom" if up else "top", rotation=90,
            fontsize=8.6, color="white", fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.25", fc=COL[key], ec="none"), zorder=7)


def chip(ax, x0, x1, y0, y1, colour, label, fs=9):
    ax.add_patch(FancyBboxPatch((x0, y0), x1 - x0, y1 - y0, boxstyle="round,pad=0.05,rounding_size=0.3",
                                fc=colour, ec="#1f2937", lw=1.2, alpha=0.93, zorder=3))
    ax.text((x0 + x1) / 2, (y0 + y1) / 2, label, ha="center", va="center", color="white", fontsize=fs,
            fontweight="bold", zorder=4)


def pins(ax, positions, labels, side):
    for (x, y), lab in zip(positions, labels):
        ax.add_patch(Circle((x, y), 0.2, fc="#fbbf24", ec="#78350f", lw=1, zorder=8))
        ax.text(x + side * 0.0, y + (0.5 if side > 0 else -0.5), lab, ha="center", va="center", fontsize=7.4,
                fontweight="bold", color=INK, zorder=9,
                bbox=dict(boxstyle="round,pad=0.12", fc="white", ec="none", alpha=0.85))


def draw_layout():
    fig, ax = plt.subplots(figsize=(16, 11.6))
    ax.set_xlim(-3.2, 35.0)
    ax.set_ylim(-14.2, 21.0)
    ax.set_aspect("equal")
    ax.axis("off")
    ax.text(15, 20.3, "Sparky - breadboard layout (half breadboard, ESP32 off the board)", ha="center",
            fontsize=18, fontweight="bold", color=INK)
    ax.text(15, 19.4, "Each coloured flag is one jumper to the ESP32 pin named on it. Rows are numbered 1-30; "
            "the five holes a-e (and f-j) in one row are connected.", ha="center", fontsize=9.5, color="#475569")

    # board
    ax.add_patch(FancyBboxPatch((-1.5, -5.6), 33.0, 18.2, boxstyle="round,pad=0.1,rounding_size=0.6",
                                fc="#f8fafc", ec="#cbd5e1", lw=1.5, zorder=0))
    ax.add_patch(Rectangle((-1.0, 3.0), 32.0, 1.0, fc="#e2e8f0", ec="none", zorder=0))
    ax.text(15, 3.5, "centre gap", ha="center", va="center", fontsize=8, color="#64748b")
    for name, y in RAIL.items():
        colour = {"top-": GND, "top+": V5, "bot+": V33, "bot-": GND}[name]
        ax.plot([0.3, 30.7], [y + (0.42 if name in ("top-", "bot+") else -0.42)] * 2, color=colour, lw=1.2, alpha=0.7)
        for r in range(1, 31):
            ax.add_patch(Rectangle((r - 0.12, y - 0.12), 0.24, 0.24, fc="#94a3b8", ec="none", zorder=1))
    ax.text(-1.2, RAIL["top-"], "− GND", ha="right", va="center", fontsize=9, fontweight="bold", color=GND)
    ax.text(-1.2, RAIL["top+"], "+ 5 V", ha="right", va="center", fontsize=9, fontweight="bold", color=V5)
    ax.text(-1.2, RAIL["bot+"], "+ 3.3 V", ha="right", va="center", fontsize=9, fontweight="bold", color=V33)
    ax.text(-1.2, RAIL["bot-"], "− GND", ha="right", va="center", fontsize=9, fontweight="bold", color=GND)
    for c, y in COLY.items():
        ax.text(0.15, y, c, ha="center", va="center", fontsize=8, color="#64748b")
        for r in range(1, 31):
            ax.add_patch(Rectangle((r - 0.12, y - 0.12), 0.24, 0.24, fc="#94a3b8", ec="none", zorder=1))
    for r in range(1, 31):
        ax.text(r, 9.75, str(r), ha="center", fontsize=7, color="#64748b")
        ax.text(r, -5.25, str(r), ha="center", fontsize=7, color="#64748b")

    # power from the ESP32 + GND link
    flag(ax, (7, RAIL["top+"]), "ESP32 VIN", "5V", True)
    flag(ax, (8, RAIL["top-"]), "ESP32 GND", "GND", True)
    flag(ax, (7, RAIL["bot+"]), "ESP32 3V3", "3V3", False)
    wire(ax, (1, RAIL["top-"]), (1, RAIL["bot-"]), "GND", lw=2.6)
    ax.text(1, 12.15, "GND link", ha="center", va="bottom", fontsize=8, fontweight="bold", color=GND)

    # matrix cable (VCC/GND into the top rails; DIN/CS/CLK go straight to the ESP32)
    flag(ax, (16, RAIL["top+"]), "MATRIX VCC", "5V", True)
    flag(ax, (17, RAIL["top-"]), "MATRIX GND", "GND", True)

    # mic: straddles the centre gap, rows 3-5
    chip(ax, 2.45, 5.55, 1.6, 5.4, COL["mic"], "MIC\n(sound\nhole\nup)", fs=7.5)
    pins(ax, [hole("f", r) for r in (3, 4, 5)], ["L/R", "WS", "SCK"], +1)
    pins(ax, [hole("e", r) for r in (3, 4, 5)], ["SD", "VDD", "GND"], -1)
    wire(ax, hole("j", 3), hole("top-", 3), "GND")
    flag(ax, hole("i", 4), "GPIO 25", "mic", True)
    flag(ax, hole("i", 5), "GPIO 32", "mic", True)
    flag(ax, hole("b", 3), "GPIO 33", "mic", False)
    wire(ax, hole("a", 4), hole("bot+", 4), "3V3")
    wire(ax, hole("a", 5), hole("bot-", 5), "GND")

    # amp: pins in column f rows 9-15, board lying over the gap
    chip(ax, 8.5, 15.5, 0.6, 5.4, COL["amp"], "MAX98357A amp\n(speaker terminal\non this side)", fs=8)
    pins(ax, [hole("f", r) for r in range(9, 16)], ["LRC", "BCLK", "DIN", "GAIN", "SD", "GND", "VIN"], +1)
    flag(ax, hole("i", 9), "GPIO 26", "amp", True)
    flag(ax, hole("i", 10), "GPIO 27", "amp", True)
    flag(ax, hole("i", 11), "GPIO 22", "amp", True)
    flag(ax, hole("i", 13), "GPIO 21", "amp", True)
    wire(ax, hole("j", 14), hole("top-", 14), "GND")
    wire(ax, hole("j", 15), hole("top+", 15), "5V")
    ax.text(12, -0.9, "speaker  + red / − black", ha="center", fontsize=8.5, color=COL["amp"], fontweight="bold")

    # button: tactile switch across the gap, rows 19-21, diagonal legs
    chip(ax, 18.6, 21.4, 1.6, 5.4, COL["button"], "BUTTON", fs=8)
    pins(ax, [hole("f", 19), hole("e", 21)], ["leg", "leg"], +1)
    flag(ax, hole("i", 19), "GPIO 14", "button", True)
    wire(ax, hole("a", 21), hole("bot-", 21), "GND")

    # LED + resistor (bottom half, rows 24-26)
    ax.plot([24, 24], [RAIL["bot+"], COLY["b"]], color="#a16207", lw=2, zorder=4)
    ax.add_patch(Rectangle((23.72, -3.35), 0.56, 1.0, fc="#fde68a", ec="#a16207", lw=1.2, zorder=5))
    ax.text(23.5, -2.85, "47 Ω", fontsize=8.5, fontweight="bold", color="#a16207", va="center", ha="right")
    ax.plot([24, 24.6, 26], [COLY["d"], 0.9, COLY["d"]], color="#9ca3af", lw=1.6, zorder=4)
    ax.add_patch(Circle((24.95, 1.15), 0.55, fc="#f1f5f9", ec=COL["led"], lw=2, zorder=5))
    ax.text(24.95, 1.15, "LED", ha="center", va="center", fontsize=7, fontweight="bold", color=COL["led"], zorder=6)
    ax.text(23.4, -0.3, "+ long", ha="right", fontsize=7.5, color=COL["led"], fontweight="bold")
    ax.text(26.6, -0.3, "− short", ha="left", fontsize=7.5, color=COL["led"], fontweight="bold")
    for p in (hole("d", 24), hole("d", 26), hole("b", 24)):
        ax.add_patch(Circle(p, 0.17, color="#a16207", zorder=6))
    flag(ax, hole("b", 26), "GPIO 4", "led", False)

    # touch: GPIO 13 jumper + loose jumper in row 29
    flag(ax, hole("h", 29), "GPIO 13", "touch", True)
    ax.plot([29, 31.9], [COLY["g"], COLY["g"]], color=COL["touch"], lw=3, zorder=5)
    ax.add_patch(Circle(hole("g", 29), 0.17, color=COL["touch"], zorder=6))
    ax.add_patch(Circle((31.9, COLY["g"]), 0.22, fc="white", ec=COL["touch"], lw=2, zorder=6))
    ax.text(32.3, COLY["g"], "loose end\n= touch pad", fontsize=7.5, color=COL["touch"], fontweight="bold",
            va="center")

    ax.text(15, -12.9, "Matrix DIN / CS / CLK go straight from its cable to ESP32 GPIO 23 / 5 / 18 (no breadboard). "
            "Pin order on your mic and amp may differ - wire by the printed label, not by position.",
            ha="center", fontsize=9.5, color="#b91c1c", style="italic")
    fig.savefig(LAYOUT, dpi=170, bbox_inches="tight", facecolor="white")
    plt.close(fig)


# ------------------------------------------------------------------ PDF
def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GREY)
    canvas.drawString(15 * mm, 10 * mm, "Sparky wiring, assembly and test guide - circuit v3")
    canvas.drawRightString(195 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build_pdf():
    s = []
    s += [Paragraph("Sparky - wiring, assembly and test guide", H1),
          Paragraph("Circuit v3, for the parts that arrived from Communica, Micro Robotics and DIY Electronics. "
                    "Build it on the desk first, test each part as you add it, then move it into Sparky.", P),
          Paragraph("<b>What changed since the report's wiring diagram (v2):</b>", P),
          bullets(["<b>Accent LED moved to 3.3 V</b> - the report's identified risk. It now runs 3.3 V rail -> "
                   "47 Ω -> LED -> GPIO 4, so GPIO 4 never sees more than 3.3 V. Still lit by GPIO 4 LOW.",
                   "<b>The ESP32 sits off the breadboard</b>, on female-to-male jumpers. On the half breadboard it "
                   "would take half the rows and leave at most one hole per pin - no room left for the parts.",
                   "<b>Drawn for your 30-pin ESP32 board</b> (ESP-WROOM-32). Its 5 V pin is labelled <b>VIN</b>.",
                   "<b>Amp GAIN is optional</b>: open = 9 dB to start, to GND = 12 dB if Sparky is too quiet.",
                   "<b>The LED is a plain white 5 mm LED</b> (what was bought), not a WS2812B."]),
          Paragraph("<b>You still need</b> (not in the orders):", P),
          table([["Item", "How many", "Why / where to get it"],
                 ["Female-to-male jumper wires, 20 cm", "13 (get a 40-pack)", "ESP32 to breadboard. The M-F line "
                  "was refunded - borrow from Mr Blackie or the lab, or any electronics shop"],
                 ["Resistor 47 Ω (33-68 Ω is fine)", "1", "Accent LED. Colour bands yellow-violet-black. Lab drawer"],
                 ["Soldering iron + solder", "-", "Mic header pins (they come loose). Amp too, if its pins are loose"],
                 ["Multimeter", "-", "Power checks before switching on (section 4)"],
                 ["Micro-USB data cable", "1", "A charge-only cable powers the ESP32 but can't upload"]],
                [52, 30, 98]),
          Spacer(1, 6),
          Paragraph("<b>Three rules that protect the parts:</b> (1) the microphone gets 3.3 V only - 5 V destroys it; "
                    "(2) never connect 5 V to a GPIO pin or to the ESP32's 3V3 pin; (3) unplug the USB cable "
                    "whenever you move a wire.", BOX),
          PageBreak()]

    s += [Paragraph("1. Pinout - what connects to what", H2),
          sized(PINOUT, 180),
          Paragraph("Tag colours match the wire colours used on the next page and in the checklist. "
                    "Grey pins are unused - leave them free (D2, D12 and D15 also affect start-up).", SMALL),
          PageBreak(),
          Paragraph("2. Breadboard layout", H2),
          sized(LAYOUT, 180),
          bullets(["<b>Rails:</b> top + = 5 V (matrix, amp), bottom + = 3.3 V (mic, LED). Both − rails are GND - "
                   "link them with one jumper at the end. Check your breadboard: some rails are split in the "
                   "middle; if so, bridge the two halves too.",
                   "<b>Mic</b> straddles the centre gap like a chip - its two rows of pins must be on opposite "
                   "sides. Both rows on the same side shorts the pins together. Sound hole facing up.",
                   "<b>Amp</b> pins go into column f, rows 9-15, with the board lying over the gap. Connect through "
                   "the free holes g-j in the same rows.",
                   "<b>Button:</b> a tactile switch across the gap, wired by <i>diagonally opposite</i> legs - that "
                   "always works, whichever way round it is. The arcade button replaces it later (its COM and NO "
                   "terminals take the same two wires)."], SMALL),
          PageBreak()]

    rows = [["#", "Part", "From", "To", "Wire", "Done"]]
    for i, (part, a, b, kind, _key) in enumerate(WIRES, 1):
        rows.append([str(i), part, a, b, kind, "[   ]"])
    s += [Paragraph("3. Wire checklist", H2),
          Paragraph("Work top to bottom and tick each wire. The order matches section 4: power first, then one "
                    "part at a time, each tested before the next.", P),
          table(rows, [8, 15, 48, 58, 37, 14]),
          PageBreak()]

    s += [Paragraph("4. Assembly and test - one part at a time", H2),
          Paragraph("Upload the test program once, before wiring anything: it then runs every time the ESP32 "
                    "powers up. It is <font face='Courier'>firmware/sparky_hw_test</font> in the repository - ask "
                    "Claude to upload it, or:", P),
          Paragraph("<font face='Courier' size='8'>arduino-cli upload --fqbn esp32:esp32:esp32 -p COM5 "
                    "firmware/sparky_hw_test<br/>arduino-cli monitor -p COM5 -c baudrate=115200</font>", BOX),
          Paragraph("In the monitor, type the test number and press Enter. <b>q</b> stops a long test. Each test "
                    "prints what a pass looks like. Test IDs (M-xx) are the report's module tests.", P),
          Paragraph("Step A - power only", H3),
          steps(["Wire the four power rows of the checklist (ESP32 VIN, 3V3, GND, GND link). Nothing else yet.",
                 "<b>USB unplugged</b>, multimeter on continuity (beep): top + to top − must <b>not</b> beep; bottom "
                 "+ to bottom − must <b>not</b> beep; top + to bottom + must <b>not</b> beep.",
                 "Plug in USB. Volts mode: top + to − = <b>4.4-5.1 V</b> (VIN is a little under 5 V on USB); bottom + to − = <b>3.2-3.4 V</b>. Unplug."]),
          Paragraph("Step B - LED matrix (M-05) -> test 1", H3),
          Paragraph("Wire the 5 matrix rows. Test 1 first lights a single dot: it must be in the <b>top-left</b> "
                    "corner seen from the front. If it's top-right, set <font face='Courier'>SPARKY_FLIP_X 0</font>; "
                    "bottom-left, set <font face='Courier'>SPARKY_FLIP_Y 1</font> - in both "
                    "<font face='Courier'>sparky_hw_test.ino</font> and <font face='Courier'>firmware/sparky/config.h"
                    "</font>. Then the six mood faces show for 2.5 s each.", P),
          Paragraph("Step C - amp and speaker (M-04) -> test 2", H3),
          Paragraph("Wire the amp rows and the speaker. Low beep, high beep, then silence. Hiss in the silence "
                    "means the mute (SD, GPIO 21) isn't connected.", P),
          Paragraph("Step D - microphone (M-01, M-02) -> tests 3, 4, 5", H3),
          Paragraph("Before plugging in USB: with the multimeter on continuity, mic VDD to the bottom + rail (3.3 V) "
                    "<b>beeps</b>, and mic VDD to the top + rail (5 V) does <b>not</b>. Test 3 shows a level bar for "
                    "each channel: one should jump when you talk. Test 4 records 2.5 s and plays it back - you "
                    "should hear yourself. Test 5 counts samples for 10 s: about 16 000 per second.", P),
          Paragraph("Step E - button (M-07) -> test 6", H3),
          Paragraph("Press 100 times; the count must end at exactly 100. It counts by itself without "
                    "pressing = the button is wired to the wrong pair of legs (use diagonal legs).", P),
          Paragraph("Step F - accent LED and touch pad (M-20) -> tests 8 and 7", H3),
          Paragraph("Test 8 blinks three times, then pulses. Test 7 calibrates for 2 s (don't touch), then counts "
                    "50 taps on the loose jumper end.", P),
          Paragraph("Step G - power under load (M-08) -> test 9", H3),
          Paragraph("All 256 LEDs on with a beep at brightness 2, 5 and 8. If the ESP32 restarts, the top line "
                    "says BROWNOUT: use a 5 V / 2 A phone charger instead of a laptop port, and keep the face "
                    "brightness low. A USB power meter, if you have one, gives the M-08 numbers.", P),
          PageBreak()]

    s += [Paragraph("5. If something doesn't work", H2),
          table([["Symptom", "Most likely cause"],
                 ["Nothing at all, no USB port appears", "Charge-only cable; try another cable/port. Windows may "
                  "need the CP210x or CH340 USB driver"],
                 ["Upload fails 'waiting for download'", "Hold the BOOT button while the upload starts"],
                 ["Matrix blank", "Cable on the DOUT end instead of DIN; VCC/GND missing; CS on the wrong pin"],
                 ["Matrix shows garbage / random dots", "CLK and DIN swapped; loose GND"],
                 ["Faces mirrored or upside down", "SPARKY_FLIP_X / SPARKY_FLIP_Y (step B)"],
                 ["No sound", "Amp VIN not on 5 V; SD not on GPIO 21; speaker not tight in the terminal"],
                 ["Constant hiss", "SD (mute) not connected - the amp is never muted"],
                 ["Distorted or too loud", "Leave GAIN open (9 dB); move the speaker away from the mic"],
                 ["Mic level always 0", "VDD not on 3.3 V; SCK / WS / SD swapped; mic not straddling the gap"],
                 ["Mic level always full", "GND missing; L/R floating (tie it to GND)"],
                 ["Recording sounds fast or slow", "Test 5 reads far from 16 000: check SCK and WS"],
                 ["Button counts by itself", "Wrong legs - use diagonal legs; GPIO 14 wire loose"],
                 ["LED never lights", "LED backwards (long leg goes to the resistor); resistor in the wrong row"],
                 ["Touch counts without touching", "Loose wire too long or near the matrix cable - shorten it"],
                 ["Restarts when the matrix lights", "Brownout - stronger 5 V supply, lower brightness"]],
                [62, 118]),
          Spacer(1, 6),
          Paragraph("6. When every test passes", H2),
          steps(["Upload the real Sparky program: <font face='Courier'>firmware/sparky</font> "
                 "(same command, different folder). Its README lists nine more checks: Wi-Fi setup, Studio sync, "
                 "live preview, voice lines, power cut.",
                 "Move into Sparky: same connections, longer F-M jumpers to the mic (forehead) and amp (belly). "
                 "Swap the tactile switch for the arcade button and the loose touch wire for a copper-tape pad.",
                 "Re-run tests 1, 2, 4 and 6 inside the enclosure - wires get bumped during assembly."]),
          Paragraph("Results sheet for the report", H3),
          table([["Test", "Part", "Pass criterion (report Table)", "Result / date"],
                 ["M-01", "Microphone", "Recording audible, no clipping or dropouts, 10 of 10", ""],
                 ["M-02", "Mic bus", "Sample rate as configured (16 000 Hz), no frame slip", ""],
                 ["M-04", "Speaker", "Intelligible at 2 m, no distortion", ""],
                 ["M-05", "Face display", "Every face distinct and recognisable at arm's length", ""],
                 ["M-07", "Button", "100 presses = 100 events", ""],
                 ["M-08", "Power", "No brownout under peak load (charger and power bank)", ""],
                 ["M-20", "LED, touch", "Patterns distinct; 50 taps = 50 touches", ""]],
                [14, 26, 100, 40])]

    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=14 * mm, bottomMargin=18 * mm, title="Sparky wiring, assembly and test guide",
                            author="Sparky project")
    doc.build(s, onFirstPage=footer, onLaterPages=footer)


if __name__ == "__main__":
    draw_pinout()
    draw_layout()
    build_pdf()
    print(f"Wrote {PINOUT.name}, {LAYOUT.name} and {OUT}")
