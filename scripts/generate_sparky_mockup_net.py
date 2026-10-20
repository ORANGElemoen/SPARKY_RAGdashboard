#!/usr/bin/env python3
"""
One-off generator for docs/sparky_mockup_net.pdf - a 1:1 printable net
(unfolded box) for a cardboard mock-up of Sparky's enclosure, used for the
enclosure fit test (M-21) before 3D printing.

Sizes come from the CAD fit check (report Table "Enclosure fit check"):
body 178 x 173 x 66 mm, LED-matrix window 124 x 28 mm (revised), 30 mm
push-to-talk hole on top, 5 mm accent LED and mic holes, speaker grille.
Window/grille/LED positions are approximate (read off the CAD render).

Page 1 is an overview; pages 2-5 are the net at actual size, tiled over A4
landscape with a 10 mm overlap. Print at 100% / "actual size".

Not part of the running app; run manually when the enclosure changes:
    python scripts/generate_sparky_mockup_net.py
"""
from pathlib import Path

from reportlab.lib.colors import Color, black, white
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent.parent / "docs" / "sparky_mockup_net.pdf"

W, H, D = 178, 173, 66   # body width, height, depth (mm)
TAB, SIDE_TAB = 12, 15   # glue tab depths
BLUE = Color(0.16, 0.45, 0.65)
RED = Color(0.75, 0.22, 0.17)
GRAY = Color(0.45, 0.45, 0.45)
SHADE = Color(0.9, 0.9, 0.9)

# Net layout (mm, origin bottom-left): [tab | side | FRONT | side | BACK]
X_SIDE_L, X_FRONT, X_SIDE_R, X_BACK = SIDE_TAB, SIDE_TAB + D, SIDE_TAB + D + W, SIDE_TAB + 2 * D + W
Y_BOTTOM, Y_MAIN, Y_TOP = TAB, TAB + D, TAB + D + H
NET_W, NET_H = X_BACK + W, Y_TOP + D + TAB

PANELS = {  # name: (x, y, w, h)
    "SIDE": (X_SIDE_L, Y_MAIN, D, H),
    "FRONT": (X_FRONT, Y_MAIN, W, H),
    "SIDE ": (X_SIDE_R, Y_MAIN, D, H),
    "BACK": (X_BACK, Y_MAIN, W, H),
    "TOP": (X_FRONT, Y_TOP, W, D),
    "BOTTOM": (X_FRONT, Y_BOTTOM, W, D),
}
TABS = [  # (base start, base end, outward unit vector, depth)
    ((X_SIDE_L, Y_MAIN), (X_SIDE_L, Y_TOP), (-1, 0), SIDE_TAB),          # glues inside BACK
    ((X_FRONT, Y_TOP + D), (X_FRONT + W, Y_TOP + D), (0, 1), TAB),       # TOP rear
    ((X_FRONT, Y_TOP), (X_FRONT, Y_TOP + D), (-1, 0), TAB),              # TOP left
    ((X_SIDE_R, Y_TOP), (X_SIDE_R, Y_TOP + D), (1, 0), TAB),             # TOP right
    ((X_FRONT, Y_BOTTOM), (X_FRONT + W, Y_BOTTOM), (0, -1), TAB),        # BOTTOM rear
    ((X_FRONT, Y_BOTTOM), (X_FRONT, Y_MAIN), (-1, 0), TAB),              # BOTTOM left
    ((X_SIDE_R, Y_BOTTOM), (X_SIDE_R, Y_MAIN), (1, 0), TAB),             # BOTTOM right
]


def edges():
    """Panel edges split into fold (shared or tab base) and cut segments."""
    count = {}
    for x, y, w, h in PANELS.values():
        for seg in (((x, y), (x + w, y)), ((x, y + h), (x + w, y + h)),
                    ((x, y), (x, y + h)), ((x + w, y), (x + w, y + h))):
            count[seg] = count.get(seg, 0) + 1
    bases = {(a, b) for a, b, _, _ in TABS}
    folds = [s for s, n in count.items() if n > 1 or s in bases]
    cuts = [s for s, n in count.items() if n == 1 and s not in bases]
    return folds, cuts


