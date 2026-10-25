# Sparky firmware

Faces, mood mapping and voice lines come from **Sparky Studio** over Wi-Fi
(docs/PROTOCOL.md, "Personality pack"). This program only has to be put on
the ESP32 once.

Wiring, and a test for each part before this program goes on: `docs/sparky_wiring_guide.pdf`
and the test sketch in `../sparky_hw_test/`.

## Build and upload

Board: **ESP32 Dev Module**, partition scheme **Default 4MB with spiffs**
(about 1.3 MB of flash for voice lines, and room for program updates over
Wi-Fi later). Libraries: WiFiManager, ArduinoJson 7, MD_MAX72XX.
`build_opt.h` drops HTTPS support from HTTPClient (Sparky only uses plain http on the
local network) - it saves ~90 KB of program space; keep it.

From a terminal, using the `arduino-cli` that ships with the Arduino IDE
(no need to open the IDE):

```bash
CLI="$LOCALAPPDATA/Programs/Arduino IDE/resources/app/lib/backend/resources/arduino-cli.exe"
"$CLI" lib install WiFiManager ArduinoJson MD_MAX72XX     # once
"$CLI" compile --fqbn esp32:esp32:esp32 firmware/sparky
"$CLI" board list                                          # find the COM port
"$CLI" upload --fqbn esp32:esp32:esp32 -p COM5 firmware/sparky
"$CLI" monitor -p COM5 -c baudrate=115200                  # watch what Sparky is doing
```

(Opening `sparky.ino` in the Arduino IDE and pressing Upload works too.)

## First boot

Sparky opens the **"Sparky Setup"** Wi-Fi hotspot (password `sparky123`).
Connect with a phone, choose the school Wi-Fi, and enter:

- **Server address** - e.g. `http://192.168.1.20:8001` (the PC running `python simple_api.py`)
- **Device key** - from the admin **Devices** page (Register device)

Hold Sparky's button while switching on to open the setup page again (new
Wi-Fi, new server or new key). The device key is a password: type it into
the setup page, never into the code (this repository is public).

## Hardware checks

1. **Matrix:** before the first sync Sparky shows the built-in happy `^ ^`
   face. Mirrored? Set `SPARKY_FLIP_X` to 0 in `config.h`. Upside down? Set
   `SPARKY_FLIP_Y` to 1. Write down which values are right - the Studio's
   `sparky_faces.h` download uses the same two settings.
2. **Setup:** first boot opens the hotspot; after setup the serial monitor
   prints `Wi-Fi OK, server http://...`. Press reset - it reconnects
   **without** the hotspot. Hold the button + reset - the hotspot opens with
   the saved values filled in.
3. **Sync:** the monitor prints `[pack] installed <version>`; the Studio's
   "Your Sparkys" table shows the device as "Up to date"; the idle face is
   the one mapped to "idle".
4. **Live preview:** draw a face in the Studio, press **Send to Sparky
   now** - it appears within 1-2 s and goes back to idle after 10 s.
5. **Update:** save a face change in the Studio - Sparky shows it within a
   few seconds (the server nudges it).
6. **Voice:** make a "startup" line in the Studio, press reset - Sparky says
   it. Too high and fast, or slow and deep = sample-rate problem. No hiss
   between clips (the amplifier is muted).
7. **Button:** make a "button_release" line - it plays as soon as the
   button is let go, even while Sparky is waiting on the server.
8. **Power cut:** pull the power while a voice line is downloading. After
   power-up Sparky still shows its previous faces, and the next sync
   finishes the job.
9. **Server down:** stop the server for a minute - Sparky keeps its faces
   and voice lines and picks up again when the server is back.
10. **Voice question (the main one):** hold the button, ask "Why do we have
    day and night?", let go. Expected: listening face while held, the
    "button_release" line plays straight away, then the answer is spoken
    sentence by sentence with the talking face. The serial monitor shows
    `[ask] heard: "..."` - if the words are wrong, the mic is too quiet or
    too loud: change `MIC_SHIFT` in `config.h` (13 = twice as loud).
    No Wi-Fi or server: the "wifi_error" / "server_error" line plays.

## Files

| File | Does |
|---|---|
| `sparky.ino` | Start-up and the main loop (button, moods, live preview) |
| `config.h` | Pins (report pin map), timings, flip settings |
| `settings.*` | Wi-Fi setup page, server address + device key in flash |
| `pack_sync.*` | Downloads the personality pack into LittleFS, safely |
| `faces.*` | Faces and mood mapping from the pack, drawn on the MAX7219 matrix |
| `voice.*` | Plays voice lines through the MAX98357A amplifier |
| `network_task.*` | Background sync + "Send to Sparky now", so the button never waits |
| `ask.*` | Push to talk: record, send the question, play the answer as it streams in |
| `mic.*` | Records the INMP441 microphone into flash |

`scripts/fake_sparky.py` does exactly what `pack_sync.cpp` does, in Python -
handy for testing the server side without hardware.
