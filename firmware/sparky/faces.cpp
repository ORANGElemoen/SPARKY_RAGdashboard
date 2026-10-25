// Faces + accent LED, animated by one background task (~30 fps) so Sparky keeps moving even
// while the main loop waits on the server. Everyone else just says which mood to show.
//
// Animations are transforms of whatever face is mapped to the mood (blink, glance, drift,
// bob, shake), so they work with any face designed in Sparky Studio.
#include "faces.h"
#include "config.h"
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <MD_MAX72xx.h>

const char* const MOOD_NAMES[MOOD_COUNT] = {"idle", "listening", "thinking", "talking", "happy", "error", "startup",
                                            "wifi_connected", "wifi_setup", "wifi_error"};

static MD_MAX72XX mx(MD_MAX72XX::FC16_HW, PIN_MATRIX_CS, MATRIX_DEVICES);
static uint32_t moodFaces[MOOD_COUNT][8];
constexpr int MAX_EXTRAS = 32;
static uint32_t extras[MAX_EXTRAS][8];                     // library faces no mood uses ("surprise faces")
static volatile int extraCount = 0;
static portMUX_TYPE lock = portMUX_INITIALIZER_UNLOCKED;   // guards moodFaces / extras / preview

static volatile uint8_t mood = MOOD_IDLE;
static volatile uint32_t moodSince = 0;
static volatile uint8_t level = 0;                         // voice loudness 0-255 while talking
static uint32_t preview[8];
static volatile bool previewOn = false;

// Built-in faces so Sparky has a face before its first sync (Studio's "Happy ^ ^" and "Error X X").
static const uint32_t FALLBACK_HAPPY[8] = {0x00000000, 0x03C003C0, 0x07E007E0, 0x0C300C30,
                                           0x0C300C30, 0x18181818, 0x18181818, 0x00000000};
static const uint32_t FALLBACK_ERROR[8] = {0x0C300C30, 0x06600660, 0x03C003C0, 0x01800180,
                                           0x03C003C0, 0x06600660, 0x0C300C30, 0x00000000};

static uint32_t rowBits(const char* row) {   // bit 31 = leftmost LED, like studio_service.row_bits
  uint32_t v = 0;
  for (int c = 0; c < 32; c++) v = (v << 1) | (row[c] == '#' ? 1u : 0u);
  return v;
}

static void drawBits(const uint32_t face[8]) {
  mx.control(MD_MAX72XX::UPDATE, MD_MAX72XX::OFF);
  for (uint8_t r = 0; r < 8; r++)
    for (uint8_t c = 0; c < 32; c++)
      mx.setPoint(SPARKY_FLIP_Y ? 7 - r : r, SPARKY_FLIP_X ? 31 - c : c, (face[r] >> (31 - c)) & 1u);
  mx.control(MD_MAX72XX::UPDATE, MD_MAX72XX::ON);
}

static void useFallback() {
  portENTER_CRITICAL(&lock);
  for (uint8_t m = 0; m < MOOD_COUNT; m++)
    memcpy(moodFaces[m], m == MOOD_ERROR ? FALLBACK_ERROR : FALLBACK_HAPPY, sizeof(moodFaces[m]));
  extraCount = 0;
  portEXIT_CRITICAL(&lock);
}

