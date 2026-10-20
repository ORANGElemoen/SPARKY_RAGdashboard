// Sparky firmware - faces, voice lines and live preview from Sparky Studio over Wi-Fi.
// See README.md. The voice-question part (record -> /api/v1/voice/query -> play the
// answer) plugs into the marked spots; it is a separate task.
#include <Arduino.h>
#include <LittleFS.h>
#include <WiFi.h>
#include "config.h"
#include "faces.h"
#include "network_task.h"
#include "settings.h"
#include "voice.h"

static uint32_t previewUntil = 0;

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  if (!LittleFS.begin(true)) Serial.println("LittleFS failed");
  facesBegin();
  voiceBegin();
  settingsBegin();
  Serial.printf("Wi-Fi %s, server %s, flash free %u bytes\n", WiFi.isConnected() ? "OK" : "FAILED",
                settingsServerUrl().c_str(), (unsigned)(LittleFS.totalBytes() - LittleFS.usedBytes()));
  uint8_t mood;
  voicePlay(WiFi.isConnected() ? "startup" : "wifi_error", &mood);
  facesShowMood(WiFi.isConnected() ? MOOD_IDLE : MOOD_ERROR);
  networkBegin();
}

void loop() {
  if (digitalRead(PIN_BUTTON) == LOW) {
    sparkyIdle = false;                                      // no syncing while Sparky is busy
    facesShowMood(MOOD_LISTENING);
    while (digitalRead(PIN_BUTTON) == LOW) delay(10);        // (recording happens here in the voice-question task)
    uint8_t mood;
    voicePlay("button_release", &mood);                      // instant "Hmm, let me think!" while the answer is fetched
    facesShowMood(MOOD_THINKING);
    // (send the recording, play the answer with MOOD_TALKING, then fall through to idle)
    facesShowMood(MOOD_IDLE);
    previewUntil = 0;
    sparkyIdle = true;
    return;
  }

  if (packChanged) {                                         // new faces arrived - load them while idle
    packChanged = false;
    facesLoad();
    if (!previewUntil) facesShowMood(MOOD_IDLE);
  }

  char rows[8][33];
  uint16_t seconds;
  if (networkTakePreview(rows, &seconds)) {                  // "Send to Sparky now"
    const char* ptrs[8];
    for (int r = 0; r < 8; r++) ptrs[r] = rows[r];
    facesShowRows(ptrs);
    previewUntil = millis() + seconds * 1000UL;
  }
  if (previewUntil && (int32_t)(millis() - previewUntil) > 0) {
    previewUntil = 0;
    facesShowMood(MOOD_IDLE);
  }
  delay(20);
}
