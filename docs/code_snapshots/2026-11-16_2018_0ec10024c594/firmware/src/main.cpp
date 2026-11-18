// On-board sound source localization. No Wi-Fi: everything is computed on the
// ESP32 and only the results go to the PC, as JSON lines over the USB serial
// port (921600 baud). Host side: host/telemetry.py.
//
// The work is split across the ESP32's two cores:
//   core 1 (Arduino loop): read ADC DMA blocks, average, push every set
//                          (one sample of all 4 mics) into the ring buffer
//   core 0 (dspTask):      streaming matched filter over the ring finds the
//                          test chirp and copies the window around it; then
//                          GCC-PHAT, arrival times, 3D position, telemetry,
//                          serial commands. Detection and processing take
//                          turns because they share one 32 KB FFT buffer
//                          (the heap has no second block that large); the
//                          ring holds enough audio to cover ~100 ms of processing.
// The DSP itself is in lib/tdoa (also built on the PC by test_native/).
//
// Serial output, one JSON object per line:
//   {"type":"event", ...}   one per detected chirp (see formatEventJson)
//   {"type":"status", ...}  once a second
//   {"type":"dump", ...}    raw window of one chirp, on request (base64 uint16 LE [n][4])
//   {"type":"info"/"error", "msg":...}
//   {"type":"sig", "ok":..}  answer to a template upload
//   {"type":"levels", ...}  per-mic loudness, while "levels <hz>" is on
//   {"type":"scope", ...}   live waveform, averaged down, while "scope <avg>" is on
// Commands (one per line):
//   temp <C> | thr <x> | holdoff <s> | dump | status
//   levels <hz>                     stream per-mic levels <hz> times a second
//                                   (0 = off): to identify / check the mics
//   scope <avg>                     stream the waveform, each value the average of
//                                   <avg> samples (6..64; 0 = off), 20x a second
//   array <side cm>                 mic square side length (10..60 cm), saved in
//                                   flash; Mic1 (-h,+h) Mic2 (+h,+h) Mic3 (+h,-h) Mic4 (-h,-h)
//   micdelay <d1> <d2> <d3> <d4>    per-mic channel delay calibration in us,
//                                   saved in flash (survives reboots)
//   sig_begin <len> <k_lo> <k_hi>   start uploading a new template: len samples
//                                   at FS, analysis band = FFT bins k_lo..k_hi
//   sig_data <offset> <base64>      template samples, int16 LE (any scale)
//   sig_end <checksum>              checksum = sum of all int16 samples mod 2^32
//   sig_default                     back to the boot-time chirp
// Detection is paused during an upload (the template is staged in the FFT buffer).

#include <Arduino.h>
#include <Preferences.h>
#include <esp_adc/adc_continuous.h>
#include <esp_heap_caps.h>
#include <esp_timer.h>

#include "detector.h"
#include "tdoa.h"

using namespace dsp;

#ifndef FW_SRC_HASH
#define FW_SRC_HASH "unknown"
#endif

// GPIO34, 35, 32, 33 are ADC1 channels 6, 7, 4, 5 (only ADC1 supports DMA)
constexpr adc_channel_t MIC_CHANNELS[NUM_MICS] = {
    ADC_CHANNEL_6, ADC_CHANNEL_7, ADC_CHANNEL_4, ADC_CHANNEL_5};
constexpr uint32_t ADC_RATE = FS * OVERSAMPLE * NUM_MICS;  // total conversions/s
constexpr size_t DMA_FRAME_BYTES = 4096;  // bytes the driver hands us per read
constexpr size_t FRAME_SETS = 128;
constexpr uint32_t SERIAL_BAUD = 921600;

static adc_continuous_handle_t adc;
static volatile uint32_t adcOverflows = 0;

static Fft fft;
static Ring ring;
static Detector detector;
static TdoaProcessor processor;

// The window of the last chirp found, waiting to be processed
static uint16_t window[MAX_GCC_LEN][NUM_MICS];
static Chirp windowChirp;
static bool windowPending = false;
static uint32_t droppedChirps = 0;  // found while one was already waiting

static float tempC = 21.0f;
static bool dumpNext = false;
static uint64_t dspBusyUs = 0;
static float levelsHz = 0;      // "levels" stream rate, 0 = off  // time spent detecting + processing, for the load figure

