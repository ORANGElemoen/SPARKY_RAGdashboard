#!/usr/bin/env python3
"""
One-off generator for docs/hardware_demo_script.pdf - cue cards for
re-running the Sparky hardware/dashboard demo (WiFi captive portal,
Sparky-branded admin dashboard, real ESP32-to-backend voice pipeline test).

Covers what was added since docs/demo_script.pdf (the earlier, software-only
demo doc) - that one predates the physical ESP32 entirely. This one is
hardware-focused per the project leader's next check-in; CAD/enclosure work
is deliberately out of scope here.

Not part of the running app; run manually when the content needs updating:
    python scripts/generate_hardware_demo_script.py
"""
from fpdf import FPDF

PAGE_W = 210 - 2 * 18  # A4 width minus margins, mm


class Doc(FPDF):
    def header(self):
        pass

    def footer(self):
        self.set_y(-12)
        self.set_font("Helvetica", "I", 8)
        self.set_text_color(140, 140, 140)
        self.cell(0, 8, f"Sparky - Hardware Demo Script | Page {self.page_no()}", align="C")


def section(doc: Doc, number: str, title: str, on_screen: str = None):
    doc.ln(4)
    doc.set_fill_color(30, 41, 82)
    doc.set_text_color(255, 255, 255)
    doc.set_font("Helvetica", "B", 13)
    doc.cell(0, 10, f"  {number}. {title}", fill=True, new_x="LMARGIN", new_y="NEXT")
    doc.set_text_color(20, 20, 20)
    if on_screen:
        doc.ln(2)
        doc.set_font("Helvetica", "BI", 9.5)
        doc.set_text_color(90, 90, 90)
        doc.multi_cell(PAGE_W, 5.5, f"ON SCREEN: {on_screen}", align="L", new_x="LMARGIN", new_y="NEXT")
        doc.set_text_color(20, 20, 20)
    doc.ln(1)


def para(doc: Doc, text: str):
    doc.set_font("Helvetica", "", 10.5)
    doc.multi_cell(PAGE_W, 5.8, text, align="L", markdown=True, new_x="LMARGIN", new_y="NEXT")
    doc.ln(1)


def bullet(doc: Doc, text: str):
    doc.set_font("Helvetica", "", 10.5)
    doc.multi_cell(PAGE_W, 5.8, f"-  {text}", align="L", markdown=True, new_x="LMARGIN", new_y="NEXT")


def numbered(doc: Doc, n: int, text: str):
    doc.set_font("Helvetica", "", 10.5)
    doc.multi_cell(PAGE_W, 5.8, f"{n}.  {text}", align="L", markdown=True, new_x="LMARGIN", new_y="NEXT")


def subhead(doc: Doc, text: str):
    doc.ln(1)
    doc.set_font("Helvetica", "B", 10.5)
    doc.set_text_color(30, 41, 82)
    doc.cell(0, 6, text, new_x="LMARGIN", new_y="NEXT")
    doc.set_text_color(20, 20, 20)


def qa(doc: Doc, question: str, answer: str):
    doc.set_font("Helvetica", "B", 10.5)
    doc.set_text_color(150, 30, 30)
    doc.multi_cell(PAGE_W, 5.8, f"Q: {question}", align="L", new_x="LMARGIN", new_y="NEXT")
    doc.set_font("Helvetica", "", 10.5)
    doc.set_text_color(20, 20, 20)
    doc.multi_cell(PAGE_W, 5.8, f"A: {answer}", align="L", new_x="LMARGIN", new_y="NEXT")
    doc.ln(3)


doc = Doc()
doc.set_auto_page_break(auto=True, margin=18)
doc.set_margins(18, 15, 18)
doc.add_page()

# Title
doc.set_font("Helvetica", "B", 20)
doc.set_text_color(30, 41, 82)
doc.cell(0, 12, "Sparky", align="C", new_x="LMARGIN", new_y="NEXT")
doc.set_font("Helvetica", "", 13)
doc.set_text_color(80, 80, 80)
doc.cell(0, 8, "Hardware & Dashboard Demo Script", align="C", new_x="LMARGIN", new_y="NEXT")
doc.set_font("Helvetica", "I", 10)
doc.cell(0, 6, "What's new since the last demo: real ESP32 hardware, WiFi onboarding, Sparky-branded admin",
          align="C", new_x="LMARGIN", new_y="NEXT")
doc.ln(4)
doc.set_text_color(20, 20, 20)

section(doc, "0", "Recap - What's New Since Last Time")
para(doc, "The previous demo (docs/demo_script.pdf) covered the software side only - no ESP32 existed "
    "yet, and the hardware wire protocol was shown simulated via a test page. Since then:")
