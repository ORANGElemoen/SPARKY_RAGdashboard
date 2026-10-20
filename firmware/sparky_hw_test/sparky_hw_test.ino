// Sparky hardware test - checks each part of the circuit on its own, no Wi-Fi or server needed.
// Goes with docs/sparky_wiring_guide.pdf (wiring + test procedure). Open the serial monitor at
// 115200 baud and type a number:
//
//   1 face display (M-05)      4 record + play back (M-01/M-04)   7 touch pad (M-20)
//   2 speaker tone (M-04)      5 mic sample rate (M-02)           8 accent LED (M-20)
//   3 mic level meter (M-01)   6 button counter (M-07)            9 power stress (M-08)
//   q stops a running test.
//
// Pins must match firmware/sparky/config.h (report pin map).
#include <Arduino.h>
#include <MD_MAX72xx.h>
#include <driver/i2s.h>
#include <esp_system.h>

constexpr int PIN_MIC_SCK = 32, PIN_MIC_WS = 25, PIN_MIC_SD = 33;
constexpr int PIN_AMP_BCLK = 27, PIN_AMP_LRC = 26, PIN_AMP_DIN = 22, PIN_AMP_SD = 21;
constexpr int PIN_MATRIX_CS = 5;                 // CLK 18 / DIN 23 = default VSPI pins
constexpr int PIN_BUTTON = 14, PIN_LED = 4, PIN_TOUCH = 13;
constexpr int RATE = 16000;
#define SPARKY_FLIP_X 1                          // same knobs as firmware/sparky/config.h
#define SPARKY_FLIP_Y 0

MD_MAX72XX mx(MD_MAX72XX::FC16_HW, PIN_MATRIX_CS, 4);

// The six mood faces from Sparky Studio's defaults (bit 31 = leftmost LED).
const char* const MOODS[6] = {"idle", "listening", "thinking", "talking", "happy", "error"};
const uint32_t FACES[6][8] = {
  {0x00000000, 0x00000000, 0x00000000, 0x00000000, 0x0FF00FF0, 0x07E007E0, 0x00000000, 0x00000000},
  {0x00000000, 0x03C003C0, 0x07E007E0, 0x07E007E0, 0x07E007E0, 0x07E007E0, 0x03C003C0, 0x00000000},
  {0x00600060, 0x00F000F0, 0x00F000F0, 0x00600060, 0x00000000, 0x00000000, 0x00000000, 0x00000000},
  {0x00000000, 0x03C003C0, 0x07E007E0, 0x0C300C30, 0x0C300C30, 0x18181818, 0x18181818, 0x00000000},
  {0x00000000, 0x03C003C0, 0x07E007E0, 0x0C300C30, 0x0C300C30, 0x18181818, 0x18181818, 0x00000000},
  {0x0C300C30, 0x06600660, 0x03C003C0, 0x01800180, 0x03C003C0, 0x06600660, 0x0C300C30, 0x00000000},
};

// ------------------------------------------------------------------ helpers
bool stopRequested() {
  while (Serial.available()) if (tolower(Serial.read()) == 'q') return true;
  return false;
}

void setPixel(int r, int c, bool on) {           // same mapping as firmware/sparky/faces.cpp
  mx.setPoint(SPARKY_FLIP_Y ? 7 - r : r, SPARKY_FLIP_X ? 31 - c : c, on);
}

void drawFace(const uint32_t face[8]) {
  mx.control(MD_MAX72XX::UPDATE, MD_MAX72XX::OFF);
  for (int r = 0; r < 8; r++)
    for (int c = 0; c < 32; c++) setPixel(r, c, (face[r] >> (31 - c)) & 1u);
  mx.control(MD_MAX72XX::UPDATE, MD_MAX72XX::ON);
}

void ledSet(bool on) { digitalWrite(PIN_LED, on ? LOW : HIGH); }   // LED is wired from 3V3 into GPIO 4: LOW = on