// Template upload in progress (see handleCommand)
static struct {
  bool active = false;
  SignalInfo sig;
  uint32_t checksum = 0;
  int64_t startedUs = 0;
} upload;

// Channel number -> mic index (-1 = not ours), so the hot loop needs no search.
static int8_t micOfChannel[16];

static bool IRAM_ATTR onOverflow(adc_continuous_handle_t, const adc_continuous_evt_data_t *, void *) {
  adcOverflows = adcOverflows + 1;
  return false;
}

// ------------------------------------------------------------------ core 0

// Runs inside detector.poll() while the window is still in the ring. Only
// copies: the processing must wait until poll() no longer needs the FFT buffer.
static void onChirp(void *, const Chirp &c, const Ring &r) {
  if (windowPending) {
    droppedChirps++;
    return;
  }
  r.copy(c.start - GCC_PRE, detector.signal().gccLen(), window);
  windowChirp = c;
  windowPending = true;
}

static void writeB64(const uint8_t *bytes, size_t n) {
  static const char B64[] = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
  char out[256];
  size_t o = 0;
  for (size_t i = 0; i < n; i += 3) {
    const uint32_t v = bytes[i] << 16 | (i + 1 < n ? bytes[i + 1] << 8 : 0) | (i + 2 < n ? bytes[i + 2] : 0);
    out[o++] = B64[v >> 18 & 63];
    out[o++] = B64[v >> 12 & 63];
    out[o++] = i + 1 < n ? B64[v >> 6 & 63] : '=';
    out[o++] = i + 2 < n ? B64[v & 63] : '=';
    if (o >= sizeof(out) - 4) Serial.write(out, o), o = 0;
  }
  Serial.write(out, o);
}

static void printDump(uint32_t eventNo) {
  const int len = detector.signal().gccLen();
  Serial.printf("{\"type\":\"dump\",\"n\":%lu,\"start\":%lu,\"pre\":%d,\"len\":%d,\"b64\":\"",
                (unsigned long)eventNo, (unsigned long)(windowChirp.start - GCC_PRE), GCC_PRE, len);
  writeB64(reinterpret_cast<const uint8_t *>(window), sizeof(window[0]) * len);
  Serial.println("\"}");
}

// Live waveform for the viewer (host/mic_viewer.py). The full 44.1 kHz audio
// does not fit through the serial port, so every `scopeAvg` sets are averaged
// into one (scopeAvg 8 -> 5.5 kHz per mic). Values are the average x 16
// (uint16 LE, [set][mic]): the averaging adds resolution below one ADC count.
static int scopeAvg = 0;  // 0 = off
static void printScope() {
  constexpr int MAX_OUT = 600;
  static uint32_t from = 0;
  static bool running = false;
  static uint16_t out[MAX_OUT][NUM_MICS];
  const uint32_t end = ring.count();
  bool gap = false;
  if (!running || end - from > RING_LEN / 2) {  // first call, or fell behind
    gap = running;
    running = true;
    from = end;
    if (!gap) return;
  }
  int ns = (end - from) / scopeAvg;
  if (ns <= 0) return;
  if (ns > MAX_OUT) ns = MAX_OUT;
  uint16_t v[NUM_MICS];
  uint32_t i = from;
  for (int k = 0; k < ns; k++) {
    uint32_t acc[NUM_MICS] = {};
    for (int j = 0; j < scopeAvg; j++, i++) {
      ring.get(i, v);
      for (int m = 0; m < NUM_MICS; m++) acc[m] += v[m];
    }
    for (int m = 0; m < NUM_MICS; m++) out[k][m] = (acc[m] * 16 + scopeAvg / 2) / scopeAvg;
  }
  Serial.printf("{\"type\":\"scope\",\"n0\":%lu,\"avg\":%d,\"ns\":%d,\"gap\":%s,\"b64\":\"",
                (unsigned long)from, scopeAvg, ns, gap ? "true" : "false");
  writeB64(reinterpret_cast<const uint8_t *>(out), sizeof(out[0]) * ns);
  Serial.println("\"}");
  from = i;
}

