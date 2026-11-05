// Runs on core 0 so a 25-second long-poll never blocks the button (loop() runs on core 1).
#include "network_task.h"
#include "config.h"
#include "pack_sync.h"
#include "settings.h"
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <WiFi.h>

volatile bool sparkyIdle = true;
volatile bool packChanged = false;
volatile WifiState sparkyWifi = WIFI_STATE_OK;
static volatile bool networkBusy = false;
static char previewRows[8][33];
static uint16_t previewSeconds = 0;
static volatile bool previewReady = false;
static portMUX_TYPE previewLock = portMUX_INITIALIZER_UNLOCKED;

bool networkTakePreview(char rows[8][33], uint16_t* seconds) {
  if (!previewReady) return false;
  portENTER_CRITICAL(&previewLock);
  memcpy(rows, previewRows, sizeof(previewRows));
  *seconds = previewSeconds;
  previewReady = false;
  portEXIT_CRITICAL(&previewLock);
  return true;
}

static void pollCommands() {
  // Over the internet, a held-open request would keep a secure connection's RAM from the next question
  int wait = settingsOnInternet() ? 0 : LONG_POLL_SECONDS;
  HTTPClient http;
  settingsHttpBegin(http, "/api/v1/device/commands?wait=" + String(wait));
  http.setTimeout((wait + 5) * 1000);
  int code = http.GET();
  String body = code == 200 ? http.getString() : String();
  http.end();
  if (code == 200) {
    JsonDocument doc;
    if (!deserializeJson(doc, body)) {
      const char* type = doc["type"] | "";
      if (strcmp(type, "sync") == 0) {
        if (packSync()) packChanged = true;
      } else if (strcmp(type, "show_face") == 0 && doc["rows"].size() == 8) {
        char rows[8][33];                          // copy outside the lock (no allocation inside a critical section)
        for (int r = 0; r < 8; r++) strlcpy(rows[r], doc["rows"][r] | "", 33);
        uint16_t seconds = doc["seconds"] | 10;
        portENTER_CRITICAL(&previewLock);
        memcpy(previewRows, rows, sizeof(rows));
        previewSeconds = seconds;
        previewReady = true;
        portEXIT_CRITICAL(&previewLock);
      }
    }
  } else if (code != 204) {
    Serial.printf("[net] commands: %d\n", code);
    settingsChooseServer();                        // maybe the other address works
    vTaskDelay(pdMS_TO_TICKS(5000));               // server unreachable or key revoked - back off
  }
}

void networkReportStatus(float answerSeconds, int stalls, uint32_t stallMs, int32_t latencyMs, int complete) {
  if (!WiFi.isConnected()) return;
  JsonDocument doc;
  doc["rssi"] = WiFi.RSSI();
  doc["uptime_s"] = millis() / 1000;
  if (stalls >= 0) {
    doc["answer_audio_s"] = answerSeconds;
    doc["answer_stalls"] = stalls;
    doc["answer_stall_ms"] = stallMs;
  }
  if (latencyMs >= 0) doc["answer_latency_ms"] = latencyMs;
  if (complete >= 0) doc["answer_complete"] = complete == 1;
  String body;
  serializeJson(doc, body);
  HTTPClient http;
  settingsHttpBegin(http, "/api/v1/device/status");
  http.addHeader("Content-Type", "application/json");
  http.setTimeout(5000);
  http.POST(body);
  http.end();
}

// Wi-Fi dropped: a short blip reconnects by itself, then look for any remembered network.
static void watchWifi() {
  static uint32_t droppedAt = 0;
  if (WiFi.isConnected()) {
    droppedAt = 0;
    sparkyWifi = WIFI_STATE_OK;
    return;
  }
  if (!droppedAt) droppedAt = millis();
  if (!sparkyIdle || millis() - droppedAt < WIFI_GRACE_MS) return;
  if (sparkyWifi == WIFI_STATE_OK) sparkyWifi = WIFI_STATE_LOOKING;
  if (settingsRejoinWifi()) return;                // the check above clears the state next time round
  if (millis() - droppedAt > WIFI_GIVE_UP_MS) sparkyWifi = WIFI_STATE_LOST;
}

static void networkTask(void*) {
  uint32_t lastSync = 0, lastStatus = 0;
  bool firstSync = true;
  for (;;) {
    watchWifi();
    if (WiFi.isConnected() && sparkyIdle) {
      networkBusy = true;
      if (settingsOnInternet()) settingsChooseServer();   // back to the hotspot as soon as it's reachable
      if (firstSync || millis() - lastSync > SYNC_EVERY_MS) {
        if (packSync()) packChanged = true;
        lastSync = millis();
        firstSync = false;
      }
      if (!lastStatus || millis() - lastStatus > STATUS_EVERY_MS) {
        networkReportStatus();
        lastStatus = millis();
      }
      pollCommands();
      networkBusy = false;
      if (settingsOnInternet()) {                  // the pause the server's long-poll gives on the hotspot
        for (int i = 0; i < LONG_POLL_SECONDS && sparkyIdle; i++) vTaskDelay(pdMS_TO_TICKS(1000));
      }
    } else {
      vTaskDelay(pdMS_TO_TICKS(1000));
    }
  }
}

void networkWaitUntilQuiet() {
  uint32_t started = millis();
  while (settingsOnInternet() && networkBusy && millis() - started < 8000) delay(20);
}

void networkBegin() { xTaskCreatePinnedToCore(networkTask, "network", 12288, nullptr, 1, nullptr, 0); }
