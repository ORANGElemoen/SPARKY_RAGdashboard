#!/usr/bin/env python3
"""
One-off generator for docs/sparky_build_guide.pdf - a beginner-friendly build
and print guide for the Sparky mascot enclosure (hardware/cad/sparky_v6_mascot):
renders, where every component goes and whether it fits, stability, 3D printing
help, wiring/power tips, assembly order and the plan up to the Milestone 3 demo.

Fit results come from docs/sparky_3d_viewer.html (scripts/generate_sparky_viewer.py),
which checks each component against the printed walls.

Not part of the running app; re-run when the design changes:
    python scripts/generate_sparky_build_guide.py
"""
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (Image, KeepTogether, ListFlowable, ListItem, PageBreak, Paragraph,
                                SimpleDocTemplate, Spacer, Table, TableStyle)

ROOT = Path(__file__).resolve().parent.parent
IMG = ROOT / "docs" / "images"
CAD = ROOT / "hardware" / "cad" / "sparky_v6_mascot"
OUT = ROOT / "docs" / "sparky_build_guide.pdf"

BLUE = colors.HexColor("#1d4ed8")
ORANGE = colors.HexColor("#f97316")
GREY = colors.HexColor("#6b7280")
LIGHT = colors.HexColor("#eef4fb")

ss = getSampleStyleSheet()
H1 = ParagraphStyle("H1", parent=ss["Heading1"], fontSize=20, textColor=BLUE, spaceAfter=6)
H2 = ParagraphStyle("H2", parent=ss["Heading2"], fontSize=14, textColor=BLUE, spaceBefore=10, spaceAfter=4)
H3 = ParagraphStyle("H3", parent=ss["Heading3"], fontSize=11.5, spaceBefore=6, spaceAfter=2)
P = ParagraphStyle("P", parent=ss["BodyText"], fontSize=10, leading=13.5, spaceAfter=5)
SMALL = ParagraphStyle("S", parent=P, fontSize=8.5, leading=11, textColor=GREY)
CELL = ParagraphStyle("C", parent=P, fontSize=8.6, leading=10.8, spaceAfter=0)
CELLB = ParagraphStyle("CB", parent=CELL, fontName="Helvetica-Bold")
CAPTION = ParagraphStyle("Cap", parent=SMALL, alignment=TA_CENTER, spaceAfter=8)
BOX = ParagraphStyle("Box", parent=P, backColor=LIGHT, borderColor=BLUE, borderWidth=0.6, borderPadding=6,
                     spaceBefore=6, spaceAfter=10)


def bullets(items, style=P):
    return ListFlowable([ListItem(Paragraph(t, style), leftIndent=10) for t in items],
                        bulletType="bullet", start="•", leftIndent=12, bulletFontSize=9)


def steps(items):
    return ListFlowable([ListItem(Paragraph(t, P), leftIndent=12) for t in items],
                        bulletType="1", leftIndent=14, bulletFontSize=9.5)


def sized(path, width_mm):
    img = Image(str(path))
    img.drawHeight = width_mm * mm * img.imageHeight / img.imageWidth
    img.drawWidth = width_mm * mm
    return img


def image(path, width_mm, caption):
    return KeepTogether([sized(path, width_mm), Paragraph(caption, CAPTION)])


def table(rows, widths, header=True):
    data = [[Paragraph(str(c), CELLB if (header and i == 0) else CELL) for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1 if header else 0)
    style = [("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#cbd5e1")),
             ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("LEFTPADDING", (0, 0), (-1, -1), 4), ("RIGHTPADDING", (0, 0), (-1, -1), 4)]
    if header:
        style.append(("BACKGROUND", (0, 0), (-1, 0), LIGHT))
    t.setStyle(TableStyle(style))
    return t


