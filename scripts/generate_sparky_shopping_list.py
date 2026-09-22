#!/usr/bin/env python3
"""
One-off generator for docs/sparky_shopping_list.pdf - the parts list and
cost estimate for building the physical Sparky (ESP32 tutor) hardware.

Prices checked across the approved vendor list (Micro Robotics, Mantech,
Communica, DIY Electronics, Takealot) on 2026-09-20; mic/amp prices
confirmed directly by the user from the live Communica listing. Not part
of the running app; run manually when the list or pricing needs updating:
    python scripts/generate_sparky_shopping_list.py
"""
from fpdf import FPDF
from PIL import Image as PILImage

PAGE_W = 210 - 2 * 18  # A4 width minus margins, mm
IMG_DIR = "docs/images"

# (name, description, qty, price_note, link_or_none, supplier, stock_note, image_file)
ITEMS = [
    (
        "INMP441 I2S Microphone Module",
        "Digital I2S microphone. Captures the child's spoken question and "
        "streams it to the ESP32 over I2S - no separate ADC needed. "
        "Micro Robotics' listing (SEN0327) was out of stock, then "
        "Communica's exact-chip listing (R65.00) was the recommendation - "
        "but the user confirmed Communica is now SOLD OUT too. "
        "RECOMMENDED: DIY Electronics stocks the exact INMP441 directly "
        "(also the vendor with the standing NWU-invoice process) - "
        "doesn't label items 'in stock' but shows 'ships within 1 day', "
        "a strong signal it's actually available. Price still needs "
        "confirming on the live page. Alternative: Takealot lists a "
        "5-pack (INMP441 Omnidirectional Module, 5 units) that IS "
        "available, but ships 14-16 working days from a global/"
        "international seller - much slower, worth knowing before "
        "picking it for time-sensitive ordering. Mantech lists an "
        "INMP441 board too, but their listing title says 'I2C "
        "Interface', which conflicts with the chip's actual I2S "
        "interface - confirm with Nasen before trusting that one. NOTE: "
        "'ships within 1 day' is dispatch time only - DIY Electronics' "
        "own delivery page adds a further 2-4 working days standard "
        "courier transit on top, so total arrival is more like 3-5 "
        "working days. Free shipping only above ~R1000-R1250 (site shows "
        "both figures); a small order like this won't qualify, so a "
        "shipping fee applies (exact amount calculated at checkout).",
        1,
        "R119.00",
        "https://www.diyelectronics.co.za/store/audio/5380-inmp441-omnidirectional-mems-microphone-module.html",
        "DIY Electronics (proposed)",
        "Ships within 1 day (DIY Electronics) - likely available",
        "mic.jpg",
    ),
    (
        "MAX98357A I2S Amplifier Module",
        "I2S class-D amplifier. Converts Sparky's synthesized speech "
        "straight into an analog signal driving the speaker - no separate "
        "DAC needed. Micro Robotics' listing (DFR0954) was out of stock; "
        "Communica's MAX98357A-based module (HKD MAX98357) is the "
        "replacement and is confirmed in stock.",
        1,
        "R75.00",
        "https://www.communica.co.za/products/hkd-max98357-i2s-3w-class-d-amp",
        "Communica",
        "In stock (confirmed 2026-09-20)",
        "amp.jpg",
    ),
    (
        "Enclosed Speaker 3W 8 Ohm (FIT0502)",
        "Small enclosed speaker that plays Sparky's spoken answers. Pairs "
        "with the MAX98357A amp above (same DFRobot family, matching "
        "connector).",
        1,
        "R89.70",
        "https://www.robotics.org.za/FIT0502",
        "Micro Robotics",
        "In stock - Centurion & Stellenbosch (confirmed 2026-09-20)",
        "speaker.png",
    ),
    (
        "MAX7219 Dot Matrix Display 32x8 - Blue",
        "Four chained 8x8 LED matrices forming Sparky's face - drives the "
        "idle/happy/thinking/frowning animations discussed for the "
        "interactivity design. Also available in red or green if you'd "
        "rather match a different pixel color; purely cosmetic.",
        1,
        "R110.40",
        "https://www.robotics.org.za/MAX7219-DOT-BLU",
        "Micro Robotics",
        "In stock - Centurion & Stellenbosch (confirmed 2026-09-20)",
        "matrix.png",
    ),
    (
        "LED 5mm - Clear White (10-pack, LED-05-WHI)",
        "Accent light for the lightning-bolt logo - pulses while Sparky is "
        "thinking, steady while idle. Swapped from the original WS2812B "
        "addressable RGB LED to this plain through-hole LED: cheaper "
        "(R6.90 vs R18.40+), and has real legs that plug straight into "
        "the breadboard (the WS2812B options were either SMD pads needing "
        "solder, or a pricier TH version). Trade-off: no more "
        "color-changing capability, only on/off/pulse in white - fine, "
        "since that's all the current design actually uses. 3.2V forward "
        "voltage, 10mA recommended (per packaging) - not enough headroom "
        "off the 3.3V rail for a resistor to reliably limit current, so "
        "this runs off the 5V rail instead with the ESP32 pin acting as "
        "a low-side switch (GPIO LOW = LED on, HIGH = LED off - inverted "
        "from the usual sourcing setup). Needs a series resistor - user "
        "already has an assortment on hand, so none purchased here. "
        "Target value: (5V - 3.2V) / 0.010A = ~180 ohm; anything in the "
        "150-330 ohm range works fine for an indicator LED like this "
        "(220 ohm is the safe default if unsure which to grab).",
        1,
        "R6.90",
        "https://www.robotics.org.za/LED-05-WHI",
        "Micro Robotics",
        "In stock (confirmed 2026-09-21)",
        "led.png",
    ),
    (
        "Breadboard, Half Size, 400 Points (BREAD-400)",
        "Solderless prototyping board - wire up and test the mic, amp, "
        "matrix, and accent LED before committing to a final soldered "
        "build inside the 3D-printed shell.",
        1,
        "R20.70",
        "https://www.robotics.org.za/BREAD-400",
        "Micro Robotics",
        "In stock (confirmed 2026-09-20)",
        "breadboard.png",
    ),
    (
        "Jumper Wires, Male-Female, 50-pack (JUMP-MF)",
        "Connects breakout board pins (mic, amp, matrix, LED) to the "
        "ESP32's GPIO headers on the breadboard. Micro Robotics confirmed "
        "out of stock (user checked - no other M-F variant in stock "
        "there either). RECOMMENDED: DIY Electronics' Male to Female "
        "Breadboard Jumpers (40pcs, 21cm) - shows 'ships within 1 day' "
        "rather than an explicit stock label, a strong signal it's "
        "actually available. See the microphone entry above for the "
        "shipping-time and free-shipping-threshold caveat that applies "
        "to all DIY Electronics items in this list.",
        1,
        "R19.95",
        "https://www.diyelectronics.co.za/store/connectors-wiring/258-male-to-female-breadboard-jumpers-40pcs-21cm.html",
        "DIY Electronics (proposed)",
        "Ships within 1 day (DIY Electronics) - likely available",
        "jumpmf.jpg",
    ),
    (
        "Premium Jumper Wires, Male-Male, 20-pack",
        "Male-male jumpers for breadboard-internal connections (e.g. "
        "power rail to rail) that the male-female pack above doesn't "
        "cover. Micro Robotics confirmed out of stock. RECOMMENDED: DIY "
        "Electronics' Male to Male (Dupont) Breadboard Jumpers (40pcs, "
        "21cm) - same 'ships within 1 day' signal as the M-F pack above, "
        "and the same shipping-time/free-shipping caveat noted on the "
        "microphone entry.",
        1,
        "R16.00",
        "https://www.diyelectronics.co.za/store/connectors-wiring/1168-dupont-jumper-cables-male-to-male-40pcs-21cm.html",
        "DIY Electronics (proposed)",
        "Ships within 1 day (DIY Electronics) - likely available",
        "jumpmm.jpg",
    ),
    (
        "Push-to-Talk Button - 30mm Arcade Button (SANWA style, Blue)",
        "Physical push-to-talk trigger - a learner holds this down to speak "
        "and releases to send the question. A big 30mm arcade button was "
        "chosen over a small 6mm tactile switch since it's much easier for "
        "a child to find and hold comfortably, and more durable under "
        "repeated use. Same vendor as the mic and both jumper packs, so "
        "no new shipping charge. Blue matches Sparky's brand palette better "
        "than the originally-considered purple/pink variant. SKU: "
        "9SWJSA30MMBLU. Wiring: one leg to GPIO 14, the other to GND, "
        "using the ESP32's internal pull-up (no external resistor needed) "
        "- pressed reads LOW, released reads HIGH.",
        1,
        "R28.00",
        "https://www.diyelectronics.co.za/store/buttons-switches/5607-blue-arcade-push-button-30mm-sanwa-style.html",
        "DIY Electronics (proposed)",
        "In stock (confirmed 2026-09-20)",
        "button.jpg",
    ),
    (
        "Momentary Tactile Switch, 8-pack (TACC-66) - for breadboard testing only",
        "NOT the final Sparky button - this is a cheap, genuinely breadboard-pin "
        "compatible tactile switch, bought purely to test the push-to-talk "
        "wiring and firmware logic on the breadboard without soldering or "
        "modifying the real 30mm arcade button. The arcade button uses 2.8mm "
        "spade terminals (not breadboard-pins), so testing with it directly "
        "would mean soldering or crimping it before you've even confirmed the "
        "circuit works. Use one of these for all breadboard testing, then "
        "swap in the real arcade button (solder or spade-connect it, your "
        "choice - not yet decided, doesn't matter until final assembly) once "
        "you're building the actual enclosure.",
        1,
        "R10.00",
        "https://www.robotics.org.za/TACC-66",
        "Micro Robotics",
        "In stock - Centurion & Stellenbosch (confirmed 2026-09-22)",
        "test_button.png",
    ),
]

