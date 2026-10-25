#pragma once
#include <Arduino.h>
void voiceBegin();
bool voicePlay(const char* trigger, uint8_t* moodOut);   // random line with this trigger; blocks until it finishes
// Streamed playback (tutor answers arrive sentence by sentence at the voice's own rate).
void voiceStreamBegin(uint32_t sampleRate);   // unmutes the amp
void voiceStreamWrite(const int16_t* mono, size_t samples);
void voiceStreamEnd();                        // mutes the amp, back to 16 kHz
