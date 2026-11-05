// Ported from the bring-up sketch Sparky_Wifi_Setup.ino (OneDrive/Documents/Arduino):
// same Sparky-styled WiFiManager portal, hotspot name/password and class-code field.
// Changes from the sketch:
//   - no wm.resetSettings() on every boot: the portal only opens when Sparky has no
//     Wi-Fi/server/key yet, or when the button is held while switching on;
//   - server address and device key are typed into the portal and saved in flash
//     (Preferences) instead of being written into the code.
#include "settings.h"
#include "config.h"
#include "faces.h"
#include "tls_roots.h"
#include "voice.h"
#include <ArduinoJson.h>
#include <Preferences.h>
#include <WiFi.h>
#include <WiFiClientSecure.h>
#include "mbedtls/sha256.h"
#include "mbedtls/x509_crt.h"
#include <WiFiManager.h>

static const char* SPARKY_CSS = R"rawliteral(
<style>
  body { background-color: #EAF6FD; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; color: #1A1A1A; }
  .wrap { background-color: #FFFFFF; max-width: 340px; margin: 30px auto; padding: 24px; border-radius: 16px;
          box-shadow: 0 8px 24px rgba(0,0,0,0.12); text-align: left; }
  h1, h2, h3 { color: #3AA0D8; text-align: center; }
  button { background-color: #F5821F; color: #FFFFFF; border: 0; border-radius: 10px; line-height: 2.4rem;
           font-size: 1.1rem; width: 100%; margin-top: 8px; cursor: pointer; }
  button:hover { background-color: #D96F16; }
  input, select { border-radius: 8px; border: 1px solid #CFE6F3; padding: 8px; font-size: 1rem; width: 92%; }
  a { color: #3AA0D8; }
  .msg { border-radius: 10px; padding: 10px; }
</style>
)rawliteral";

static Preferences prefs;
static String serverUrl, internetUrl, deviceKey, classCode;

// Every network Sparky has joined, newest first, as JSON: [{"s": name, "p": password, "l": true}]
// so it reconnects anywhere it has been before. WiFiManager itself only remembers one.
// "l" marks a network where the local server answered: Sparky is local first, so those win.
static constexpr int MAX_NETWORKS = 8;

static void rememberNetwork(const String& name, const String& password, bool serverIsLocal) {
  if (name.isEmpty()) return;
  JsonDocument saved, updated;
  deserializeJson(saved, prefs.getString("nets", "[]"));
  JsonArray list = updated.to<JsonArray>();
  JsonObject newest = list.add<JsonObject>();
  newest["s"] = name;
  newest["p"] = password;
  for (JsonObject net : saved.as<JsonArray>()) {
    if (name == (const char*)net["s"]) serverIsLocal = serverIsLocal || (net["l"] | false);
    else if ((int)list.size() < MAX_NETWORKS) list.add(net);
  }
  if (serverIsLocal) newest["l"] = true;
  String json;
  serializeJson(updated, json);
  prefs.putString("nets", json);
}

static bool tryNetwork(const char* name, const char* password) {
  Serial.printf("[wifi] trying %s\n", name);
  WiFi.begin(name, password);
  for (int i = 0; i < 120 && WiFi.status() != WL_CONNECTED; i++) delay(100);
  if (WiFi.status() == WL_CONNECTED) return true;
  WiFi.disconnect();
  delay(200);
  return false;
}

// Scans, then tries the remembered networks that are in range, strongest first.
static bool joinRememberedNetwork() {
  JsonDocument saved;
  deserializeJson(saved, prefs.getString("nets", "[]"));
  JsonArray list = saved.as<JsonArray>();
  if (list.size() == 0) return false;
  WiFi.persistent(false);                // don't replace WiFiManager's own saved network
  WiFi.mode(WIFI_STA);
  WiFi.disconnect();
  delay(100);
  int found = WiFi.scanNetworks();
  bool joined = false;
  bool tried[MAX_NETWORKS] = {};
  for (int attempt = 0; attempt < (int)list.size() && !joined; attempt++) {
    int best = -1, bestRssi = -1000;
    for (int i = 0; i < (int)list.size() && i < MAX_NETWORKS; i++) {
      if (tried[i]) continue;
      for (int s = 0; s < found; s++) {
        int score = WiFi.RSSI(s) + ((list[i]["l"] | false) ? 200 : 0);   // any local-server network beats the rest
        if (WiFi.SSID(s) == (const char*)list[i]["s"] && score > bestRssi) {
          best = i;
          bestRssi = score;
        }
      }
    }
    if (best < 0) break;
    tried[best] = true;
    joined = tryNetwork(list[best]["s"], list[best]["p"]);
  }
  WiFi.scanDelete();
  WiFi.persistent(true);
  return joined;
}

static volatile bool useInternet = false;

static String cleanUrl(String url) {
  // Tablets auto-capitalise and it's easy to hit the comma key. Neither belongs in these addresses.
  url.trim();
  url.toLowerCase();
  url.replace(",", ".");
  if (url.endsWith("/")) url.remove(url.length() - 1);
  return url;
}

static bool localServerReachable() {
  if (serverUrl.isEmpty()) return false;
  int hostStart = serverUrl.indexOf("://") + 3;       // indexOf gives -1 without a scheme, so this is 2: reject below
  if (hostStart < 3) return false;
  int colon = serverUrl.indexOf(':', hostStart);
  String host = serverUrl.substring(hostStart, colon > 0 ? colon : serverUrl.length());
  uint16_t port = colon > 0 ? serverUrl.substring(colon + 1).toInt() : 80;
  WiFiClient client;
  bool reachable = client.connect(host.c_str(), port, 1500);
  client.stop();
  return reachable;
}

// Checks the server's certificate after connecting, before anything is sent. The usual check during
// the handshake takes the ESP32 about 1.75 s, and ngrok hangs up on a client that quiet (error -29312).
// So the slow check runs once per certificate, and later connections compare fingerprints in milliseconds.
class VerifiedClient : public WiFiClientSecure {
public:
  VerifiedClient() { setInsecure(); }   // the handshake doesn't check: connect() below does

  int connect(const char* host, uint16_t port, int32_t timeout) override {
    if (!secureConnect(host, port, timeout)) return 0;
    uint8_t fingerprint[32];
    if (!peerFingerprint(fingerprint)) { stop(); return 0; }
    if (isTrusted(fingerprint)) return 1;

    if (!peerChainIsValid(host)) { stop(); return 0; }
    portENTER_CRITICAL(&trustedLock);
    memcpy(trustedFingerprint, fingerprint, sizeof(fingerprint));
    haveTrusted = true;
    portEXIT_CRITICAL(&trustedLock);
    Serial.println("[tls] server certificate verified");

    stop();                              // ngrok has hung up by now, so connect again
    if (!secureConnect(host, port, timeout)) return 0;
    if (peerFingerprint(fingerprint) && isTrusted(fingerprint)) return 1;
    stop();
    return 0;
  }

private:
  static portMUX_TYPE trustedLock;
  static uint8_t trustedFingerprint[32];
  static bool haveTrusted;

  int secureConnect(const char* host, uint16_t port, int32_t timeout) {
    uint32_t started = millis();
    int connected = WiFiClientSecure::connect(host, port, timeout);
    if (!connected) {
      char reason[80] = "";
      int code = lastError(reason, sizeof(reason));
      IPAddress ip;
      bool named = WiFi.hostByName(host, ip);
      Serial.printf("[tls] connect failed after %u ms: %d %s; name lookup %s; free %u, largest %u, core %d\n",
                    (unsigned)(millis() - started), code, reason, named ? "OK" : "FAILED", (unsigned)ESP.getFreeHeap(),
                    (unsigned)ESP.getMaxAllocHeap(), xPortGetCoreID());
    }
    return connected;
  }

  static bool isTrusted(const uint8_t* fingerprint) {
    portENTER_CRITICAL(&trustedLock);
    bool trusted = haveTrusted && memcmp(fingerprint, trustedFingerprint, 32) == 0;
    portEXIT_CRITICAL(&trustedLock);
    return trusted;
  }

  bool peerFingerprint(uint8_t* out) {
    const mbedtls_x509_crt* peer = getPeerCertificate();
    return peer && mbedtls_sha256(peer->raw.p, peer->raw.len, out, 0) == 0;
  }

  bool peerChainIsValid(const char* host) {
    mbedtls_x509_crt roots;
    mbedtls_x509_crt_init(&roots);
    uint32_t flags = 0;
    int parsed = mbedtls_x509_crt_parse(&roots, (const unsigned char*)TLS_ROOTS, strlen(TLS_ROOTS) + 1);
    int result = parsed == 0 ? mbedtls_x509_crt_verify(const_cast<mbedtls_x509_crt*>(getPeerCertificate()), &roots,
                                                       nullptr, host, &flags, nullptr, nullptr) : parsed;
    mbedtls_x509_crt_free(&roots);
    if (result == 0) return true;
    char reason[120] = "";
    mbedtls_x509_crt_verify_info(reason, sizeof(reason), "", flags);
    Serial.printf("[tls] REFUSED server %s: %d %s\n", host, result, reason);
    return false;
  }
};
portMUX_TYPE VerifiedClient::trustedLock = portMUX_INITIALIZER_UNLOCKED;
uint8_t VerifiedClient::trustedFingerprint[32];
bool VerifiedClient::haveTrusted = false;

static VerifiedClient secureClients[2];   // one per core: the network task on 0, loop() on 1

void settingsChooseServer() {
  bool internet = !internetUrl.isEmpty() && !localServerReachable();
  if (internet != useInternet) Serial.printf("[net] now using %s\n", (internet ? internetUrl : serverUrl).c_str());
  useInternet = internet;
}

bool settingsOnInternet() { return useInternet; }

bool settingsHttpBegin(HTTPClient& http, const String& path) {
  String url = settingsServerUrl() + path;
  bool ok = url.startsWith("https://") ? http.begin(secureClients[xPortGetCoreID()], url) : http.begin(url);
  http.addHeader("X-Device-Key", deviceKey);
  http.addHeader("ngrok-skip-browser-warning", "1");  // ngrok's warning page is for people, not for Sparky
  return ok;
}

static void afterJoiningWifi() {
  settingsChooseServer();
  rememberNetwork(WiFi.SSID(), WiFi.psk(), !useInternet && !serverUrl.isEmpty());
}

void settingsBegin() {
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  prefs.begin("sparky", false);
  serverUrl = prefs.getString("server", SPARKY_SERVER);
  internetUrl = prefs.getString("internet", "");
  if (internetUrl.isEmpty()) internetUrl = SPARKY_INTERNET;  // built in, so nobody has to type it
  deviceKey = prefs.getString("key", SPARKY_DEVICE_KEY);
  classCode = prefs.getString("class", "");
  if (prefs.isKey("wifi2")) {                                // from the older "second Wi-Fi" fields
    rememberNetwork(prefs.getString("wifi2", ""), prefs.getString("wifi2pass", ""), false);
    prefs.remove("wifi2");
    prefs.remove("wifi2pass");
  }

  WiFiManager wm;
  wm.setCustomHeadElement(SPARKY_CSS);
  wm.setTitle("Sparky Setup");
  WiFiManagerParameter pServer("server", "Local server address (e.g. http://192.168.137.1:8001)", serverUrl.c_str(), 80);
  WiFiManagerParameter pInternet("internet", "Internet address (optional, e.g. https://you.ngrok-free.dev)", internetUrl.c_str(), 100);
  WiFiManagerParameter pKey("key", "Device key (from the Devices admin page)", deviceKey.c_str(), 80);
  WiFiManagerParameter pClass("classcode", "Class Code (optional)", classCode.c_str(), 20);
  wm.addParameter(&pServer);
  wm.addParameter(&pInternet);
  wm.addParameter(&pKey);
  wm.addParameter(&pClass);
  wm.setConfigPortalTimeout(300);
  wm.setAPCallback([](WiFiManager*) {                       // no Wi-Fi: say so, so nobody waits in silence
    uint8_t mood;
    facesShowMood(MOOD_WIFI_SETUP);                       // stays up while the hotspot is open
    if (!voicePlay("wifi_setup", &mood)) voiceChirp(700, 400, 300);   // "Looking for a network..."
    Serial.println("[wifi] no network - setup hotspot 'Sparky Setup' is open");
  });

  bool asked = prefs.getBool("setup", false);                // five quick presses, see sparky.ino
  if (asked) {
    prefs.remove("setup");
    wm.setConfigPortalTimeout(SETUP_TAPS_PORTAL_SECONDS);
  }
  bool forceSetup = asked || digitalRead(PIN_BUTTON) == LOW;          // hold the button while switching on = set up again
  if (forceSetup || (serverUrl.isEmpty() && internetUrl.isEmpty()) || deviceKey.isEmpty()) wm.startConfigPortal(SETUP_AP_NAME, SETUP_AP_PASSWORD);
  else {
    bool joined = joinRememberedNetwork();
    if (!joined) {
      wm.setConnectTimeout(15);                              // a missing network otherwise takes 40 s to give up
      wm.setEnableConfigPortal(false);
      joined = wm.autoConnect(SETUP_AP_NAME, SETUP_AP_PASSWORD);
    }
    if (!joined) {
      wm.setEnableConfigPortal(true);
      wm.startConfigPortal(SETUP_AP_NAME, SETUP_AP_PASSWORD);
    }
  }

  serverUrl = cleanUrl(pServer.getValue());
  internetUrl = cleanUrl(pInternet.getValue());
  deviceKey = pKey.getValue();     deviceKey.trim();
  classCode = pClass.getValue();   classCode.trim();
  prefs.putString("server", serverUrl);
  prefs.putString("internet", internetUrl);
  prefs.putString("key", deviceKey);
  prefs.putString("class", classCode);
  WiFi.setTxPower(SPARKY_WIFI_TX_POWER);  // smaller current spikes (see config.h)
  WiFi.setSleep(false);   // modem power-save makes packets arrive in bursts: streamed answers stuttered
  if (WiFi.isConnected()) afterJoiningWifi();
}

void settingsOpenSetupAndRestart() {
  prefs.putBool("setup", true);
  ESP.restart();
}

bool settingsRejoinWifi() {
  if (!joinRememberedNetwork()) return false;
  WiFi.setTxPower(SPARKY_WIFI_TX_POWER);
  WiFi.setSleep(false);
  afterJoiningWifi();
  return true;
}

String settingsServerUrl() { return useInternet ? internetUrl : serverUrl; }
String settingsDeviceKey() { return deviceKey; }

// One conversation per device, never shared (docs/PROTOCOL.md, "Sessions").
String settingsSessionId() {
  String sid = prefs.getString("sid", "");
  if (sid.isEmpty()) {
    char buf[33];
    for (int i = 0; i < 4; i++) snprintf(buf + 8 * i, 9, "%08lx", (unsigned long)esp_random());
    sid = buf;
    prefs.putString("sid", sid);
  }
  return sid;
}
