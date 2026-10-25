// Sparky firmware - push-to-talk voice questions, plus faces, voice lines and live preview
// from Sparky Studio over Wi-Fi. See README.md.
#include <Arduino.h>
#include <LittleFS.h>
#include <WiFi.h>
#include "ask.h"
#include "config.h"
#include "faces.h"
#include "mic.h"
#include "network_task.h"
#include "settings.h"
#include "voice.h"

SET_LOOP_TASK_STACK_SIZE(16 * 1024);                        // the question/answer HTTP call runs in loop()
static uint32_t previewUntil = 0;

static bool buttonHeld() { return digitalRead(PIN_BUTTON) == LOW; }

void setup() {
  Serial.begin(115200);
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  if (!LittleFS.begin(true)) Serial.println("LittleFS failed");
  facesBegin();
  voiceBegin();
  micBegin();
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
    previewUntil = 0;
    AskResult result = askQuestion(buttonHeld);              // listen -> think -> talk
    uint8_t mood;
    if (result == ASK_NO_WIFI || result == ASK_SERVER_ERROR) {
      if (!voicePlay(result == ASK_NO_WIFI ? "wifi_error" : "server_error", &mood)) facesShowMood(MOOD_ERROR);
      delay(1500);
    }
    while (buttonHeld()) delay(10);                          // still held after an 8 s question
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