static void printStatus() {
  static uint32_t lastCount = 0;
  static int64_t lastTime = 0;
  static uint64_t lastBusy = 0;
  const int64_t now = esp_timer_get_time();
  const uint32_t count = ring.count();
  const uint64_t busy = dspBusyUs;
  const float dt = (now - lastTime) / 1e6f;
  const float rate = lastTime ? (count - lastCount) / dt : 0;
  const float load = lastTime ? (busy - lastBusy) / 1e4f / dt : 0;  // percent of core 0
  lastCount = count, lastTime = now, lastBusy = busy;
  Serial.printf(
      "{\"type\":\"status\",\"up_s\":%.1f,\"fs\":%.0f,\"adc_ovf\":%lu,\"noise\":%.0f,"
      "\"thr\":%.1f,\"temp\":%.1f,\"chirps\":%lu,\"dropped\":%lu,\"overruns\":%lu,"
      "\"dsp_load\":%.1f,\"heap\":%lu,\"sig\":[%d,%.0f,%.0f],\"holdoff\":%.2f,"
      "\"micdelay_us\":[%.2f,%.2f,%.2f,%.2f],\"array_cm\":%.1f,\"fw\":\"%s\"}\n",
      now / 1e6, rate, (unsigned long)adcOverflows, detector.noise(), detector.threshold,
      (float)tempC, (unsigned long)detector.chirps(), (unsigned long)droppedChirps,
      (unsigned long)detector.overruns(), load, (unsigned long)ESP.getFreeHeap(),
      detector.signal().len, detector.signal().fLo(), detector.signal().fHi(), detector.holdoffS,
      processor.micDelay[0] * 1e6f, processor.micDelay[1] * 1e6f, processor.micDelay[2] * 1e6f,
      processor.micDelay[3] * 1e6f, arraySide() * 100, FW_SRC_HASH);
}

// Loudness of every mic over the samples since the last call: AC rms, DC,
// peak-to-peak and samples at the ADC limits (raw 12-bit counts).
static void printLevels() {
  static uint32_t from = 0;
  const uint32_t end = ring.count();
  uint32_t n = end - from;
  if (n > RING_LEN / 2) n = RING_LEN / 2;  // keep clear of the writer
  from = end;
  if (!n) return;
  uint64_t sum[NUM_MICS] = {}, sq[NUM_MICS] = {};
  uint16_t lo[NUM_MICS], hi[NUM_MICS];
  uint32_t clip[NUM_MICS] = {};
  for (int m = 0; m < NUM_MICS; m++) lo[m] = 0xFFFF, hi[m] = 0;
  uint16_t v[NUM_MICS];
  for (uint32_t i = end - n; i != end; i++) {
    ring.get(i, v);
    for (int m = 0; m < NUM_MICS; m++) {
      sum[m] += v[m];
      sq[m] += uint32_t(v[m]) * v[m];
      if (v[m] < lo[m]) lo[m] = v[m];
      if (v[m] > hi[m]) hi[m] = v[m];
      if (v[m] == 0 || v[m] >= 4095) clip[m]++;
    }
  }
  float dc[NUM_MICS], rms[NUM_MICS];
  for (int m = 0; m < NUM_MICS; m++) {
    dc[m] = float(sum[m]) / n;
    const float var = float(sq[m]) / n - dc[m] * dc[m];
    rms[m] = var > 0 ? sqrtf(var) : 0;
  }
  Serial.printf("{\"type\":\"levels\",\"n\":%lu,\"rms\":[%.1f,%.1f,%.1f,%.1f],"
                "\"dc\":[%.0f,%.0f,%.0f,%.0f],\"pp\":[%d,%d,%d,%d],\"clip\":[%lu,%lu,%lu,%lu]}\n",
                (unsigned long)n, rms[0], rms[1], rms[2], rms[3], dc[0], dc[1], dc[2], dc[3],
                hi[0] - lo[0], hi[1] - lo[1], hi[2] - lo[2], hi[3] - lo[3], (unsigned long)clip[0],
                (unsigned long)clip[1], (unsigned long)clip[2], (unsigned long)clip[3]);
}

static int b64val(char c) {
  if (c >= 'A' && c <= 'Z') return c - 'A';
  if (c >= 'a' && c <= 'z') return c - 'a' + 26;
  if (c >= '0' && c <= '9') return c - '0' + 52;
  if (c == '+') return 62;
  if (c == '/') return 63;
  return -1;
}

