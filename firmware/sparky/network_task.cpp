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
  HTTPClient http;
  http.begin(settingsServerUrl() + "/api/v1/device/commands?wait=" + String(LONG_POLL_SECONDS));
  http.addHeader("X-Device-Key", settingsDeviceKey());
  http.setTimeout((LONG_POLL_SECONDS + 5) * 1000);
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
    vTaskDelay(pdMS_TO_TICKS(5000));               // server unreachable or key revoked - back off
  }
}

static void networkTask(void*) {
  uint32_t lastSync = 0;
  bool firstSync = true;
  for (;;) {
    if (WiFi.isConnected() && sparkyIdle) {
      if (firstSync || millis() - lastSync > SYNC_EVERY_MS) {
        if (packSync()) packChanged = true;
        lastSync = millis();
        firstSync = false;
      }
      pollCommands();
    } else {
      vTaskDelay(pdMS_TO_TICKS(1000));
    }
  }
}

void networkBegin() { xTaskCreatePinnedToCore(networkTask, "network", 12288, nullptr, 1, nullptr, 0); }
