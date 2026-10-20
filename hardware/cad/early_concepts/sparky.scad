// Sparky — desk-buddy STEM tutor enclosure
// ESP32-S3 + INMP441 mic + MAX98357A amp + speaker + 2x MAX7219 8x8 LED matrix eyes
//
// HOW TO USE (OpenSCAD, free — openscad.org):
//   1. Open this file in OpenSCAD.
//   2. Set PART below to "front", "back", or "both" (preview only).
//   3. Press F6 (Render), then File > Export > Export as STL.
//   4. Repeat for the other half. Print each with its flat (cut) face down — no supports needed.
//
// Nothing has been ordered yet, so board footprints below are best-guess placeholders.
// Once your boards arrive, measure them and update the *_dims variables — that's the
// only thing you should need to touch to make everything line up.

PART = "both";      // "front" | "back" | "both"
EXPLODE = false;    // true = pull halves apart in preview, to eyeball the fit
$fn = 48;

// ===== Overall body =====
body_w = 85;   // left-right
body_d = 65;   // front-back
body_h = 100;  // torso+head height, feet sit below z=0
wall   = 2.5;  // shell thickness

// ===== Face: two MAX7219 8x8 matrices as eyes =====
eye_size = 33;     // ponytail: placeholder, measure your actual matrix module and update
eye_gap  = 6;
eye_z    = body_h * 0.62;

// ===== Speaker grille (belly) =====
speaker_hole_d = 3;
speaker_rows = 4;
speaker_cols = 4;
speaker_spacing = 6;
speaker_z = body_h * 0.28;

// ===== Mic port (top of head, straight path to open air) =====
mic_hole_d = 2.5;
mic_z = body_h * 0.97;

// ===== USB-C cable port (back, near base) =====
usb_w = 10;
usb_h = 4;
usb_z = 12;

// ===== Screw bosses joining front/back halves =====
boss_od       = 8;
boss_pilot_d  = 2.6;  // M3 self-tap pilot hole (back half)
boss_clear_d  = 3.4;  // M3 clearance hole (front half)
boss_len      = 8;

// Body is a blob, not a box — bosses must sit within the torso's wide middle
// (not up near the tapering head) or they'd land outside the actual shell.
boss_x   = body_w * 0.25;
boss_z_hi = body_h * 0.55;
boss_z_lo = body_h * 0.20;

boss_xy = [
  [-boss_x, boss_z_hi],
  [ boss_x, boss_z_hi],
  [-boss_x, boss_z_lo],
  [ boss_x, boss_z_lo],
];

// ===== Internal board shelves =====
// ponytail: generous friction pegs + zip-tie slot, not precision screw-hole mounts —
// exact hole spacing varies by vendor/batch and nothing's ordered yet.
// Upgrade path once parts are in hand: measure real hole spacing, swap pegs for screw posts.
shelf_h = 3;
peg_d = 2.6;
peg_h = 5;
esp32_dims = [51, 28];
amp_dims   = [20, 20];
mic_dims   = [15, 15];

module blob(w, d, h) {
    scale([w/2, d/2, h/2]) sphere(1);
}

module torso_blob() {
    translate([0, 0, body_h * 0.42]) blob(body_w, body_d, body_h * 0.62);
}

module body_solid() {
    union() {
        hull() {
            torso_blob();
            translate([0, 0, body_h * 0.82]) blob(body_w * 0.72, body_d * 0.72, body_h * 0.42);
        }
        // stub arms — hulled to the torso so the join is solid, not a pinch point
        for (side = [-1, 1])
            hull() {
                torso_blob();
                translate([side * body_w * 0.52, 0, body_h * 0.42])
                    blob(body_w * 0.22, body_d * 0.32, body_h * 0.18);
            }
        // little feet peeking out front-bottom — same reasoning
        for (side = [-1, 1])
            hull() {
                torso_blob();
                translate([side * body_w * 0.2, -body_d * 0.18, body_h * 0.06])
                    blob(body_w * 0.22, body_d * 0.3, body_h * 0.16);
            }
    }
}

module body_standing() {
    // flat bottom so it sits on a desk
    intersection() {
        body_solid();
        translate([0, 0, 5000]) cube([10000, 10000, 10000], center = true);
    }
}

