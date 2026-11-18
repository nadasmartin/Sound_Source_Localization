// Samples 4 electret microphones with the ADC in continuous (DMA) mode and
// streams them to the PC over Wi-Fi (TCP port 3333, host "esp32-mics.local").
//
// The work is split across the ESP32's two cores:
//   core 1 (Arduino loop): read ADC DMA blocks, average, pack into frames,
//                          push frames into a stream buffer
//   core 0 (netTask):      Wi-Fi + TCP, drain the stream buffer to the client
// The stream buffer absorbs Wi-Fi stalls so sampling never has to wait.
//
// Frame format (little-endian):
//   0xAA 0x55        sync bytes, so the PC can find the frame start
//   uint16 seq       frame counter, lets the PC detect lost frames
//   uint16 ovf       how many times the ADC DMA buffer overflowed (total)
//   FRAME_SETS x 6B  each set = one sample of all 4 mics, 12 bits each,
//                    packed as two pairs: [a0..7][a8..11|b0..3][b4..11]

#include <Arduino.h>
#include <ESPmDNS.h>
#include <WiFi.h>
#include <esp_adc/adc_continuous.h>
#include <freertos/stream_buffer.h>

#include "wifi_secrets.h"

constexpr int NUM_MICS = 4;
// GPIO34, 35, 32, 33 are ADC1 channels 6, 7, 4, 5 (only ADC1 supports DMA)
constexpr adc_channel_t MIC_CHANNELS[NUM_MICS] = {
    ADC_CHANNEL_6, ADC_CHANNEL_7, ADC_CHANNEL_4, ADC_CHANNEL_5};

// Wi-Fi measured ~410 kB/s. 44100 sets/s * 6 B = 265 kB/s.
constexpr uint32_t SAMPLE_RATE = 44100;  // per microphone, after averaging
constexpr uint32_t OVERSAMPLE = 4;
constexpr uint32_t ADC_RATE = SAMPLE_RATE * OVERSAMPLE * NUM_MICS;  // total conversions/s

constexpr size_t FRAME_SETS = 128;
constexpr size_t DMA_FRAME_BYTES = 4096;  // bytes the driver hands us per read
// Wi-Fi needs ~100 KB of heap for itself; a bigger buffer made it crash.
constexpr size_t STREAM_BUF_BYTES = 48 * 1024;  // ~0.18 s of audio
constexpr uint16_t TCP_PORT = 3333;

static adc_continuous_handle_t adc;
static StreamBufferHandle_t stream;
static volatile uint16_t overflows = 0;
static volatile bool clientConnected = false;

static uint8_t frame[6 + FRAME_SETS * 6];
static uint16_t seq = 0;

// Channel number -> mic index (-1 = not ours), so the hot loop needs no search.
static int8_t micOfChannel[16];

// Per-microphone averaging state and output position.
static uint32_t accum[NUM_MICS];
static uint32_t accumCount[NUM_MICS];
static size_t outIdx[NUM_MICS];
static uint16_t out[FRAME_SETS][NUM_MICS];

// Called from an interrupt when the ADC produced data faster than we read it.
static bool IRAM_ATTR onOverflow(adc_continuous_handle_t, const adc_continuous_evt_data_t *, void *) {
  overflows = overflows + 1;
  return false;
}

static void queueFrame() {
  frame[0] = 0xAA;
  frame[1] = 0x55;
  frame[2] = seq & 0xFF;
  frame[3] = seq >> 8;
  frame[4] = overflows & 0xFF;
  frame[5] = overflows >> 8;
  uint8_t *p = frame + 6;
  for (size_t s = 0; s < FRAME_SETS; s++) {
    for (int m = 0; m < NUM_MICS; m += 2) {
      uint16_t a = out[s][m], b = out[s][m + 1];
      *p++ = a & 0xFF;
      *p++ = (a >> 8) | ((b & 0x0F) << 4);
      *p++ = b >> 4;
    }
  }
  // Never block the sampling core: if the network fell behind and the buffer
  // is full, drop this frame. The PC sees the gap in seq.
  if (clientConnected && xStreamBufferSpacesAvailable(stream) >= sizeof(frame))
    xStreamBufferSend(stream, frame, sizeof(frame), 0);
  seq++;
}