bullet(doc, "Real ESP32-WROOM-32 hardware was sourced, flashed, and brought up.")
bullet(doc, "A branded WiFi captive portal (WiFiManager) now handles onboarding a Sparky unit onto a "
    "local network with no hardcoded credentials and no laptop/serial cable required after first flash.")
bullet(doc, "The admin dashboard was rebranded to Sparky, and a device delete feature (permanently "
    "remove a revoked device) was added alongside the existing register/revoke flow.")
bullet(doc, "The full software pipeline - audio in, transcription, tutor answer, synthesized answer out - "
    "was tested end-to-end against this real physical unit's real network stack and HTTP client, not "
    "just a browser or the protocol test page.")
para(doc, "**Scope, stated plainly so it isn't oversold:** the mic/amp/speaker circuit hasn't been built "
    "yet - today's unit is bare ESP32 only. The firmware sends a pre-recorded test WAV (embedded in "
    "firmware) instead of a live recording, and there's nothing on the device yet to play the spoken "
    "answer back through. What this demo proves is that the real hardware's WiFi onboarding, HTTP "
    "client, and device authentication genuinely talk to the real backend end-to-end - the remaining "
    "gap is physical audio I/O, which is a wiring/assembly task, not a software one.")
para(doc, "This script covers three demo segments in order: the dashboard, the captive portal (which "
    "also triggers the pipeline test automatically), and verifying that exchange server-side. "
    "CAD/enclosure work is a separate, ongoing track and isn't shown here.")

section(doc, "1", "Setup Checklist (do this before the audience arrives)")
numbered(doc, 1, "Start Ollama and confirm the default model is pulled (`ollama list`).")
numbered(doc, 2, "Start the backend: `python simple_api.py` from the repo root. Note the machine's LAN "
    "IP (not localhost/127.0.0.1) - the ESP32 needs a real address on the same WiFi network.")
numbered(doc, 3, "Open the admin dashboard in a browser at `http://<your-lan-ip>:8001/admin` and confirm "
    "it loads with current Sparky branding.")
numbered(doc, 4, "Power on the ESP32. If it should demo the captive portal fresh, trigger a WiFi-settings "
    "reset first (either the reset routine in the sketch, or hold the configured reset button/pin) so it "
    "boots straight into its own onboarding hotspot instead of reconnecting silently.")
numbered(doc, 5, "Have a phone or laptop ready to join the ESP32's onboarding hotspot on cue.")

section(doc, "2", "Sparky-Branded Admin Dashboard", "/admin, /admin/devices/view, /admin/interaction-log/view")
para(doc, "Quick tour of what changed here - this is the operator/teacher-facing side of the system.")
bullet(doc, "Sparky branding throughout - the dashboard, devices page, interaction log, document "
    "management, diagnostics, and protocol test page all carry consistent Sparky styling now, not the "
    "generic RAG-system look from earlier.")
subhead(doc, "Devices page:")
bullet(doc, "Register a device -> a one-time API key is shown, exactly once, to be copied into that "
    "unit's firmware (same hashed-key model as before - see the original demo script's device-auth Q&A "
    "if asked, it hasn't changed).")
bullet(doc, "Revoke a device (orange, reversible) vs. Delete a device (red, only available once already "
    "revoked, permanently removes it). Two-step by design - you can't accidentally hard-delete a live "
    "device.")
subhead(doc, "Interaction log page - new device filter:")
bullet(doc, "Filter the log down to a single device's questions using the Device dropdown.")
bullet(doc, "With a device selected, an AI-generated activity summary appears: a short, plain-language "
    "narrative (built from the same local Ollama model, no cloud call) covering what topics that "
    "learner explored, signs of struggle, and what they seemed most engaged with - written for a "
    "teacher reviewing a learner's session, not a developer.")
para(doc, "**Good line for a project leader specifically:** this turns a raw chat log into something a "
    "non-technical teacher could actually read and act on, entirely offline.")

section(doc, "3", "WiFi Captive Portal (this also fires the pipeline test)", "on the physical ESP32 unit")
para(doc, "This replaces hardcoded WiFi credentials in firmware - the real deployment story is a "
    "teacher or technician with no coding ability setting up a unit on-site. On this unit, the "
    "firmware is wired to automatically send its embedded test audio file the moment WiFi connects - "
    "so finishing the portal *is* the pipeline test, in one motion, not two separate demo steps.")
numbered(doc, 1, "Power on the ESP32 with WiFi settings cleared (see Setup step 4). It boots into its "
    "own access point instead of trying to connect to anything.")
numbered(doc, 2, "On a phone/laptop, join that hotspot. Most phones auto-open the portal page; "
    "otherwise navigate to the ESP32's AP address manually.")
numbered(doc, 3, "Show the portal page itself is Sparky-branded (custom head element/styling), not the "
    "generic WiFiManager default page.")