// Decode base64 into out (at most maxBytes). Returns the byte count, -1 on bad input.
static int b64decode(const char *in, uint8_t *out, int maxBytes) {
  int n = 0, bits = 0;
  uint32_t acc = 0;
  for (; *in && *in != '='; in++) {
    const int v = b64val(*in);
    if (v < 0) return -1;
    acc = acc << 6 | v;
    bits += 6;
    if (bits >= 8) {
      bits -= 8;
      if (n >= maxBytes) return -1;
      out[n++] = acc >> bits & 0xFF;
    }
  }
  return n;
}

static void sigReply(bool ok, const char *msg) {
  const SignalInfo &s = detector.signal();
  Serial.printf("{\"type\":\"sig\",\"ok\":%s,\"msg\":\"%s\",\"len\":%d,\"k_lo\":%d,\"k_hi\":%d,"
                "\"f_lo\":%.1f,\"f_hi\":%.1f}\n",
                ok ? "true" : "false", msg, s.len, s.kLo, s.kHi, s.fLo(), s.fHi());
}

static void handleSigCommand(char *line) {
  int len, kLo, kHi;
  unsigned long offset, checksum;
  char b64[1000];
  if (sscanf(line, "sig_begin %d %d %d", &len, &kLo, &kHi) == 3) {
    upload.sig.len = len, upload.sig.kLo = kLo, upload.sig.kHi = kHi;
    if (!upload.sig.valid()) return sigReply(false, "invalid length or band");
    detector.stage();  // zeroes the staging buffer
    upload.active = true;
    upload.checksum = 0;
    upload.startedUs = esp_timer_get_time();
    Serial.println("{\"type\":\"info\",\"msg\":\"template upload started\"}");
  } else if (sscanf(line, "sig_data %lu %999s", &offset, b64) == 2) {
    if (!upload.active) return sigReply(false, "sig_data without sig_begin");
    static uint8_t bytes[750];
    const int n = b64decode(b64, bytes, sizeof(bytes));
    if (n < 0 || n % 2 || offset + n / 2 > (unsigned long)upload.sig.len) {
      upload.active = false;
      return sigReply(false, "bad sig_data chunk");
    }
    cpx *stage = detector.stagingBuffer();
    for (int i = 0; i < n / 2; i++) {
      const int16_t v = int16_t(bytes[2 * i] | bytes[2 * i + 1] << 8);
      stage[offset + i].re = v / 32768.0f;
      upload.checksum += uint32_t(int32_t(v));
    }
  } else if (sscanf(line, "sig_end %lu", &checksum) == 1) {
    if (!upload.active) return sigReply(false, "sig_end without sig_begin");
    upload.active = false;
    if (uint32_t(checksum) != upload.checksum) return sigReply(false, "checksum mismatch");
    if (!detector.setTemplate(upload.sig)) return sigReply(false, "rejected");
    processor.setSignal(detector.signal());
    sigReply(true, "template loaded");
  } else if (strcmp(line, "sig_default") == 0) {
    upload.active = false;
    defaultChirp(detector.stage());
    detector.setTemplate(SignalInfo{});
    processor.setSignal(detector.signal());
    sigReply(true, "default chirp");
  } else {
    sigReply(false, "usage: sig_begin <len> <k_lo> <k_hi> | sig_data <offset> <b64> | sig_end <sum>");
  }
}

// Per-mic delay calibration, kept in flash (NVS)
static void loadMicDelay() {
  Preferences prefs;
  prefs.begin("tdoa", true);
  if (prefs.getBytesLength("micdelay") == sizeof(processor.micDelay))
    prefs.getBytes("micdelay", processor.micDelay, sizeof(processor.micDelay));
  prefs.end();
}

static void loadArray() {
  Preferences prefs;
  prefs.begin("tdoa", true);
  const float a = prefs.getFloat("array", DEFAULT_ARRAY_SIDE);
  prefs.end();
  setArraySide(a);
}

static void saveMicDelay() {
  Preferences prefs;
  prefs.begin("tdoa", false);
  prefs.putBytes("micdelay", processor.micDelay, sizeof(processor.micDelay));
  prefs.end();
}

