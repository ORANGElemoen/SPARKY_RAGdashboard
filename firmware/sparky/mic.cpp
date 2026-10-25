// INMP441 on I2S port 0 (legacy driver, same as the speaker on port 1). Reads both stereo
// slots and keeps the one the mic talks on - which slot "left" lands in differs between
// driver versions, so it is picked from the signal instead of trusted.
#include "mic.h"
#include "config.h"
#include <driver/i2s.h>

void micBegin() {
  i2s_config_t cfg = {};
  cfg.mode = (i2s_mode_t)(I2S_MODE_MASTER | I2S_MODE_RX);
  cfg.sample_rate = 16000;
  cfg.bits_per_sample = I2S_BITS_PER_SAMPLE_32BIT;   // 24-bit samples in 32-bit slots
  cfg.channel_format = I2S_CHANNEL_FMT_RIGHT_LEFT;
  cfg.communication_format = I2S_COMM_FORMAT_STAND_I2S;
  cfg.dma_desc_num = 8;
  cfg.dma_frame_num = 256;
  i2s_pin_config_t pins = {};
  pins.mck_io_num = I2S_PIN_NO_CHANGE;
  pins.bck_io_num = PIN_MIC_SCK;
  pins.ws_io_num = PIN_MIC_WS;
  pins.data_out_num = I2S_PIN_NO_CHANGE;
  pins.data_in_num = PIN_MIC_SD;
  i2s_driver_install(I2S_NUM_0, &cfg, 0, nullptr);
  i2s_set_pin(I2S_NUM_0, &pins);
  i2s_stop(I2S_NUM_0);                             // only clock the mic while recording
}

size_t micRecord(File& out, uint32_t maxMs, bool (*keepGoing)()) {
  static int32_t frames[512];                      // 256 stereo frames
  static int16_t pcm[256];
  size_t got, samples = 0;
  i2s_start(I2S_NUM_0);
  int64_t sumL = 0, sumR = 0;
  for (int i = 0; i < 4; i++) {                    // first 64 ms: settle, and find the mic's slot
    i2s_read(I2S_NUM_0, frames, sizeof(frames), &got, portMAX_DELAY);
    for (size_t j = 0; j < got / 8; j++) {
      sumL += abs(frames[2 * j] >> 16);
      sumR += abs(frames[2 * j + 1] >> 16);
    }
  }
  int slot = sumR > sumL ? 1 : 0;
  uint32_t start = millis();
  while (millis() - start < maxMs && keepGoing()) {
    i2s_read(I2S_NUM_0, frames, sizeof(frames), &got, portMAX_DELAY);
    size_t n = got / 8;
    for (size_t j = 0; j < n; j++) pcm[j] = constrain(frames[2 * j + slot] >> MIC_SHIFT, -32768, 32767);
    out.write((const uint8_t*)pcm, n * 2);
    samples += n;
  }
  i2s_stop(I2S_NUM_0);
  return samples;
}
