#!/usr/bin/env python3
"""
One-off generator for docs/sparky_expenditure_approval_form.pdf - a cover
note plus the completed Project Expenditure Approval Form fields, ready to
send to the study leader for Cost Centre input and sign-off.

Not part of the running app; run manually when the form's details change:
    python scripts/generate_sparky_expenditure_form.py
"""
from fpdf import FPDF

PAGE_W = 210 - 2 * 18

STUDENT_NUMBER = "34308229"
STUDENT_NAME = "Roelof Stephanus (Stephan)"
STUDENT_SURNAME = "Du Plessis"
STUDY_LEADER = "Mr. Herman Blackie"
PROJECT_TITLE = "Lack of Hands on STEM"
COURSE_LINE = "BEng Computer Electronic"
AVAILABLE_FUNDS = "R4,500.00"

ITEMS = [
    ("1", "INMP441 I2S Microphone Module", "DIY Electronics", "9MVOLNMP441", "1", "R119.00"),
    ("2", "MAX98357A I2S 3W Class D Amp Module", "Communica", "HKD MAX98357 I2S 3W CLASS D AMP", "1", "R75.00"),
    ("3", "Enclosed Speaker 3W 8 Ohm", "Micro Robotics", "FIT0502", "1", "R89.70"),
    ("4", "MAX7219 Dot Matrix Display 32x8 (Blue)", "Micro Robotics", "MAX7219-DOT-BLU", "1", "R110.40"),
    ("5", "LED 5mm Clear White, 10-pack", "Micro Robotics", "LED-05-WHI", "1", "R6.90"),
    ("6", "Breadboard, Half Size, 400 Points", "Micro Robotics", "BREAD-400", "1", "R20.70"),
    ("7", "Jumper Wires, Male-Female, 40pcs", "DIY Electronics", "9BBDUPONTFM", "1", "R19.95"),
    ("8", "Jumper Wires, Male-Male, 40pcs", "DIY Electronics", "9BBDUPONTMM", "1", "R16.00"),
    ("9", "Push-to-Talk Button, 30mm Arcade (Blue)", "DIY Electronics", "9SWJSA30MMBLU", "1", "R28.00"),
    ("10", "Momentary Tactile Switch, 8-pack (breadboard testing only)", "Micro Robotics", "TACC-66", "1", "R10.00"),
]
TOTAL = "R495.65"


class Doc(FPDF):
    def header(self):
        pass

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(140, 140, 140)
        self.cell(0, 8, f"Project Expenditure Approval Form | Page {self.page_no()}", align="C")


def para(doc, text, size=10.5):
    doc.set_font("Helvetica", "", size)
    doc.multi_cell(PAGE_W, 6, text, new_x="LMARGIN", new_y="NEXT")


def field_row(doc, label, value, highlight=False):
    doc.set_font("Helvetica", "B", 10)
    doc.set_text_color(20, 20, 20)
    doc.cell(55, 8, label, border=1)
    if highlight:
        doc.set_font("Helvetica", "BI", 10)
        doc.set_text_color(168, 40, 30)
        doc.cell(PAGE_W - 55, 8, value, border=1, new_x="LMARGIN", new_y="NEXT")
        doc.set_text_color(20, 20, 20)
    else:
        doc.set_font("Helvetica", "", 10)
        doc.cell(PAGE_W - 55, 8, value, border=1, new_x="LMARGIN", new_y="NEXT")