void speakerBegin() {
  i2s_config_t cfg = {};
  cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX);
  cfg.sample_rate = RATE;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  cfg.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;   // stereo: same sample on both slots, works for any SD mode
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.dma_desc_num = 8;
  cfg.dma_frame_num = 256;
  cfg.tx_desc_auto_clear = true;
  i2s_pin_config_t pins = {};
  pins.mck_io_num = I2S_PIN_NO_CHANGE;
  pins.bck_io_num = PIN_AMP_BCLK;
  pins.ws_io_num = PIN_AMP_LRC;
  pins.data_out_num = PIN_AMP_DIN;
  pins.data_in_num = I2S_PIN_NO_CHANGE;
  i2s_driver_install(I2S_NUM_1, &cfg, 0, nullptr);
  i2s_set_pin(I2S_NUM_1, &pins);
}

void micBegin() {
  i2s_config_t cfg = {};
  cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  cfg.sample_rate = RATE;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;   // INMP441 sends 24 bits in a 32-bit slot
  cfg.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;   // read both slots and use whichever carries the mic
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.dma_desc_num = 8;
  cfg.dma_frame_num = 256;
  i2s_pin_config_t pins = {};
  pins.mck_io_num = I2S_PIN_NO_CHANGE;
  pins.bck_io_num = PIN_MIC_SCK;
  pins.ws_io_num = PIN_MIC_WS;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num = PIN_MIC_SD;
  i2s_driver_install(I2S_NUM_0, &cfg, 0, nullptr);
  i2s_set_pin(I2S_NUM_0, &pins);
}

void playSamples(const int16_t* mono, size_t n) {   // mono 16 kHz -> both I2S slots
  int16_t frame[512];
  size_t written;
  digitalWrite(PIN_AMP_SD, HIGH);
  for (size_t i = 0; i < n; i += 256) {
    size_t k = min((size_t)256, n - i);
    for (size_t j = 0; j < k; j++) frame[2 * j] = frame[2 * j + 1] = mono[i + j];
    i2s_write(I2S_NUM_1, frame, k * 4, &written, portMAX_DELAY);
  }
  i2s_zero_dma_buffer(I2S_NUM_1);
  delay(30);
  digitalWrite(PIN_AMP_SD, LOW);
}

void beep(float hz, float seconds, int16_t amplitude) {
  static int16_t buf[256];
  size_t total = seconds * RATE;
  for (size_t done = 0; done < total; done += 256) {
    for (int i = 0; i < 256; i++) buf[i] = amplitude * sinf(2 * PI * hz * (done + i) / RATE);
    playSamples(buf, 256);
  }
}

// Reads 256 stereo frames; returns how many it got and the peak of each slot (as 16-bit levels).
size_t micRead(int32_t* frames, int32_t& peakL, int32_t& peakR) {
  size_t got = 0;
  i2s_read(I2S_NUM_0, frames, 256 * 8, &got, portMAX_DELAY);
  got /= 8;
  peakL = peakR = 0;
  for (size_t i = 0; i < got; i++) {
    peakL = max(peakL, abs(frames[2 * i] >> 16));
    peakR = max(peakR, abs(frames[2 * i + 1] >> 16));
  }
  return got;
}

void bar(const char* label, int32_t level) {
  int n = constrain(level / 512, 0, 40);
  Serial.printf("%s %6ld |", label, (long)level);
  for (int i = 0; i < 40; i++) Serial.print(i < n ? '#' : ' ');
  Serial.print("| ");
}

// ------------------------------------------------------------------ tests
void testFaces() {
  Serial.println("\n[1] Face display (M-05)");
  mx.clear();
  setPixel(0, 0, true);
  Serial.println("  ONE dot should be lit in the TOP-LEFT corner (seen from the front).");
  Serial.println("  Top-right instead? -> set SPARKY_FLIP_X 0.  Bottom-left? -> set SPARKY_FLIP_Y 1.");
  Serial.println("  (Change it in this sketch AND firmware/sparky/config.h.)  Next in 5 s...");
  for (int i = 0; i < 50 && !stopRequested(); i++) delay(100);
  for (int m = 0; m < 6; m++) {
    Serial.printf("  showing: %s\n", MOODS[m]);
    drawFace(FACES[m]);
    for (int i = 0; i < 25; i++) { if (stopRequested()) return; delay(100); }
  }
  Serial.println("  PASS if every face looked right way round and recognisable at arm's length.");
}

