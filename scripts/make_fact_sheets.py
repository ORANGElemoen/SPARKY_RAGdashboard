#!/usr/bin/env python3
"""
Sparky's fact sheets: one A4 PDF per question children often ask, written for children in South
Africa, ready to upload to the tutor as documents. They complement the experiment sheets
(scripts/make_experiment_pdfs.py), which are hands-on activities.

Each sheet has a short answer, a simple explanation, key words, "common mix-ups" (the wrong ideas
children, and small AI models, often have) and something to try. One question per file and under
2000 characters, for the same reason as the experiment sheets: the tutor then retrieves it whole.

    python scripts/make_fact_sheets.py   -> docs/fact-sheets/*.pdf  (needs Microsoft Edge or Chrome)
"""
import html
import subprocess
import sys
import tempfile
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "fact-sheets"
BROWSERS = [Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
            Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"),
            Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")]
MAX_CHARS = 2000  # MAX_CONTEXT_CHARS in core/services/simple_rag_service.py

SHEETS = [
    # ------------------------------------------------------------------ Biology
    dict(
        category="Biology", title="How Do Plants Make Their Food?", ages="7+",
        answer="Plants make their own food in their leaves, using sunlight, water and air. This is called "
               "photosynthesis.",
        explain=["Roots take in water from the soil. Tiny holes under the leaves take in a gas from the air "
                 "called carbon dioxide.",
                 "The green colour in leaves, chlorophyll, catches sunlight.",
                 "The leaf uses the sunlight's energy to turn water and carbon dioxide into sugar. The sugar "
                 "is the plant's food, for growing.",
                 "The plant gives out oxygen, the gas we need to breathe."],
        words=[("Photosynthesis", "making food from light"), ("Chlorophyll", "the green stuff in leaves")],
        mixups=["Plants do not eat soil. Soil gives them water and minerals, but they make their food themselves.",
                "Plants need light to make food: a plant kept in a dark cupboard turns pale and weak."],
        local="The Cape Floral Kingdom in the Western Cape has about 9,000 kinds of plants, and most of them "
              "grow nowhere else on Earth.",
        try_it="Cover one leaf of a pot plant with foil for a week (with a grown-up's OK). It turns pale "
               "without light.",
        ask=["Why are most leaves green?", "Do plants breathe?"],
    ),
    dict(
        category="Biology", title="How Does Your Heart Work?", ages="7+",
        answer="Your heart is a strong muscle about the size of your fist. It pumps blood all around your "
               "body, all day and all night.",
        explain=["Each beat squeezes blood into tubes called arteries, which carry it to every part of you.",
                 "Blood carries oxygen from your lungs and food from your meal to all your cells.",
                 "Veins bring the blood back to the heart, and it goes to the lungs to collect fresh oxygen.",
                 "A child's heart beats about 70 to 100 times a minute when resting, and faster when you run."],
        words=[("Pulse", "the beat you feel in your wrist or neck"), ("Arteries and veins", "blood's roads")],
        mixups=["Blood is never blue. Blood in veins is dark red; veins only look blue through your skin.",
                "Your heart is not on the far left of your chest: it is in the middle, tilted a little left."],
        local="The first human heart transplant was done in Cape Town in 1967, by Dr Chris Barnard at Groote "
              "Schuur Hospital.",
        try_it="Put two fingers on your wrist and count the beats for 15 seconds, then times 4. Jump for a "
               "minute and count again!",
        ask=["Why does my heart beat faster when I run?", "What is blood made of?"],
    ),
    dict(
        category="Biology", title="How Do Frogs and Butterflies Change as They Grow?", ages="5+",
        answer="Frogs and butterflies go through big changes as they grow up. This is called metamorphosis.",
        explain=["A frog starts as an egg in water. A tadpole hatches, with a tail and gills to breathe "
                 "underwater.",
                 "The tadpole grows legs, its tail shrinks, and it grows lungs. It becomes a small froglet, "
                 "then a frog that can live on land.",
                 "A butterfly starts as an egg on a leaf. A caterpillar hatches and eats and eats.",
                 "The caterpillar makes a hard case called a chrysalis. Inside, it changes completely, and a "
                 "butterfly comes out."],
        words=[("Metamorphosis", "a big change in body shape"), ("Larva", "the young stage, like a caterpillar")],
        mixups=["A tadpole is not a fish: it is a baby frog.",
                "A caterpillar does not just grow wings: inside the chrysalis its whole body is rebuilt."],
        local="The African bullfrog is one of the biggest frogs in Africa. The father guards his tadpoles and "
              "even digs channels to save them when their pond dries up.",
        try_it="Look under leaves in a garden for tiny eggs or caterpillars. Only look, don't touch: some "
               "caterpillars have stinging hairs.",
        ask=["How long is a frog a tadpole?", "Do moths change like butterflies?"],
    ),
    # ------------------------------------------------------------------ Astronomy
    dict(
        category="Astronomy", title="What Are the Planets?", ages="7+",
        answer="Eight planets travel around our Sun. In order from the Sun they are Mercury, Venus, Earth, "
               "Mars, Jupiter, Saturn, Uranus and Neptune.",
        explain=["The Sun is a star. It is not a planet, and it gives the planets light and heat.",
                 "The four closest planets are small and rocky. The four far ones are giant balls of gas and ice.",
                 "Jupiter is the biggest planet. Mercury is the smallest and closest to the Sun.",
                 "Venus is the hottest planet, even though Mercury is closer, because its thick clouds trap heat.",
                 "Earth is the only planet we know of with living things."],
        words=[("Orbit", "the path around the Sun"), ("Dwarf planet", "a small world like Pluto")],
        mixups=["Pluto is not a planet any more: since 2006 it is called a dwarf planet.",
                "Stars twinkle; planets usually shine with a steady light."],
        local="SALT, one of the biggest telescopes in the southern half of the world, is near Sutherland in "
              "the Northern Cape, where the night sky is very dark.",
        try_it="Remember the order with: My Very Eager Mother Just Served Us Nachos.",
        ask=["Which planet has rings?", "Could people live on Mars?"],
    ),
    dict(
        category="Astronomy", title="Why Does the Moon Change Shape?", ages="7+",
        answer="The Moon does not really change shape. We just see different amounts of its sunny side as it "
               "travels around the Earth.",
        explain=["The Moon makes no light of its own. It shines because sunlight lights it up.",
                 "Half of the Moon is always lit by the Sun, like half of a ball in torchlight.",
                 "The Moon goes around the Earth about once a month: from one new moon to the next takes "
                 "about 29 and a half days.",
                 "At new moon we see none of the sunny side, at full moon all of it, and crescent and half "
                 "moons in between. These are the phases of the Moon."],
        words=[("Phases", "the shapes the Moon seems to have"), ("Waxing and waning", "growing and shrinking")],
        mixups=["The phases are not caused by the Earth's shadow. The Earth's shadow on the Moon is a lunar "
                "eclipse, which happens only now and then, at full moon.",
                "In South Africa the growing Moon is lit on the left. Pictures from the north show it on the right."],
        local="Many farmers in Southern Africa have long used the Moon's phases to count the months.",
        try_it="In a dark room, hold a ball at arm's length near a lamp and turn slowly around. Watch the "
               "lit part change, just like the Moon!",
        ask=["Why can we sometimes see the Moon in the day?", "What is a lunar eclipse?"],
    ),
    dict(
        category="Astronomy", title="Why Do We Have Day, Night and Seasons?", ages="7+",
        answer="We have day and night because the Earth spins. We have seasons because the Earth is tilted "
               "as it travels around the Sun.",
        explain=["The Earth spins around once every 24 hours. The side facing the Sun has day; the other side "
                 "has night.",
                 "The Earth takes one year, about 365 days, to go all the way around the Sun.",
                 "The Earth is tilted. When the southern half leans towards the Sun, sunlight is stronger and "
                 "days are longer: it is summer in South Africa.",
                 "Six months later the southern half leans away from the Sun, and we have winter."],
        words=[("Axis", "the line the Earth spins around"), ("Tilt", "the lean of the Earth's axis")],
        mixups=["Summer is not because the Earth is closer to the Sun. The Earth is actually closest to the "
                "Sun in January, which is summer here but winter in Europe.",
                "The Sun does not move around the Earth: the Earth spins, so the Sun seems to rise and set."],
        local="In South Africa, Christmas is in summer, while in countries in the north it is in winter.",
        try_it="Shine a torch on a ball with a sticker for your home, and spin the ball slowly to see day and "
               "night come and go.",
        ask=["Why are winter days shorter?", "Do other planets have seasons?"],
    ),
    # ------------------------------------------------------------------ Mathematics
    dict(
        category="Mathematics", title="What Are Fractions?", ages="7+",
        answer="A fraction is a part of a whole that has been cut into equal parts. A half means 1 of 2 equal "
               "parts.",
        explain=["The bottom number, the denominator, says how many equal parts the whole is cut into.",
                 "The top number, the numerator, says how many of those parts you have. Three quarters is 3 "
                 "of 4 equal parts.",
                 "The parts must be equal: a bread cut into one big and one small piece is not cut in half.",
                 "Different fractions can be the same amount: one half is the same as two quarters and three "
                 "sixths.",
                 "To add fractions with the same bottom number, add the top numbers: one quarter plus two "
                 "quarters is three quarters."],
        words=[("Numerator", "the top number"), ("Denominator", "the bottom number")],
        mixups=["One eighth is smaller than one quarter, even though 8 is bigger than 4. More parts means "
                "smaller pieces.",
                "When adding, do not add the bottom numbers: one quarter plus one quarter is two quarters, "
                "not two eighths."],
        local="50 cents is half of R1, and 25 cents is a quarter of R1.",
        try_it="Fold a piece of paper in half, then in half again. Open it: you have 4 quarters!",
        ask=["Is one third bigger than one half?", "How do I share 3 pizzas between 4 people?"],
    ),
    dict(
        category="Mathematics", title="What Are the Different Shapes?", ages="5+",
        answer="Flat shapes have sides and corners. Solid shapes, like a box or a ball, have faces too.",
        explain=["A triangle has 3 straight sides and 3 corners. A square has 4 equal sides and 4 square corners.",
                 "A rectangle has 4 sides and 4 square corners, with opposite sides the same length.",
                 "A pentagon has 5 sides and a hexagon has 6. A circle has no corners at all.",
                 "Solid shapes: a cube (like a dice) has 6 square faces, a sphere is a ball, and a cylinder is "
                 "like a tin of beans.",
                 "The three corners, or angles, of any triangle always add up to 180 degrees."],
        words=[("Angle", "the turn at a corner"), ("Face", "a flat side of a solid shape")],
        mixups=["A square is also a rectangle: it is a special rectangle with all four sides equal.",
                "Turning a square on its corner does not make it a diamond: it is still a square."],
        local="Ndebele house paintings in South Africa are famous for their bold, bright triangles, squares "
              "and stripes.",
        try_it="Go on a shape hunt at home: find 3 circles, 3 rectangles and 1 triangle. Bees build hexagons!",
        ask=["How many sides does an octagon have?", "Why are wheels round?"],
    ),
    # ------------------------------------------------------------------ Engineering
    dict(
        category="Engineering", title="What Are Simple Machines?", ages="7+",
        answer="Simple machines are tools that make work easier, like levers, ramps, pulleys and wheels.",
        explain=["A lever is a bar that turns on a point. A seesaw and a bottle opener are levers.",
                 "A ramp, or inclined plane, lets you push something up slowly instead of lifting it straight up.",
                 "A pulley is a wheel with a rope. It lets you pull down to lift something up, like a flag "
                 "on a flagpole.",
                 "A wheel and axle, like on a wheelbarrow, makes things easy to roll.",
                 "Simple machines let you use a smaller push, but you have to push for longer."],
        words=[("Lever", "a bar that turns on a pivot"), ("Pivot", "the point a lever turns on")],
        mixups=["Machines do not make energy: they only change how you use your push.",
                "A longer lever makes lifting easier: push far from the pivot, close to the load."],
        local="A wheelbarrow is a lever and a wheel together. It helps builders all over South Africa carry "
              "heavy bricks and sand.",
        try_it="Put a pencil under a ruler and a small book on one end. Press the other end to lift the book. "
               "Move the pencil and feel the difference!",
        ask=["Is a pair of scissors a machine?", "How does a crane lift heavy things?"],
    ),
    dict(
        category="Engineering", title="How Do Bridges Stay Up?", ages="7+",
        answer="Bridges stay up because engineers choose strong shapes, like triangles and arches, that send "
               "the weight safely down into the ground.",
        explain=["A beam bridge is a strong beam resting on supports at each end, like a plank over a stream.",
                 "An arch bridge curves upward. The arch pushes the weight sideways and down into the "
                 "ground at its ends.",
                 "A suspension bridge hangs from strong cables held up by tall towers.",
                 "Triangles are used in many bridges because a triangle keeps its shape when it is pushed. "
                 "A square can be squashed into a diamond."],
        words=[("Load", "the weight a bridge carries"), ("Truss", "a frame made of triangles")],
        mixups=["Thicker is not always stronger: the shape matters. A folded sheet of paper holds much more "
                "than a flat one.",
                "Bridges are not perfectly still. They bend a little, safely, under heavy loads and wind."],
        local="The Bloukrans Bridge on the Garden Route is a huge concrete arch bridge. People bungee jump "
              "216 metres from it!",
        try_it="Lay a sheet of paper between two books and put coins on it. Then fold the paper like a fan "
               "and try again. Which holds more?",
        ask=["Why are there triangles on cranes?", "How do bridges float on water?"],
    ),
    # ------------------------------------------------------------------ Electricity
    dict(
        category="Electricity", title="What Is an Electric Circuit?", ages="7+",
        must_say="Never play with plug sockets or wall electricity - it can kill. Only use small batteries "
                 "for experiments.",
        answer="A circuit is a complete loop that electricity flows around, from a battery, through wires and a "
               "bulb, and back to the battery.",
        explain=["The battery pushes electricity around the loop. The bulb lights up when electricity flows "
                 "through it.",
                 "If there is a gap anywhere in the loop, the electricity stops and the bulb goes off.",
                 "A switch is a gate: it closes the gap to turn the bulb on, and opens it to turn it off.",
                 "Conductors let electricity flow: metals like copper and aluminium.",
                 "Insulators stop electricity: plastic, rubber, wood and glass. Wires have a plastic coat to "
                 "keep us safe."],
        words=[("Conductor", "lets electricity through"), ("Insulator", "blocks electricity")],
        mixups=["Electricity does not get used up in the wires: it flows around the loop.",
                "Water is not safe near electricity: tap water conducts, so never touch switches with wet hands."],
        local="The plug sockets in South African homes give 230 volts. That is about 150 times more than one "
              "1.5 volt battery.",
        try_it="With a grown-up, use a torch battery, two wires and a small bulb to test which things are "
               "conductors: a spoon, a pencil, a coin, an eraser.",
        ask=["Why does the bulb need two wires?", "Is the human body a conductor?"],
    ),
    dict(
        category="Electricity", title="How Does Electricity Get to Your Home?", ages="7+",
        must_say="Never touch fallen power lines or fly kites near them - stay far away and tell a grown-up.",
        answer="Electricity is made in power stations and travels to your home through long power lines.",
        explain=["Most power stations spin big machines called generators, which turn movement into electricity.",
                 "In South Africa most electricity comes from burning coal, which heats water into steam to "
                 "spin the generators.",
                 "Solar panels turn sunlight straight into electricity, and wind turbines use the wind to "
                 "spin generators.",
                 "Electricity travels very far through high pylons and power lines. Transformers then lower "
                 "it to a safer level for homes."],
        words=[("Generator", "turns spinning into electricity"), ("Renewable", "energy that won't run out")],
        mixups=["Electricity is not stored in the plug socket: it comes from the power station all the time.",
                "Solar panels still work on cloudy days, just not as well."],
        local="South Africa has a lot of sunshine, so more and more homes and schools are adding solar panels.",
        try_it="Count the things in your home that use electricity. Which ones could run on a solar battery?",
        ask=["What is load-shedding?", "How does a solar panel work?"],
    ),
    # ------------------------------------------------------------------ Sound
    dict(
        category="Sound", title="How Does Sound Travel?", ages="7+",
        answer="Sound is made when something vibrates, or shakes very fast. The vibrations travel through the "
               "air to your ears.",
        explain=["When you hit a drum, its skin shakes back and forth and pushes the air, making sound waves.",
                 "The waves travel through the air, and make your eardrum shake. Your brain hears this as sound.",
                 "Sound travels about 340 metres every second in air: that is about 1 kilometre in 3 seconds.",
                 "Sound travels even faster through water and solid things like walls and tables.",
                 "In space there is no air, so there is no sound."],
        words=[("Vibrate", "shake back and forth very fast"), ("Eardrum", "the thin skin inside your ear")],
        mixups=["We see lightning before we hear thunder because light is much faster than sound, not because "
                "they happen at different times.",
                "Sound cannot travel through empty space: space battles in films would really be silent."],
        local="In a summer thunderstorm on the Highveld, count the seconds from the flash to the thunder and "
              "divide by 3. That is how many kilometres away the storm is.",
        try_it="Put your hand on your throat and hum. Feel the vibration! Then stretch a rubber band over a box "
               "and pluck it.",
        ask=["Why do I hear an echo in a big hall?", "Can sound travel through water?"],
        must_say="Loud sounds can hurt your ears - never shout into someone's ear or put things inside your ear.",
    ),
    dict(
        category="Sound", title="Why Are Some Sounds High and Some Low?", ages="7+",
        answer="A sound is high when something vibrates very fast, and low when it vibrates slowly. A sound is "
               "loud when the vibration is big.",
        explain=["How high or low a sound is, is called its pitch.",
                 "Short, thin or tight things vibrate fast and make high sounds. Long, thick or loose things make "
                 "low sounds.",
                 "How loud a sound is depends on how big the vibration is. A hard pluck makes a big, loud "
                 "vibration.",
                 "People can hear many pitches, but dogs can hear sounds too high for us."],
        words=[("Pitch", "how high or low a sound is"), ("Volume", "how loud or soft a sound is")],
        mixups=["Loud does not mean high: a big drum can be very loud and very low.",
                "Tapping a bottle with more water gives a lower note, but blowing across it gives a higher note."],
        local="On a marimba, the long wooden bars play the low notes and the short bars play the high notes.",
        try_it="Fill glass bottles with different amounts of water and tap them gently with a spoon. Can you "
               "play a tune? Do it with a grown-up, as glass can break.",
        ask=["Why does a guitar have thick and thin strings?", "What is an echo?"],
        must_say="",
    ),
]

CSS = """
@page { size: A4; margin: 14mm 15mm; }
body { font-family: Arial, Helvetica, sans-serif; font-size: 10.6pt; line-height: 1.32; color: #1d2433; }
.brand { color: #1f6feb; font-weight: bold; letter-spacing: 0.06em; font-size: 9pt; }
h1 { font-size: 19pt; margin: 2px 0 2px; }
.meta { color: #5a6475; font-size: 9pt; margin-bottom: 8px; }
h2 { font-size: 11.5pt; margin: 9px 0 3px; color: #b3541e; }
.answer { font-size: 12pt; background: #eef5ff; border-left: 4px solid #1f6feb; padding: 7px 10px; }
.safety { background: #fff4e5; border: 1px solid #f5a35c; padding: 4px 10px; border-radius: 6px; }
ul { margin: 2px 0; padding-left: 20px; } li { margin: 2px 0; }
.mixups { background: #fdecec; padding: 4px 10px; border-radius: 6px; }
.local, .try, .ask { margin: 6px 0; }
"""


def page(e):
    esc = html.escape
    items = lambda xs: "".join(f"<li>{esc(x)}</li>" for x in xs)  # noqa: E731
    words = "; ".join(f"{esc(w)}: {esc(m)}" for w, m in e["words"])
    # "Sparky always says:" = must_say_marker in config/languages/en.yaml (see the experiment sheets)
    must = (f"<p class='safety'><b>Sparky always says:</b> {esc(e['must_say'])}</p>"
            if e.get("must_say") else "")
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{esc(e['title'])}</title>
<style>{CSS}</style></head><body>
<div class="brand">SPARKY'S SCIENCE FACTS</div>
<h1>{esc(e['title'])}</h1>
<div class="meta">{esc(e['category'])} &middot; Ages {esc(e['ages'])}</div>
<p class="answer"><b>Short answer:</b> {esc(e['answer'])}</p>
{must}
<h2>How it works</h2><ul>{items(e['explain'])}</ul>
<p><b>Key words:</b> {words}</p>
<div class="mixups"><h2>Common mix-ups</h2><ul>{items(e['mixups'])}</ul></div>
<p class="local"><b>Did you know?</b> {esc(e['local'])}</p>
<p class="try"><b>Try it:</b> {esc(e['try_it'])}</p>
<p class="ask"><b>Ask Sparky:</b> {esc(' '.join(e['ask']))}</p>
</body></html>"""


def main():
    import PyPDF2

    browser = next((b for b in BROWSERS if b.exists()), None)
    if browser is None:
        sys.exit("Needs Google Chrome or Microsoft Edge to print the PDFs.")
    OUT.mkdir(parents=True, exist_ok=True)
    problems = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, e in enumerate(SHEETS, 1):
            name = f"Sparky Facts {i:02d} - {e['category']} - {e['title'].rstrip('?')}"
            src = Path(tmp) / f"{i:02d}.html"
            src.write_text(page(e), encoding="utf-8")
            pdf = OUT / f"{name}.pdf"
            subprocess.run([str(browser), "--headless", "--disable-gpu", "--no-pdf-header-footer",
                            f"--user-data-dir={Path(tmp) / 'browser'}",  # own profile: an open browser won't swallow the job
                            f"--print-to-pdf={pdf}", src.as_uri()], check=True, capture_output=True)
            reader = PyPDF2.PdfReader(str(pdf))
            text = "".join((p.extract_text() or "") + "\n" for p in reader.pages).strip()
            chars = len(text) + len("[1]: ")
            print(f"{len(reader.pages)} page(s) {chars:5d} chars  {pdf.name}")
            if chars > MAX_CHARS or len(reader.pages) != 1:
                problems.append(pdf.name)
    if problems:
        sys.exit(f"Over {MAX_CHARS} characters or more than one page: {problems}")


if __name__ == "__main__":
    main()
