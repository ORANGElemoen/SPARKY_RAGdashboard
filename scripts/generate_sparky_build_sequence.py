#!/usr/bin/env python3
"""
One-off generator for docs/sparky_build_sequence.pdf - the complete,
connection-by-connection breadboard build sequence for Sparky's electronics.

Assumes: ESP32-WROOM kept OFF the breadboard (most dev boards are too wide
for a half-size board), wired in entirely via jumper wires. Breadboard row
numbers below are a concrete suggested layout, not a hardware requirement -
what matters is that each pin gets its own row so it can be jumpered
individually; renumber to fit your actual board if needed.

Not part of the running app; run manually when the wiring changes:
    python scripts/generate_sparky_build_sequence.py
"""
from fpdf import FPDF

PAGE_W = 210 - 2 * 18


class Doc(FPDF):
    def header(self):
        pass

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(140, 140, 140)
        self.cell(0, 8, f"Sparky Build Sequence | Page {self.page_no()}", align="C")


def title_block(doc):
    doc.set_font("Helvetica", "B", 18)
    doc.set_text_color(13, 36, 54)
    doc.cell(0, 12, "Sparky Build Sequence", new_x="LMARGIN", new_y="NEXT")
    doc.set_font("Helvetica", "", 10)
    doc.set_text_color(90, 90, 90)
    doc.cell(0, 6, "Complete, connection-by-connection breadboard wiring instructions",
              new_x="LMARGIN", new_y="NEXT")
    doc.set_text_color(20, 20, 20)
    doc.ln(4)


def para(doc, text):
    doc.set_font("Helvetica", "", 10.5)
    doc.multi_cell(PAGE_W, 5.8, text, new_x="LMARGIN", new_y="NEXT")
    doc.ln(1)


def phase_header(doc, number, title):
    doc.ln(3)
    doc.set_fill_color(13, 36, 54)
    doc.set_text_color(255, 255, 255)
    doc.set_font("Helvetica", "B", 12.5)
    doc.cell(0, 9, f"  PHASE {number}: {title}", fill=True, new_x="LMARGIN", new_y="NEXT")
    doc.set_text_color(20, 20, 20)
    doc.ln(2)


def step(doc, number, text, warning=False):
    doc.set_font("Helvetica", "B", 10)
    doc.set_text_color(168, 80, 13) if warning else doc.set_text_color(58, 160, 216)
    doc.cell(8, 6, f"{number}.", new_x="RIGHT", new_y="TOP")
    doc.set_font("Helvetica", "", 10.5)
    doc.set_text_color(20, 20, 20)
    doc.multi_cell(PAGE_W - 8, 6, text, new_x="LMARGIN", new_y="NEXT")


def subnote(doc, text):
    doc.set_font("Helvetica", "I", 9)
    doc.set_text_color(150, 40, 30)
    doc.set_x(doc.get_x() + 8)
    doc.multi_cell(PAGE_W - 8, 5.5, text, new_x="LMARGIN", new_y="NEXT")
    doc.set_text_color(20, 20, 20)


