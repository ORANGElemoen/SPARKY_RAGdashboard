#pragma once
#include <Arduino.h>
void voiceBegin();
bool voicePlay(const char* trigger, uint8_t* moodOut);   // random line with this trigger; blocks until it finishes