module shell() {
    // Approximate constant-thickness hollowing by scaling a copy of the body inward.
    // Body sits on z=0..z_top (not centered on the origin), so the scale must be
    // centered on the body's own midpoint in Z — scaling about the origin would
    // leave the wall ~2x too thick at the head and paper-thin (zero) at the base.
    z_top = body_h * 1.03;
    z_mid = z_top / 2;
    inner_scale = [
        (body_w - 2 * wall) / body_w,
        (body_d - 2 * wall) / body_d,
        (z_top - 2 * wall) / z_top,
    ];
    difference() {
        body_standing();
        translate([0, 0, z_mid])
            scale(inner_scale)
                translate([0, 0, -z_mid])
                    body_standing();
    }
}

// Wall cutouts are cylinders/prisms centered near the body's y=0 axis, extruded far
// enough to punch through one wall with margin — NOT sized to reach the opposite wall.
cut_len = body_d * 1.5;
cut_margin = 5;

module eyes_cut() {
    for (side = [-1, 1])
        translate([side * (eye_size / 2 + eye_gap / 2), cut_margin, eye_z])
            rotate([90, 0, 0])
                linear_extrude(cut_len)
                    square([eye_size, eye_size], center = true);
}

module speaker_cut() {
    translate([0, cut_margin, speaker_z])
        rotate([90, 0, 0])
            for (r = [0 : speaker_rows - 1], c = [0 : speaker_cols - 1])
                translate([
                    (c - (speaker_cols - 1) / 2) * speaker_spacing,
                    (r - (speaker_rows - 1) / 2) * speaker_spacing,
                    0
                ])
                    linear_extrude(cut_len) circle(d = speaker_hole_d);
}

module mic_cut() {
    translate([0, 0, mic_z])
        cylinder(h = body_h, d = mic_hole_d, center = true);
}

module usb_cut() {
    translate([0, -cut_margin, usb_z])
        rotate([-90, 0, 0])
            linear_extrude(cut_len)
                hull() {
                    translate([-usb_w/2 + usb_h/2, 0]) circle(d = usb_h);
                    translate([ usb_w/2 - usb_h/2, 0]) circle(d = usb_h);
                }
}

module boss_and_holes() {
    union() {
        for (p = boss_xy)
            translate([p[0], -1, p[1]])
                rotate([-90, 0, 0])
                    difference() {
                        cylinder(h = boss_len + 1, d = boss_od);
                        translate([0, 0, -1]) cylinder(h = boss_len + 3, d = boss_pilot_d);
                    }
    }
}

module boss_clearance_holes() {
    for (p = boss_xy)
        translate([p[0], -body_d, p[1]])
            rotate([-90, 0, 0])
                cylinder(h = body_d + 4, d = boss_clear_d);
}

module board_shelf(dims, pos_z) {
    translate([0, 0, pos_z]) {
        cube([dims[0] + 4, dims[1] + 4, shelf_h], center = true);
        for (x = [-1, 1], y = [-1, 1])
            translate([x * dims[0]/2, y * dims[1]/2, shelf_h/2 + peg_h/2])
                cylinder(h = peg_h, d = peg_d, center = true);
    }
}

module sparky_assembly() {
    difference() {
        union() {
            shell();
            boss_and_holes();
            // Heights chosen to stay in the torso's wide middle band (the body
            // tapers to a point at top and bottom, like any ellipsoid) and clear
            // of the eye cutouts above z=0.45*body_h — otherwise boards either
            // don't physically fit or get chewed up by a cutout.
            board_shelf(mic_dims, body_h * 0.20);
            board_shelf(amp_dims, body_h * 0.30);
            board_shelf(esp32_dims, body_h * 0.40);
        }
        eyes_cut();
        speaker_cut();
        mic_cut();
        usb_cut();
        boss_clearance_holes();
    }
}

module half_space(sign) {
    // sign = -1 keeps front (y<=0), +1 keeps back (y>=0)
    translate([0, sign * 5000, 0]) cube([10000, 10000, 10000], center = true);
}

module render_part(part) {
    if (part == "front")
        intersection() { sparky_assembly(); half_space(-1); }
    else if (part == "back")
        intersection() { sparky_assembly(); half_space(1); }
    else
        sparky_assembly();
}

if (PART == "both" && EXPLODE) {
    translate([0, -15, 0]) intersection() { sparky_assembly(); half_space(-1); }
    translate([0, 15, 0]) intersection() { sparky_assembly(); half_space(1); }
} else {
    render_part(PART);
}