void testSpeaker() {
  Serial.println("\n[2] Speaker (M-04): 1 s low beep, 1 s high beep, then 1 s silence (amp muted)");
  beep(440, 1.0, 6000);
  beep(880, 1.0, 6000);
  digitalWrite(PIN_AMP_SD, LOW);
  delay(1000);
  Serial.println("  PASS if both beeps were clear and the silence had no hiss or buzz.");
}

void testMicLevel() {
  Serial.println("\n[3] Mic level meter (M-01 wiring): talk, clap, then stay quiet. q = stop");
  static int32_t frames[512];
  uint32_t until = millis() + 15000;
  while (millis() < until && !stopRequested()) {
    int32_t pl, pr;
    micRead(frames, pl, pr);
    bar("L", pl); bar("R", pr); Serial.println();
    delay(80);
  }
  Serial.println("  PASS if ONE side jumps when you talk and drops when quiet (L/R pad to GND -> usually L).");
  Serial.println("  Both stuck at 0 -> check SD/SCK/WS and 3V3. Both stuck high -> check GND.");
}

void testRecordPlay() {
  Serial.println("\n[4] Record + play back (M-01, M-04): say something after the beep (2.5 s)");
  const size_t n = RATE * 25 / 10;
  int16_t* rec = (int16_t*)malloc(n * sizeof(int16_t));
  if (!rec) { Serial.println("  not enough memory"); return; }
  static int32_t frames[512];
  beep(660, 0.15, 4000);
  int32_t pl, pr, sumL = 0, sumR = 0;
  for (int i = 0; i < 5; i++) { micRead(frames, pl, pr); sumL += pl; sumR += pr; }   // pick the slot the mic talks on
  int slot = sumR > sumL ? 1 : 0;
  size_t have = 0, clipped = 0;
  int32_t peak = 0;
  while (have < n) {
    size_t got = micRead(frames, pl, pr);
    for (size_t i = 0; i < got && have < n; i++) {
      int32_t s = frames[2 * i + slot] >> 14;     // 24-bit -> 16-bit with x4 gain
      if (abs(s) > 32767) clipped++;
      s = constrain(s, -32768, 32767);
      peak = max(peak, abs(s));
      rec[have++] = s;
    }
  }
  Serial.printf("  recorded %u samples on the %s slot, peak %ld, clipped %u\n", (unsigned)n, slot ? "R" : "L", (long)peak, (unsigned)clipped);
  delay(300);
  playSamples(rec, n);
  free(rec);
  Serial.println("  PASS if you heard yourself clearly, with no crackle or gaps. (Repeat 10x for M-01.)");
}

void testSampleRate() {
  Serial.println("\n[5] Mic sample rate (M-02): counting samples for 10 s...");
  static int32_t frames[512];
  int32_t pl, pr;
  micRead(frames, pl, pr);                        // let the bus settle
  uint32_t t0 = micros(), count = 0;
  while (micros() - t0 < 10000000UL) count += micRead(frames, pl, pr);
  float rate = count / ((micros() - t0) / 1e6f);
  Serial.printf("  %lu frames in 10 s = %.0f Hz (expected %d)\n", (unsigned long)count, rate, RATE);
  Serial.println(fabsf(rate - RATE) < RATE * 0.01f ? "  PASS (within 1%)" : "  FAIL - check the clock wires (SCK, WS)");
}

void testButton() {
  Serial.println("\n[6] Button (M-07): press it 100 times. q = stop");
  int count = 0;
  bool last = HIGH;
  uint32_t lastChange = 0;
  while (!stopRequested()) {
    bool now = digitalRead(PIN_BUTTON);
    if (now != last && millis() - lastChange > 25) {   // 25 ms debounce
      lastChange = millis();
      last = now;
      if (now == LOW) Serial.printf("  press %d\n", ++count);
    }
    if (count >= 100) break;
  }
  Serial.printf("  %d presses counted. PASS if it matches what you pressed (no doubles, none missed).\n", count);
}