def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(GREY)
    canvas.drawString(18 * mm, 10 * mm, "Sparky build & print guide - enclosure v6 (mascot)")
    canvas.drawRightString(192 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build():
    s = []
    # ---------------------------------------------------------------- cover
    s += [Paragraph("Sparky - build &amp; print guide", H1),
          Paragraph("Enclosure v6 ('little astronaut'), designed in SolidCraft. Written for a first-time "
                    "3D printer user. All sizes in millimetres.", P),
          image(IMG / "sparky_face_portrait_happy.png", 120,
                "Sparky as designed, showing the 'happy ^ ^' face on his 32 x 8 blue LED matrix behind the black screen.")]
    s.append(Paragraph(
        "<b>Short answer: yes, this design should work.</b> Every component fits inside with the sizes from "
        "its datasheet, Sparky stands steadily on his feet, and he closes with four screws and no glue. "
        "It has not been printed yet, so the first print and a fit test with the real parts are still the "
        "real proof. The biggest risk is not the design but the print itself: the front piece is a large, "
        "tall part that needs supports.", BOX))
    s.append(PageBreak())

    # ---------------------------------------------------------------- the parts
    s += [Paragraph("1. What you are printing", H2),
          Paragraph("Sparky is three printed parts. The front piece is one solid print with the face, head, "
                    "body, arms and feet already joined. The two back panels screw on so you can open him "
                    "again for repairs.", P),
          table([["Part", "Size (approx.)", "What it holds", "How it attaches"],
                 ["Front piece", "179 x 75 x 205", "Matrix, button, mic, speaker, amp, LED - everything mounts here",
                  "-"],
                 ["Head back panel", "164 x 48 x 110", "Nothing (cover)", "2 x M2.5 screws from the back"],
                 ["Body back panel", "130 x 39 x 77", "ESP32 shelf, USB cable exit", "2 x M2.5 screws from the back"]],
                [30, 30, 72, 48]),
          Spacer(1, 6),
          image(CAD / "front_piece_inside.png", 95,
                "The front piece seen from the back (panels removed): matrix rails, mic pad, screw posts, "
                "speaker posts and the neck opening for wires."),
          ]

    # ---------------------------------------------------------------- fit check
    s += [Paragraph("2. Where every component goes - and does it fit?", H2),
          image(IMG / "sparky_viewer_overview.png", 150,
                "The interactive fit-check viewer (docs/sparky_3d_viewer.html): the shell is see-through, every "
                "component is in its planned place, and each one is checked against the walls."),
          Paragraph("Each component was modelled at its datasheet size and checked against the printed walls "
                    "and against the other components. 'Fits' means nothing goes through a wall.", P),
          table([["Component", "Real size", "Where it goes", "Held by", "Fit"],
                 ["LED matrix 32x8 (MAX7219 4-in-1)", "128-129 x 32-33 x 12-15, ~55 g",
                  "Head, behind the face window", "Two rails (33.6 mm slot)", "Fits"],
                 ["Arcade button 30 mm", "~33 deep under the panel", "Top of the head, behind the matrix",
                  "Snaps into the 30 mm hole", "Fits"],
                 ["Microphone INMP441", "14 round", "Behind the forehead hole", "Flat pad - clip still to add",
                  "Fits"],
                 ["Speaker 3 W 8 ohm (FIT0502)", "70 x 30 x 16, 24 g", "Belly, behind the dot grille",
                  "4 screws on posts (63 x 24 pattern)", "Fits"],
                 ["Amplifier MAX98357A", "~19 x 18", "Body floor, between the foot pegs", "Clip/tape still to add",
                  "Fits"],
                 ["ESP32-DevKitC (38-pin)", "54.4 x 27.9", "Shelf on the body back wall", "Shelf - clip still to add",
                  "Fits"],
                 ["Accent LED 5 mm", "5 round", "Through the chest lightning bolt", "Push-fit", "Fits"],
                 ["Half breadboard (optional)", "82.5 x 54.5 x 8.5", "Head floor, lying flat on 3 mm standoffs",
                  "Standoffs still to add", "Fits (1-2 mm gap)"]],
                [38, 32, 42, 38, 20]),
          Spacer(1, 4),
          Paragraph("All components were checked with the rest of Sparky assembled. Positions are the planned "
                    "ones; after your parts arrive, measure them and the clips can be added.", SMALL),
          image(IMG / "sparky_viewer_section.png", 78,
                "Cut through the middle (front on the left): matrix behind the face, button above it, "
                "breadboard on the head floor, speaker and amp in the belly, ESP32 on its back shelf."),
          ]

    # ---------------------------------------------------------------- breadboard
    s += [Paragraph("3. The breadboard question", H2),
          Paragraph("You asked whether the half breadboard could go inside. The fit check tried it in five "
                    "places:", P),
          table([["Where", "Result"],
                 ["Head floor, lying flat (3 mm standoffs)", "<b>Fits</b> - with a 1-2 mm gap to the walls, even with "
                  "the ESP32 plugged into it, its USB plug, and 15 mm of room for jumper wires"],
                 ["Body floor, lying flat", "Does not fit - hits the amplifier"],
                 ["Body back wall, standing up", "Does not fit - goes through the rounded back wall"],
                 ["Head back, standing up", "Does not fit - goes through the dome"],
                 ["Anywhere outside the head floor", "Use the sliders in the viewer to try your own ideas"]],
                [70, 110]),
          Spacer(1, 4),
          image(IMG / "sparky_viewer_breadboard_head.png", 80,
                "The breadboard (grey) with the ESP32 (green) on the head floor, under the LED matrix (blue). "
                "The orange box is room for jumper wires."),
          Paragraph("So it <i>can</i> live in the head. That is handy: the matrix, button and mic are all in the "
                    "head, so their wires become very short, and only the speaker, amp, LED and USB wires go down "
                    "through the neck. The USB cable then runs from the back of the body, up through the neck, to "
                    "the ESP32. Two things to know: it is a tight fit (1-2 mm), and the breadboard needs two small "
                    "standoffs on the head floor, which are not in the CAD yet. For a later, tidier build, a small "
                    "soldered perfboard does the same job and is easier to fix in place.", P),
          ]

    # ---------------------------------------------------------------- stability
    s += [Paragraph("4. Will he stand up?", H2),
          table([["", "Value"],
                 ["Total weight with all parts", "about 500 g"],
                 ["Centre of mass", "centred left-right, 8 mm in front of the middle, 90 mm high"],
                 ["Tilt needed to fall backwards", "about 19 degrees"],
                 ["Tilt needed to fall forwards", "about 25 degrees"],
                 ["Tilt needed to fall sideways", "about 29 degrees"]],
                [70, 110]),
          Paragraph("That is steady for a desk toy. The long feet (72 mm, reaching under the whole body) are what "
                    "make this work - an earlier version with short feet would have tipped over backwards at "
                    "about 6 degrees, for example from a tug on the USB cable.", P)]

    # ---------------------------------------------------------------- face
    s += [PageBreak(), Paragraph("5. Sparky's face", H2),
          Paragraph("The face is the 32 x 8 blue LED matrix: four 8 x 8 blocks of 3 mm LEDs on a 4 mm pitch, seen "
                    "through a 126 x 30 mm window in a black screen (paint the recess black, or use black film). "
                    "A piece of smoked film over the window hides the unlit LEDs and makes the lit ones pop.", P),
          Table([[[sized(IMG / "sparky_face_happy.png", 85), Paragraph("Happy ^ ^ (the default)", CAPTION)],
                  [sized(IMG / "sparky_face_surprised.png", 85), Paragraph("Surprised O O", CAPTION)]]],
                colWidths=[90 * mm, 90 * mm]),
          Paragraph("The viewer has seven ready-made faces - happy, surprised, neutral (listening), wink, "
                    "sleepy, thinking and error - and a grid where you can click LEDs on and off to design your "
                    "own. It prints each face as 8 lines of 32 characters ('#' = on), ready to copy into the "
                    "firmware later.", P),
          Paragraph("One thing the render shows: the window frame covers about 1 mm around the edge of the "
                    "matrix so the board cannot fall out forwards. The very top and bottom rows of LEDs are "
                    "therefore about two-thirds visible (you can see it on the round 'O' eyes). Faces that keep "
                    "the outer rows empty, like the happy face, look perfect. If you want every row fully "
                    "visible, the window can be opened up to the full 128 x 32 mm and the matrix held only by its "
                    "rails and clips.", SMALL),
          PageBreak()]

    # ---------------------------------------------------------------- printing
    s += [Paragraph("6. 3D printing it - a guide for your first print", H2),
          Paragraph("Big idea: do not make Sparky your very first print. Print small test pieces first, check "
                    "your parts fit, then print the big piece.", BOX),
          Paragraph("Step by step", H3),
          steps([
              "<b>Find a printer and a helper.</b> Ask whether the university has a makerspace or lab technician. "
              "Someone who knows the printer is worth more than any setting in this guide.",
              "<b>Install the slicer</b> for that printer (Bambu Studio, PrusaSlicer or OrcaSlicer). The slicer "
              "turns the 3D file into printer instructions and tells you the real print time and material.",
              "<b>Print the test pieces first</b> (about 20 minutes each): a 30 mm button hole, a short piece of the "
              "matrix slot, one screw post and the LED hole. Check the button snaps in, the matrix slides in, an "
              "M2.5 screw grips, and the LED pushes through. If something is too tight, the CAD can be adjusted "
              "before the long print.",
              "<b>Print the body back panel</b> (smallest, quickest) and check it against the real ESP32.",
              "<b>Print the head back panel.</b>",
              "<b>Print the front piece last</b>, standing upright on its feet.",
          ]),
          Paragraph("Settings to start with", H3),
          table([["Setting", "Use", "Why"],
                 ["Material", "PLA", "Easiest to print, cheap, comes in light blue"],
                 ["Nozzle", "0.4 mm (0.6 mm if available)", "0.6 mm is roughly 30-40% faster and suits the 2 mm walls"],
                 ["Layer height", "0.2 mm (0.28 mm for speed)", "0.28 is faster but shows more lines on the round helmet"],
                 ["Walls / perimeters", "5 walls with a 0.4 nozzle (3 with 0.6)", "Makes the 2 mm walls fully solid "
                  "and the screw posts strong"],
                 ["Infill", "15%", "Only the feet and arms are thick enough to need it"],
                 ["Supports", "Tree supports, on build plate and on the model", "Needed under the head, under the arms, "
                  "inside the head ceiling and across the top of the face window"],
                 ["Brim", "Yes, 5-8 mm", "The front piece is tall and only touches the bed with its feet - a brim stops "
                  "it from tipping over mid-print"],
                 ["Orientation", "Front piece upright on its feet; panels lying on their open side",
                  "The open back lets you reach in and remove the supports"]],
                [30, 55, 95]),
          Paragraph("Time and material", H3),
          bullets([
              "Plastic: about 390 g for the three parts plus 50-100 g of supports. One 1 kg spool is enough, with "
              "room for a reprint.",
              "Time: very roughly 12-16 hours on a fast modern printer, or 30+ hours on an older one. Your slicer "
              "gives the real number when you load the file.",
              "Faster printing: use a 0.6 mm nozzle, 0.28 mm layers, and print the two back panels on another printer "
              "at the same time. Keep the 2 mm walls - thinner walls save little time and weaken the screw posts.",
          ]),
          Paragraph("Files: hardware/cad/sparky_v6_mascot/sparky_mascot.3mf (all three parts, for the slicer) and "
                    "sparky_mascot.step (for CAD).", SMALL),
          ]

    # ---------------------------------------------------------------- electronics
    s += [Paragraph("7. Wiring and power tips", H2),
          bullets([
              "<b>Get it working on the breadboard on your desk first.</b> The demo is about Sparky working, not about "
              "the shell.",
              "<b>Inside Sparky</b> you have two options: (1) the breadboard on the head floor (it fits - see section 3), "
              "or (2) jumper wires straight from the ESP32 pins to each module, with Wago 221 lever connectors "
              "(no soldering) to share 5 V and GND.",
              "<b>LED matrix pins:</b> if its 5-pin plug points out sideways from the end of the board, bend the pins "
              "backwards or solder the wires on - a sideways plug is too long to fit across the head.",
              "<b>Power is the most common ESP32 problem.</b> The matrix at full brightness plus the speaker at full "
              "volume can draw more than a laptop USB port gives. The ESP32 then keeps restarting with a "
              "'brownout detector triggered' message. Keep matrix brightness low (about 2-4 out of 15) and use a "
              "5 V / 2 A phone charger instead of a laptop port.",
              "<b>USB cable:</b> put a cable tie around the cable just inside the hole in the back. If someone pulls "
              "the cable, the tie takes the force instead of the ESP32's USB socket.",
          ])]

    # ---------------------------------------------------------------- assembly
    s += [Paragraph("8. Putting him together (no glue)", H2),
          steps([
              "Clean the supports out of all three parts.",
              "Push the arcade button into the hole on top of the head until it clicks.",
              "Slide the LED matrix into its rails from the back, LEDs facing the window.",
              "Place the mic board on its pad behind the forehead hole, sound hole facing out.",
              "Screw the speaker onto its four posts behind the grille (M2.5 or M3 self-tapping screws).",
              "Push the 5 mm LED into the hole in the lightning bolt.",
              "Place the amp on the body floor and the ESP32 on its shelf in the body back panel (or the breadboard "
              "on the head floor).",
              "Feed the USB cable in through the hole at the back of the body and plug it into the ESP32.",
              "Connect the wires; run the speaker/amp/LED wires up through the neck if the ESP32 is in the head.",
              "Screw on the body back panel (2 screws), then the head back panel (2 screws).",
          ]),
          Paragraph("Still to design once your parts arrive: small clips for the matrix (to stop it sliding "
                    "backwards), the mic, the amp and the ESP32, plus breadboard standoffs if you choose the head "
                    "position. They are left out until the real boards can be measured.", SMALL)]

    # ---------------------------------------------------------------- plan
    s += [Paragraph("9. Plan up to the demo (28 October)", H2),
          table([["When", "What"],
                 ["This week", "Wire everything on the breadboard and test it. Print the test pieces."],
                 ["When the parts arrive", "Measure the matrix, ESP32 and mic boards so the clips can be added. "
                  "Check which way the matrix pins point."],
                 ["After the test pieces fit", "Print the back panels, then the front piece."],
                 ["Backup for the demo", "If the print is not ready, demo with the open breadboard or the cereal-box "
                  "mock-up - the electronics and software are what is being demonstrated."]],
                [45, 135])]

    # ---------------------------------------------------------------- viewer
    s += [Paragraph("10. Using the interactive 3D viewer", H2),
          Paragraph("Open <b>docs/sparky_3d_viewer.html</b> in Chrome, Edge or Firefox. It works offline.", P),
          bullets([
              "Drag to rotate, right-drag to move, scroll to zoom. Click any part to see its name and size.",
              "'Shell see-through' makes the walls transparent; 'Slice open' cuts Sparky in half so you can look inside.",
              "Untick the back panels, or slide 'Pull back panels away', to see how he opens.",
              "Breadboard test: choose a place and orientation, or move it with the sliders. The box underneath "
              "tells you straight away whether it fits, is tight, or hits a wall or another part.",
              "'ESP32 goes' lets you put the ESP32 on its shelf or on the breadboard.",
              "The check uses each part's outer box, so near curved walls it errs on the safe side.",
          ])]

    # ---------------------------------------------------------------- sources
    s += [Paragraph("Sources for component sizes", H3),
          Paragraph("Speaker FIT0502: robotshop.com (DFRobot Stereo Enclosed Speaker 3W 8 ohm), digikey.in (FIT0502), "
                    "element14 (FIT0502), bastelgarage.ch (3W 8 ohm speaker in housing). LED matrix MAX7219 4-in-1: "
                    "handsontec.com datasheet, beemong.com, diyables.io (FC16), makerguides.com, opencircuit.shop. "
                    "ESP32-DevKitC and half breadboard: standard published board sizes.", SMALL)]

    doc = SimpleDocTemplate(str(OUT), pagesize=A4, leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=15 * mm, bottomMargin=18 * mm, title="Sparky build & print guide",
                            author="Sparky project")
    doc.build(s, onFirstPage=footer, onLaterPages=footer)
    print(f"Wrote {OUT}")


if __name__ == "__main__":
    build()
