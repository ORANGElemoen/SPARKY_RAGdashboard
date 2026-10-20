#pragma once
#include <Arduino.h>
extern volatile bool sparkyIdle;      // main loop: true only when not listening/thinking/talking
extern volatile bool packChanged;     // network task: a new pack was installed -> reload faces
void networkBegin();
bool networkTakePreview(char rows[8][33], uint16_t* seconds);