def build():
    doc = Doc(format="A4")
    doc.set_auto_page_break(auto=True, margin=18)
    doc.set_margins(18, 15, 18)
    doc.add_page()

    # Title
    doc.set_font("Helvetica", "B", 16)
    doc.set_text_color(13, 36, 54)
    doc.cell(0, 10, "Project Expenditure Approval Form", new_x="LMARGIN", new_y="NEXT")
    doc.set_text_color(20, 20, 20)
    doc.ln(4)

    # Cover note to the study leader
    doc.set_font("Helvetica", "B", 10.5)
    doc.cell(0, 6, f"To: {STUDY_LEADER} (Study Leader)", new_x="LMARGIN", new_y="NEXT")
    doc.cell(0, 6, f"From: {STUDENT_NAME} {STUDENT_SURNAME} (Student Number: {STUDENT_NUMBER})",
              new_x="LMARGIN", new_y="NEXT")
    doc.cell(0, 6, f"Re: Expenditure approval - {PROJECT_TITLE}", new_x="LMARGIN", new_y="NEXT")
    doc.ln(3)

    para(doc,
         "Please find below the completed expenditure form for the electronic components "
         "required for this project. Two things I'd appreciate your input on before I submit "
         "this for ordering:")
    doc.set_font("Helvetica", "", 10.5)
    doc.multi_cell(PAGE_W, 6,
                    "  1.  The Cost Centre field below is not yet completed - could you "
                    "please provide or confirm the correct code for this project's budget?\n"
                    "  2.  Could you please review the component list and confirm you're "
                    "happy with the selections?",
                    new_x="LMARGIN", new_y="NEXT")
    doc.ln(2)
    para(doc,
         f"Total cost comes to {TOTAL}, comfortably within the {AVAILABLE_FUNDS} allocated "
         f"for {COURSE_LINE}.")
    para(doc,
         "Once confirmed, I'll submit quote requests to the listed vendors and forward the "
         "completed form to Mr. Rhoderick Williams for processing.")
    doc.ln(4)

    # Form fields
    doc.set_font("Helvetica", "B", 13)
    doc.set_text_color(13, 36, 54)
    doc.cell(0, 9, "Student & Project Details", new_x="LMARGIN", new_y="NEXT")
    doc.set_text_color(20, 20, 20)
    doc.ln(1)

    field_row(doc, "Student Number", STUDENT_NUMBER)
    field_row(doc, "Name", STUDENT_NAME)
    field_row(doc, "Surname", STUDENT_SURNAME)
    field_row(doc, "Study Leader", STUDY_LEADER)
    field_row(doc, "Project", PROJECT_TITLE)
    field_row(doc, "Cost Centre", "[ TO BE COMPLETED BY STUDY LEADER ]", highlight=True)
    field_row(doc, "Course / Budget Line", COURSE_LINE)
    field_row(doc, "Available Funds", AVAILABLE_FUNDS)
    field_row(doc, "Source of Additional Funding", "Not required")
    field_row(doc, "Total Project Expenditure", TOTAL)
    doc.ln(6)

    # Purchase details table
    doc.set_font("Helvetica", "B", 13)
    doc.set_text_color(13, 36, 54)
    doc.cell(0, 9, "Purchase Details", new_x="LMARGIN", new_y="NEXT")
    doc.set_text_color(20, 20, 20)
    doc.ln(1)

    col_widths = [8, 62, 30, 42, 10, 22]
    headers = ["#", "Description", "Supplier", "Reference", "Qty", "Cost"]
    doc.set_font("Helvetica", "B", 8.5)
    doc.set_fill_color(230, 236, 240)
    for w, h in zip(col_widths, headers):
        doc.cell(w, 8, h, border=1, fill=True, align="L")
    doc.ln()

    doc.set_font("Helvetica", "", 8)
    for row in ITEMS:
        x0, y0 = doc.get_x(), doc.get_y()
        line_counts = [
            doc.multi_cell(col_widths[i], 4.5, row[i], border=0, dry_run=True, output="LINES")
            for i in range(len(row))
        ]
        n_lines = max(len(lc) for lc in line_counts)
        row_h = 4.5 * n_lines
        for i, text in enumerate(row):
            doc.set_xy(x0 + sum(col_widths[:i]), y0)
            doc.multi_cell(col_widths[i], 4.5, text, border=1, align="L")
        doc.set_xy(x0, y0 + row_h)

    doc.ln(4)
    doc.set_font("Helvetica", "B", 11)
    doc.cell(0, 8, f"Total: {TOTAL}", new_x="LMARGIN", new_y="NEXT")
    doc.ln(8)

    # Approval section
    doc.set_font("Helvetica", "B", 13)
    doc.set_text_color(13, 36, 54)
    doc.cell(0, 9, "Approval", new_x="LMARGIN", new_y="NEXT")
    doc.set_text_color(20, 20, 20)
    doc.ln(4)
    doc.set_font("Helvetica", "", 10.5)
    doc.cell(90, 8, "Study Leader Signature: ______________________")
    doc.cell(0, 8, "Date: ______________________", new_x="LMARGIN", new_y="NEXT")

    output_path = "docs/sparky_expenditure_approval_form.pdf"
    doc.output(output_path)
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    build()