// Core 0: keep Wi-Fi up, accept one TCP client, ship the buffered frames.
static void netTask(void *) {
  WiFi.mode(WIFI_STA);
  WiFi.setSleep(false);  // power saving adds latency and cuts throughput
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  // Each transmit burst draws a current spike that ripples the 3.3 V rail the
  // mics share. Lower power = smaller spikes = less noise; 8.5 dBm is plenty
  // indoors and kept the full 275 kB/s.
  WiFi.setTxPower(WIFI_POWER_8_5dBm);
  while (WiFi.status() != WL_CONNECTED) vTaskDelay(pdMS_TO_TICKS(250));
  Serial.printf("Wi-Fi up: %s (RSSI %d dBm), stream on port %u\n",
                WiFi.localIP().toString().c_str(), WiFi.RSSI(), TCP_PORT);
  MDNS.begin("esp32-mics");
  Serial.printf("free heap with Wi-Fi up: %lu bytes\n", (unsigned long)ESP.getFreeHeap());

  WiFiServer server(TCP_PORT);
  server.begin();
  static uint8_t chunk[8192];
  for (;;) {
    WiFiClient client = server.accept();
    if (!client) {
      vTaskDelay(pdMS_TO_TICKS(100));
      continue;
    }
    client.setNoDelay(true);
    xStreamBufferReset(stream);  // start the client with fresh audio
    clientConnected = true;
    Serial.printf("client %s connected\n", client.remoteIP().toString().c_str());
    while (client.connected()) {
      size_t n = xStreamBufferReceive(stream, chunk, sizeof(chunk), pdMS_TO_TICKS(100));
      if (n && client.write(chunk, n) != n) break;
    }
    clientConnected = false;
    client.stop();
    Serial.println("client disconnected");
  }
}

void setup() {
  Serial.begin(115200);

  stream = xStreamBufferCreate(STREAM_BUF_BYTES, 1);
  if (!stream) {
    Serial.println("not enough RAM for the stream buffer");
    for (;;) delay(1000);
  }

  for (auto &m : micOfChannel) m = -1;
  for (int i = 0; i < NUM_MICS; i++) micOfChannel[MIC_CHANNELS[i]] = i;

  adc_continuous_handle_cfg_t handleCfg = {
      .max_store_buf_size = 16384,  // DMA ring buffer
      .conv_frame_size = DMA_FRAME_BYTES,
  };
  ESP_ERROR_CHECK(adc_continuous_new_handle(&handleCfg, &adc));

  // The "pattern" is the list of channels the ADC cycles through.
  adc_digi_pattern_config_t pattern[NUM_MICS];
  for (int i = 0; i < NUM_MICS; i++) {
    pattern[i].atten = ADC_ATTEN_DB_12;  // input range ~0..3.1 V
    pattern[i].channel = MIC_CHANNELS[i];
    pattern[i].unit = ADC_UNIT_1;
    pattern[i].bit_width = ADC_BITWIDTH_12;
  }
  adc_continuous_config_t cfg = {
      .pattern_num = NUM_MICS,
      .adc_pattern = pattern,
      .sample_freq_hz = ADC_RATE,
      .conv_mode = ADC_CONV_SINGLE_UNIT_1,
      .format = ADC_DIGI_OUTPUT_FORMAT_TYPE1,  // the only format the ESP32 supports
  };
  ESP_ERROR_CHECK(adc_continuous_config(adc, &cfg));

  adc_continuous_evt_cbs_t cbs = {};
  cbs.on_pool_ovf = onOverflow;
  ESP_ERROR_CHECK(adc_continuous_register_event_callbacks(adc, &cbs, nullptr));
  ESP_ERROR_CHECK(adc_continuous_start(adc));

  // Wi-Fi's own tasks run on core 0, so the network task goes there too.
  xTaskCreatePinnedToCore(netTask, "net", 8192, nullptr, 2, nullptr, 0);
  Serial.printf("free heap after setup: %lu bytes\n", (unsigned long)ESP.getFreeHeap());
}

void loop() {
  static uint8_t dma[DMA_FRAME_BYTES];
  uint32_t got = 0;
  // Poll without blocking: keeping the CPU busy keeps its current draw
  // constant. Sleeping and waking per DMA block made the 3.3 V supply ripple,
  // and the mic amplifiers picked that up as a tone.
  if (adc_continuous_read(adc, dma, sizeof(dma), &got, 0) != ESP_OK) return;

  // Each result is 2 bytes: 12-bit value + 4-bit channel number.
  const auto *results = reinterpret_cast<const adc_digi_output_data_t *>(dma);
  for (size_t i = 0; i < got / sizeof(adc_digi_output_data_t); i++) {
    int m = micOfChannel[results[i].type1.channel];
    if (m < 0) continue;
    accum[m] += results[i].type1.data;
    if (++accumCount[m] < OVERSAMPLE) continue;

    if (outIdx[m] < FRAME_SETS) out[outIdx[m]++][m] = accum[m] / OVERSAMPLE;
    accum[m] = 0;
    accumCount[m] = 0;

    // Send once every mic has filled the frame. The ADC scans the channels in
    // turn, so they fill at the same pace.
    bool full = true;
    for (int k = 0; k < NUM_MICS; k++) full &= outIdx[k] == FRAME_SETS;
    if (full) {
      queueFrame();
      for (int k = 0; k < NUM_MICS; k++) outIdx[k] = 0;
    }
  }
}
