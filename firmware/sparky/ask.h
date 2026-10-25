#pragma once
#include <Arduino.h>
enum AskResult : uint8_t { ASK_OK, ASK_TOO_SHORT, ASK_NO_WIFI, ASK_SERVER_ERROR };
// Push to talk: records while buttonHeld() is true, sends the question to the tutor server
// and plays the spoken answer as it streams in. Blocks until Sparky has finished answering.
AskResult askQuestion(bool (*buttonHeld)());