static void handleCommand(char *line) {
  float v, d[NUM_MICS];
  if (strncmp(line, "sig_", 4) == 0) {
    handleSigCommand(line);
  } else if (sscanf(line, "temp %f", &v) == 1 && v > -30 && v < 60) {
    tempC = v;
    Serial.printf("{\"type\":\"info\",\"msg\":\"temp %.1f C, c = %.1f m/s\"}\n", v, speedOfSound(v));
  } else if (sscanf(line, "thr %f", &v) == 1 && v > 1) {
    detector.threshold = v;
    Serial.printf("{\"type\":\"info\",\"msg\":\"threshold %.1f\"}\n", v);
  } else if (sscanf(line, "micdelay %f %f %f %f", &d[0], &d[1], &d[2], &d[3]) == 4) {
    for (int m = 0; m < NUM_MICS; m++) processor.micDelay[m] = d[m] * 1e-6f;
    saveMicDelay();
    Serial.printf("{\"type\":\"info\",\"msg\":\"mic delays %.2f %.2f %.2f %.2f us (saved)\"}\n",
                  d[0], d[1], d[2], d[3]);
  } else if (sscanf(line, "array %f", &v) == 1 && v >= 5 && v <= 60) {
    setArraySide(v / 100);
    Preferences prefs;
    prefs.begin("tdoa", false);
    prefs.putFloat("array", v / 100);
    prefs.end();
    Serial.printf("{\"type\":\"info\",\"msg\":\"array side %.1f cm (saved)\"}\n", v);
  } else if (sscanf(line, "holdoff %f", &v) == 1 && v >= 0.06f && v <= 5) {
    detector.holdoffS = v;
    Serial.printf("{\"type\":\"info\",\"msg\":\"holdoff %.2f s\"}\n", v);
  } else if (sscanf(line, "levels %f", &v) == 1 && v >= 0 && v <= 50) {
    levelsHz = v;
    Serial.printf("{\"type\":\"info\",\"msg\":\"levels %.0f per second\"}\n", v);
  } else if (sscanf(line, "scope %f", &v) == 1 && (v == 0 || (v >= 6 && v <= 64))) {
    scopeAvg = int(v);
    Serial.printf("{\"type\":\"info\",\"msg\":\"scope: average of %d sets, %.0f Hz per mic\"}\n",
                  scopeAvg, scopeAvg ? float(FS) / scopeAvg : 0.0f);
  } else if (strcmp(line, "dump") == 0) {
    dumpNext = true;
    Serial.println("{\"type\":\"info\",\"msg\":\"raw window of the next chirp will follow\"}");
  } else if (strcmp(line, "status") == 0) {
    printStatus();
  } else if (line[0]) {
    Serial.println("{\"type\":\"error\",\"msg\":\"commands: temp <C> | thr <x> | holdoff <s> | dump | "
                   "status | array <cm> | levels <hz> | scope <avg> | micdelay <us x4> | sig_begin/sig_data/sig_end | sig_default\"}");
  }
}

static void pollSerial() {
  static char line[1100];  // sig_data lines are ~700 characters
  static size_t len = 0;
  static bool overflow = false;
  while (Serial.available()) {
    const char ch = Serial.read();
    if (ch == '\n' || ch == '\r') {
      line[len] = 0;
      if (overflow)
        Serial.println("{\"type\":\"error\",\"msg\":\"command line too long\"}");
      else
        handleCommand(line);
      len = 0;
      overflow = false;
    } else if (len < sizeof(line) - 1) {
      line[len++] = ch;
    } else {
      overflow = true;
    }
  }
  // An abandoned upload must not pause detection forever
  if (upload.active && esp_timer_get_time() - upload.startedUs > 5000000) {
    upload.active = false;
    sigReply(false, "upload timed out, old template kept");
  }
}

