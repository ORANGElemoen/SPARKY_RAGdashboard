#pragma once
#include <Arduino.h>
extern volatile bool sparkyIdle;      // main loop: true only when not listening/thinking/talking
extern volatile bool packChanged;     // network task: a new pack was installed -> reload faces
void networkBegin();
// Tells the server how Sparky is doing (shown in Studio): Wi-Fi signal, plus the last answer's
// seconds of speech and stalls when stalls >= 0.
void networkReportStatus(float answerSeconds = 0, int stalls = -1, uint32_t stallMs = 0);
bool networkTakePreview(char rows[8][33], uint16_t* seconds);
