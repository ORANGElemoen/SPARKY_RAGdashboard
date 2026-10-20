#!/usr/bin/env python3
"""
One-off generator for docs/sparky_3d_viewer.html - an interactive, fully
offline 3D viewer of the Sparky mascot enclosure (hardware/cad/sparky_v6_mascot)
with every electronic component placed where it is meant to go, a movable
half-size breadboard, and a live "does it fit?" check against the printed walls.

The shell comes from the SolidCraft 3MF export (three parts: front piece, head
back panel, body back panel). Component sizes are datasheet values (speaker
DFRobot FIT0502, MAX7219 4-in-1, ESP32-DevKitC 38-pin, half breadboard).
three.js (MIT, scripts/vendor/three) is embedded so the page works without
internet - open the HTML file in Chrome/Edge/Firefox.

Not part of the running app; re-run after the CAD changes:
    python scripts/generate_sparky_viewer.py
"""
import base64
import json
import re
import struct
import zipfile
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from core.services.studio_service import DEFAULT_FACES  # noqa: E402

MODEL_3MF = ROOT / "hardware" / "cad" / "sparky_v6_mascot" / "sparky_mascot.3mf"
VENDOR = Path(__file__).resolve().parent / "vendor" / "three"
OUT = ROOT / "docs" / "sparky_3d_viewer.html"

PART_LABELS = {  # 3MF object name -> what it is
    "Torso (1)": ("front", "Front piece (face, head, body, arms, feet)", "#86c5f0"),
    "Head": ("headPanel", "Head back panel (2 screws)", "#a9d6f5"),
    "Torso": ("bodyPanel", "Body back panel (2 screws)", "#a9d6f5"),
}

# Components, world mm, Z up, front of Sparky is -Y. Boxes are [min, max].
# "mounted": rests against its mount by design (contact is not a collision).
COMPONENTS = [
    dict(id="matrix", name="LED matrix 32x8 (MAX7219 4-in-1)", color="#1e2a4a", emissive="#1d4ed8",
         box=[[-64.5, -48.5, 130], [64.5, -33.5, 162]], mounted=True,
         note="128-129 x 32-33 x 12-15 mm, 52-55 g. Slides into the rails behind the face window."),
    dict(id="button_body", name="Arcade button body (30 mm)", color="#2563eb",
         cyl=dict(axis="z", c=[0, -17], r=12, a0=166, a1=199), mounted=True,
         note="Snap-in body under the head top, behind the matrix."),
    dict(id="button_cap", name="Arcade button cap (outside)", color="#3b82f6",
         cyl=dict(axis="z", c=[0, -17], r=16, a0=201, a1=208), mounted=True, nowall=True,
         note="Bezel and plunger sitting inside the halo on top of the head."),
    dict(id="mic", name="Microphone (INMP441)", color="#16a34a",
         cyl=dict(axis="y", c=[0, 187], r=7, a0=-48.3, a1=-45.3), mounted=True,
         note="14 mm round board on the flat pad behind the forehead hole."),
    dict(id="speaker", name="Speaker 3 W 8 ohm (FIT0502)", color="#374151",
         box=[[-35, -36, 22], [35, -20, 52]], mounted=True,
         note="70 x 30 x 16 mm, 24 g, screws onto the 4 posts (63 x 24 mm) behind the grille."),
    dict(id="amp", name="Amplifier (MAX98357A)", color="#7c3aed",
         box=[[-9.5, -18, 16.5], [9.5, 1, 26.5]], mounted=True,
         note="About 19 x 18 mm board plus header pins, on the body floor between the foot pegs."),
    dict(id="led", name="Accent LED (5 mm)", color="#f8fafc", emissive="#fef9c3",
         cyl=dict(axis="y", c=[0.5, 62.5], r=2.5, a0=-45.5, a1=-35), nowall=True,
         note="Pushed through the hole in the lightning bolt."),
]

FACES = DEFAULT_FACES  # one source of truth, shared with Sparky Studio

ESP32_SHELF = dict(
    board=[[-35, 28, 39.2], [20, 42, 67.2]],
    jumpers=[[-35, 14, 39.2], [20, 28, 67.2]],
    usb=[[20, 33, 49], [40, 41, 57]],
)