def draw_net(c, s=mm, text=True):
    """Draw the net with 1 net-mm = s points."""
    folds, cuts = edges()
    c.setStrokeColor(black)
    c.setLineWidth(0.8)
    c.setDash()
    for (x1, y1), (x2, y2) in cuts:
        c.line(x1 * s, y1 * s, x2 * s, y2 * s)
    for (x1, y1), (x2, y2), (dx, dy), depth in TABS:
        inset = 4 if depth == TAB else 6
        ux, uy = (x2 - x1, y2 - y1)
        length = abs(ux) + abs(uy)
        ux, uy = ux / length, uy / length
        p = [(x1, y1), (x1 + dx * depth + ux * inset, y1 + dy * depth + uy * inset),
             (x2 + dx * depth - ux * inset, y2 + dy * depth - uy * inset), (x2, y2)]
        for (a, b), (cx, cy) in zip(p[:-1], p[1:]):
            c.line(a * s, b * s, cx * s, cy * s)
        if text:
            c.setFillColor(GRAY)
            c.setFont("Helvetica", 6)
            mx, my = (x1 + x2) / 2 + dx * depth / 2, (y1 + y2) / 2 + dy * depth / 2
            c.drawCentredString(mx * s, my * s - 2, "glue")
    c.setStrokeColor(BLUE)
    c.setDash(4, 3)
    for (x1, y1), (x2, y2) in folds:
        c.line(x1 * s, y1 * s, x2 * s, y2 * s)
    c.setDash()

    # Cut-outs (red), positioned from the CAD render
    c.setStrokeColor(RED)
    c.setLineWidth(0.8)
    fx, fy = X_FRONT, Y_MAIN
    c.rect((fx + (W - 124) / 2) * s, (fy + H - 35 - 28) * s, 124 * s, 28 * s)  # face window
    c.circle((fx + W / 2) * s, (fy + H - 12) * s, 2.5 * s)                     # mic
    c.circle((fx + W - 45) * s, (fy + 40) * s, 2.5 * s)                        # accent LED
    gx, gy = fx + 45, fy + 40                                                  # speaker grille
    for row in range(-3, 4):
        for col in range(-3, 4):
            x, y = gx + col * 6 + (3 if row % 2 else 0), gy + row * 5.2
            if (x - gx) ** 2 + (y - gy) ** 2 <= 16 ** 2:
                c.circle(x * s, y * s, 1.4 * s)
    c.circle((X_FRONT + W / 2) * s, (Y_TOP + 33) * s, 15 * s)                  # button, 30 mm
    c.rect((X_BACK + W / 2 - 6) * s, (Y_MAIN + 12) * s, 12 * s, 6 * s)         # USB slot

    if not text:
        return
    c.setFillColor(GRAY)
    for name, (x, y, w, h) in PANELS.items():
        c.setFont("Helvetica-Bold", 10)
        label_y = y + h / 2 if name not in ("FRONT", "TOP") else y + (h * 0.22 if name == "FRONT" else 18)
        c.drawCentredString((x + w / 2) * s, label_y * s, name.strip())
        c.setFont("Helvetica", 7)
        c.drawCentredString((x + w / 2) * s, label_y * s - 9, f"{w} x {h} mm")
    c.setFillColor(RED)
    c.setFont("Helvetica", 6.5)
    notes = [
        (fx + W / 2, fy + H - 35 - 28 - 5, "LED matrix window 124 x 28 mm"),
        (fx + W / 2, fy + H - 7, "mic 5 mm"),
        (fx + W - 45, fy + 33, "accent LED 5 mm"),
        (gx, gy - 21, "speaker grille (poke with a pen)"),
        (X_FRONT + W / 2, Y_TOP + 51, "push-to-talk button 30 mm (bottle cap)"),
        (X_BACK + W / 2, Y_MAIN + 21, "USB slot 12 x 6 mm (move to match your ESP32)"),
    ]
    for x, y, t in notes:
        c.drawCentredString(x * s, y * s, t)
    c.setFillColor(GRAY)
    c.setFont("Helvetica", 6.5)
    c.drawCentredString((X_FRONT + W / 2) * s, (Y_TOP + 3) * s, "front edge of the head (fold)")


def scale_bar(c, x, y):
    c.setStrokeColor(black)
    c.setLineWidth(0.8)
    c.setDash()
    c.line(x, y, x + 100 * mm, y)
    for i in range(0, 101, 10):
        c.line(x + i * mm, y, x + i * mm, y + (2.5 if i % 50 else 4) * mm)
    c.setFillColor(black)
    c.setFont("Helvetica", 7)
    c.drawString(x + 102 * mm, y, "100 mm - measure this with a ruler; if it is not 100 mm, reprint at 100% / actual size")


