// Voice question: record -> POST /api/v1/voice/query (Accept: application/x-tutor-voice; version=2)
// -> play each answer sentence as soon as it arrives. Wire format: docs/PROTOCOL.md.
//
// The recording goes to LittleFS (8 s = 256 KB is too much RAM next to Wi-Fi), already
// wrapped in the multipart body, so the upload is one file stream. While it uploads and
// the server thinks, the "button_release" voice line ("Hmm, let me think!") plays.
#include "ask.h"
#include "config.h"
#include "faces.h"
#include "mic.h"
#include "network_task.h"
#include "settings.h"
#include "voice.h"
#include <ArduinoJson.h>
#include <HTTPClient.h>
#include <LittleFS.h>
#include <WiFi.h>
#include <freertos/stream_buffer.h>

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

#if SPARKY_TEST_QUESTION
// Bench test without a microphone: the Studio "test_question" voice line (already 16 kHz mono)
// is sent as the question, once the button is let go.
static size_t testQuestion(File& out, bool (*buttonHeld)()) {
  while (buttonHeld()) delay(10);
  String path = voiceLinePath("test_question");
  if (path.isEmpty()) {
    Serial.println("[ask] test mode: make a voice line with the 'test_question' trigger in Sparky Studio");
    return 0;
  }
  File in = LittleFS.open(path, "r");
  in.seek(44);
  uint8_t buf[512];
  size_t n, bytes = 0;
  while ((n = in.read(buf, sizeof(buf))) > 0) bytes += out.write(buf, n);
  in.close();
  return bytes / 2;
}
#endif

static void wavHeader(uint8_t h[44], uint32_t samples) {
  const uint32_t rate = 16000, dataBytes = samples * 2;
  auto le32 = [&](int at, uint32_t v) { for (int i = 0; i < 4; i++) h[at + i] = v >> (8 * i); };
  auto le16 = [&](int at, uint16_t v) { h[at] = v; h[at + 1] = v >> 8; };
  memcpy(h, "RIFF", 4); le32(4, 36 + dataBytes); memcpy(h + 8, "WAVEfmt ", 8);
  le32(16, 16); le16(20, 1); le16(22, 1); le32(24, rate); le32(28, rate * 2); le16(32, 2); le16(34, 16);
  memcpy(h + 36, "data", 4); le32(40, dataBytes);
}

// ---------------------------------------------------------------- buffered answer playback
// The network side (AnswerSink) pours answer audio into a RAM buffer and a player task feeds
// the speaker from it. Playback starts once ~1 s is buffered (or the whole sentence is in), and
// if the buffer ever runs dry mid-sentence it refills to ~1 s before carrying on - a weak Wi-Fi
// moment becomes one short pause instead of choppy speech. Each such pause counts as a stall.
static StreamBufferHandle_t pcm = nullptr;
static size_t pcmCapacity = 0;
static volatile bool receiving = false, answerDone = false, playerDone = true;
static volatile uint32_t playRate = 22050, stalls = 0, stallMs = 0, playedBytes = 0;
static volatile uint32_t firstAnswerMs = 0;            // when the first word of the answer played

static void playerTask(void*) {
  int16_t raw[512];
  uint8_t* buf = (uint8_t*)raw;
  size_t keep = 0;                               // an odd byte carried over to the next read
  bool started = false, waiting = true;
  uint32_t stallStart = 0;
  for (;;) {
    size_t avail = xStreamBufferBytesAvailable(pcm);
    if (waiting) {                               // (re)fill before speaking
      size_t target = min((size_t)(playRate * 2 * PREBUFFER_MS / 1000), pcmCapacity - 1024);
      if (avail >= target || (!receiving && avail > 0)) {
        waiting = false;
        if (stallStart) { stallMs += millis() - stallStart; stallStart = 0; }
      } else if (answerDone && avail == 0) {
        break;
      } else {
        vTaskDelay(pdMS_TO_TICKS(5));
        continue;
      }
    }
    size_t n = xStreamBufferReceive(pcm, buf + keep, sizeof(raw) - keep, pdMS_TO_TICKS(20));
    if (n == 0) {
      if (answerDone) break;
      waiting = true;                            // ran dry
      if (receiving) { stalls = stalls + 1; stallStart = millis(); }   // ...in the middle of a sentence
      continue;
    }
    if (!started) {
      firstAnswerMs = millis();
      facesShowMood(MOOD_TALKING);
      voiceStreamBegin(playRate);
      started = true;
    }
    n += keep;
    keep = n & 1;
    voiceStreamWrite(raw, n / 2);
    if (keep) buf[0] = buf[n - 1];
    playedBytes += n - keep;
  }
  if (started) voiceStreamEnd();
  playerDone = true;
  vTaskDelete(nullptr);
}