bool facesLoad() {
  if (!LittleFS.exists("/pack/manifest.json")) { useFallback(); return false; }
  File f = LittleFS.open("/pack/manifest.json", "r");
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, f);
  f.close();
  if (err) { useFallback(); return false; }
  uint32_t loaded[MOOD_COUNT][8];
  for (uint8_t m = 0; m < MOOD_COUNT; m++) {
    const char* faceName = doc["moods"][MOOD_NAMES[m]] | "";
    JsonArray rows = doc["faces"][faceName];
    if (rows.size() != 8 && m >= MOOD_STARTUP) rows = doc["faces"][doc["moods"]["happy"] | ""];   // older server
    if (rows.size() != 8) { useFallback(); return false; }
    for (uint8_t r = 0; r < 8; r++) {
      const char* row = rows[r] | "";
      if (strlen(row) != 32) { useFallback(); return false; }
      loaded[m][r] = rowBits(row);
    }
  }
  // every other valid face in the library becomes a surprise face
  static uint32_t more[MAX_EXTRAS][8];
  int n = 0;
  for (JsonPair kv : doc["faces"].as<JsonObject>()) {
    bool used = false;
    for (uint8_t m = 0; m < MOOD_COUNT; m++) used |= strcmp(doc["moods"][MOOD_NAMES[m]] | "", kv.key().c_str()) == 0;
    JsonArray rows = kv.value();
    if (used || rows.size() != 8 || n == MAX_EXTRAS) continue;
    bool ok = true;
    for (uint8_t r = 0; r < 8; r++) {
      const char* row = rows[r] | "";
      ok &= strlen(row) == 32;
      if (ok) more[n][r] = rowBits(row);
    }
    if (ok) n++;
  }
  portENTER_CRITICAL(&lock);
  memcpy(moodFaces, loaded, sizeof(moodFaces));
  memcpy(extras, more, sizeof(extras));
  extraCount = n;
  portEXIT_CRITICAL(&lock);
  return true;
}

void facesShowMood(uint8_t m) {
  if (m >= MOOD_COUNT) return;
  previewOn = false;
  if (m != mood) moodSince = millis();
  mood = m;
}

void facesShowRows(const char* const rows[8]) {     // "Send to Sparky now": shown still, no animation
  uint32_t face[8];
  for (uint8_t r = 0; r < 8; r++) face[r] = strlen(rows[r]) == 32 ? rowBits(rows[r]) : 0;
  portENTER_CRITICAL(&lock);
  memcpy(preview, face, sizeof(preview));
  portEXIT_CRITICAL(&lock);
  previewOn = true;
}

void facesSetLevel(uint8_t loudness) { if (loudness > level) level = loudness; }

// ---------------------------------------------------------------- frame transforms
static void shift(uint32_t f[8], int dx, int dy) {  // only moves if nothing falls off the edge
  uint32_t any = 0;
  for (int r = 0; r < 8; r++) any |= f[r];
  if ((dx < 0 && (any & 0x80000000u)) || (dx > 0 && (any & 1u))) dx = 0;
  if ((dy < 0 && f[0]) || (dy > 0 && f[7])) dy = 0;
  uint32_t out[8] = {};
  for (int r = 0; r < 8; r++) {
    int rr = r + dy;
    if (rr < 0 || rr > 7) continue;
    out[rr] = dx > 0 ? f[r] >> dx : dx < 0 ? f[r] << -dx : f[r];
  }
  memcpy(f, out, sizeof(out));
}

static void blink(uint32_t f[8], int stage) {        // 1 = half closed, 2 = closed
  int top = -1, bottom = -1;
  uint32_t all = 0;
  for (int r = 0; r < 8; r++) if (f[r]) { if (top < 0) top = r; bottom = r; all |= f[r]; }
  if (top < 0) return;
  int mid = (top + bottom) / 2;
  if (stage == 2) {                                   // a line where the eyes were
    memset(f, 0, 8 * sizeof(uint32_t));
    f[mid] = all;
    return;
  }
  int cut = max(1, (bottom - top + 1) / 4);           // squash: drop the top and bottom quarter
  for (int r = 0; r < 8; r++) if (r < top + cut || r > bottom - cut) f[r] = 0;
}

static uint8_t ease(uint32_t t, uint32_t period) {    // 0..255 triangle wave, smooth enough for a LED
  uint32_t p = t % period;
  uint32_t v = p < period / 2 ? p * 510 / period : (period - p) * 510 / period;
  return v * v / 255;                                 // squared: looks more like breathing
}

static void setLed(uint8_t brightness) { ledcWrite(PIN_LED, 255 - brightness); }   // wired 3V3 -> LED -> GPIO: LOW = on