numbered(doc, 4, "Pick the real WiFi network from the scanned list, enter its password, submit.")
numbered(doc, 5, "The ESP32 reboots and joins the real network - and immediately, automatically, sends "
    "its embedded test audio file to the backend. Nothing else to press.")
para(doc, "**If asked why the portal matters:** low-connectivity deployment sites won't always have "
    "someone who can flash firmware or edit a config file to change WiFi networks - this makes "
    "onboarding (and re-onboarding after a network change) a no-code, on-device process.")

section(doc, "4", "Verifying the Round-Trip, Server-Side", "server console + admin Interaction Log + admin Devices")
para(doc, "Because there's no mic or speaker on this unit yet, there is no audible confirmation to "
    "point to - verification happens entirely by checking the server independently agrees the exchange "
    "happened. Check all three; each is separate evidence, not just one screen repeated:")
numbered(doc, 1, "**Server console** (the terminal running simple_api.py) - the transcript and "
    "generated answer print live as the request is processed. This is the most reliable evidence, "
    "since it comes straight from the backend, not from the device's own limited feedback.")
numbered(doc, 2, "**Admin Interaction Log**, filtered to this device - the new entry appears with the "
    "real transcript, answer, and grounding badge, tied to that specific device's ID.")
numbered(doc, 3, "**Admin Devices page** - that device's \"last seen\" timestamp updates to just now, "
    "independent confirmation the request really came from that physical unit's registered key.")
para(doc, "**Honest caveat if asked:** this proves the ESP32's real WiFi stack, HTTP client, and device "
    "key genuinely reached the backend and got a correct answer back - not a simulation. It does not "
    "yet prove live microphone capture or audible playback, since that circuit isn't assembled. That's "
    "the next concrete milestone, not a hidden gap - worth saying so directly rather than implying "
    "more than what's built.")

section(doc, "5", "Other Things Worth Showing, If Time Allows")
bullet(doc, "**On-demand translation for QA review** (Text Chat / Interaction Log - Translate control): "
    "lets a reviewer check answer quality in a language they're more fluent in without changing the "
    "tutor's actual response language.")
bullet(doc, "**Response cache language fix:** a real bug where a cached answer could be served back in "
    "the wrong language after a language switch was found and fixed - good example of the kind of "
    "reliability issue that only shows up with multiple languages in real use, worth mentioning if the "
    "project leader asks about testing rigor.")
bullet(doc, "Everything in the original demo script (Sections 1-11 of docs/demo_script.pdf) still "
    "applies and hasn't changed - Text Chat, Voice Chat over the browser, document management, "
    "concurrency/load-test story, and multi-language support. This new script only covers what's new.")

doc.add_page()
doc.set_font("Helvetica", "B", 15)
doc.set_text_color(30, 41, 82)
doc.cell(0, 10, "Anticipated Q&A - Hardware-Specific", new_x="LMARGIN", new_y="NEXT")
doc.ln(2)
doc.set_text_color(20, 20, 20)

qa(doc, "Why a captive portal instead of just hardcoding WiFi credentials in firmware?",
   "Hardcoded credentials mean re-flashing firmware every time a unit moves networks. A captive portal "
   "lets anyone on-site - not just someone who can program the device - onboard or re-onboard it.")
qa(doc, "What happens if the ESP32 loses WiFi mid-deployment?",
   "It falls back to its own onboarding hotspot rather than failing silently, so it's always "
   "recoverable without physical reflashing - this fallback was specifically tested, not just assumed.")
qa(doc, "How do you know the voice pipeline actually worked on real hardware, not just in a browser?",
   "Confirmed independently via the backend's own server-side logs showing the real transcript and "
   "generated answer for that request, plus the resulting interaction log entry tied to that specific "
   "device's ID - not just trusting the device's own limited on-screen feedback.")
qa(doc, "Can a device be permanently removed if it's lost, stolen, or decommissioned?",
   "Yes - revoke immediately disables its key; delete (only available after revoking) permanently "
   "removes the device record. Two-step so a live device can't be hard-deleted by accident.")
qa(doc, "What's the AI-generated activity summary actually useful for?",
   "Gives a teacher a plain-language read on one learner's session - topics covered, signs of "
   "struggle, engagement - without them having to read a raw transcript, and without any cloud call.")
qa(doc, "Why isn't the unit actually talking today - no live mic, no spoken answer?",
   "The mic/amp/speaker circuit hasn't been assembled yet - this unit is bare ESP32 for now, running "
   "a firmware build that sends an embedded test recording instead of a live one. Today's demo proves "
   "the harder, less visible part - real WiFi onboarding, HTTP, and device auth all working against "
   "actual hardware. Wiring up audio I/O is a follow-on assembly task, not a software unknown.")

doc.output("docs/hardware_demo_script.pdf")
print("Wrote docs/hardware_demo_script.pdf")