static void dspTask(void *) {
  uint32_t events = 0;
  int64_t lastStatus = 0;
  char json[512];
  for (;;) {
    const int64_t t0 = esp_timer_get_time();
    if (!upload.active) detector.poll(ring, onChirp, nullptr);
    if (windowPending) {
      TdoaResult r;
      r.mfSnr = windowChirp.snr;
      const int64_t t1 = esp_timer_get_time();
      processor.process(window, speedOfSound(tempC), r);
      const float ms = (esp_timer_get_time() - t1) / 1000.0f;
      formatEventJson(json, sizeof(json), ++events, double(windowChirp.start) / FS, r, ms);
      Serial.println(json);
      if (dumpNext) {
        // ~0.3 s of serial output: the detector falls behind and skips ahead (an overrun)
        dumpNext = false;
        printDump(events);
      }
      windowPending = false;
    }
    dspBusyUs += esp_timer_get_time() - t0;
    pollSerial();
    static int64_t lastLevels = 0;
    if (levelsHz > 0 && esp_timer_get_time() - lastLevels >= int64_t(1e6f / levelsHz)) {
      lastLevels = esp_timer_get_time();
      printLevels();
    }
    static int64_t lastScope = 0;
    if (scopeAvg > 0 && esp_timer_get_time() - lastScope >= 50000) {
      lastScope = esp_timer_get_time();
      printScope();
    }
    if (esp_timer_get_time() - lastStatus >= 1000000) {
      lastStatus = esp_timer_get_time();
      printStatus();
    }
    vTaskDelay(pdMS_TO_TICKS(5));  // a block pair arrives every 86 ms
  }
}

// ------------------------------------------------------------------ setup

static void fail(const char *what) {
  heap_caps_print_heap_info(MALLOC_CAP_8BIT);
  for (;;) {
    Serial.printf("{\"type\":\"error\",\"msg\":\"%s\"}\n", what);
    delay(2000);
  }
}

void setup() {
  Serial.setTxBufferSize(4096);
  Serial.setRxBufferSize(4096);  // template uploads arrive in ~700-byte lines
  Serial.begin(SERIAL_BAUD);
  Serial.printf("\n{\"type\":\"info\",\"msg\":\"on-board TDOA, free heap %lu, largest block %lu\"}\n",
                (unsigned long)ESP.getFreeHeap(), (unsigned long)ESP.getMaxAllocHeap());

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

  // DSP buffers after the ADC driver, which needs DMA-capable RAM first, and
  // the one big block (32 KB) before the small ones fragment the heap. The
  // ring goes to the 32-bit-only IRAM heap where possible (see lib/tdoa/mem.h).
  static cpx *work = static_cast<cpx *>(malloc(sizeof(cpx) * NFFT));
  if (!work) fail("not enough RAM: fft work");
  if (!fft.begin(NFFT)) fail("not enough RAM: fft");
  if (!ring.begin()) fail("not enough RAM: ring");
  if (!detector.begin(&fft, work)) fail("not enough RAM: detector");
  if (!processor.begin(&fft, work)) fail("not enough RAM: processor");
  loadMicDelay();
  loadArray();

  adc_continuous_evt_cbs_t cbs = {};
  cbs.on_pool_ovf = onOverflow;
  ESP_ERROR_CHECK(adc_continuous_register_event_callbacks(adc, &cbs, nullptr));
  ESP_ERROR_CHECK(adc_continuous_start(adc));

  xTaskCreatePinnedToCore(dspTask, "dsp", 8192, nullptr, 2, nullptr, 0);
  Serial.printf("{\"type\":\"info\",\"msg\":\"running, free heap %lu (byte-addressable %lu)\"}\n",
                (unsigned long)ESP.getFreeHeap(), (unsigned long)heap_caps_get_free_size(MALLOC_CAP_8BIT));
}

// ------------------------------------------------------------------ core 1

void loop() {
  static uint8_t dma[DMA_FRAME_BYTES];
  static uint32_t accum[NUM_MICS], accumCount[NUM_MICS];
  static size_t outIdx[NUM_MICS];
  static uint16_t out[FRAME_SETS][NUM_MICS];

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

    // Hand over once every mic has filled the frame. The ADC scans the
    // channels in turn, so they fill at the same pace.
    bool full = true;
    for (int k = 0; k < NUM_MICS; k++) full &= outIdx[k] == FRAME_SETS;
    if (full) {
      for (size_t s = 0; s < FRAME_SETS; s++) ring.push(out[s]);
      for (int k = 0; k < NUM_MICS; k++) outIdx[k] = 0;
    }
  }
}
