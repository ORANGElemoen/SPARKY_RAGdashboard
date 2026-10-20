#pragma once
#include <Arduino.h>
// Same order as the pack's mood_order (core/services/studio_service.py MOODS).
enum : uint8_t { MOOD_IDLE, MOOD_LISTENING, MOOD_THINKING, MOOD_TALKING, MOOD_HAPPY, MOOD_ERROR, MOOD_COUNT };
extern const char* const MOOD_NAMES[MOOD_COUNT];
void facesBegin();
bool facesLoad();                                   // re-read /pack/manifest.json; false = using built-ins
void facesShowMood(uint8_t mood);
void facesShowRows(const char* const rows[8]);      // 8 strings of 32 '#'/'.'
