// Sparky firmware - push-to-talk voice questions, plus faces, voice lines and live preview
// from Sparky Studio over Wi-Fi. See README.md.
#include <Arduino.h>
#include <LittleFS.h>
#include <WiFi.h>
#include <driver/gpio.h>
#include <driver/rtc_io.h>
#include <esp_sleep.h>
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
  if (esp_sleep_get_wakeup_cause() == ESP_SLEEP_WAKEUP_EXT0) {
    gpio_deep_sleep_hold_dis();
    gpio_hold_dis((gpio_num_t)PIN_AMP_SD);
    gpio_hold_dis((gpio_num_t)PIN_LED);
    rtc_gpio_deinit((gpio_num_t)PIN_BUTTON);
    pinMode(PIN_BUTTON, INPUT_PULLUP);
    Serial.println("[power] woken by the button");
    while (buttonHeld()) delay(10);                          // the wake press isn't "hold to open setup"
  }
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  if (!LittleFS.begin(true)) Serial.println("LittleFS failed");
  facesBegin();
  voiceBegin();
  micBegin();
  uint8_t mood;
  facesShowMood(MOOD_STARTUP);                               // e.g. the SPARKY face
  voicePlay("startup", &mood);                               // "Sparky here!" (shows its own mood's face)
  delay(1200);
  settingsBegin();                                           // joins the Wi-Fi (says so if it can't)
  Serial.printf("Wi-Fi %s, server %s, flash free %u bytes\n", WiFi.isConnected() ? "OK" : "FAILED",
                settingsServerUrl().c_str(), (unsigned)(LittleFS.totalBytes() - LittleFS.usedBytes()));
  if (WiFi.isConnected()) {
    facesShowMood(MOOD_WIFI_CONNECTED);
    if (!voicePlay("wifi_connected", &mood)) voiceChirp(500, 1000, 200);   // "Wi-Fi connected!"
    delay(1200);
    facesShowMood(MOOD_IDLE);
  } else {
    facesShowMood(MOOD_WIFI_ERROR);
    if (!voicePlay("wifi_error", &mood)) voiceChirp(220, 150, 300);
  }
  networkBegin();
}

// Quick presses too short to be questions: 3 = sleep, 5 or more = setup page. A real question resets
// the count, so these can't happen by accident in normal use.
static int taps = 0;
static uint32_t lastTap = 0;

static void goToSleep() {
  Serial.println("[power] going to sleep");
  sparkyIdle = false;                                        // stops the network task's requests
  uint8_t mood;
  voicePlay("goodbye", &mood);
  facesSleep();
  while (buttonHeld()) delay(10);                            // a held button would wake Sparky straight away
  delay(100);
  WiFi.disconnect(true);
  WiFi.mode(WIFI_OFF);
  gpio_hold_en((gpio_num_t)PIN_AMP_SD);                      // amplifier stays muted, LED stays off
  gpio_hold_en((gpio_num_t)PIN_LED);
  gpio_deep_sleep_hold_en();
  rtc_gpio_pullup_en((gpio_num_t)PIN_BUTTON);
  rtc_gpio_pulldown_dis((gpio_num_t)PIN_BUTTON);
  esp_sleep_enable_ext0_wakeup((gpio_num_t)PIN_BUTTON, 0);   // the button pulls the pin low
  esp_deep_sleep_start();
}

static void actOnTaps() {
  if (!taps || millis() - lastTap < TAPS_FINISHED_MS) return;
  int count = taps;
  taps = 0;
  if (count >= SETUP_TAPS) {
    Serial.println("[wifi] quick presses: restarting into setup");
    voiceChirp(700, 400, 300);
    settingsOpenSetupAndRestart();
  } else if (count == SLEEP_TAPS) {
    goToSleep();
  }
}

// Shows what the network task reports, so a child knows why Sparky can't answer.
static void showWifiState() {
  static WifiState shown = WIFI_STATE_OK;
  WifiState now = sparkyWifi;
  if (now == shown) return;
  uint8_t mood;
  if (now == WIFI_STATE_LOOKING) {
    facesShowMood(MOOD_WIFI_SETUP);
  } else if (now == WIFI_STATE_LOST) {
    facesShowMood(MOOD_WIFI_ERROR);
    if (!voicePlay("wifi_error", &mood)) voiceChirp(220, 150, 300);
    facesShowMood(MOOD_WIFI_ERROR);
  } else {
    facesShowMood(MOOD_WIFI_CONNECTED);
    if (!voicePlay("wifi_connected", &mood)) voiceChirp(500, 1000, 200);
    delay(1200);
    facesShowMood(MOOD_IDLE);
  }
  shown = now;
}

void loop() {
  if (digitalRead(PIN_BUTTON) == LOW) {
    sparkyIdle = false;                                      // no syncing while Sparky is busy
    previewUntil = 0;
    AskResult result = askQuestion(buttonHeld);              // listen -> think -> talk
    if (result == ASK_TOO_SHORT) {
      taps++;
      lastTap = millis();
    } else {
      taps = 0;
    }
    uint8_t mood;
    if (result == ASK_NO_WIFI || result == ASK_SERVER_ERROR) {
      facesShowMood(MOOD_ERROR);
      voiceChirp(220, 150, 220);                             // "bonk"
      voicePlay(result == ASK_NO_WIFI ? "wifi_error" : "server_error", &mood);
      facesShowMood(MOOD_ERROR);
      delay(1500);
    }
    if (result == ASK_OK) {                                  // a moment of joy after answering
      facesShowMood(MOOD_HAPPY);
      delay(HAPPY_AFTER_ANSWER_MS);
    }
    while (buttonHeld()) delay(10);                          // still held after an 8 s question
    facesShowMood(MOOD_IDLE);
    previewUntil = 0;
    sparkyIdle = true;
    return;
  }

  actOnTaps();
  showWifiState();

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