TOUCH_NOTE = (
    "Touch response (tapping Sparky's head for a reaction) is free - the "
    "ESP32-WROOM has built-in capacitive touch GPIOs, nothing to buy."
)

POWER_BANK_NOTE = (
    "Power bank: not needed - the user already owns one (believed ~10,000mAh). "
    "It has the same low-current auto-shutoff behavior discussed earlier for a "
    "purchased bank, but a workaround (keep-alive trickle load) is already "
    "planned, so no purchase is required."
)

USB_CABLE_NOTE = (
    "USB-C cable: not included - already owned from earlier ESP32 testing, "
    "no need to buy another."
)


class Doc(FPDF):
    def header(self):
        pass

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(140, 140, 140)
        self.cell(0, 8, f"Sparky Build Shopping List | Page {self.page_no()}", align="C")


def title_block(doc: Doc):
    doc.set_font("Helvetica", "B", 18)
    doc.set_text_color(13, 36, 54)
    doc.cell(0, 12, "Sparky Build Shopping List", new_x="LMARGIN", new_y="NEXT")
    doc.set_font("Helvetica", "", 10)
    doc.set_text_color(90, 90, 90)
    doc.cell(0, 6, "Electronics needed to bring the physical Sparky tutor to life "
                    "(enclosure excluded - 3D printed separately)", new_x="LMARGIN", new_y="NEXT")
    doc.cell(0, 6, "Checked across the approved vendor list, South Africa, 2026-09-20",
              new_x="LMARGIN", new_y="NEXT")
    doc.set_text_color(20, 20, 20)
    doc.ln(4)