// Receives the answer body (HTTPClient has already removed the chunked encoding):
// [u32 BE length][metadata JSON] then [u32 BE length][one WAV file] per sentence; protocol v2
// ends with one more JSON block (answer text + sentence count), told apart by not being "RIFF".
class AnswerSink : public Stream {
 public:
  int framesReceived = 0, framesExpected = -1;
  uint32_t bytesExpected = 0;   // PCM bytes the server sent, to check nothing was cut off

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
  bool gotMeta = false, firstFrame = true;

  // The metadata block (v1: has answer_text + frame_count; v2: frame_count is null) or the
  // v2 closing summary (answer_text + frame_count).
  void finishJson() {
    if (meta) {
      meta[need] = 0;
      JsonDocument filter, doc;
      filter["transcript"] = true;
      filter["answer_text"] = true;
      filter["frame_count"] = true;
      if (!deserializeJson(doc, meta, need, DeserializationOption::Filter(filter))) {
        if (doc["transcript"].is<const char*>()) Serial.printf("[ask] heard: \"%s\"\n", (const char*)doc["transcript"]);
        if (!doc["frame_count"].isNull()) framesExpected = doc["frame_count"];
        if (doc["answer_text"].is<const char*>())
          Serial.printf("[ask] answer (%d sentences): %s\n", framesExpected, (const char*)doc["answer_text"]);
      }
      free(meta);
      meta = nullptr;
    }
    gotMeta = true;
    state = LEN;
    have = 0;
  }

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
            state = WAVHDR;
          }
        }
        return k;
      }
      case META: {
        size_t k = take((uint8_t*)meta, p, n);
        if (have == need) finishJson();
        return k;
      }
      case WAVHDR: {                             // a sentence's WAV header, or the v2 closing summary
        uint32_t frameLen = need, head = min(frameLen, (uint32_t)44);
        need = head;
        size_t k = take(hdr, p, n);
        need = frameLen;                         // keep the frame length for the PCM part
        if (have < head) return k;
        if (frameLen <= 44 || memcmp(hdr, "RIFF", 4) != 0) {
          meta = frameLen <= 32768 ? (char*)malloc(frameLen + 1) : nullptr;
          if (meta) memcpy(meta, hdr, have);
          state = META;
          if (have == need) finishJson();
          return k;
        }
        if (firstFrame) {
          waitFiller();                          // the "let me think" line finishes first
          playRate = hdr[24] | hdr[25] << 8 | hdr[26] << 16 | (uint32_t)hdr[27] << 24;
          firstFrame = false;
        }
        receiving = true;
        need = frameLen - 44;                    // PCM bytes in this frame
        bytesExpected += need;
        have = 0;
        state = PCM;
        return k;
      }
      case PCM: {
        size_t k = min((size_t)(need - have), n);
        xStreamBufferSend(pcm, p, k, portMAX_DELAY);   // blocks while the buffer is full
        have += k;
        if (have == need) {
          receiving = false;
          framesReceived++;
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

static bool ensureBuffer() {
  if (pcm) return true;
  for (size_t size : {(size_t)PCM_BUFFER_BYTES, (size_t)PCM_BUFFER_BYTES / 2}) {   // smaller if RAM is short
    pcm = xStreamBufferCreate(size, 1);
    if (pcm) { pcmCapacity = size; Serial.printf("[ask] answer buffer %u KB\n", (unsigned)(size / 1024)); return true; }
  }
  Serial.println("[ask] no RAM for the answer buffer");
  return false;
}

AskResult askQuestion(bool (*buttonHeld)()) {
  if (!WiFi.isConnected()) {
    while (buttonHeld()) delay(10);
    return ASK_NO_WIFI;
  }

  // 1. record, already wrapped in the multipart body
  facesShowMood(MOOD_LISTENING);
  voiceChirp(500, 900, 120);                     // "bloop": I'm listening (done before the mic starts)
  String head = "--" BOUNDARY "\r\nContent-Disposition: form-data; name=\"session_id\"\r\n\r\n" +
                settingsSessionId() +
                "\r\n--" BOUNDARY "\r\nContent-Disposition: form-data; name=\"audio\"; filename=\"question.wav\"\r\n"
                "Content-Type: audio/wav\r\n\r\n";
  uint8_t wav[44] = {};
  File f = LittleFS.open(BODY_PATH, "w");
  if (!f) return ASK_SERVER_ERROR;
  f.print(head);
  f.write(wav, 44);                              // placeholder, sizes known after recording
#if SPARKY_TEST_QUESTION
  size_t samples = testQuestion(f, buttonHeld);
#else
  size_t samples = micRecord(f, MAX_QUESTION_MS, buttonHeld);
#endif
  uint32_t releaseMs = millis();                 // end of the child's question (REQ-N-01 starts here)
  f.print("\r\n--" BOUNDARY "--\r\n");
  f.close();
  voiceChirp(900, 500, 90);                      // "blip": got it
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
  if (!ensureBuffer()) { LittleFS.remove(BODY_PATH); return ASK_SERVER_ERROR; }

  // 2. "Hmm, let me think!" plays while the question uploads and the server answers
  fillerDone = false;
  xTaskCreate(fillerTask, "filler", 8192, nullptr, 1, nullptr);

  // 3. ask; the answer streams into the buffer and the player speaks it
  AskResult result = ASK_SERVER_ERROR;
  HTTPClient http;
  http.begin(settingsServerUrl() + "/api/v1/voice/query");
  http.addHeader("X-Device-Key", settingsDeviceKey());
  http.addHeader("Accept", "application/x-tutor-voice; version=2");   // v2: answer streams as it's written
  http.addHeader("Content-Type", "multipart/form-data; boundary=" BOUNDARY);
  http.setConnectTimeout(5000);
  http.setTimeout(ANSWER_TIMEOUT_MS);
  File body = LittleFS.open(BODY_PATH, "r");
  int code = http.sendRequest("POST", &body, body.size());
  body.close();
  if (code == 200) {
    xStreamBufferReset(pcm);
    receiving = false;
    answerDone = false;
    playerDone = false;
    stalls = 0;
    stallMs = 0;
    playedBytes = 0;
    firstAnswerMs = 0;
    xTaskCreatePinnedToCore(playerTask, "player", 4096, nullptr, 3, nullptr, 1);
    AnswerSink sink;
    http.writeToStream(&sink);
    receiving = false;
    answerDone = true;
    while (!playerDone) delay(10);
    if (sink.framesReceived > 0) result = ASK_OK;
    float speech = playedBytes / 2.0f / playRate;
    int32_t latency = firstAnswerMs ? (int32_t)(firstAnswerMs - releaseMs) : -1;
    // complete = every sentence the server announced arrived, and every byte of it was played
    bool complete = sink.framesReceived == sink.framesExpected && playedBytes + 1 >= sink.bytesExpected;
    Serial.printf("[ask] played %d sentences, %.1f s of speech, %u stalls (%u ms), Wi-Fi %d dBm\n",
                  sink.framesReceived, speech, (unsigned)stalls, (unsigned)stallMs, WiFi.RSSI());
    Serial.printf("[ask] first word of the answer %.1f s after letting go; %d/%d sentences, %u/%u bytes: %s\n",
                  latency / 1000.0f, sink.framesReceived, sink.framesExpected, (unsigned)playedBytes,
                  (unsigned)sink.bytesExpected, complete ? "COMPLETE" : "CUT OFF");
    networkReportStatus(speech, stalls, stallMs, latency, complete ? 1 : 0);
  } else {
    Serial.printf("[ask] server said %d: %s\n", code, code > 0 ? http.getString().c_str() : http.errorToString(code).c_str());
  }
  http.end();
  waitFiller();
  LittleFS.remove(BODY_PATH);
  return result;
}
