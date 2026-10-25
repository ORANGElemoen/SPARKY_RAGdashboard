// Voice question: record -> POST /api/v1/voice/query (Accept: application/x-tutor-voice)
// -> play each answer sentence as soon as it arrives. Wire format: docs/PROTOCOL.md.
//
// The recording goes to LittleFS (8 s = 256 KB is too much RAM next to Wi-Fi), already
// wrapped in the multipart body, so the upload is one file stream. While it uploads and
// the server thinks, the "button_release" voice line ("Hmm, let me think!") plays.
#include "ask.h"
#include "config.h"
#include "faces.h"
#include "mic.h"
#include "settings.h"
#include "voice.h"
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <WiFi.h>

#define BOUNDARY "SparkyQuestionBoundary"
static const char* BODY_PATH = "/q.bin";
static volatile bool fillerDone = true;

static void fillerTask(void*) {
  uint8_t mood;
  voicePlay("button_release", &mood);
  facesShowMood(MOOD_THINKING);
  fillerDone = true;
  vTaskDelete(nullptr);
}

static void waitFiller() {
  while (!fillerDone) delay(10);
}

static void wavHeader(uint8_t h[44], uint32_t samples) {
  const uint32_t rate = 16000, dataBytes = samples * 2;
  auto le32 = [&](int at, uint32_t v) { for (int i = 0; i < 4; i++) h[at + i] = v >> (8 * i); };
  auto le16 = [&](int at, uint16_t v) { h[at] = v; h[at + 1] = v >> 8; };
  memcpy(h, "RIFF", 4); le32(4, 36 + dataBytes); memcpy(h + 8, "WAVEfmt ", 8);
  le32(16, 16); le16(20, 1); le16(22, 1); le32(24, rate); le32(28, rate * 2); le16(32, 2); le16(34, 16);
  memcpy(h + 36, "data", 4); le32(40, dataBytes);
}

// Receives the answer body (HTTPClient has already removed the chunked encoding) and plays it:
// [u32 BE length][metadata JSON] then frame_count x [u32 BE length][one WAV file].
class AnswerSink : public Stream {
 public:
  int framesPlayed = 0;
  bool streaming = false;

  int available() override { return 0; }
  int read() override { return -1; }
  int peek() override { return -1; }
  size_t write(uint8_t b) override { return write(&b, 1); }
  size_t write(const uint8_t* p, size_t n) override {
    size_t left = n;
    while (left) {
      size_t used = step(p, left);
      p += used;
      left -= used;
    }
    return n;                                    // always "accept" so HTTPClient keeps reading
  }

 private:
  enum { LEN, META, WAVHDR, PCM, SKIP } state = LEN;
  uint8_t lenBuf[4], hdr[44];
  uint32_t need = 0, have = 0;
  char* meta = nullptr;
  bool gotMeta = false, hasOdd = false;
  uint8_t odd = 0;

  size_t take(uint8_t* dst, const uint8_t* p, size_t n) {
    size_t k = min((size_t)(need - have), n);
    if (dst) memcpy(dst + have, p, k);
    have += k;
    return k;
  }