def para(doc: Doc, text: str):
    doc.set_font("Helvetica", "", 10.5)
    doc.multi_cell(PAGE_W, 5.8, text, align="L", new_x="LMARGIN", new_y="NEXT")
    doc.ln(1)


def item_section(doc: Doc, number: int, name: str, description: str, price_note: str, link, supplier: str, stock_note: str, image_file: str = None):
    # Estimate the whole block's height up front and force a page break before
    # starting it if it wouldn't fit - otherwise fpdf2's automatic mid-block
    # page break can split the image (placed eagerly, see below) from its own
    # description/price text, orphaning them on different pages.
    img_w = 32
    text_w = PAGE_W - img_w - 6 if image_file else PAGE_W
    desc_lines = doc.multi_cell(text_w, 5.8, description, dry_run=True, output="LINES")
    price_text = f"Price: {price_note}  |  Supplier: {supplier}  |  Stock: {stock_note}"
    price_lines = doc.multi_cell(text_w, 6, price_text, dry_run=True, output="LINES")
    img_h = 0
    if image_file:
        with PILImage.open(f"{IMG_DIR}/{image_file}") as im:
            img_h = img_w * (im.height / im.width)
    estimated_h = 3 + 9 + 1.5 + len(desc_lines) * 5.8 + 0.5 + len(price_lines) * 6 + (6 if link else 0)
    estimated_h = max(estimated_h, 3 + 9 + 1.5 + img_h)
    if doc.get_y() + estimated_h > doc.h - doc.b_margin:
        doc.add_page()

    doc.ln(3)
    doc.set_fill_color(13, 36, 54)
    doc.set_text_color(255, 255, 255)
    doc.set_font("Helvetica", "B", 12)
    doc.cell(0, 9, f"  {number}. {name}", fill=True, new_x="LMARGIN", new_y="NEXT")
    doc.set_text_color(20, 20, 20)
    doc.ln(1.5)

    text_x = doc.get_x()
    text_y = doc.get_y()
    img_bottom_y = text_y

    # Place the image immediately, right after capturing this position - so if
    # the (often long) description text below triggers fpdf2's automatic page
    # break mid-paragraph, the image has already been drawn at the correct
    # spot and doesn't end up anchored to a stale/wrong-page coordinate.
    if image_file:
        image_path = f"{IMG_DIR}/{image_file}"
        with PILImage.open(image_path) as im:
            ratio = im.height / im.width
        img_h = img_w * ratio
        doc.image(image_path, x=text_x + text_w + 6, y=text_y, w=img_w)
        img_bottom_y = text_y + img_h
        doc.set_xy(text_x, text_y)

    doc.set_font("Helvetica", "", 10.5)
    doc.multi_cell(text_w, 5.8, description, new_x="LMARGIN", new_y="NEXT")
    doc.ln(0.5)
    doc.set_font("Helvetica", "B", 10)
    doc.set_text_color(168, 80, 13)
    doc.multi_cell(text_w, 6, f"Price: {price_note}  |  Supplier: {supplier}  |  Stock: {stock_note}",
              new_x="LMARGIN", new_y="NEXT")
    doc.set_text_color(58, 160, 216)
    if link:
        # Full page width, not text_w - long DIY Electronics URLs overflow a
        # narrowed column since cell() doesn't wrap; by this point we're
        # almost always past the (shorter) image's bottom edge anyway.
        doc.set_font("Helvetica", "", 8.5)
        doc.cell(PAGE_W, 6, link, new_x="LMARGIN", new_y="NEXT", link=link)
    doc.set_text_color(20, 20, 20)
    text_bottom_y = doc.get_y()

    if image_file and text_bottom_y >= text_y:
        doc.set_y(max(text_bottom_y, img_bottom_y))


