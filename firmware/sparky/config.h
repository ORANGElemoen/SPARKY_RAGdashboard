// Pins from the report's ESP32 pin map, and timings.
#pragma once
#include <Arduino.h>

// Bench settings that stay on this PC (gitignored): SPARKY_SERVER, SPARKY_DEVICE_KEY (so the
// setup page only needs the Wi-Fi) and SPARKY_TEST_QUESTION 1 (send the Studio "test_question"
// voice line instead of recording the mic).
#if __has_include("local_config.h")
#include "local_config.h"
#endif
#ifndef SPARKY_SERVER
#define SPARKY_SERVER ""
#endif
#ifndef SPARKY_DEVICE_KEY
#define SPARKY_DEVICE_KEY ""
#endif
#ifndef SPARKY_TEST_QUESTION
#define SPARKY_TEST_QUESTION 0
#endif

constexpr int PIN_AMP_BCLK = 27, PIN_AMP_LRC = 26, PIN_AMP_DIN = 22, PIN_AMP_SD = 21;
constexpr int PIN_MATRIX_CS = 5;              // CLK 18 / DIN 23 are the default VSPI pins
constexpr int PIN_BUTTON = 14;
constexpr int PIN_MIC_SCK = 32, PIN_MIC_WS = 25, PIN_MIC_SD = 33;   // INMP441, L/R pin to GND
constexpr int MATRIX_DEVICES = 4;             // 4 x 8x8 = 32 x 8
constexpr uint32_t SYNC_EVERY_MS = 5UL * 60UL * 1000UL;
constexpr int LONG_POLL_SECONDS = 25;
constexpr size_t FLASH_MARGIN_BYTES = 32 * 1024;   // never fill LittleFS completely

// Voice question (push to talk): hold the button, speak, let go.
constexpr uint32_t MAX_QUESTION_MS = 8000;    // 8 s at 16 kHz = 256 KB in LittleFS
constexpr uint32_t MIN_QUESTION_MS = 300;     // shorter presses are taps, not questions
constexpr uint16_t ANSWER_TIMEOUT_MS = 65000; // speech-to-text + LLM on a CPU server can be slow (16-bit max)
constexpr int MIC_SHIFT = 14;                 // INMP441 24-bit -> 16-bit; lower = louder (13 = x2)

// Same setup hotspot as the bring-up sketch (Sparky_Wifi_Setup.ino).
constexpr const char* SETUP_AP_NAME = "Sparky Setup";
constexpr const char* SETUP_AP_PASSWORD = "sparky123";   // WPA2 needs 8+ characters

#ifndef SPARKY_FLIP_X
#define SPARKY_FLIP_X 1                       // flip if faces show up mirrored
#endif
#ifndef SPARKY_FLIP_Y
#define SPARKY_FLIP_Y 0                       // flip if faces show up upside down
#endif
