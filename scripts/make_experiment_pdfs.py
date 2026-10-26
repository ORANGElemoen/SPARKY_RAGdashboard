#!/usr/bin/env python3
"""
Sparky's experiment sheets: one A4 PDF per experiment, written for children in South Africa
(and the adults helping them), ready to upload to the tutor as documents.

One experiment per file on purpose: the tutor chunks documents by word count and only gives the
LLM the first 2000 characters of what it finds, so a short single-experiment file is retrieved
whole - safety lines included. The check at the end fails if a sheet grows past that.

    python scripts/make_experiment_pdfs.py          -> docs/experiments/*.pdf  (needs Google Chrome)
"""
import html
import subprocess
import sys
import tempfile
from pathlib import Path

OUT = Path(__file__).resolve().parent.parent / "docs" / "experiments"
CHROME = Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe")
MAX_CHARS = 2000  # MAX_CONTEXT_CHARS in core/services/simple_rag_service.py

EXPERIMENTS = [
    dict(
        title="Beans in a Jar: Watch Roots Grow Down",
        subject="Life Science (plants)", ages="5+", time="10 minutes, then watch for a week",
        summary="Grow dry beans in a clear jar with cotton wool or paper towel, so you can see the roots "
                "grow down and the shoot grow up. Yes, beans grow well in cotton wool!",
        must_say="Don't eat the raw beans - some kinds make you sick!",
        safety=['Wash your hands after touching the seeds. Throw it away if fuzzy mould grows.'],
        materials=["A clear jar or plastic cup", "Cotton wool or paper towel",
                   "3-4 dry beans (sugar beans work; mielie kernels too)", "Water and a ruler"],
        steps=["Fill the jar loosely with cotton wool or crumpled paper towel.",
               "Make it damp all through, but pour out any water lying at the bottom.",
               "Push the beans between the cotton and the glass, halfway up, so you can see them.",
               "Keep the jar in a warm, bright place, out of hot sun all day. Add a little water daily.",
               "Look and measure every day. In 2 to 5 days a root comes out; a green shoot follows.",
               "When the roots are 2 cm long, lay the jar on its side. In a day or two the root bends down again!"],
        troubleshoot=['No root after 5 days? Keep the cotton damp (not soaking) and the jar warm - cold slows it down.', 'Mould? It is too wet: start again with fresh cotton and less water.', 'Still nothing? Old beans may not sprout - try beans from a new packet.'],
        science="Inside a seed is a tiny baby plant with its food. Water and warmth wake it up: this is "
                "germination. Roots grow down and shoots grow up because the plant can feel gravity "
                "(gravitropism). Tiny grains of starch in the root tip sink to the bottom of the cells and "
                "show the root which way is down.",
        local="Farmers in most of South Africa plant mielies and beans when the summer rains start, "
              "because seeds need water to germinate.",
        ask=["Will the roots still grow down in the dark?", "Which grows faster, a bean or a mielie?"],
    ),
    dict(
        title="Paper Aeroplane: The Forces of Flight",
        subject="Physical Science (forces)", ages="7+", time="30 minutes",
        summary="Fold a dart paper plane (paper aeroplane), test how a paper clip on the nose and wing "
                "flaps change the way it flies, and fix a plane that dives or drops.",
        must_say='Never throw your plane at people or animals - the point can hurt an eye!',
        safety=['Throw it in an open space.', 'Ask an adult to help with scissors.'],
        materials=["A sheet of A4 paper (scrap paper is fine)", "Paper clips and scissors",
                   "A tape measure, or count your steps", "An open space like a school field"],
        steps=["Fold the paper in half the long way and open it. Fold the two top corners to the middle line.",
               "Fold the new slanted edges to the middle line again.",
               "Fold the whole thing in half along the middle line.",
               "Fold each wing down to line up with the bottom of the body. Throw it gently, straight ahead.",
               "Test 1: throw it 3 times and measure. Add a paper clip to the nose and throw 3 more times.",
               "Test 2: cut two slits 1 cm apart at the back of each wing and bend the flaps up a little. "
               "Then try them bent down."],
        troubleshoot=['Dives into the ground? Bend the back flaps up a little. Still dives? Take off any nose paper clip and bend the flaps up more.', 'Climbs up, then drops? Flatten the flaps.', 'Turns to one side? Make both wings the same shape and size.'],
        science="Four forces act on a plane. Thrust is your throw pushing it forward. Drag is the air "
                "pushing back. Weight is gravity pulling down. Lift is the air pushing up: the wings push "
                "air down, so the air pushes the wings up. A paper clip on the nose helps it fly straight. "
                "Flaps bent up lift the nose for more lift - but too much and the plane slows and drops.",
        local="Planes at O.R. Tambo Airport in Johannesburg need a longer run to take off than at the "
              "coast, because the air is thinner high up on the Highveld.",
        ask=["Why do real planes have flaps on their wings?"],
    ),
    dict(
        title="Lemon Battery: Electricity from Fruit",
        subject="Physical Science (electricity)", ages="8+", time="45 minutes",
        summary="Make a battery from lemons, copper and zinc-coated nails that lights a small LED.",
        must_say='Never connect your lemon battery to a wall plug socket - that is very dangerous!',
        safety=['An adult must help - nails are sharp.', "Don't eat the lemons afterwards - metal gets into the juice."],
        materials=["3 or 4 juicy lemons (potatoes work too)",
                   "3 or 4 pieces of copper: bare copper wire, or 10c, 20c or 50c coins (copper- or bronze-coated)",
                   "3 or 4 galvanised (zinc-coated) nails", "5 crocodile-clip wires", "1 small red LED"],
        steps=["Roll each lemon firmly on the table to make it juicy inside.",
               "Push one copper piece and one nail into each lemon, 2 cm apart. They must not touch.",
               "Make a chain: a wire from the copper of lemon 1 to the nail of lemon 2, and so on.",
               "Clip the copper at one end of the chain to the LED's long leg (+), and the nail at the other "
               "end to the short leg (-).",
               "Switch off the lights and look closely: the LED glows faintly!"],
        troubleshoot=['Turn the LED round - this is the most common mistake.', "Make sure the coin and nail don't touch inside each lemon.", 'Check every clip is tight, then add another lemon. Look in a dark room - the glow is faint.'],
        science="The electricity comes from two different metals. The zinc slowly dissolves in the lemon "
                "juice and gives away tiny particles called electrons, which flow through the wire and LED "
                "to the copper: an electric current. The zinc nail is the negative side (anode) and the "
                "copper is the positive side (cathode). The sour juice is the electrolyte. One lemon gives "
                "about 1 volt and an LED needs about 2, so we join lemons in series.",
        local="A torch battery works the same way - two different materials and an electrolyte - just "
              "much stronger.",
        ask=["Would an orange or a potato work?", "What happens with only one lemon?"],
    ),
    dict(
        title="Bottle Water Filter: Clean Muddy Water",
        subject="Natural Science (water)", ages="6+", time="30 minutes",
        summary="Make a water filter to clean muddy water, from a plastic bottle, cloth, charcoal, "
                "sand and gravel.",
        must_say='Never drink the water from your filter - it can still have germs that make you sick!',
        safety=['Only an adult can make water safe to drink, by boiling it for at least 1 minute.', 'An adult should cut the bottle. Use cold charcoal only.'],
        materials=["A 2-litre plastic cool-drink bottle", "A piece of cotton cloth (an old T-shirt)",
                   "Cold braai charcoal, crushed small (not briquettes)", "Clean fine sand and small stones",
                   "A cup of muddy water"],
        steps=["An adult cuts the bottle in half. Turn the top half upside down in the bottom half, "
               "like a funnel.",
               "Push the cloth into the neck so sand can't fall through.",
               "Rinse the charcoal and sand with clean water. Add layers: charcoal (3 cm), then sand (5 cm), "
               "then stones on top (5 cm).",
               "Slowly pour the muddy water onto the stones and watch it trickle down.",
               "Compare the water that comes out with your muddy water."],
        troubleshoot=['Water comes out black? That is charcoal dust - rinse the charcoal better.', 'Sand in the water? Push the cloth into the neck more firmly.', 'Still cloudy? Pour it through again, or add more sand.'],
        science="Each layer catches something. Stones catch big bits like leaves. Sand catches tiny bits "
                "of dirt between its grains. Charcoal is full of tiny holes, and some smells and colours "
                "stick to it (adsorption). Real filters use special 'activated' charcoal that works much "
                "better. No filter like this removes germs - they are far too small - so water must still "
                "be boiled.",
        local="In 2018 Cape Town nearly ran out of water. South African water works also use sand "
              "filters, then add chlorine to kill germs.",
        ask=["Which layer does the most work?", "Why must we still boil the water?"],
    ),
    dict(
        title="Bottle Light: Light a Dark Room Without Electricity",
        subject="Physical Science (light)", ages="7+", time="30 minutes, on a sunny day",
        summary="Light up a dark room without electricity: a bottle of water in the roof spreads "
                "sunlight all around inside - a daytime light for load-shedding.",
        must_say='Never look straight at the sun - it can hurt your eyes!',
        safety=['An adult must cut the box.'],
        materials=["A clear 1.5 or 2-litre plastic bottle with its cap (label off)", "Clean water",
                   "A cardboard box with a lid", "Scissors or a craft knife (adult only)", "Sticky tape"],
        steps=["Fill the bottle to the top with water and close it tightly.",
               "An adult cuts a round hole in the top of the box, just big enough for the body of the "
               "bottle to slide through, and a small peep-hole in one side.",
               "Push the bottle into the top hole so the top part sticks out and the rest hangs inside. "
               "Tape around it so no light leaks in.",
               "Put the box in bright sun and look through the peep-hole.",
               "Now try an empty bottle. Which lights the box better?"],
        troubleshoot=['Not bright? The top of the bottle needs direct sunshine, not shade.', 'Box not dark inside? Tape over gaps where light leaks in.', 'Fill the bottle right to the top, with no big air bubble.'],
        science="Light bends when it goes from air into water - this is called refraction. The water and "
                "the round bottle bend and scatter the sunlight in all directions, so the whole box lights "
                "up instead of one small spot. An empty bottle lets light go mostly straight down. Bottle "
                "lights in real roofs have a little bleach added by an adult to stop green algae growing.",
        local="Alfredo Moser, a mechanic in Brazil, invented the bottle light in 2002. In a sunny roof, one "
              "can be about as bright as a 40 to 60 watt bulb - but only in the day.",
        ask=["Why doesn't it work at night?", "Would muddy water work as well?"],
    ),
    dict(
        title="Floating Needle Compass",
        subject="Natural Science (magnetism)", ages="8+", time="15 minutes",
        summary="Make your own compass: turn a sewing needle into a magnet and float it on water so "
                "it points north and south.",
        must_say='Keep magnets away from little children - swallowing them is very dangerous!',
        safety=['Needles are sharp - an adult should help.', 'Keep magnets away from phones and bank cards.'],
        materials=["A steel sewing needle (or a straightened paper clip)",
                   "A strong magnet, e.g. from an old speaker (fridge magnets are usually too weak)",
                   "A bottle cap, piece of cork or small leaf", "A bowl of water"],
        steps=["Stroke the needle with one end of the magnet, from the eye to the point, 30 to 40 times. "
               "Always the same way: lift the magnet off between strokes.",
               "Lay the needle on the bottle cap, cork or leaf.",
               "Float it in the middle of the bowl, away from metal and phones.",
               "Watch it turn and settle. Push it gently - it swings back to the same line!",
               "Which end is north? At midday in South Africa the sun is in the northern sky, so the end "
               "pointing towards the sun's side is north."],
        troubleshoot=["Doesn't turn? Move away from metal and phones, and keep the float off the side of the bowl.", 'Points a different way each time? Stroke it more, always the same way.'],
        science="Earth is like a giant magnet. Stroking the needle lines up tiny magnetic areas in the "
                "steel, so it becomes a small magnet with a north and a south pole. Floating lets it turn "
                "easily, and Earth's magnetism pulls it into a north-south line. In South Africa a compass "
                "points about 18 to 30 degrees west of true north: about 21 in Johannesburg, 27 in Cape "
                "Town and Durban.",
        local="At night, the Southern Cross stars help you find south: follow the long arm of the cross "
              "about four and a half times its length, then look straight down to the horizon.",
        ask=["What happens if you bring the magnet close?", "Why keep a compass away from metal?"],
    ),
    dict(
        title="Shadow Clock: Tell the Time with the Sun",
        subject="Natural Science (Earth and space)", ages="6+", time="10 minutes, then check every hour",
        summary="Stand a stick in the ground and mark its shadow every hour to see how the sun seems to "
                "move across the sky.",
        must_say='Never look straight at the sun - it can hurt your eyes!',
        safety=['Wear a hat and drink water when you are out in the sun.'],
        materials=["A straight stick about 1 metre long (or a broom handle)",
                   "Small stones or bottle caps", "Chalk or paper and a pencil", "A sunny, flat open space"],
        steps=["On a sunny morning, stand the stick straight up in the ground or in a bucket of sand.",
               "Put a stone at the tip of the shadow and write down the time.",
               "Mark the shadow tip again every hour until the afternoon.",
               "When was the shadow shortest? Which way did it point then?",
               "Next sunny day, use your stones as a clock."],
        troubleshoot=['Shadow hard to see? Wait for a sunny day - clouds make shadows fade.', "Marks don't match the next day? Check the stick has not moved or tilted."],
        science="The Earth spins once a day, so the sun seems to travel from east to west. Shadows point "
                "away from the sun: west in the morning, east in the afternoon. In almost all of South "
                "Africa the midday sun is in the northern sky, so the shortest shadow points south, and a "
                "shadow moves anticlockwise around the stick - the opposite way to clock hands! The "
                "shortest shadow is not exactly at 12:00: in Durban it is close to 12:00, in Cape Town "
                "closer to 13:00.",
        local="Near the equator, in Kenya or Uganda, the midday sun is high overhead all year, so noon "
              "shadows are always short.",
        ask=["Will your clock still be right in winter?", "Why are shadows long in the morning?"],
    ),
    dict(
        title="Red Cabbage Colour Test: Acids and Bases",
        subject="Physical Science (chemistry)", ages="7+", time="30 minutes",
        summary="Make purple red-cabbage juice that changes colour to show whether something is an acid "
                "or a base.",
        must_say='Never test bleach, drain cleaner or pool chemicals - they burn skin and eyes!',
        safety=['An adult must use the knife and the hot water.', "Only test the kitchen things listed, and don't drink the mixtures."],
        materials=["A quarter of a red cabbage", "Hot water from the kettle (adult only)",
                   "A jug, a sieve and 5 clear glasses", "To test: vinegar, lemon juice, bicarbonate of "
                   "soda in water, plain water, soapy water"],
        steps=["An adult chops the cabbage and pours hot water over it in the jug.",
               "Wait 15 minutes until the water is dark purple, then pour it through the sieve.",
               "Pour a finger-deep layer of the purple juice into each glass.",
               "Add a teaspoon of a different thing to each glass. Stir, watch, and write down the colour.",
               "Bonus: add vinegar to the bicarbonate of soda glass and watch it fizz!"],
        troubleshoot=['Colours weak? Use less water or more cabbage so the juice is darker.', 'No change? Add a little more of the thing you are testing and stir.'],
        science="Red cabbage has a natural purple colour (anthocyanin) that changes with what it is mixed "
                "with, so it is an indicator. Acids like vinegar and lemon juice turn it pink or red. "
                "Neutral things like plain water leave it purple. Bases like bicarbonate of soda and soap "
                "turn it blue or green. Vinegar (an acid) and bicarbonate of soda (a base) react and make "
                "carbon dioxide gas - the fizz.",
        local="South African farmers test whether their soil is acidic, because mielies grow poorly in "
              "very acidic soil.",
        ask=["What colour will tomato juice make it?", "Is toothpaste an acid or a base?"],
    ),
    dict(
        title="Wet Cloth Cooler: Keep Water Cool Without a Fridge",
        subject="Physical Science (heat)", ages="6+", time="10 minutes, then wait 1-2 hours",
        summary="Wrap one bottle of water in a wet cloth and one in a dry cloth to discover how "
                "evaporation keeps things cool - the idea behind the clay pot fridge.",
        must_say=None,
        safety=['A safe experiment. Use a shady place.'],
        materials=["Two plastic bottles of tap water, filled at the same time",
                   "Two pieces of cotton cloth (old socks work)", "Rubber bands or string",
                   "A thermometer if you have one (or use your hands)"],
        steps=["Wrap each bottle in cloth and hold it on with rubber bands.",
               "Soak one cloth in water until it is dripping wet. Leave the other dry.",
               "Stand both bottles in the shade where there is a breeze.",
               "After 1 to 2 hours, feel both bottles or measure the water. Which is cooler?",
               "Keep the cloth wet and try again in still air. Is the breeze important?"],
        troubleshoot=['No difference? Keep the cloth wet - it dries out quickly in wind.', 'Wait longer, or move both bottles to a breezier spot. On humid days the cooling is small.'],
        science="To evaporate (turn into an invisible gas), water needs heat. It takes that heat from the "
                "cloth, the bottle and the water inside, so they cool down. Wind carries the damp air away "
                "and speeds this up. It works best on hot, dry days; in humid weather, like summer in "
                "Durban, it cools less. Sweating cools your body the same way.",
        local="The pot-in-pot cooler, made famous by Nigerian teacher Mohammed Bah Abba in the 1990s, uses "
              "two clay pots with wet sand between them to keep vegetables fresh without electricity.",
        ask=["Why do you feel cold climbing out of a pool?", "Would it work better in the Karoo or Durban?"],
    ),
    dict(
        title="Bottle Rain Gauge: Measure the Rain",
        subject="Natural Science (weather)", ages="7+", time="20 minutes, then check every day",
        summary="Make a rain gauge from a plastic bottle and measure how many millimetres of rain fall "
                "where you live.",
        must_say='Never go outside to check your rain gauge in a thunderstorm - lightning is dangerous!',
        safety=['An adult should cut the bottle.', "Empty it every day so mosquitoes can't breed in it."],
        materials=["A clear 2-litre plastic bottle with straight sides", "Scissors (adult)",
                   "A ruler and a permanent marker", "A handful of small stones", "Water"],
        steps=["An adult cuts off the top of the bottle where the sides become straight.",
               "Put the stones in the bottom, then add water until the bumpy bottom is just covered. "
               "Mark that level 0.",
               "With the ruler, mark lines every 5 mm up the side and number them.",
               "Put the cut-off top in upside down, as a funnel.",
               "Stand it in an open place, away from trees and roofs.",
               "Every morning, read the level, write it down, and pour out water to the 0 line."],
        troubleshoot=['Too much rain? Make sure you poured back to the 0 line each day.', 'Too little? Trees or roofs may block the rain - move it into the open.', 'Falls over? Add more stones or push it into the ground.'],
        science="Rain is measured in millimetres: how deep it would be if it stayed where it fell. 1 mm of "
                "rain means 1 litre of water on every square metre of ground. The funnel is as wide as the "
                "bottle, so the water height in the bottle is the rain that fell, and it stops water "
                "evaporating.",
        local="Most of South Africa gets its rain in summer, often from afternoon thunderstorms, but the "
              "Western Cape gets most of its rain in winter. South Africa is dry: about 450 mm a year.",
        ask=["How much rain fell this week?", "Is it rainy season where you live?"],
    ),
    dict(
        title="Balloon Rocket on a String",
        subject="Physical Science (forces and motion)", ages="6+", time="20 minutes",
        summary="Tape a balloon to a straw on a string and let it go - the air rushing out pushes the "
                "balloon along like a rocket.",
        must_say='Children under 8 need an adult with balloons - a burst piece can choke a small child!',
        safety=['Throw burst balloon pieces away at once.'],
        materials=["3 to 5 metres of string or wool", "A drinking straw", "A balloon (long ones work best)",
                   "Sticky tape", "Two chairs (or two trees)"],
        steps=["Thread the string through the straw. Tie the ends to the chairs and pull it tight.",
               "Blow up the balloon and pinch the end shut. Don't tie it.",
               "Tape the balloon under the straw, with its opening pointing at one chair.",
               "Pull it back to that chair, then let go. Whoosh!",
               "Measure how far it went. Try less air, more air, or a sloping string."],
        troubleshoot=["Doesn't move? Pull the string tighter and check the tape isn't sticking the straw to the string.", 'Spins round? Tape the balloon straight along the straw.', 'Stops early? Use more air or a smoother string.'],
        science="The balloon squeezes air out of the back, and the air pushes the balloon forward just as "
                "hard. Isaac Newton described this: for every action there is an equal and opposite "
                "reaction (his third law of motion). Real rockets work the same way, pushing hot gas out "
                "of the back very fast.",
        local="In 1999, students at Stellenbosch University built SUNSAT, South Africa's first satellite.",
        ask=["What happens with a bigger balloon?", "Why does the balloon stop?"],
    ),
    dict(
        title="Floating Egg: Salt Water and Density",
        subject="Physical Science (floating and sinking)", ages="5+", time="15 minutes",
        summary="Make an egg float by adding salt to water, and find out why it is easier to float in "
                "the sea.",
        must_say='Wash your hands after touching raw eggs!',
        safety=["An adult can help so the egg doesn't break."],
        materials=["A raw egg", "A tall clear glass or jar", "Tap water", "Table salt and a tablespoon"],
        steps=["Fill the glass two-thirds with water. Gently put the egg in. Does it sink or float?",
               "Take the egg out, add a tablespoon of salt and stir until it disappears.",
               "Put the egg back. Keep adding salt, a spoon at a time, until the egg floats. Count the spoons.",
               "Challenge: slowly pour plain water down the side of the glass, on top of the salty water. "
               "Can you make the egg float in the middle?"],
        troubleshoot=["Won't float? Keep adding salt and stir until it disappears - you may need 6 or more spoons.", "Salt won't dissolve? Stir longer, or ask an adult for warm water."],
        science="Density is how much stuff is packed into a space. An egg is a bit denser than tap water, "
                "so it sinks. Dissolving salt makes the water denser. Once the salty water is denser than "
                "the egg, the egg floats. In the challenge, plain water stays on top of the heavier salty "
                "water, so the egg floats in between.",
        local="Sea water is salty, so swimmers and ships float a little higher in the sea at Durban or "
              "Cape Town than in a dam. A very old egg floats even in tap water, because air gets into it.",
        ask=["Would sugar work instead of salt?", "Is it easier to float in the sea or a pool?"],
    ),
    dict(
        title="Box Solar Oven: Cook with Sunlight",
        subject="Physical Science (energy)", ages="8+", time="1 hour, on a sunny day",
        summary="Build an oven from a cardboard box, foil and plastic that uses only sunshine to melt "
                "chocolate and warm food.",
        must_say='The oven gets hot inside - always use an oven glove to take food out!',
        safety=["An adult must cut the box. Don't stare at the shiny foil in the sun.", 'Only warm food that is safe to eat cold, like bread or chocolate - never raw meat or eggs.'],
        materials=["A box with a flap lid (pizza box or shoe box)", "Aluminium foil",
                   "Cling film (clear plastic wrap)", "Black paper or a black plastic bag",
                   "Tape, a ruler, a stick, and a craft knife (adult)"],
        steps=["Draw a square on the lid, 3 cm in from the edges. An adult cuts three sides to make a flap.",
               "Cover the inside of the flap with foil, shiny side out. Tape it flat.",
               "Tape cling film tightly over the hole under the flap, as a window.",
               "Line the bottom of the box with black paper and put the food on it.",
               "Close the lid, face the box to the sun (north around midday in South Africa) and prop the "
               "flap with the stick so it shines light through the window.",
               "Wait 30 to 60 minutes, turning the box to follow the sun."],
        troubleshoot=['Not getting hot? It needs a hot day with direct sun, best between 11:00 and 15:00.', "Check the cling film is tight with no gaps, so warm air can't escape.", 'Turn the box to face the sun every 20 minutes.'],
        science="The foil reflects extra sunlight into the box. The black paper absorbs the light and turns "
                "it into heat. The plastic window lets sunlight in but traps the warm air, like a car in "
                "the sun. A box oven can reach about 65 to 90 degrees Celsius on a hot day.",
        local="South Africa gets about 2,500 hours of sunshine a year on average - that is why many big "
              "solar power stations have been built in the sunny Northern Cape.",
        ask=["Why is the inside black and the flap shiny?"],
    ),
]