// ---------------------------------------------------------------- animator task
static void animator(void*) {
  uint32_t nextBlink = millis() + 3000, nextGlance = millis() + 9000, glanceUntil = 0;
  uint32_t nextSurprise = millis() + SURPRISE_FIRST_MS, surpriseUntil = 0;
  int glanceDx = 0, surprise = 0;
  uint32_t last[8] = {1};                             // forces the first draw
  uint8_t talk = 0;
  for (;;) {
    uint32_t now = millis(), f[8];
    uint8_t m = mood;
    uint32_t inMood = now - moodSince;
    portENTER_CRITICAL(&lock);
    memcpy(f, previewOn ? preview : moodFaces[m], sizeof(f));
    portEXIT_CRITICAL(&lock);
    talk = max<int>(level, max(0, talk - 24));                // fast attack, smooth fall
    level = 0;
    uint8_t led = 0;
    bool surprising = false;

    if (!previewOn) {
      switch (m) {
        case MOOD_IDLE:
          led = 8 + ease(now, 4000) * 100 / 255;      // slow breathing
          if (now > nextSurprise) {                   // now and then: a face from the library
            if (extraCount) { surprise = esp_random() % extraCount; surpriseUntil = now + SURPRISE_SHOW_MS; }
            nextSurprise = now + SURPRISE_MIN_MS + esp_random() % (SURPRISE_MAX_MS - SURPRISE_MIN_MS);
          }
          if (now < surpriseUntil && surprise < extraCount) {
            portENTER_CRITICAL(&lock);
            memcpy(f, extras[surprise], sizeof(f));
            portEXIT_CRITICAL(&lock);
            led = 255;
            surprising = true;
            break;
          }
          if (now > nextGlance) {                     // look left or right for a moment
            glanceDx = (esp_random() & 1) ? 2 : -2;
            glanceUntil = now + 700 + esp_random() % 800;
            nextGlance = now + 8000 + esp_random() % 8000;
          }
          if (now < glanceUntil) shift(f, glanceDx, 0);
          break;
        case MOOD_LISTENING:
          led = 255;
          if (inMood < 160) shift(f, 0, -1);          // little "I'm awake" hop
          break;
        case MOOD_THINKING: {
          led = (now / 220) % 2 ? 255 : 0;            // blinking
          static const int8_t path[4][2] = {{0, -1}, {-1, -1}, {0, -1}, {1, -1}};
          const int8_t* p = path[(now / 450) % 4];    // eyes drift around up top
          shift(f, p[0], p[1]);
          break;
        }
        case MOOD_TALKING:
          led = 180 + talk / 4;
          if (talk > 70) shift(f, 0, 1);              // bob with the voice, like a jaw
          break;
        case MOOD_HAPPY:
          led = 255;
          if ((now / 300) % 3 == 0) shift(f, 0, -1);  // bouncy
          break;
        case MOOD_STARTUP:
        case MOOD_WIFI_CONNECTED:
          led = 255;                                  // shown still: words and symbols
          break;
        case MOOD_WIFI_SETUP:
          led = (now / 600) % 2 ? 255 : 0;            // slow blink: "come and help me"
          break;
        case MOOD_WIFI_ERROR:
          led = (now / 120) % 2 ? 255 : 0;            // fast blink
          break;
        case MOOD_ERROR:
          led = (now / 70) % 2 ? 255 : 0;             // fast blink
          if (inMood < 700) shift(f, (now / 80) % 2 ? 1 : -1, 0);   // head shake
          break;
      }
      if (!surprising && (m == MOOD_IDLE || m == MOOD_LISTENING || m == MOOD_HAPPY || m == MOOD_TALKING)) {
        if (now > nextBlink + 180) nextBlink = now + 2500 + esp_random() % 3500;
        else if (now > nextBlink) blink(f, now - nextBlink < 60 || now - nextBlink > 120 ? 1 : 2);
      }
    }
    setLed(led);
    if (memcmp(f, last, sizeof(f))) {                 // only talk to the matrix when the frame changed
      drawBits(f);
      memcpy(last, f, sizeof(f));
    }
    vTaskDelay(pdMS_TO_TICKS(33));
  }
}

void facesBegin() {
  mx.begin();
  mx.control(MD_MAX72XX::INTENSITY, MATRIX_BRIGHTNESS);
  ledcAttach(PIN_LED, 5000, 8);
  setLed(0);
  facesLoad();
  moodSince = millis();
  xTaskCreatePinnedToCore(animator, "faces", 4096, nullptr, 2, nullptr, 1);
}
