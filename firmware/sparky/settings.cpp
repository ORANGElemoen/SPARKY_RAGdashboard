// Ported from the bring-up sketch Sparky_Wifi_Setup.ino (OneDrive/Documents/Arduino):
// same Sparky-styled WiFiManager portal, hotspot name/password and class-code field.
// Changes from the sketch:
//   - no wm.resetSettings() on every boot: the portal only opens when Sparky has no
//     Wi-Fi/server/key yet, or when the button is held while switching on;
//   - server address and device key are typed into the portal and saved in flash
//     (Preferences) instead of being written into the code.
#include "settings.h"
#include "config.h"
#include <Preferences.h>
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
static String serverUrl, deviceKey, classCode;

void settingsBegin() {
  pinMode(PIN_BUTTON, INPUT_PULLUP);
  prefs.begin("sparky", false);
  serverUrl = prefs.getString("server", "");
  deviceKey = prefs.getString("key", "");
  classCode = prefs.getString("class", "");

  WiFiManager wm;
  wm.setCustomHeadElement(SPARKY_CSS);
  wm.setTitle("Sparky Setup");
  WiFiManagerParameter pServer("server", "Server address (e.g. http://192.168.1.20:8001)", serverUrl.c_str(), 80);
  WiFiManagerParameter pKey("key", "Device key (from the Devices admin page)", deviceKey.c_str(), 80);
  WiFiManagerParameter pClass("classcode", "Class Code (optional)", classCode.c_str(), 20);
  wm.addParameter(&pServer);
  wm.addParameter(&pKey);
  wm.addParameter(&pClass);
  wm.setConfigPortalTimeout(300);

  bool forceSetup = digitalRead(PIN_BUTTON) == LOW;          // hold the button while switching on = set up again
  if (forceSetup || serverUrl.isEmpty() || deviceKey.isEmpty()) wm.startConfigPortal(SETUP_AP_NAME, SETUP_AP_PASSWORD);
  else wm.autoConnect(SETUP_AP_NAME, SETUP_AP_PASSWORD);

  serverUrl = pServer.getValue();  serverUrl.trim();
  if (serverUrl.endsWith("/")) serverUrl.remove(serverUrl.length() - 1);
  deviceKey = pKey.getValue();     deviceKey.trim();
  classCode = pClass.getValue();   classCode.trim();
  prefs.putString("server", serverUrl);
  prefs.putString("key", deviceKey);
  prefs.putString("class", classCode);
}

String settingsServerUrl() { return serverUrl; }
String settingsDeviceKey() { return deviceKey; }