CSS = """
@page { size: A4; margin: 12mm 15mm; }
body { font-family: 'Segoe UI', Arial, sans-serif; color: #1f2933; font-size: 10.5pt; line-height: 1.35; }
.brand { color: #c2410c; font-weight: 700; letter-spacing: .04em; font-size: 9.5pt; }
h1 { font-size: 21pt; margin: 2mm 0 1mm; }
.meta { color: #52606d; margin-bottom: 3mm; }
.summary { font-size: 12pt; margin: 0 0 4mm; }
h2 { font-size: 12pt; margin: 3mm 0 1mm; color: #0b6e4f; }
.safety { background: #fff4e5; border-left: 5px solid #e8590c; padding: 2mm 4mm; border-radius: 2mm; }
.safety h2 { color: #c2410c; margin-top: 1mm; }
.must { margin: 1mm 0; }
.science { background: #e8f6ef; border-left: 5px solid #0b6e4f; padding: 2mm 4mm; border-radius: 2mm; margin-top: 4mm; }
ul, ol { margin: 1mm 0; padding-left: 6mm; }
li { margin: .8mm 0; }
.local { margin-top: 4mm; }
.ask { margin-top: 3mm; color: #3e4c59; }
"""


def page(e):
    esc = html.escape
    items = lambda xs: "".join(f"<li>{esc(x)}</li>" for x in xs)  # noqa: E731
    # "Sparky always says:" = must_say_marker in config/languages/en.yaml: the tutor adds this
    # sentence to any answer based on the sheet, since the small LLM often drops it
    must = f"<p class='must'><b>Sparky always says:</b> {esc(e['must_say'])}</p>" if e["must_say"] else ""
    return f"""<!doctype html><html><head><meta charset="utf-8"><title>{esc(e['title'])}</title>
<style>{CSS}</style></head><body>
<div class="brand">SPARKY'S SCIENCE EXPERIMENTS</div>
<h1>{esc(e['title'])}</h1>
<div class="meta">{esc(e['subject'])} &middot; Ages {esc(e['ages'])} &middot; {esc(e['time'])}</div>
<p class="summary">{esc(e['summary'])}</p>
<div class="safety"><h2>Safety first</h2>{must}<ul>{items(e['safety'])}</ul></div>
<h2>You need</h2><ul>{items(e['materials'])}</ul>
<h2>Steps</h2><ol>{items(e['steps'])}</ol>
<h2>If it doesn't work, try these in order</h2><ol>{items(e['troubleshoot'])}</ol>
<div class="science"><h2>Why it works</h2><p>{esc(e['science'])}</p></div>
<p class="local"><b>Did you know?</b> {esc(e['local'])}</p>
<p class="ask"><b>Ask Sparky:</b> {esc(' '.join(e['ask']))}</p>
</body></html>"""