def build():
    doc = Doc(format="A4")
    doc.set_auto_page_break(auto=True, margin=18)
    doc.set_margins(18, 15, 18)
    doc.add_page()

    title_block(doc)

    para(doc,
         "This is the full build order for wiring Sparky's electronics on the "
         "breadboard, one connection at a time. It assumes the ESP32-WROOM is "
         "kept OFF the breadboard and sitting beside it - most ESP32 dev boards "
         "are too wide for a half-size 400-point board, so every ESP32 "
         "connection uses its own jumper wire rather than the board plugging "
         "in directly.")
    para(doc,
         "Jumper wire types matter: use a MALE-TO-FEMALE jumper for anything "
         "connecting to the ESP32 (female end on the ESP32's pin, male end "
         "into the breadboard). Use a MALE-TO-MALE jumper for anything that "
         "connects two points that are both already on the breadboard "
         "(rail-to-rail, or a component's row to a rail).")
    para(doc,
         "Breadboard row numbers below are a concrete suggested layout so "
         "these instructions are unambiguous - not a hardware requirement. "
         "What actually matters is that each pin of a module lands in its "
         "own row, so it can be jumpered individually. Adjust the numbers to "
         "fit your actual board if the layout doesn't match.")

    # PHASE 0
    phase_header(doc, 0, "Before You Start - Physical Prep")
    step(doc, "0.1", "Solder the loose 6-pin header onto the INMP441 microphone module, if it "
                       "didn't ship pre-soldered - check the module on arrival.")
    step(doc, "0.2", "Solder two ~15cm wire leads onto the push button's two terminals "
                       "(these are 2.8mm spade-style terminals, not breadboard pins), "
                       "or crimp on 2.8mm female quick-disconnect spade connectors instead "
                       "if you'd rather keep it solder-free and removable.")
    step(doc, "0.3", "Check the MAX7219 dot matrix module on arrival: if it has its own pin "
                       "header on the board edge, it can go straight into the breadboard like "
                       "the other modules. If it only has the small included 5-wire cable, "
                       "you'll be plugging jumper wires onto that cable's connector instead - "
                       "either way, the pin names and connections below are the same.")
    step(doc, "0.4", "Confirm you have: the half-size breadboard, both jumper wire packs "
                       "(male-female and male-male), one resistor in the 150-330 ohm range "
                       "from your own stash, a small soldering iron, and the ESP32 itself.")

    # PHASE 1
    phase_header(doc, 1, "Breadboard Power Rails")
    step(doc, "1.1", "Orient the breadboard so both rail pairs (top and bottom edges) are "
                       "accessible. The top rail pair will be 5V/GND, the bottom rail pair "
                       "will be 3.3V/GND.")
    step(doc, "1.2", "MALE-TO-MALE jumper: bridge the top rail's GND line to the bottom "
                       "rail's GND line, so there is one shared ground plane across the "
                       "whole board.")
    step(doc, "1.3", "MALE-TO-FEMALE jumper: ESP32 '5V' or 'VIN' pin -> top rail, + line.")
    step(doc, "1.4", "MALE-TO-FEMALE jumper: ESP32 'GND' pin -> top rail, - line.")
    step(doc, "1.5", "MALE-TO-FEMALE jumper: ESP32 '3V3' pin -> bottom rail, + line.")
    subnote(doc, "Double-check with a multimeter (or just visually trace the wires) that "
                  "the bottom rail is genuinely 3.3V, not 5V, before continuing - the mic "
                  "in Phase 3 will be damaged if this is wrong.")

    # PHASE 2
    phase_header(doc, 2, "Place Components on the Breadboard")
    step(doc, "2.1", "MAX98357A amp: insert its pin header into rows 1-6, one pin per row "
                       "(VIN, GND, SD, BCLK, LRC, DIN in whichever order the module's own "
                       "silkscreen lists them). If your specific board also breaks out a GAIN "
                       "pin, give it row 7 too - not all cheap MAX98357A boards expose this "
                       "pin, so check your module first.")
    step(doc, "2.2", "MAX7219 dot matrix: insert its header (or its included cable's "
                       "connector) into rows 8-12, one pin per row (VCC, GND, CLK, DIN, CS).")
    step(doc, "2.3", "INMP441 mic: insert its newly-soldered header into rows 14-19, one pin "
                       "per row (VDD, GND, L/R, SCK, WS, SD).")
    step(doc, "2.4", "Plain white LED: insert its two legs into rows 21 and 22 - note which "
                       "leg is which: the LONGER leg is the anode (+), the SHORTER leg is the "
                       "cathode (-). If the legs have been trimmed level, look for a flat spot "
                       "on the LED's plastic dome, which marks the cathode side.")
    step(doc, "2.5", "Insert your chosen resistor (150-330 ohm) so one leg shares row 21 "
                       "(the LED's anode row) and the other leg sits in a fresh row, e.g. row 23.")

    doc.add_page()

    # PHASE 3
    phase_header(doc, 3, "Power Connections (Male-to-Male jumpers, breadboard-to-breadboard)")
    step(doc, "3.1", "Amp VIN row -> top rail, + line (5V).")
    step(doc, "3.2", "Amp GND row -> top rail, - line (GND).")
    step(doc, "3.3", "If your amp module breaks out a GAIN pin: GAIN row -> top rail, - line "
                       "(GND) - sets 12dB gain (louder) instead of the ~9dB default when left "
                       "unconnected. Idea from "
                       "https://www.phippselectronics.com/i2s-audio-on-the-esp32-s3/")
    step(doc, "3.4", "Matrix VCC row -> top rail, + line (5V).")
    step(doc, "3.5", "Matrix GND row -> top rail, - line (GND).")
    step(doc, "3.6", "Mic GND row -> top rail, - line (GND).")
    step(doc, "3.7", "Mic L/R row -> top rail, - line (GND) - selects the left/mono channel.")
    step(doc, "3.8", "Mic VDD row -> BOTTOM rail, + line (3.3V) ONLY.", warning=True)
    subnote(doc, "Never connect the mic's VDD to the 5V rail - the INMP441's datasheet is "
                  "explicit that 5V permanently destroys the chip.")
    step(doc, "3.9", "LED's resistor row (row 23) -> top rail, + line (5V).")

    # PHASE 4
    phase_header(doc, 4, "Signal Connections (Male-to-Female jumpers, ESP32 to breadboard)")
    step(doc, "4.1", "ESP32 GPIO 32 -> mic's SCK row (bit clock).")
    step(doc, "4.2", "ESP32 GPIO 25 -> mic's WS row (word select).")
    step(doc, "4.3", "ESP32 GPIO 33 -> mic's SD row (data out).")
    step(doc, "4.4", "ESP32 GPIO 27 -> amp's BCLK row.")
    step(doc, "4.5", "ESP32 GPIO 26 -> amp's LRC row.")
    step(doc, "4.6", "ESP32 GPIO 22 -> amp's DIN row.")
    step(doc, "4.7", "ESP32 GPIO 18 -> matrix's CLK row.")
    step(doc, "4.8", "ESP32 GPIO 23 -> matrix's DIN row.")
    step(doc, "4.9", "ESP32 GPIO 5 -> matrix's CS/LOAD row.")
    step(doc, "4.10", "ESP32 GPIO 4 -> LED's cathode row (row 22). Remember: this pin drives "
                        "the LED as a low-side switch - GPIO LOW turns the LED ON, GPIO HIGH "
                        "turns it OFF (inverted from the usual setup).")
    step(doc, "4.11", "ESP32 GPIO 13 -> a short loose wire or small exposed pad, for the "
                        "capacitive touch pad. No other component needed - just an exposed "
                        "conductor for a finger to touch.")
    step(doc, "4.12", "ESP32 GPIO 21 -> amp's SD row. This replaces the old always-on wiring: "
                        "SD is now under firmware control instead of hardwired to 3.3V. "
                        "Firmware should drive this pin HIGH to enable the amp and LOW to "
                        "mute it - in particular, mute the amp while the mic is actively "
                        "recording, so the speaker's own output doesn't bleed into the mic "
                        "(mic and speaker share one small enclosure on Sparky, so this "
                        "matters more here than it would on a more spread-out board).")

    # PHASE 5
    phase_header(doc, 5, "Push Button")
    step(doc, "5.1", "Button leg 1's soldered wire -> MALE-TO-FEMALE jumper -> ESP32 GPIO 14.")
    step(doc, "5.2", "Button leg 2's soldered wire -> MALE-TO-FEMALE jumper -> ESP32 GND "
                       "(or into any hole on the breadboard's GND rail, whichever is easier "
                       "to reach).")
    subnote(doc, "No resistor needed here - the firmware will enable the ESP32's internal "
                  "pull-up on GPIO 14, so the pin reads HIGH normally and LOW when the "
                  "button is pressed.")

    # PHASE 6
    phase_header(doc, 6, "Speaker")
    step(doc, "6.1", "Connect the speaker's two wires directly to the MAX98357A module's "
                       "speaker output terminal (its own screw terminal or JST connector) - "
                       "this does not go through the breadboard at all.")

    doc.add_page()

    # PHASE 7
    phase_header(doc, 7, "Pre-Power-On Checklist")
    checklist = [
        "INMP441 VDD is on the 3.3V rail - NOT 5V. Check this one twice.",
        "LED polarity is correct: anode (long leg) toward the resistor/5V side, "
        "cathode (short leg) toward GPIO 4.",
        "The two GND rail pairs (top and bottom) are bridged together with a "
        "male-to-male jumper.",
        "No bare wire ends are touching or bridging adjacent rows - a quick visual "
        "scan down each side of the breadboard.",
        "The amp's SD pin is connected to GPIO 21, not left floating or wired to a "
        "rail - firmware must drive it HIGH to hear anything.",
        "All ESP32 connections use male-to-female jumpers (female end on the ESP32).",
    ]
    for i, item in enumerate(checklist, start=1):
        step(doc, str(i), item)

    doc.ln(3)
    para(doc,
         "Once everything above checks out, power the ESP32 via USB-C from the power "
         "bank. Test one peripheral at a time in firmware rather than all at once - "
         "confirm the mic transcribes, then the amp/speaker plays audio, then the "
         "matrix lights up, then the LED and button - so any wiring mistake is easy "
         "to isolate to a single connection.")

    para(doc, "GPIO pin quick reference:")
    doc.set_font("Helvetica", "", 9.5)
    pin_table = [
        ("GPIO 32", "Mic SCK"), ("GPIO 25", "Mic WS"), ("GPIO 33", "Mic SD"),
        ("GPIO 27", "Amp BCLK"), ("GPIO 26", "Amp LRC"), ("GPIO 22", "Amp DIN"),
        ("GPIO 18", "Matrix CLK"), ("GPIO 23", "Matrix DIN"), ("GPIO 5", "Matrix CS"),
        ("GPIO 4", "LED cathode (low-side switch)"), ("GPIO 13", "Touch pad"),
        ("GPIO 14", "Push button (internal pull-up)"),
        ("GPIO 21", "Amp SD (mute control - HIGH = audio on)"),
    ]
    col_w = PAGE_W / 2
    for i in range(0, len(pin_table), 2):
        left = pin_table[i]
        right = pin_table[i + 1] if i + 1 < len(pin_table) else None
        doc.cell(col_w, 6, f"{left[0]}: {left[1]}")
        if right:
            doc.cell(col_w, 6, f"{right[0]}: {right[1]}")
        doc.ln()

    doc.add_page()
    doc.set_font("Helvetica", "B", 14)
    doc.set_text_color(13, 36, 54)
    doc.cell(0, 10, "Reference: Wiring Diagram", new_x="LMARGIN", new_y="NEXT")
    doc.set_text_color(20, 20, 20)
    doc.ln(2)
    doc.image("docs/sparky_wiring_diagram.png", x=doc.get_x(), w=PAGE_W)

    output_path = "docs/sparky_build_sequence.pdf"
    doc.output(output_path)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    build()
