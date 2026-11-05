#pragma once
#include <Arduino.h>
#include <HTTPClient.h>
// Sparky stores two server addresses: the local one (hotspot) and the internet one (ngrok).
// It uses the local one whenever it can reach it.
bool settingsHttpBegin(HTTPClient& http, const String& path);   // address + device key headers; https is verified
bool settingsRejoinWifi();       // after Wi-Fi was lost: tries the remembered networks in range
void settingsChooseServer();     // checks which address to use; can take 1.5 s
bool settingsOnInternet();       // currently using the internet address
void settingsOpenSetupAndRestart();   // restarts into the setup page
void settingsBegin();            // Wi-Fi (setup hotspot on first boot) + server URL + device key
String settingsServerUrl();      // e.g. "http://192.168.1.20:8001"
String settingsDeviceKey();
String settingsSessionId();     // this Sparky's conversation id (made once, kept in flash)