  size_t step(const uint8_t* p, size_t n) {
    switch (state) {
      case LEN: {
        need = 4;
        size_t k = take(lenBuf, p, n);
        if (have == 4) {
          need = (uint32_t)lenBuf[0] << 24 | lenBuf[1] << 16 | lenBuf[2] << 8 | lenBuf[3];
          have = 0;
          if (!gotMeta) {
            meta = need <= 32768 ? (char*)malloc(need + 1) : nullptr;   // huge metadata: skip it
            state = META;
          } else {
            state = need > 44 ? WAVHDR : SKIP;
          }
        }
        return k;
      }
      case META: {
        size_t k = take((uint8_t*)meta, p, n);
        if (have == need) {
          if (meta) {
            meta[need] = 0;
            JsonDocument filter, doc;
            filter["transcript"] = true;
            filter["answer_text"] = true;
            filter["frame_count"] = true;
            if (!deserializeJson(doc, meta, need, DeserializationOption::Filter(filter))) {
              Serial.printf("[ask] heard: \"%s\"\n", (const char*)(doc["transcript"] | ""));
              Serial.printf("[ask] answer (%d sentences): %s\n", (int)(doc["frame_count"] | 0),
                            (const char*)(doc["answer_text"] | ""));
            }
            free(meta);
            meta = nullptr;
          }
          gotMeta = true;
          state = LEN;
          have = 0;
        }
        return k;
      }
      case WAVHDR: {
        uint32_t frameLen = need;
        need = 44;
        size_t k = take(hdr, p, n);
        need = frameLen;                         // keep the frame length for the PCM part
        if (have == 44) {
          uint32_t rate = hdr[24] | hdr[25] << 8 | hdr[26] << 16 | (uint32_t)hdr[27] << 24;
          if (!streaming) {
            waitFiller();                        // the "let me think" line finishes first
            facesShowMood(MOOD_TALKING);
            streaming = true;
          }
          voiceStreamBegin(rate);
          need = frameLen - 44;                  // PCM bytes in this frame
          have = 0;
          hasOdd = false;
          state = PCM;
        }
        return k;
      }
      case PCM: {
        size_t k = min((size_t)(need - have), n);
        const uint8_t* q = p;
        size_t m = k;
        int16_t buf[256];
        size_t cnt = 0;
        if (hasOdd && m) {                       // a sample split across two network reads
          buf[cnt++] = (int16_t)(odd | q[0] << 8);
          q++, m--, hasOdd = false;
        }
        while (m >= 2) {
          buf[cnt++] = (int16_t)(q[0] | q[1] << 8);
          q += 2, m -= 2;
          if (cnt == 256) { voiceStreamWrite(buf, cnt); cnt = 0; }
        }
        if (cnt) voiceStreamWrite(buf, cnt);
        if (m) { odd = q[0]; hasOdd = true; }
        have += k;
        if (have == need) {
          framesPlayed++;
          state = LEN;
          have = 0;
        }
        return k;
      }
      case SKIP: {
        size_t k = take(nullptr, p, n);
        if (have == need) { state = LEN; have = 0; }
        return k;
      }
    }
    return n;
  }
};

AskResult askQuestion(bool (*buttonHeld)()) {
  if (!WiFi.isConnected()) {
    while (buttonHeld()) delay(10);
    return ASK_NO_WIFI;
  }

  // 1. record, already wrapped in the multipart body
  facesShowMood(MOOD_LISTENING);
  String head = "--" BOUNDARY "\r\nContent-Disposition: form-data; name=\"session_id\"\r\n\r\n" +
                settingsSessionId() +
                "\r\n--" BOUNDARY "\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"question.wav\"\r\n"
                "Content-Type: audio/wav\r\n\r\n";
  uint8_t wav[44] = {};
  File f = LittleFS.open(BODY_PATH, "w");
  if (!f) return ASK_SERVER_ERROR;
  f.print(head);
  f.write(wav, 44);                              // placeholder, sizes known after recording
  size_t samples = micRecord(f, MAX_QUESTION_MS, buttonHeld);
  f.print("\r\n--" BOUNDARY "--\r\n");
  f.close();
  if (samples < 16000UL * MIN_QUESTION_MS / 1000) {
    LittleFS.remove(BODY_PATH);
    return ASK_TOO_SHORT;
  }
  wavHeader(wav, samples);
  f = LittleFS.open(BODY_PATH, "r+");
  f.seek(head.length());
  f.write(wav, 44);
  f.close();
  Serial.printf("[ask] recorded %.1f s\n", samples / 16000.0f);

  // 2. "Hmm, let me think!" plays while the question uploads and the server answers
  fillerDone = false;
  xTaskCreate(fillerTask, "filler", 8192, nullptr, 1, nullptr);

  // 3. ask, and play the answer as it streams in
  AskResult result = ASK_SERVER_ERROR;
  HTTPClient http;
  http.begin(settingsServerUrl() + "/api/v1/voice/query");
  http.addHeader("X-Device-Key", settingsDeviceKey());
  http.addHeader("Accept", "application/x-tutor-voice");
  http.addHeader("Content-Type", "multipart/form-data; boundary=" BOUNDARY);
  http.setConnectTimeout(5000);
  http.setTimeout(ANSWER_TIMEOUT_MS);
  File body = LittleFS.open(BODY_PATH, "r");
  int code = http.sendRequest("POST", &body, body.size());
  body.close();
  if (code == 200) {
    AnswerSink sink;
    http.writeToStream(&sink);
    if (sink.streaming) voiceStreamEnd();
    if (sink.framesPlayed > 0) result = ASK_OK;
    Serial.printf("[ask] played %d sentences\n", sink.framesPlayed);
  } else {
    Serial.printf("[ask] server said %d: %s\n", code, code > 0 ? http.getString().c_str() : http.errorToString(code).c_str());
  }
  http.end();
  waitFiller();
  LittleFS.remove(BODY_PATH);
  return result;
}