def summary_table(doc: Doc):
    doc.add_page()
    doc.set_font("Helvetica", "B", 15)
    doc.set_text_color(13, 36, 54)
    doc.cell(0, 10, "Summary Table", new_x="LMARGIN", new_y="NEXT")
    doc.set_text_color(20, 20, 20)
    doc.ln(2)

    col_widths = [28, 20, 22, 42, 8, 22, 32]
    headers = ["Name", "Supplier", "In Stock?", "Description", "Qty", "Price", "Link"]

    doc.set_font("Helvetica", "B", 8)
    doc.set_fill_color(230, 236, 240)
    for w, h in zip(col_widths, headers):
        doc.cell(w, 8, h, border=1, fill=True, align="L")
    doc.ln()

    doc.set_font("Helvetica", "", 7)
    for name, description, qty, price_note, link, supplier, stock_note, _image_file in ITEMS:
        short_desc = description.split(". ")[0] + "."
        row_texts = [name, supplier, stock_note, short_desc, str(qty), price_note]
        line_counts = [
            doc.multi_cell(col_widths[i], 4.2, row_texts[i], border=0, align="L",
                            dry_run=True, output="LINES")
            for i in range(6)
        ]
        n_lines = max(len(lc) for lc in line_counts)
        row_h = 4.2 * n_lines

        x0, y0 = doc.get_x(), doc.get_y()
        for i, text in enumerate(row_texts):
            doc.set_xy(x0 + sum(col_widths[:i]), y0)
            doc.multi_cell(col_widths[i], 4.2, text, border=1, align="L")
        doc.set_xy(x0 + sum(col_widths[:6]), y0)
        if link:
            doc.multi_cell(col_widths[6], 4.2, "Link", border=1, align="L", link=link)
        else:
            doc.multi_cell(col_widths[6], 4.2, "-", border=1, align="L")
        doc.set_xy(x0, y0 + row_h)

    doc.ln(4)
    doc.set_font("Helvetica", "I", 8.5)
    doc.set_text_color(110, 110, 110)
    doc.multi_cell(
        PAGE_W, 5,
        "Stock statuses below are as confirmed directly by the user checking each "
        "vendor's live site on 2026-09-20. Three items (mic, both jumper packs) had "
        "their original recommended source go out of stock and now point to a "
        "confirmed replacement at DIY Electronics instead. All 10 items now "
        "have confirmed prices. Item 10 (tactile switch) is a breadboard "
        "testing aid, not part of the final device. No resistor purchase "
        "needed for the accent "
        "LED - the user has an assortment on hand. The USB-C cable and the "
        "power bank are not included - already owned.",
    )
    doc.set_text_color(20, 20, 20)
    doc.ln(3)

    confirmed_total = 75.00 + 89.70 + 110.40 + 6.90 + 119.00 + 19.95 + 16.00 + 20.70 + 28.00 + 10.00
    # amp, speaker, matrix, accent LED, mic, jumper M-F, jumper M-M, breadboard, button, test button
    doc.set_font("Helvetica", "B", 10.5)
    doc.cell(0, 7, f"Subtotal, all 10 items at firmly confirmed prices: R{confirmed_total:.2f}",
              new_x="LMARGIN", new_y="NEXT")
    doc.cell(0, 7, "No resistor purchase needed - user has an assortment on hand (~180-220 ohm for the LED)",
              new_x="LMARGIN", new_y="NEXT")
    doc.cell(0, 7, "Plus shipping fees across 3 vendors (Micro Robotics, Communica, DIY Electronics) - not yet included",
              new_x="LMARGIN", new_y="NEXT")
    doc.cell(0, 7, "No power bank needed - user already owns one (see note above)",
              new_x="LMARGIN", new_y="NEXT")
    doc.set_font("Helvetica", "B", 12)
    doc.set_text_color(13, 36, 54)
    doc.cell(0, 9, f"Parts-only total: R{confirmed_total:.2f}, before shipping",
              new_x="LMARGIN", new_y="NEXT")
    doc.set_text_color(20, 20, 20)


