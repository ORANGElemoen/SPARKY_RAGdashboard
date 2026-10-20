#include "faces.h"
#include "config.h"
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <MD_MAX72xx.h>

const char* const MOOD_NAMES[MOOD_COUNT] = {"idle", "listening", "thinking", "talking", "happy", "error"};

static MD_MAX72XX mx(MD_MAX72XX::FC16_HW, PIN_MATRIX_CS, MATRIX_DEVICES);
static uint32_t moodFaces[MOOD_COUNT][8];

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
  for (uint8_t m = 0; m < MOOD_COUNT; m++)
    memcpy(moodFaces[m], m == MOOD_ERROR ? FALLBACK_ERROR : FALLBACK_HAPPY, sizeof(moodFaces[m]));
}

bool facesLoad() {
  if (!LittleFS.exists("/pack/manifest.json")) { useFallback(); return false; }
  File f = LittleFS.open("/pack/manifest.json", "r");
  JsonDocument doc;
  DeserializationError err = deserializeJson(doc, f);
  f.close();
  if (err) { useFallback(); return false; }
  for (uint8_t m = 0; m < MOOD_COUNT; m++) {
    const char* faceName = doc["moods"][MOOD_NAMES[m]] | "";
    JsonArray rows = doc["faces"][faceName];
    if (rows.size() != 8) { useFallback(); return false; }
    for (uint8_t r = 0; r < 8; r++) {
      const char* row = rows[r] | "";
      if (strlen(row) != 32) { useFallback(); return false; }
      moodFaces[m][r] = rowBits(row);
    }
  }
  return true;
}

void facesBegin() {
  mx.begin();
  mx.control(MD_MAX72XX::INTENSITY, 3);      // low brightness keeps current (and USB brownouts) down
  facesLoad();
  facesShowMood(MOOD_IDLE);
}

void facesShowMood(uint8_t mood) { if (mood < MOOD_COUNT) drawBits(moodFaces[mood]); }

void facesShowRows(const char* const rows[8]) {
  uint32_t face[8];
  for (uint8_t r = 0; r < 8; r++) face[r] = strlen(rows[r]) == 32 ? rowBits(rows[r]) : 0;
  drawBits(face);
}
