// Plays 16 kHz 16-bit mono WAVs from LittleFS through the MAX98357A on I2S port 1
// (port 0 stays free for the INMP441 microphone). Each mono sample goes out on both
// stereo slots, so the amp plays it whichever channel its SD pin level selects.
// Legacy I2S driver: still in ESP32 Arduino core 3.x (deprecation warning only);
// the microphone code must use the same driver - the old and new ones can't mix.
#include "voice.h"
#include "config.h"
#include "faces.h"
#include <ArduinoJson.h>
#include <LittleFS.h>
#include <driver/i2s.h>

void voiceBegin() {
  pinMode(PIN_AMP_SD, OUTPUT);
  digitalWrite(PIN_AMP_SD, LOW);                 // amplifier muted until a clip plays
  i2s_config_t cfg = {};
  cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_TX);
  cfg.sample_rate = 16000;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_16BIT;
  cfg.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;
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

// A random voice line with this trigger from the pack: its file path and its mood.
static bool pickLine(const char* trigger, String& path, uint8_t& mood) {
  if (!LittleFS.exists("/pack/manifest.json")) return false;
  File mf = LittleFS.open("/pack/manifest.json", "r");
  JsonDocument doc;
  bool bad = deserializeJson(doc, mf) != DeserializationError::Ok;
  mf.close();
  if (bad) return false;

  JsonObject pick;
  int seen = 0;
  for (JsonObject v : doc["voice_lines"].as<JsonArray>())
    if (strcmp(v["trigger"] | "", trigger) == 0 && random(++seen) == 0) pick = v;
  if (pick.isNull()) return false;
  mood = MOOD_IDLE;
  for (uint8_t m = 0; m < MOOD_COUNT; m++) if (strcmp(pick["mood"] | "", MOOD_NAMES[m]) == 0) mood = m;
  path = "/pack/v/" + pick["id"].as<String>() + ".wav";
  return LittleFS.exists(path);
}

String voiceLinePath(const char* trigger) {
  String path;
  uint8_t mood;
  return pickLine(trigger, path, mood) ? path : String();
}

bool voicePlay(const char* trigger, uint8_t* moodOut) {
  String path;
  uint8_t mood;
  if (!pickLine(trigger, path, mood)) return false;
  if (moodOut) {
    *moodOut = mood;
    facesShowMood(mood);                         // face first, so it shows while Sparky talks
  }
  File f = LittleFS.open(path, "r");
  f.seek(44);                                    // skip the 44-byte WAV header (server always writes this layout)
  int16_t mono[256];
  size_t n;
  voiceStreamBegin(16000);
  while ((n = f.read((uint8_t*)mono, sizeof(mono)) / 2) > 0) voiceStreamWrite(mono, n);
  voiceStreamEnd();
  f.close();
  return true;
}

void voiceStreamBegin(uint32_t sampleRate) {
  i2s_set_sample_rates(I2S_NUM_1, sampleRate);
  digitalWrite(PIN_AMP_SD, HIGH);
}

void voiceStreamWrite(const int16_t* mono, size_t samples) {
  int16_t stereo[512];
  size_t written;
  for (size_t i = 0; i < samples; i += 256) {
    size_t n = min((size_t)256, samples - i);
    for (size_t j = 0; j < n; j++) stereo[2 * j] = stereo[2 * j + 1] = mono[i + j];
    i2s_write(I2S_NUM_1, stereo, n * 4, &written, portMAX_DELAY);
  }
}

void voiceStreamEnd() {
  i2s_zero_dma_buffer(I2S_NUM_1);
  delay(30);                                     // let the last DMA buffer drain before muting
  digitalWrite(PIN_AMP_SD, LOW);
  i2s_set_sample_rates(I2S_NUM_1, 16000);
}
