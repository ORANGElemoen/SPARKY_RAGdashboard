#pragma once
#include <Arduino.h>
#include <FS.h>
void micBegin();
// Records 16 kHz mono while keepGoing() is true (at most maxMs) and appends it to `out`: 16-bit
// samples, or one G.711 mu-law byte per sample if mulaw is set. Returns the number of samples written.
size_t micRecord(File& out, uint32_t maxMs, bool (*keepGoing)(), bool mulaw);