def legend(c, x, y):
    c.setFont("Helvetica", 8)
    for i, (colour, dash, text) in enumerate([
            (black, None, "cut (outline)"), (BLUE, (4, 3), "fold (score lightly first)"),
            (RED, None, "cut out (holes)")]):
        c.setStrokeColor(colour)
        c.setDash(*dash) if dash else c.setDash()
        c.line(x, y - i * 12, x + 25, y - i * 12)
        c.setFillColor(black)
        c.drawString(x + 30, y - i * 12 - 3, text)
    c.setDash()


def main():
    page_w, page_h = landscape(A4)
    margin, overlap = 10, 10
    tile_w, tile_h = page_w / mm - 2 * margin, page_h / mm - 2 * margin
    step_x, step_y = tile_w - overlap, tile_h - overlap
    cols = rows = 2
    assert step_x + tile_w >= NET_W and step_y + tile_h >= NET_H, "net needs more pages"
    names = {(0, 0): "Page 2", (1, 0): "Page 3", (0, 1): "Page 4", (1, 1): "Page 5"}

    c = canvas.Canvas(str(OUT), pagesize=(page_w, page_h))
    c.setTitle("Sparky cardboard mock-up net (1:1)")

    # Page 1: overview
    c.setFont("Helvetica-Bold", 16)
    c.drawString(15 * mm, page_h - 18 * mm, "Sparky cardboard mock-up - box net")
    c.setFont("Helvetica", 9)
    lines = [
        f"Finished box: {W} wide x {H} tall x {D} deep mm (CAD body size). Pages 2-5 are the net at actual size.",
        "1. Print pages 2-5 at 100% / 'actual size' (not 'fit to page'). Check the 100 mm bar on each page.",
        "2. Lay them out as below (Page 4 | Page 5 on top, Page 2 | Page 3 underneath). Slide each grey shaded strip",
        "   under the neighbouring page so the lines meet, then tape the pages together.",
        "3. Glue the sheet onto flattened cereal-box card (or cut it into panels along fold lines if the card is too small).",
        "4. Cut out the red holes first while the card is flat, then the black outline.",
        "5. Score the blue fold lines with a pen, fold, and glue the tabs inside.",
        "Fit test (M-21): LED matrix 128 x 32 mm behind the window, button from the top, breadboard flat on the bottom,",
        "speaker behind the grille, USB cable through the back slot. Photograph each check.",
    ]
    for i, t in enumerate(lines):
        c.drawString(15 * mm, page_h - (28 + i * 5) * mm, t)
    s = 0.33 * mm
    ox, oy = 25 * mm, 10 * mm
    c.saveState()
    c.translate(ox, oy)
    draw_net(c, s, text=False)
    c.setStrokeColor(GRAY)
    c.setDash(1, 2)
    c.setFillColor(GRAY)
    c.setFont("Helvetica-Bold", 9)
    for (i, j), name in names.items():
        x, y = i * step_x, j * step_y
        c.rect(x * s, y * s, tile_w * s, tile_h * s)
        c.drawString((x + 4) * s, (y + tile_h - 12) * s, name)
    c.restoreState()
    legend(c, page_w - 75 * mm, 60 * mm)
    c.showPage()

    # Pages 2-5: tiles at 1:1
    for j in range(rows):
        for i in range(cols):
            x0, y0 = i * step_x, j * step_y
            c.saveState()
            p = c.beginPath()
            p.rect(margin * mm, margin * mm, tile_w * mm, tile_h * mm)
            c.clipPath(p, stroke=0, fill=0)
            c.translate((margin - x0) * mm, (margin - y0) * mm)
            c.setFillColor(SHADE)
            if i > 0:
                c.rect(x0 * mm, y0 * mm, overlap * mm, tile_h * mm, stroke=0, fill=1)
            if j > 0:
                c.rect(x0 * mm, y0 * mm, tile_w * mm, overlap * mm, stroke=0, fill=1)
            draw_net(c)
            c.restoreState()
            c.setStrokeColor(GRAY)
            c.setDash(1, 2)
            c.rect(margin * mm, margin * mm, tile_w * mm, tile_h * mm)
            c.setDash()
            c.setFillColor(black)
            c.setFont("Helvetica-Bold", 8)
            where = ("top" if j else "bottom") + ("-right" if i else "-left")
            c.drawString(margin * mm, page_h - 7 * mm, f"Sparky mock-up net - {names[(i, j)]} ({where})")
            c.setFont("Helvetica", 7)
            if i or j:
                c.drawRightString(page_w - margin * mm, page_h - 7 * mm,
                                  "Shaded strip = overlap: slide it under the neighbouring page so the lines meet")
            scale_bar(c, margin * mm, 4 * mm)
            c.showPage()
    c.save()
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    main()
