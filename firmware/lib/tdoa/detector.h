// Ring buffer of recent audio + streaming matched-filter chirp detector.
//
// The sampling core only calls Ring::push(). The detector (another task)
// correlates the mic sum with the known chirp block by block (a streaming
// matched filter): a peak above `threshold` x the median correlation is a chirp start. The chirp is
// usually far below the background noise per sample (~25 dB processing gain
// from the 50 ms sweep), so a plain loudness trigger would not see it.
#pragma once

#include <stdint.h>

#include "dsp_config.h"
#include "fft.h"

namespace dsp {

class Ring {
 public:
  bool begin();  // false if out of memory
  // One set = one sample of every mic, raw 12-bit ADC values. Single writer.
  void push(const uint16_t set[NUM_MICS]) {
    const uint32_t n = count_;
    uint32_t *dst = slot(n);
    dst[0] = set[0] | uint32_t(set[1]) << 16;
    dst[1] = set[2] | uint32_t(set[3]) << 16;
    count_ = n + 1;  // publish after the data
  }
  uint32_t count() const { return count_; }  // sets written so far
  void get(uint32_t abs, uint16_t out[NUM_MICS]) const {
    const uint32_t *w = const_cast<Ring *>(this)->slot(abs);
    const uint32_t a = w[0], b = w[1];
    out[0] = a & 0xFFFF, out[1] = a >> 16, out[2] = b & 0xFFFF, out[3] = b >> 16;
  }
  float sum(uint32_t abs) const {  // sum of the 4 mics
    const uint32_t *w = const_cast<Ring *>(this)->slot(abs);
    const uint32_t a = w[0], b = w[1];
    return float((a & 0xFFFF) + (a >> 16) + (b & 0xFFFF) + (b >> 16));
  }
  void copy(uint32_t from, int n, uint16_t (*dst)[NUM_MICS]) const;

 private:
  // Stored as 32-bit words, two samples each: see mem.h for why.
  uint32_t *slot(uint32_t abs) {
    const uint32_t i = abs % RING_LEN;
    return chunks_[i / RING_CHUNK] + 2 * (i % RING_CHUNK);
  }
  uint32_t *chunks_[RING_CHUNKS] = {};
  volatile uint32_t count_ = 0;
};

struct Chirp {
  uint32_t start;  // absolute sample index of the chirp start
  float snr;       // matched-filter peak / median
};

class Detector {
 public:
  // fft: NFFT points. work: NFFT cpx, may be shared with TdoaProcessor as
  // long as the two never run at the same time. False if out of memory.
  bool begin(const Fft *fft, cpx *work);
  // Process every complete block pair available in the ring. For each chirp
  // found, calls onChirp(ctx, chirp, ring) while the GCC window
  // [start - GCC_PRE, start - GCC_PRE + signal().gccLen()) is still in the ring.
  // Returns the number of block pairs processed.
  typedef void (*Callback)(void *ctx, const Chirp &c, const Ring &ring);
  int poll(const Ring &ring, Callback onChirp, void *ctx);

  // Replace the template: fill stage()[n].re for n < sig.len (the time
  // signal at FS, any scale), then setTemplate(sig). stage() is the shared
  // work buffer, so neither poll() nor the processor may run in between.
  // setTemplate returns false (and keeps the old template) if sig is invalid.
  cpx *stage();                         // clears the staging buffer and returns it
  cpx *stagingBuffer() { return work_; }  // the same buffer, not cleared
  bool setTemplate(const SignalInfo &sig);
  const SignalInfo &signal() const { return sig_; }

  float threshold = DEFAULT_MF_THRESHOLD;
  float holdoffS = HOLDOFF_S;  // ignore new detections this long after one
  float noise() const { return noise_; }        // median |correlation|
  uint32_t chirps() const { return chirps_; }
  uint32_t overruns() const { return overruns_; }  // fell so far behind that audio was lost

 private:
  void scan(const cpx *y, bool imag, uint32_t first, Callback cb, void *ctx, const Ring &ring);
  const Fft *fft_ = nullptr;
  cpx *work_ = nullptr;   // NFFT, not owned
  cpx *tmpl_ = nullptr;   // conj chirp spectrum, in-band bins
  float *mag_ = nullptr;  // every MEDIAN_STEP-th |correlation| of a block, for the median
  SignalInfo sig_;
  bool resync_ = true;    // jump to the newest audio on the next poll
  uint32_t next_ = 0;     // absolute index of the next correlation output
  uint32_t blocks_ = 0;
  float noise_ = 0;
  bool candidate_ = false;
  uint32_t candBest_ = 0, candEnd_ = 0, holdoffUntil_ = 0;
  float candVal_ = 0;
  uint32_t chirps_ = 0, overruns_ = 0;
};

// The boot-time chirp (= signals_lib.DEFAULT on the host) into work[0..CHIRP_LEN), rest zeroed
void defaultChirp(cpx *work);

}  // namespace dsp