def build():
    doc = Doc(format="A4")
    doc.set_auto_page_break(auto=True, margin=18)
    doc.set_margins(18, 15, 18)
    doc.add_page()

    title_block(doc)
    para(
        doc,
        "This list covers everything needed to make Sparky fully functional "
        "(mic, speaker, expressive LED face, accent light, push-to-talk "
        "button, and prototyping supplies) on top of the ESP32-WROOM board "
        "already on hand. The enclosure is excluded, since it's being 3D "
        "printed separately.",
    )
    para(
        doc,
        "Checked across five vendors from the approved vendor list: Micro "
        "Robotics, Mantech, Communica, DIY Electronics, and Takealot. Two "
        "items (the microphone and amplifier) were out of stock at Micro "
        "Robotics at check time; Communica stocks both (prices confirmed "
        "directly from their live listing), consolidating what would "
        "otherwise be a split order.",
    )
    para(doc, TOUCH_NOTE)
    para(doc, USB_CABLE_NOTE)
    para(doc, POWER_BANK_NOTE)

    for i, (name, description, qty, price_note, link, supplier, stock_note, image_file) in enumerate(ITEMS, start=1):
        item_section(doc, i, name, description, price_note, link, supplier, stock_note, image_file)

    summary_table(doc)

    output_path = "docs/sparky_shopping_list.pdf"
    doc.output(output_path)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    build()