def read_3mf(path):
    xml = zipfile.ZipFile(path).read("3D/3dmodel.model").decode("utf-8")
    parts = {}
    for obj in re.finditer(r'<object id="\d+" type="model" name="([^"]+)">(.*?)</object>', xml, re.S):
        name, body = obj.group(1), obj.group(2)
        verts = [float(v) for m in re.finditer(r'<vertex x="([^"]+)" y="([^"]+)" z="([^"]+)"/>', body)
                 for v in m.groups()]
        tris = [int(v) for m in re.finditer(r'<triangle v1="(\d+)" v2="(\d+)" v3="(\d+)"', body)
                for v in m.groups()]
        parts[name] = dict(
            pos=base64.b64encode(struct.pack(f"<{len(verts)}f", *verts)).decode(),
            idx=base64.b64encode(struct.pack(f"<{len(tris)}I", *tris)).decode(),
            nv=len(verts) // 3, nt=len(tris) // 3)
    return parts


HTML = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>Sparky - interactive fit check</title>
<style>
 :root{--bg:#0f172a;--panel:#111827;--ink:#e5e7eb;--muted:#9ca3af;--ok:#22c55e;--warn:#f59e0b;--bad:#ef4444;--accent:#38bdf8}
 *{box-sizing:border-box} body{margin:0;font:13px/1.4 system-ui,Segoe UI,sans-serif;color:var(--ink);background:var(--bg);overflow:hidden}
 #side{position:fixed;left:0;top:0;bottom:0;width:340px;overflow:auto;background:var(--panel);padding:12px 14px;border-right:1px solid #1f2937}
 #view{position:fixed;left:340px;right:0;top:0;bottom:0}
 h1{font-size:17px;margin:0 0 2px} h2{font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--accent);margin:16px 0 6px}
 .sub{color:var(--muted);font-size:12px;margin-bottom:6px}
 label{display:flex;align-items:center;gap:6px;margin:3px 0;cursor:pointer}
 input[type=range]{width:100%} .row{display:flex;gap:6px;flex-wrap:wrap}
 button{background:#1f2937;color:var(--ink);border:1px solid #374151;border-radius:6px;padding:4px 8px;cursor:pointer}
 button:hover{border-color:var(--accent)} select{background:#1f2937;color:var(--ink);border:1px solid #374151;border-radius:6px;padding:3px;width:100%}
 .sw{width:11px;height:11px;border-radius:3px;display:inline-block;flex:none}
 .st{margin-left:auto;font-size:11px;white-space:nowrap} .ok{color:var(--ok)} .warn{color:var(--warn)} .bad{color:var(--bad)}
 #bbstatus{padding:8px 10px;border-radius:8px;background:#0b1220;border:1px solid #1f2937;margin-top:6px;font-size:12.5px}
 #bbhead{font-weight:600;margin-bottom:4px}
 #info{position:fixed;right:12px;bottom:12px;max-width:360px;background:#111827ee;border:1px solid #1f2937;border-radius:8px;padding:8px 10px;font-size:12px;display:none}
 #info .dim{color:var(--muted)}
 #busy{position:fixed;left:50%;top:12px;transform:translateX(-50%);background:#111827;border:1px solid #374151;padding:4px 10px;border-radius:6px;display:none}
 .slab{display:flex;justify-content:space-between;color:var(--muted);font-size:11.5px}
 #faceEd{display:block;width:100%;height:auto;background:#020617;border:1px solid #1f2937;border-radius:6px;cursor:crosshair;touch-action:none}
 input[type=text]{background:#1f2937;color:var(--ink);border:1px solid #374151;border-radius:6px;padding:4px 6px}
 #faceDelete:disabled{opacity:.45;cursor:default}
 #facePat{width:100%;background:#020617;color:#93c5fd;border:1px solid #1f2937;border-radius:6px;font:10px/1.25 Consolas,monospace;resize:none}
</style></head><body>
<div id="side">
 <h1>Sparky - interactive fit check</h1>
 <div class="sub">Drag to rotate, right-drag to pan, scroll to zoom. Click a part for details. Sizes in mm.</div>

 <h2>Printed parts</h2>
 <div id="parts"></div>
 <div class="slab"><span>Shell see-through</span><span id="opv"></span></div>
 <input id="opacity" type="range" min="0.08" max="1" step="0.01" value="0.35">
 <div class="slab"><span>Pull back panels away</span><span id="exv"></span></div>
 <input id="explode" type="range" min="0" max="90" step="1" value="0">
 <label><input id="secOn" type="checkbox"> Slice open (section view)</label>
 <div class="slab"><span>Slice position (left/right)</span><span id="secv"></span></div>
 <input id="sec" type="range" min="-95" max="95" step="0.5" value="0">
 <div class="row" style="margin-top:6px"><button data-v="front">Front</button><button data-v="back">Back</button><button data-v="side">Side</button><button data-v="top">Top</button><button data-v="iso">3D</button></div>

 <h2>Components</h2>
 <div id="comps"></div>
 <label style="margin-top:6px">ESP32 goes:
  <select id="espLoc"><option value="shelf">on the body back-wall shelf (current design)</option><option value="breadboard">on the breadboard</option></select></label>

 <h2>Face on the LED matrix</h2>
 <label>Face: <select id="face"></select></label>
 <div class="sub" style="margin-top:4px">Click or drag on the grid to draw your own face (32 x 8 LEDs):</div>
 <canvas id="faceEd" width="312" height="80"></canvas>
 <div class="row" style="margin:4px 0"><button id="faceClear">Clear</button><button id="faceInvert">Invert</button><button data-v="face">Face close-up</button><button data-v="portrait">Whole Sparky</button></div>
 <div class="row" style="margin:6px 0 2px"><input id="faceName" type="text" maxlength="40" placeholder="Name your face" style="flex:1;min-width:0"><button id="faceSave">Save face</button></div>
 <div class="row" style="margin-bottom:4px"><button id="faceDelete" disabled>Delete saved face</button><button id="faceDownload">Download my faces</button><button id="faceLoadBtn">Load faces file</button><input id="faceLoad" type="file" accept=".json,application/json" hidden></div>
 <div id="faceMsg" class="sub"></div>
 <label><input id="visor" type="checkbox" checked> Black screen around the face (paint or film)</label>
 <label><input id="film" type="checkbox" checked> Smoked film over the LEDs</label>
 <div class="sub">Pattern for the firmware ('#' = LED on, top row first):</div>
 <textarea id="facePat" readonly rows="8" spellcheck="false"></textarea>

 <h2>Breadboard test (half size 82.5 x 54.5 x 8.5)</h2>
 <label><input id="bbOn" type="checkbox" checked> Show breadboard</label>
 <label>Place it:
  <select id="bbPreset">
   <option value="head">Head floor, lying flat (3 mm standoffs)</option>
   <option value="bodyFloor">Body floor, lying flat</option>
   <option value="bodyBack">Body back wall, standing up</option>
   <option value="headBack">Head back, standing up</option>
   <option value="custom">Custom (use sliders)</option>
  </select></label>
 <label>Turn it:
  <select id="bbOrient">
   <option value="flatX">Flat, long side left-right</option>
   <option value="flatY">Flat, long side front-back</option>
   <option value="upFront">Standing, facing forward (long side left-right)</option>
   <option value="upSide">Standing, facing sideways (long side front-back)</option>
   <option value="upTall">Standing, long side up-down</option>
  </select></label>
 <div class="slab"><span>Left / right (X)</span><span id="bxv"></span></div><input id="bx" type="range" min="-90" max="90" step="0.5">
 <div class="slab"><span>Back / front (Y)</span><span id="byv"></span></div><input id="by" type="range" min="-60" max="60" step="0.5">
 <div class="slab"><span>Height (Z, bottom face)</span><span id="bzv"></span></div><input id="bz" type="range" min="-5" max="210" step="0.5">
 <div class="slab"><span>Jumper-wire height above the board</span><span id="bjv"></span></div><input id="bj" type="range" min="0" max="25" step="1" value="15">
 <div id="bbstatus">Checking...</div>

 <h2>How to read this</h2>
 <div class="sub">
  <span class="ok">Fits</span> = no part of it goes through a wall.
  <span class="warn">Tight</span> = fits, but closer than 1 mm to a wall.
  <span class="bad">Collides</span> = goes through a wall or another part.
  Orange see-through boxes are room for jumper wires (a warning, not a hard limit).
  The check uses each part's outer box, so it is a little pessimistic near round walls.
  Parts that sit against their mount by design (matrix on its rails, speaker on its posts) are allowed to touch it.
 </div>
</div>
<div id="view"></div><div id="info"></div><div id="busy">checking fit...</div>

<script type="text/plain" id="three-src">__THREE__</script>
<script type="text/plain" id="oc-src">__ORBIT__</script>
<script type="application/json" id="mesh-data">__MESH__</script>
<script type="application/json" id="comp-data">__COMPS__</script>
<script type="module">
const blobURL = (src) => URL.createObjectURL(new Blob([src], {type: 'text/javascript'}));
const threeURL = blobURL(document.getElementById('three-src').textContent);
const THREE = await import(threeURL);
const ocSrc = document.getElementById('oc-src').textContent.replace("from 'three'", "from '" + threeURL + "'");
const {OrbitControls} = await import(blobURL(ocSrc));
const MESH = JSON.parse(document.getElementById('mesh-data').textContent);
const CFG = JSON.parse(document.getElementById('comp-data').textContent);
const $ = (id) => document.getElementById(id);
// small DOM builder (text is always set with text nodes, never parsed as HTML)
function h(tag, props = {}, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === 'class') e.className = v; else if (k === 'style') e.style.cssText = v;
    else if (k.startsWith('data-')) e.setAttribute(k, v); else e[k] = v;
  }
  for (const c of kids) e.append(c instanceof Node ? c : document.createTextNode(String(c)));
  return e;
}

// ---------- scene ----------
const view = $('view');
const renderer = new THREE.WebGLRenderer({antialias: true, preserveDrawingBuffer: true});
renderer.setPixelRatio(devicePixelRatio); renderer.localClippingEnabled = true;
view.appendChild(renderer.domElement);
const scene = new THREE.Scene(); scene.background = new THREE.Color('#0f172a');
const camera = new THREE.PerspectiveCamera(35, 1, 1, 5000); camera.up.set(0, 0, 1);
const controls = new OrbitControls(camera, renderer.domElement); controls.target.set(0, 0, 100);
scene.add(new THREE.HemisphereLight('#ffffff', '#334155', 1.1));
const sun = new THREE.DirectionalLight('#ffffff', 1.6); sun.position.set(-300, -400, 500); scene.add(sun);
const fill = new THREE.DirectionalLight('#ffffff', 0.6); fill.position.set(300, 300, 200); scene.add(fill);
const grid = new THREE.GridHelper(400, 40, '#334155', '#1e293b'); grid.rotation.x = Math.PI / 2; grid.position.z = -1.01; scene.add(grid);
const clip = new THREE.Plane(new THREE.Vector3(-1, 0, 0), 0);
function resize() { const w = view.clientWidth, hh = view.clientHeight; renderer.setSize(w, hh); camera.aspect = w / hh; camera.updateProjectionMatrix(); }
addEventListener('resize', resize); resize();

const b64 = (s, Arr) => { const bin = atob(s), u = new Uint8Array(bin.length); for (let i = 0; i < bin.length; i++) u[i] = bin.charCodeAt(i); return new Arr(u.buffer); };

// ---------- printed parts ----------
const parts = {}; const TRI = [];  // TRI: world-space triangles of all parts (assembled) for collision
for (const d of Object.values(MESH)) {
  const pos = b64(d.pos, Float32Array), idx = b64(d.idx, Uint32Array);
  for (let i = 0; i < idx.length; i++) { const k = idx[i] * 3; TRI.push(pos[k], pos[k + 1], pos[k + 2]); }
  let g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.BufferAttribute(pos, 3)); g.setIndex(new THREE.BufferAttribute(idx, 1));
  const edges = new THREE.LineSegments(new THREE.EdgesGeometry(g, 35), new THREE.LineBasicMaterial({color: '#0b3a5c', transparent: true, opacity: .55}));
  g = g.toNonIndexed(); g.computeVertexNormals();
  const meta = d.meta;
  const mat = new THREE.MeshStandardMaterial({color: meta.color, roughness: .55, metalness: 0, side: THREE.DoubleSide, transparent: true, opacity: .35, depthWrite: false});
  const mesh = new THREE.Mesh(g, mat); mesh.userData = {kind: 'part', title: meta.label};
  const grp = new THREE.Group(); grp.add(mesh); grp.add(edges); scene.add(grp);
  parts[meta.key] = {grp, mat, edges, label: meta.label, color: meta.color};
}
const T = new Float32Array(TRI); const NT = T.length / 9;
const TMIN = new Float32Array(NT * 3), TMAX = new Float32Array(NT * 3);
for (let t = 0; t < NT; t++) for (let a = 0; a < 3; a++) {
  const v0 = T[t * 9 + a], v1 = T[t * 9 + 3 + a], v2 = T[t * 9 + 6 + a];
  TMIN[t * 3 + a] = Math.min(v0, v1, v2); TMAX[t * 3 + a] = Math.max(v0, v1, v2);
}

// ---------- geometry tests ----------
function axisTest(ax, ay, az, v0, v1, v2, hx) {
  const p0 = ax * v0[0] + ay * v0[1] + az * v0[2], p1 = ax * v1[0] + ay * v1[1] + az * v1[2], p2 = ax * v2[0] + ay * v2[1] + az * v2[2];
  const r = hx[0] * Math.abs(ax) + hx[1] * Math.abs(ay) + hx[2] * Math.abs(az);
  return !(Math.min(p0, p1, p2) > r || Math.max(p0, p1, p2) < -r);
}
function triBox(c, hx, t) {  // Akenine-Moller triangle / AABB overlap
  const o = t * 9, v = [0, 1, 2].map(i => [T[o + i * 3] - c[0], T[o + i * 3 + 1] - c[1], T[o + i * 3 + 2] - c[2]]);
  const e = [[v[1][0] - v[0][0], v[1][1] - v[0][1], v[1][2] - v[0][2]], [v[2][0] - v[1][0], v[2][1] - v[1][1], v[2][2] - v[1][2]], [v[0][0] - v[2][0], v[0][1] - v[2][1], v[0][2] - v[2][2]]];
  for (const E of e) {
    if (!axisTest(0, -E[2], E[1], v[0], v[1], v[2], hx)) return false;
    if (!axisTest(E[2], 0, -E[0], v[0], v[1], v[2], hx)) return false;
    if (!axisTest(-E[1], E[0], 0, v[0], v[1], v[2], hx)) return false;
  }
  const n = [e[0][1] * e[1][2] - e[0][2] * e[1][1], e[0][2] * e[1][0] - e[0][0] * e[1][2], e[0][0] * e[1][1] - e[0][1] * e[1][0]];
  return axisTest(n[0], n[1], n[2], v[0], v[1], v[2], hx);
}
function boxHitsShell(min, max, grow) {
  const lo = [min[0] - grow, min[1] - grow, min[2] - grow], hi = [max[0] + grow, max[1] + grow, max[2] + grow];
  if (hi[0] <= lo[0] || hi[1] <= lo[1] || hi[2] <= lo[2]) return false;
  const c = [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, (lo[2] + hi[2]) / 2], hx = [(hi[0] - lo[0]) / 2, (hi[1] - lo[1]) / 2, (hi[2] - lo[2]) / 2];
  for (let t = 0; t < NT; t++) {
    const k = t * 3;
    if (TMAX[k] < lo[0] || TMIN[k] > hi[0] || TMAX[k + 1] < lo[1] || TMIN[k + 1] > hi[1] || TMAX[k + 2] < lo[2] || TMIN[k + 2] > hi[2]) continue;
    if (triBox(c, hx, t)) return true;
  }
  return false;
}
function rayHits(o, d) {  // Moller-Trumbore against every shell triangle
  for (let t = 0; t < NT; t++) {
    const b = t * 9, ax = T[b], ay = T[b + 1], az = T[b + 2];
    const e1x = T[b + 3] - ax, e1y = T[b + 4] - ay, e1z = T[b + 5] - az, e2x = T[b + 6] - ax, e2y = T[b + 7] - ay, e2z = T[b + 8] - az;
    const px = d[1] * e2z - d[2] * e2y, py = d[2] * e2x - d[0] * e2z, pz = d[0] * e2y - d[1] * e2x, det = e1x * px + e1y * py + e1z * pz;
    if (Math.abs(det) < 1e-9) continue;
    const inv = 1 / det, tx = o[0] - ax, ty = o[1] - ay, tz = o[2] - az, u = (tx * px + ty * py + tz * pz) * inv;
    if (u < 0 || u > 1) continue;
    const qx = ty * e1z - tz * e1y, qy = tz * e1x - tx * e1z, qz = tx * e1y - ty * e1x, w = (d[0] * qx + d[1] * qy + d[2] * qz) * inv;
    if (w < 0 || u + w > 1) continue;
    if ((e2x * qx + e2y * qy + e2z * qz) * inv > 0) return true;
  }
  return false;
}
const DIRS = [[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]];
// inside = walls in at least 4 of 6 directions (rays may escape through real openings: window, grille, button/USB holes)
const enclosed = (min, max) => { const c = [0, 1, 2].map(i => (min[i] + max[i]) / 2); return DIRS.filter(d => rayHits(c, d)).length >= 4; };
const boxesOverlap = (a, b, s = 0.3) => [0, 1, 2].every(i => a.min[i] + s < b.max[i] - s && b.min[i] + s < a.max[i] - s);

// ---------- components ----------
const compMeshes = {};  // id -> {mesh, min, max, def, visible}
function boxMesh(min, max, color, opts = {}) {
  const g = new THREE.BoxGeometry(max[0] - min[0], max[1] - min[1], max[2] - min[2]);
  const m = new THREE.MeshStandardMaterial({color, roughness: .6, emissive: opts.emissive || '#000', emissiveIntensity: opts.emissive ? .6 : 0, transparent: !!opts.ghost, opacity: opts.ghost ? .28 : 1, depthWrite: !opts.ghost});
  const mesh = new THREE.Mesh(g, m); mesh.position.set((min[0] + max[0]) / 2, (min[1] + max[1]) / 2, (min[2] + max[2]) / 2);
  if (opts.ghost) mesh.add(new THREE.LineSegments(new THREE.EdgesGeometry(g), new THREE.LineBasicMaterial({color})));
  return mesh;
}
function cylMesh(c, color, opts = {}) {
  const len = c.a1 - c.a0, g = new THREE.CylinderGeometry(c.r, c.r, len, 40);
  const m = new THREE.MeshStandardMaterial({color, roughness: .5, emissive: opts.emissive || '#000', emissiveIntensity: opts.emissive ? .7 : 0});
  const mesh = new THREE.Mesh(g, m), mid = (c.a0 + c.a1) / 2;
  if (c.axis === 'z') { mesh.rotation.x = Math.PI / 2; mesh.position.set(c.c[0], c.c[1], mid); }
  else { mesh.position.set(c.c[0], mid, c.c[1]); }
  const min = c.axis === 'z' ? [c.c[0] - c.r, c.c[1] - c.r, c.a0] : [c.c[0] - c.r, c.a0, c.c[1] - c.r];
  const max = c.axis === 'z' ? [c.c[0] + c.r, c.c[1] + c.r, c.a1] : [c.c[0] + c.r, c.a1, c.c[1] + c.r];
  return {mesh, min, max};
}
// ---------- realistic LED matrix (4 x 8x8 blocks, 3 mm blue LEDs on a 4 mm pitch) ----------
const LED = {cols: 32, rows: 8, pitch: 4, x0: -62, zTop: 160, y: -48.15};  // LED centres; head is 3 mm up
const ledGeo = new THREE.CylinderGeometry(1.5, 1.5, 0.6, 20);              // axis along Y = facing the window
const ledOn = new THREE.InstancedMesh(ledGeo, new THREE.MeshBasicMaterial({color: '#5fb2ff'}), 256);
const ledOff = new THREE.InstancedMesh(ledGeo, new THREE.MeshStandardMaterial({color: '#1b2433', roughness: .35}), 256);
const glowTex = (() => {
  const c = document.createElement('canvas'); c.width = c.height = 64; const g = c.getContext('2d');
  const r = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  r.addColorStop(0, 'rgba(120,195,255,1)'); r.addColorStop(.3, 'rgba(40,130,255,.6)'); r.addColorStop(1, 'rgba(20,80,255,0)');
  g.fillStyle = r; g.fillRect(0, 0, 64, 64); return new THREE.CanvasTexture(c);
})();
const glowGeo = new THREE.PlaneGeometry(7.5, 7.5); glowGeo.rotateX(Math.PI / 2);  // faces -Y (out of the window)
const ledGlow = new THREE.InstancedMesh(glowGeo, new THREE.MeshBasicMaterial({map: glowTex, transparent: true, blending: THREE.AdditiveBlending, depthWrite: false, side: THREE.DoubleSide}), 256);
let faceRows = CFG.faces[Object.keys(CFG.faces)[0]].slice();
function showFace(rows) {
  faceRows = rows.slice(); const m = new THREE.Matrix4(); let on = 0, off = 0;
  for (let r = 0; r < LED.rows; r++) for (let c = 0; c < LED.cols; c++) {
    const x = LED.x0 + c * LED.pitch, z = LED.zTop - r * LED.pitch;
    if (rows[r][c] === '#') { m.makeTranslation(x, LED.y, z); ledOn.setMatrixAt(on, m); m.makeTranslation(x, LED.y - 0.6, z); ledGlow.setMatrixAt(on, m); on++; }
    else { m.makeTranslation(x, LED.y, z); ledOff.setMatrixAt(off++, m); }
  }
  ledOn.count = on; ledGlow.count = on; ledOff.count = off;
  for (const im of [ledOn, ledOff, ledGlow]) im.instanceMatrix.needsUpdate = true;
  $('facePat').value = rows.join('\n'); drawEditor();
}
function buildMatrix() {
  const grp = new THREE.Group();
  const block = new THREE.MeshStandardMaterial({color: '#0b0d12', roughness: .45});
  for (let b = 0; b < 4; b++) {  // four 32 x 32 LED blocks, 8 mm deep, tiny gaps between them
    const x0 = -64 + b * 32 + 0.15, mesh = new THREE.Mesh(new THREE.BoxGeometry(31.7, 8, 31.7), block);
    mesh.position.set(x0 + 31.7 / 2, -48.0 + 4, 146); grp.add(mesh);
  }
  const pcb = new THREE.Mesh(new THREE.BoxGeometry(129, 1.6, 32), new THREE.MeshStandardMaterial({color: '#1e40af', roughness: .6}));
  pcb.position.set(0, -39.2, 146); grp.add(pcb);
  for (let b = 0; b < 4; b++) {  // the four MAX7219 chips on the back
    const chip = new THREE.Mesh(new THREE.BoxGeometry(15, 3.5, 7.5), new THREE.MeshStandardMaterial({color: '#111', roughness: .5}));
    chip.position.set(-48 + b * 32, -36.6, 146); grp.add(chip);
  }
  grp.add(ledOn, ledOff, ledGlow);
  return grp;
}
// black screen (painted recess) with a hole for the LED window, plus an optional smoked film
function roundedRect(path, x0, y0, x1, y1, r) {
  path.moveTo(x0 + r, y0); path.lineTo(x1 - r, y0); path.quadraticCurveTo(x1, y0, x1, y0 + r);
  path.lineTo(x1, y1 - r); path.quadraticCurveTo(x1, y1, x1 - r, y1); path.lineTo(x0 + r, y1);
  path.quadraticCurveTo(x0, y1, x0, y1 - r); path.lineTo(x0, y0 + r); path.quadraticCurveTo(x0, y0, x0 + r, y0);
}
const visorShape = new THREE.Shape(); roundedRect(visorShape, -66, 108, 66, 184, 26);
const hole = new THREE.Path(); hole.moveTo(-63, 131); hole.lineTo(63, 131); hole.lineTo(63, 161); hole.lineTo(-63, 161); hole.lineTo(-63, 131);
visorShape.holes.push(hole);
const visorGeo = new THREE.ShapeGeometry(visorShape, 24); visorGeo.rotateX(Math.PI / 2);
const visor = new THREE.Mesh(visorGeo, new THREE.MeshStandardMaterial({color: '#05070c', roughness: .25, metalness: .3, side: THREE.DoubleSide, polygonOffset: true, polygonOffsetFactor: -2}));
visor.position.y = -50.56; scene.add(visor);
const filmGeo = new THREE.PlaneGeometry(126, 30); filmGeo.rotateX(Math.PI / 2);
const film = new THREE.Mesh(filmGeo, new THREE.MeshStandardMaterial({color: '#0a0f1c', roughness: .1, metalness: .2, transparent: true, opacity: .3, side: THREE.DoubleSide, depthWrite: false}));
film.position.set(0, -50.6, 146); scene.add(film);

function addComp(def) {
  let mesh, min, max;
  if (def.id === 'matrix') { [min, max] = def.box; mesh = buildMatrix(); }
  else if (def.box) { [min, max] = def.box; mesh = boxMesh(min, max, def.color, def); }
  else ({mesh, min, max} = cylMesh(def.cyl, def.color, def));
  mesh.traverse(o => { o.userData = {kind: 'comp', id: def.id}; }); scene.add(mesh);
  compMeshes[def.id] = {mesh, min, max, def, visible: true};
}
CFG.components.forEach(addComp);
const ESP = {
  board: {def: {id: 'esp32', name: 'ESP32-DevKitC (38-pin)', color: '#0f766e', mounted: true, note: '54.4 x 27.9 mm board. Here: standing on the shelf on the body back wall, module side to the wall, pins facing forward.'}},
  jumpers: {def: {id: 'esp32_wires', name: 'Room for jumper wires (ESP32)', color: '#f97316', ghost: true, soft: true, note: 'About 14 mm for Dupont plugs on the ESP32 pins.'}},
  usb: {def: {id: 'usb', name: 'Micro-USB plug', color: '#9ca3af', mounted: true, note: 'Plug body of the USB cable at the end of the ESP32.'}},
};
const BB = {
  base: {def: {id: 'bb', name: 'Half breadboard 82.5 x 54.5 x 8.5', color: '#f1f5f9', note: 'Standard 400-point half-size breadboard.'}},
  esp: {def: {id: 'bb_esp', name: 'ESP32 on the breadboard', color: '#0f766e', note: 'ESP32-DevKitC plugged into the breadboard (about 8 mm above it).'}},
  wires: {def: {id: 'bb_wires', name: 'Room for jumper wires (breadboard)', color: '#f97316', ghost: true, soft: true, note: 'Space for jumper wires sticking up out of the breadboard - adjust with the slider.'}},
  usb: {def: {id: 'bb_usb', name: 'Micro-USB plug (on breadboard ESP32)', color: '#9ca3af', note: 'USB plug at the end of the ESP32.'}},
};
function setBoxMesh(slot, min, max) {
  if (slot.mesh) { scene.remove(slot.mesh); slot.mesh.geometry.dispose(); }
  slot.mesh = boxMesh(min, max, slot.def.color, slot.def); slot.mesh.userData = {kind: 'comp', id: slot.def.id};
  slot.min = min; slot.max = max; scene.add(slot.mesh);
}

// ---------- breadboard placement ----------
const ORIENT = {  // u = long side, v = short side, n = normal (where wires stick out)
  flatX: {u: [1, 0, 0], v: [0, 1, 0], n: [0, 0, 1]}, flatY: {u: [0, 1, 0], v: [1, 0, 0], n: [0, 0, 1]},
  upFront: {u: [1, 0, 0], v: [0, 0, 1], n: [0, -1, 0]}, upSide: {u: [0, 1, 0], v: [0, 0, 1], n: [1, 0, 0]},
  upTall: {u: [0, 0, 1], v: [1, 0, 0], n: [0, -1, 0]},
};
const PRESET = {
  head: {o: 'flatX', p: [0, -5, 96]}, bodyFloor: {o: 'flatX', p: [0, 5, 16.5]},
  bodyBack: {o: 'upFront', p: [0, 41.5, 30]}, headBack: {o: 'upFront', p: [0, 49.5, 120]},
};
function orientedBox(p, o, alongU, alongV, n0, n1) {  // p = centre of the back face; box spans n0..n1 along the normal
  const pts = [];
  for (const su of [-.5, .5]) for (const sv of [-.5, .5]) for (const sn of [n0, n1])
    pts.push([0, 1, 2].map(i => p[i] + o.u[i] * su * alongU + o.v[i] * sv * alongV + o.n[i] * sn));
  return [[0, 1, 2].map(i => Math.min(...pts.map(q => q[i]))), [0, 1, 2].map(i => Math.max(...pts.map(q => q[i])))];
}
function compVisible(id) { const el = document.querySelector(`[data-comp="${id}"]`); return el ? el.checked : true; }
function placeBreadboard() {
  const o = ORIENT[$('bbOrient').value], p = [+$('bx').value, +$('by').value, +$('bz').value], J = +$('bj').value;
  // the Z slider is the bottom of the board, so lift standing boards by half their height
  const lift = Math.abs(o.v[2]) ? 54.5 / 2 : Math.abs(o.u[2]) ? 82.5 / 2 : 0;
  const pc = [p[0], p[1], p[2] + lift];
  const onBB = $('espLoc').value === 'breadboard';
  setBoxMesh(BB.base, ...orientedBox(pc, o, 82.5, 54.5, 0, 8.5));
  setBoxMesh(BB.wires, ...orientedBox(pc, o, 82.5, 54.5, 8.5, 8.5 + J));
  if (onBB) {
    setBoxMesh(BB.esp, ...orientedBox(pc, o, 54.4, 27.9, 8.5, 16.5));
    const uc = pc.map((x, i) => x + o.u[i] * (54.4 / 2 + 10));  // USB plug sticks out of the +u end
    setBoxMesh(BB.usb, ...orientedBox(uc, o, 20, 8, 9.5, 17.5));
  }
  for (const s of [BB.esp, BB.usb]) if (s.mesh) s.mesh.visible = onBB && $('bbOn').checked;
  for (const s of [BB.base, BB.wires]) s.mesh.visible = $('bbOn').checked;
  for (const k of ['board', 'jumpers', 'usb']) if (ESP[k].mesh) ESP[k].mesh.visible = !onBB && compVisible('esp32');
  ['bx', 'by', 'bz', 'bj'].forEach(id => $(id + 'v').textContent = (+$(id).value).toFixed(1) + ' mm');
}
function placeShelfEsp() {
  setBoxMesh(ESP.board, ...CFG.esp32_shelf.board); setBoxMesh(ESP.jumpers, ...CFG.esp32_shelf.jumpers); setBoxMesh(ESP.usb, ...CFG.esp32_shelf.usb);
}

// ---------- fit evaluation ----------
function verdict(min, max, mounted, soft) {
  const shrink = mounted ? -0.3 : -0.05;
  if (boxHitsShell(min, max, shrink)) return soft ? ['warn', 'wires touch a wall'] : ['bad', 'collides with a wall'];
  if (!enclosed(min, max)) return ['bad', 'outside the shell'];
  if (mounted) return ['ok', 'fits (seated)'];
  for (const g of [1, 2, 3]) if (boxHitsShell(min, max, g)) return g === 1 ? ['warn', 'tight (<1 mm)'] : ['ok', `fits (${g - 1}-${g} mm gap)`];
  return ['ok', 'fits (>3 mm gap)'];
}
function activeItems() {
  const items = [];
  for (const c of Object.values(compMeshes)) if (c.visible) items.push({id: c.def.id, name: c.def.name, min: c.min, max: c.max, mounted: c.def.mounted, soft: c.def.soft, nowall: c.def.nowall});
  const onBB = $('espLoc').value === 'breadboard';
  if (!onBB && compVisible('esp32')) for (const k of ['board', 'jumpers', 'usb']) items.push({id: ESP[k].def.id, name: ESP[k].def.name, min: ESP[k].min, max: ESP[k].max, mounted: ESP[k].def.mounted, soft: ESP[k].def.soft});
  if ($('bbOn').checked) for (const k of onBB ? ['base', 'esp', 'usb', 'wires'] : ['base', 'wires'])
    items.push({id: BB[k].def.id, name: BB[k].def.name, min: BB[k].min, max: BB[k].max, soft: BB[k].def.soft, bb: true});
  return items;
}
const sameFamily = (a, b) => (a.bb && b.bb) || (a.id.startsWith('esp32') && b.id.startsWith('esp32')) ||
  ((a.id === 'usb' || b.id === 'usb') && (a.id.startsWith('esp32') || b.id.startsWith('esp32') || a.id === b.id)) ||
  (a.id.startsWith('button') && b.id.startsWith('button'));
function evaluate() {
  const items = activeItems(), res = {};
  for (const it of items) {
    let [cls, txt] = it.nowall ? ['ok', 'fits (through its hole)'] : verdict(it.min, it.max, it.mounted, it.soft);
    for (const o of items) {
      if (o === it || (it.soft && o.soft) || sameFamily(it, o)) continue;
      if (boxesOverlap(it, o)) {
        const other = o.name.split(' (')[0];
        if (it.soft || o.soft) { if (cls !== 'bad') [cls, txt] = ['warn', 'wire room overlaps ' + other]; }
        else [cls, txt] = ['bad', 'overlaps ' + other];
      }
    }
    res[it.id] = [cls, txt];
  }
  return res;
}
const BBNAMES = {bb: 'Breadboard', bb_esp: 'ESP32 on it', bb_usb: 'USB plug', bb_wires: 'Jumper-wire room'};
let pending = null;
function scheduleEval() {
  clearTimeout(pending); $('busy').style.display = 'block';
  pending = setTimeout(() => {
    const r = evaluate(); $('busy').style.display = 'none';
    document.querySelectorAll('[data-st]').forEach(el => {
      const v = r[el.dataset.st]; el.className = 'st ' + (v ? v[0] : ''); el.textContent = v ? v[1] : 'hidden';
    });
    const box = $('bbstatus'); box.replaceChildren();
    if (!$('bbOn').checked) { box.append('Breadboard hidden.'); return; }
    const ids = ($('espLoc').value === 'breadboard' ? ['bb', 'bb_esp', 'bb_usb', 'bb_wires'] : ['bb', 'bb_wires']).filter(id => r[id]);
    const classes = ids.map(id => r[id][0]);
    const worst = classes.includes('bad') ? 'bad' : classes.includes('warn') ? 'warn' : 'ok';
    const head = {ok: 'It fits here.', warn: 'It fits, but it is tight or the wires are cramped.', bad: 'It does not fit here.'}[worst];
    box.append(h('div', {id: 'bbhead', class: worst}, head));
    for (const id of ids) box.append(h('div', {}, h('span', {class: r[id][0]}, '● '), BBNAMES[id] + ': ', h('b', {class: r[id][0]}, r[id][1])));
  }, 60);
}

// ---------- UI ----------
for (const [key, p] of Object.entries(parts)) {
  $('parts').append(h('label', {}, h('input', {type: 'checkbox', checked: true, 'data-part': key}), h('span', {class: 'sw', style: 'background:' + p.color}), p.label));
}
$('parts').addEventListener('change', e => { const k = e.target.dataset.part; if (k) { parts[k].grp.visible = e.target.checked; applyView(); } });
const listed = [...CFG.components.map(c => [c.id, c.name, c.color]), ['esp32', 'ESP32-DevKitC (38-pin)', '#0f766e']];
for (const [id, name, color] of listed) {
  $('comps').append(h('label', {}, h('input', {type: 'checkbox', checked: true, 'data-comp': id}), h('span', {class: 'sw', style: 'background:' + color}), name, h('span', {class: 'st', 'data-st': id})));
}
$('comps').addEventListener('change', e => {
  const id = e.target.dataset.comp; if (!id) return;
  if (compMeshes[id]) { compMeshes[id].visible = e.target.checked; compMeshes[id].mesh.visible = e.target.checked; }
  placeBreadboard(); scheduleEval();
});
function applyView() {
  const op = +$('opacity').value; $('opv').textContent = Math.round(op * 100) + '%';
  for (const p of Object.values(parts)) { p.mat.opacity = op; p.mat.transparent = op < .99; p.mat.depthWrite = op >= .99; }
  const ex = +$('explode').value; $('exv').textContent = ex + ' mm';
  parts.headPanel.grp.position.y = ex; parts.bodyPanel.grp.position.y = ex;
  const on = $('secOn').checked, x = +$('sec').value; $('secv').textContent = x.toFixed(1) + ' mm'; clip.constant = x;
  for (const p of Object.values(parts)) { p.mat.clippingPlanes = on ? [clip] : []; p.edges.material.clippingPlanes = on ? [clip] : []; p.mat.needsUpdate = true; p.edges.material.needsUpdate = true; }
  for (const m of [visor.material, film.material]) { m.clippingPlanes = on ? [clip] : []; m.needsUpdate = true; }
  visor.visible = $('visor').checked && parts.front.grp.visible; film.visible = $('film').checked && parts.front.grp.visible;
}
['opacity', 'explode', 'sec', 'secOn', 'visor', 'film'].forEach(id => $(id).addEventListener('input', applyView));

// ---------- face picker and editor ----------
// saved faces live in this browser (localStorage) and can be downloaded / loaded as a JSON file
const STORE = 'sparky.faces.v1', SAVED = 'saved:', FORMAT = 'sparky-faces/1';
const validRows = r => Array.isArray(r) && r.length === 8 && r.every(x => typeof x === 'string' && /^[#.]{32}$/.test(x));
let saved = {};
try { const d = JSON.parse(localStorage.getItem(STORE) || '{}'); for (const [n, r] of Object.entries(d)) if (validRows(r)) saved[n] = r; } catch { saved = {}; }
const persist = () => { try { localStorage.setItem(STORE, JSON.stringify(saved)); return true; } catch { return false; } };
const say = (text, cls = '') => { $('faceMsg').className = 'sub ' + cls; $('faceMsg').textContent = text; };
const rowsFor = v => v.startsWith(SAVED) ? saved[v.slice(SAVED.length)] : CFG.faces[v];
function faceList(select) {
  const sel = $('face'); sel.replaceChildren();
  const builtIn = h('optgroup', {label: 'Sparky faces'});
  for (const n of Object.keys(CFG.faces)) builtIn.append(h('option', {value: n}, n));
  sel.append(builtIn);
  const mine = Object.keys(saved).sort((a, b) => a.localeCompare(b));
  if (mine.length) { const g = h('optgroup', {label: 'My saved faces'}); for (const n of mine) g.append(h('option', {value: SAVED + n}, n)); sel.append(g); }
  sel.append(h('option', {value: 'custom'}, 'My own drawing (not saved yet)'));
  sel.value = select; $('faceDelete').disabled = !sel.value.startsWith(SAVED);
}
$('face').addEventListener('change', () => {
  const v = $('face').value, rows = rowsFor(v);
  if (rows) showFace(rows);
  if (v.startsWith(SAVED)) $('faceName').value = v.slice(SAVED.length);
  $('faceDelete').disabled = !v.startsWith(SAVED); say('');
});
$('faceSave').addEventListener('click', () => {
  const name = $('faceName').value.trim();
  if (!name) return say('Type a name for your face first.', 'warn');
  if (CFG.faces[name]) return say('That name belongs to one of Sparky\'s built-in faces - pick another name.', 'warn');
  const existed = name in saved; saved[name] = faceRows.slice();
  if (!persist()) return say('This browser would not let the page save. Use "Download my faces" to keep your drawing.', 'bad');
  faceList(SAVED + name); say(existed ? `Updated "${name}".` : `Saved "${name}".`, 'ok');
});
$('faceDelete').addEventListener('click', () => {
  const v = $('face').value; if (!v.startsWith(SAVED)) return;
  const name = v.slice(SAVED.length);
  if (!confirm(`Delete your face "${name}"?`)) return;
  delete saved[name]; persist(); faceList('custom'); say(`Deleted "${name}".`);
});
$('faceDownload').addEventListener('click', () => {
  if (!Object.keys(saved).length) return say('You have not saved any faces yet.', 'warn');
  const blob = new Blob([JSON.stringify({format: FORMAT, faces: saved}, null, 1)], {type: 'application/json'});
  const a = h('a', {href: URL.createObjectURL(blob), download: 'sparky_faces.json'}); document.body.append(a); a.click(); a.remove();
  say(`Downloaded ${Object.keys(saved).length} face(s) as sparky_faces.json.`, 'ok');
});
$('faceLoadBtn').addEventListener('click', () => $('faceLoad').click());
$('faceLoad').addEventListener('change', async () => {
  const file = $('faceLoad').files[0]; $('faceLoad').value = ''; if (!file) return;
  try {
    const data = JSON.parse(await file.text()), faces = data && data.faces ? data.faces : data;
    let added = 0, skipped = 0;
    for (const [n, r] of Object.entries(faces || {})) {
      if (typeof n === 'string' && n.trim() && !CFG.faces[n] && validRows(r)) { saved[n.trim().slice(0, 40)] = r; added++; } else skipped++;
    }
    persist(); faceList($('face').value);
    say(`Loaded ${added} face(s)` + (skipped ? `, skipped ${skipped} that were not valid 32 x 8 faces.` : '.'), added ? 'ok' : 'warn');
  } catch { say('That file is not a Sparky faces file.', 'bad'); }
});
const ed = $('faceEd'), edg = ed.getContext('2d'), CELL = ed.width / 32;
function drawEditor() {
  edg.fillStyle = '#020617'; edg.fillRect(0, 0, ed.width, ed.height);
  for (let r = 0; r < 8; r++) for (let c = 0; c < 32; c++) {
    const on = faceRows[r][c] === '#';
    edg.fillStyle = on ? '#7cc4ff' : '#1e293b';
    edg.beginPath(); edg.arc(c * CELL + CELL / 2, r * (ed.height / 8) + ed.height / 16, CELL * 0.38, 0, Math.PI * 2); edg.fill();
  }
  edg.strokeStyle = '#334155'; edg.lineWidth = 1;
  for (let b = 1; b < 4; b++) { edg.beginPath(); edg.moveTo(b * 8 * CELL, 0); edg.lineTo(b * 8 * CELL, ed.height); edg.stroke(); }
}
let paint = null;
function cellAt(e) {
  const r = ed.getBoundingClientRect();
  return [Math.floor((e.clientY - r.top) / (r.height / 8)), Math.floor((e.clientX - r.left) / (r.width / 32))];
}
function setCell(row, col, on) {
  if (row < 0 || row > 7 || col < 0 || col > 31) return;
  const rows = faceRows.slice(); rows[row] = rows[row].slice(0, col) + (on ? '#' : '.') + rows[row].slice(col + 1);
  $('face').value = 'custom'; showFace(rows);
}
ed.addEventListener('pointerdown', e => { const [r, c] = cellAt(e); paint = faceRows[r][c] !== '#'; setCell(r, c, paint); ed.setPointerCapture(e.pointerId); });
ed.addEventListener('pointermove', e => { if (paint === null) return; const [r, c] = cellAt(e); if (faceRows[r] && (faceRows[r][c] === '#') !== paint) setCell(r, c, paint); });
ed.addEventListener('pointerup', () => { paint = null; });
$('faceClear').addEventListener('click', () => { $('face').value = 'custom'; showFace(Array(8).fill('.'.repeat(32))); });
$('faceInvert').addEventListener('click', () => { $('face').value = 'custom'; showFace(faceRows.map(r => [...r].map(ch => ch === '#' ? '.' : '#').join(''))); });
function setPreset(name) {
  const pr = PRESET[name]; if (!pr) return;
  $('bbOrient').value = pr.o; $('bx').value = pr.p[0]; $('by').value = pr.p[1]; $('bz').value = pr.p[2];
}
$('bbPreset').addEventListener('change', () => { setPreset($('bbPreset').value); placeBreadboard(); scheduleEval(); });
['bx', 'by', 'bz', 'bj', 'bbOrient'].forEach(id => $(id).addEventListener('input', () => { $('bbPreset').value = 'custom'; placeBreadboard(); scheduleEval(); }));
['bbOn', 'espLoc'].forEach(id => $(id).addEventListener('change', () => { placeBreadboard(); scheduleEval(); }));
const VIEWS = {front: [0, -700, 110], back: [0, 700, 110], side: [700, 0, 110], top: [0, -1, 750], iso: [-420, -560, 380], face: [0, -230, 150], portrait: [0, -440, 125]};
const TARGETS = {face: [0, 0, 146], portrait: [0, 0, 104]};
function goView(v) {
  camera.position.set(...VIEWS[v]); controls.target.set(...(TARGETS[v] || [0, 0, 100])); controls.update();
  if (v === 'face' || v === 'portrait') { $('opacity').value = 1; applyView(); }
}
document.querySelectorAll('[data-v]').forEach(b => b.addEventListener('click', () => goView(b.dataset.v)));

// click for info
const ray = new THREE.Raycaster(), mouse = new THREE.Vector2();
const ALL = () => [...Object.values(compMeshes).map(c => [c.def, c.min, c.max]), ...Object.values(ESP).map(s => [s.def, s.min, s.max]), ...Object.values(BB).map(s => [s.def, s.min, s.max])];
renderer.domElement.addEventListener('click', e => {
  const r = renderer.domElement.getBoundingClientRect();
  mouse.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
  ray.setFromCamera(mouse, camera);
  const hit = ray.intersectObjects(scene.children, true).find(x => x.object.visible && x.object.userData.kind && (x.object.userData.kind === 'comp' || x.object.parent.visible));
  const info = $('info'); info.replaceChildren();
  if (!hit) { info.style.display = 'none'; return; }
  const u = hit.object.userData;
  if (u.kind === 'part') { info.append(h('b', {}, u.title)); info.style.display = 'block'; return; }
  const f = ALL().find(([d]) => d.id === u.id); if (!f) return;
  const [d, mn, mx] = f, size = [0, 1, 2].map(i => (mx[i] - mn[i]).toFixed(1)).join(' x ');
  info.append(h('b', {}, d.name), h('br'), d.note || '', h('br'),
    h('span', {class: 'dim'}, `Box: ${size} mm, from (${mn.map(v => v.toFixed(1)).join(', ')}) to (${mx.map(v => v.toFixed(1)).join(', ')})`));
  info.style.display = 'block';
});

// expose a tiny hook so the guide generator can drive the view and read results
window.sparky = {setView: goView, evaluate, set: (id, v) => { const el = $(id); if (el.type === 'checkbox') el.checked = v; else el.value = v; el.dispatchEvent(new Event(el.tagName === 'SELECT' || el.type === 'checkbox' ? 'change' : 'input')); }};
faceList(Object.keys(CFG.faces)[0]);
placeShelfEsp(); setPreset('head'); placeBreadboard(); applyView(); showFace(faceRows);
camera.position.set(...VIEWS.iso); controls.update(); scheduleEval();
renderer.setAnimationLoop(() => { controls.update(); renderer.render(scene, camera); });
document.body.dataset.ready = '1';
</script></body></html>
"""


def main():
    parts = read_3mf(MODEL_3MF)
    for name, d in parts.items():
        key, label, color = PART_LABELS[name]
        d["meta"] = dict(key=key, label=label, color=color)
        print(f"{name:12} -> {key:10} {d['nv']} vertices, {d['nt']} triangles")
    three = (VENDOR / "three.module.min.js").read_text(encoding="utf-8")
    orbit = (VENDOR / "OrbitControls.js").read_text(encoding="utf-8")
    for src in (three, orbit):
        assert "</script" not in src.lower(), "vendored source would end the <script> block early"
    for name, rows in FACES.items():
        assert len(rows) == 8 and all(len(r) == 32 for r in rows), name
    comps = dict(components=COMPONENTS, esp32_shelf=ESP32_SHELF, faces=FACES)
    html = (HTML.replace("__THREE__", three).replace("__ORBIT__", orbit)
            .replace("__MESH__", json.dumps(parts)).replace("__COMPS__", json.dumps(comps)))
    OUT.write_text(html, encoding="utf-8")
    print(f"Wrote {OUT} ({OUT.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