def main():
    import PyPDF2

    OUT.mkdir(parents=True, exist_ok=True)
    too_long = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, e in enumerate(EXPERIMENTS, 1):
            name = f"Sparky Experiment {i:02d} - {e['title'].split(':')[0]}"
            src = Path(tmp) / f"{i:02d}.html"
            src.write_text(page(e), encoding="utf-8")
            pdf = OUT / f"{name}.pdf"
            subprocess.run([str(CHROME), "--headless", "--disable-gpu", "--no-pdf-header-footer",
                            f"--user-data-dir={Path(tmp) / 'chrome'}",  # own profile: an open Chrome won't swallow the job
                            f"--print-to-pdf={pdf}", src.as_uri()], check=True, capture_output=True)
            reader = PyPDF2.PdfReader(str(pdf))
            # exactly what document_service stores, plus the "[1]: " the prompt puts in front
            text = "".join((p.extract_text() or "") + "\n" for p in reader.pages).strip()
            chars = len(text) + len("[1]: ")
            print(f"{len(reader.pages)} page(s) {chars:5d} chars  {pdf.name}")
            if chars > MAX_CHARS or len(reader.pages) != 1:
                too_long.append(pdf.name)
    if too_long:
        sys.exit(f"Over {MAX_CHARS} characters or more than one page: {too_long}")


if __name__ == "__main__":
    main()
