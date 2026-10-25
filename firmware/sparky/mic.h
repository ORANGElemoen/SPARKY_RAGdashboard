#pragma once
#include <Arduino.h>
#include <FS.h>
void micBegin();
// Records 16 kHz 16-bit mono while keepGoing() is true (at most maxMs) and appends it to `out`.
// Returns the number of samples written.
size_t micRecord(File& out, uint32_t maxMs, bool (*keepGoing)());