void testTouch() {
  Serial.println("\n[7] Touch pad (M-20): don't touch for 2 s (calibrating)...");
  uint32_t base = 0;
  for (int i = 0; i < 40; i++) { base += touchRead(PIN_TOUCH); delay(50); }
  base /= 40;
  uint32_t threshold = base * 7 / 10;
  Serial.printf("  untouched reading %lu, touch below %lu. Now tap it 50 times. q = stop\n", (unsigned long)base, (unsigned long)threshold);
  int taps = 0;
  bool touched = false;
  while (!stopRequested() && taps < 50) {
    uint32_t v = touchRead(PIN_TOUCH);
    if (!touched && v < threshold) { touched = true; Serial.printf("  tap %d (reading %lu)\n", ++taps, (unsigned long)v); }
    if (touched && v > base * 85 / 100) touched = false;   // hysteresis
    delay(20);
  }
  Serial.printf("  %d taps counted. PASS if it matches, with none while you weren't touching.\n", taps);
}

void testLed() {
  Serial.println("\n[8] Accent LED (M-20): 3 blinks, then a slow pulse");
  for (int i = 0; i < 3; i++) { ledSet(true); delay(300); ledSet(false); delay(300); }
  ledcAttach(PIN_LED, 5000, 8);
  for (int k = 0; k < 2; k++)
    for (int d = 0; d < 512; d += 4) { int v = d < 256 ? d : 511 - d; ledcWrite(PIN_LED, 255 - v); delay(8); }  // inverted: LOW = on
  ledcDetach(PIN_LED);
  pinMode(PIN_LED, OUTPUT);
  ledSet(false);
  Serial.println("  PASS if the blink and the pulse looked distinct. Never lit -> LED the wrong way round?");
}

void testPower() {
  Serial.println("\n[9] Power stress (M-08): all LEDs on + beep, brightness 2 -> 5 -> 8. Watch for a reset.");
  for (int level : {2, 5, 8}) {
    Serial.printf("  brightness %d\n", level);
    mx.control(MD_MAX72XX::INTENSITY, level);
    for (int r = 0; r < 8; r++) for (int c = 0; c < 32; c++) setPixel(r, c, true);
    ledSet(true);
    beep(440, 2.0, 8000);
    if (stopRequested()) break;
  }
  mx.clear();
  mx.control(MD_MAX72XX::INTENSITY, 3);
  ledSet(false);
  Serial.println("  PASS if Sparky did not restart (a restart prints 'BROWNOUT' at the top).");
}

void menu() {
  Serial.println("\n=== Sparky hardware test ===");
  Serial.println(" 1 face display      4 record + play back   7 touch pad");
  Serial.println(" 2 speaker tone      5 mic sample rate      8 accent LED");
  Serial.println(" 3 mic level meter   6 button counter       9 power stress");
  Serial.print("Type a number: ");
}

void setup() {
  Serial.begin(115200);
  delay(300);
  esp_reset_reason_t why = esp_reset_reason();
  Serial.printf("\nStarted (reset reason %d)%s\n", why, why == ESP_RST_BROWNOUT ? "  *** BROWNOUT - the supply dipped ***" : "");
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  pinMode(PIN_LED, OUTPUT);
  ledSet(false);
  pinMode(PIN_AMP_SD, OUTPUT);
  digitalWrite(PIN_AMP_SD, LOW);
  mx.begin();
  mx.control(MD_MAX72XX::INTENSITY, 3);
  mx.clear();
  speakerBegin();
  micBegin();
  menu();
}

void loop() {
  if (!Serial.available()) return;
  char c = Serial.read();
  switch (c) {
    case '1': testFaces(); break;
    case '2': testSpeaker(); break;
    case '3': testMicLevel(); break;
    case '4': testRecordPlay(); break;
    case '5': testSampleRate(); break;
    case '6': testButton(); break;
    case '7': testTouch(); break;
    case '8': testLed(); break;
    case '9': testPower(); break;
    default: return;                              // ignore newlines etc.
  }
  menu();
}
