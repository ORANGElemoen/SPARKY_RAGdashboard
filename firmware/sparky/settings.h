#pragma once
#include <Arduino.h>
void settingsBegin();            // Wi-Fi (setup hotspot on first boot) + server URL + device key
String settingsServerUrl();      // e.g. "http://192.168.1.20:8001"
String settingsDeviceKey();
