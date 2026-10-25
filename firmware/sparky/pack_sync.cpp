// Mirrors scripts/fake_sparky.py: If-None-Match -> 304, download missing voice
// lines first, then switch manifest + version, then delete leftovers, then ack.
// Wire format: docs/PROTOCOL.md, "Personality pack".
#include "pack_sync.h"
#include "config.h"
#include "settings.h"
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <vector>

static String readVersion() {
  if (!LittleFS.exists("/pack/version.txt")) return "";
  File f = LittleFS.open("/pack/version.txt", "r");
  String v = f.readString();
  f.close();
  v.trim();
  return v;
}

static size_t fileSize(const String& path) {
  if (!LittleFS.exists(path)) return 0;
  File f = LittleFS.open(path, "r");
  size_t n = f.size();
  f.close();
  return n;
}

static void begin(HTTPClient& http, const String& path) {
  http.begin(settingsServerUrl() + path);
  http.addHeader("X-Device-Key", settingsDeviceKey());
  http.setTimeout(30000);
}

static void ack(const String& version, const char* error) {
  HTTPClient http;
  begin(http, "/api/v1/device/pack/ack");
  http.addHeader("Content-Type", "application/json");
  JsonDocument doc;
  doc["pack_version"] = version.length() ? version : String("none");
  doc["free_bytes"] = LittleFS.totalBytes() - LittleFS.usedBytes();
  if (error) doc["error"] = error;
  String body;
  serializeJson(doc, body);
  http.POST(body);
  http.end();
  Serial.printf("[pack] ack %s %s\n", version.c_str(), error ? error : "ok");
}

static bool download(const String& id, size_t expected) {
  String tmp = "/pack/v/" + id + ".tmp", final = "/pack/v/" + id + ".wav";
  HTTPClient http;
  begin(http, "/api/v1/device/pack/voice/" + id + ".wav");
  if (http.GET() != 200) { http.end(); return false; }
  File out = LittleFS.open(tmp, "w");
  int written = out ? http.writeToStream(&out) : -1;
  if (out) out.close();
  http.end();
  if (written < 0 || (size_t)written != expected) { LittleFS.remove(tmp); return false; }
  LittleFS.remove(final);
  return LittleFS.rename(tmp, final);
}

bool packSync() {
  LittleFS.mkdir("/pack");
  LittleFS.mkdir("/pack/v");
  String current = readVersion();

  HTTPClient http;
  begin(http, "/api/v1/device/pack");
  if (current.length()) http.addHeader("If-None-Match", "\"" + current + "\"");
  int code = http.GET();
  if (code != 200) {                                  // 304 = up to date; else server down or 401 (revoked) - try later
    http.end();
    if (code != 304) Serial.printf("[pack] check failed: %d\n", code);
    return false;
  }
  String manifestText = http.getString();
  http.end();

  JsonDocument doc;
  if (deserializeJson(doc, manifestText)) { ack(current, "bad manifest"); return false; }
  String version = doc["pack_version"] | "";
  JsonArray lines = doc["voice_lines"].as<JsonArray>();

  // 1. what to download (missing or wrong size) - same as plan_sync()
  size_t needed = 0;
  for (JsonObject v : lines) {
    size_t want = v["bytes"].as<size_t>();
    if (fileSize("/pack/v/" + v["id"].as<String>() + ".wav") != want) needed += want;
  }
  size_t free = LittleFS.totalBytes() - LittleFS.usedBytes();
  if (needed + FLASH_MARGIN_BYTES > free) { ack(current, "not enough space"); return false; }
  for (JsonObject v : lines) {
    String id = v["id"].as<String>();
    size_t want = v["bytes"].as<size_t>();
    if (fileSize("/pack/v/" + id + ".wav") != want && !download(id, want)) { ack(current, "download failed"); return false; }
  }

  // 2. switch over: manifest first, version last
  File m = LittleFS.open("/pack/manifest.tmp", "w");
  if (!m) { ack(current, "cannot write manifest"); return false; }
  m.print(manifestText);
  m.close();
  LittleFS.remove("/pack/manifest.json");
  LittleFS.rename("/pack/manifest.tmp", "/pack/manifest.json");
  File ver = LittleFS.open("/pack/version.txt", "w");
  ver.print(version);
  ver.close();

  // 3. delete voice lines (and stray .tmp files) no longer in the pack
  std::vector<String> leftovers;
  File dir = LittleFS.open("/pack/v");
  for (File f = dir.openNextFile(); f; f = dir.openNextFile()) {
    String name = f.name();                        // "<id>.wav"
    f.close();
    bool wanted = false;
    for (JsonObject v : lines) if (name == v["id"].as<String>() + ".wav") { wanted = true; break; }
    if (!wanted) leftovers.push_back(name);
  }
  dir.close();
  for (const String& name : leftovers) LittleFS.remove("/pack/v/" + name);

  Serial.printf("[pack] installed %s (%u voice lines)\n", version.c_str(), lines.size());
  ack(version, nullptr);
  return true;
}
