#include "detector.h"
#include "platform.h"

#include <math.h>
#include <stdlib.h>
#include <string.h>

#include <algorithm>

namespace dsp {

static constexpr int H = MF_HOP;
static constexpr uint32_t PAIR_INPUT = 2 * H + MAX_SIG_LEN - 1;  // samples one block pair reads
static constexpr uint32_t PEAK_WINDOW = uint32_t(MF_PEAK_WINDOW_S * FS);
static constexpr int WARMUP_BLOCKS = 4;
static constexpr float NOISE_ALPHA = 0.05f;
static constexpr int MEDIAN_STEP = 4;  // the median of every 4th value is plenty accurate
static constexpr int MEDIAN_N = H / MEDIAN_STEP;
// A shorter template is zero-padded to MAX_SIG_LEN, so H outputs per block stay valid
static_assert(H + MAX_SIG_LEN - 1 == NFFT, "overlap-save block must be one FFT");
static_assert(2 * H + GCC_PRE + PAIR_INPUT < RING_LEN, "ring too small for the detector latency");

static inline cpx cmul(cpx a, cpx b) { return {a.re * b.re - a.im * b.im, a.re * b.im + a.im * b.re}; }
static inline cpx cconj(cpx a) { return {a.re, -a.im}; }

// ------------------------------------------------------------------- ring

bool Ring::begin() {
  static_assert(NUM_MICS == 4, "the ring packs exactly 4 mics into 2 words");
  for (auto &c : chunks_) {
    c = allocWords32(2 * RING_CHUNK);
    if (!c) return false;
  }
  return true;
}

void Ring::copy(uint32_t from, int n, uint16_t (*dst)[NUM_MICS]) const {
  for (int i = 0; i < n; i++) get(from + i, dst[i]);
}

// --------------------------------------------------------------- template

void defaultChirp(cpx *work) {
  const double beta = (CHIRP_F_END - CHIRP_F_START) / CHIRP_SECONDS;
  for (int n = 0; n < NFFT; n++) work[n] = {0, 0};
  for (int n = 0; n < CHIRP_LEN; n++) {
    const double t = double(n) / FS;
    double v = cos(2.0 * M_PI * (CHIRP_F_START * t + 0.5 * beta * t * t));
    // 5 ms raised-cosine fades: 0.5 - 0.5 cos(linspace(0, pi, fade))
    if (n < CHIRP_FADE) v *= 0.5 - 0.5 * cos(M_PI * n / (CHIRP_FADE - 1));
    const int back = CHIRP_LEN - 1 - n;
    if (back < CHIRP_FADE) v *= 0.5 - 0.5 * cos(M_PI * back / (CHIRP_FADE - 1));
    work[n].re = float(v);
  }
}

// --------------------------------------------------------------- detector

bool Detector::begin(const Fft *fft, cpx *work) {
  fft_ = fft;
  work_ = work;
  tmpl_ = static_cast<cpx *>(malloc(sizeof(cpx) * N_BAND_MAX));
  mag_ = static_cast<float *>(malloc(sizeof(float) * MEDIAN_N));
  if (!work_ || !tmpl_ || !mag_) return false;
  defaultChirp(work_);
  return setTemplate(SignalInfo{});
}

cpx *Detector::stage() {
  for (int n = 0; n < NFFT; n++) work_[n] = {0, 0};
  return work_;
}

bool Detector::setTemplate(const SignalInfo &sig) {
  if (!sig.valid()) return false;
  for (int n = sig.len; n < NFFT; n++) work_[n] = {0, 0};
  fft_->forward(work_);
  for (int k = sig.kLo; k <= sig.kHi; k++) tmpl_[k - sig.kLo] = cconj(work_[k]);
  sig_ = sig;
  // Start over: new noise level, no half-finished candidate, skip stale audio
  blocks_ = 0;
  noise_ = 0;
  candidate_ = false;
  resync_ = true;
  return true;
}

int Detector::poll(const Ring &ring, Callback onChirp, void *ctx) {
  int pairs = 0;
  for (;;) {
    const uint32_t count = ring.count();
    if (resync_ && count >= PAIR_INPUT) {
      next_ = count - PAIR_INPUT;
      holdoffUntil_ = 0;
      resync_ = false;
    }
    if (resync_ || count < next_ + PAIR_INPUT) return pairs;
    // Too far behind: the oldest audio we need is about to be overwritten.
    if (count - next_ > RING_LEN - 2 * H - GCC_PRE - 512) {
      overruns_++;
      next_ = count - PAIR_INPUT;
      candidate_ = false;
      continue;
    }

    // Two overlap-save blocks in one complex FFT: block A real, block B imaginary
    float mean = 0;
    for (uint32_t n = 0; n < PAIR_INPUT; n++) mean += ring.sum(next_ + n);
    mean /= PAIR_INPUT;
    for (int n = 0; n < NFFT; n++)
      work_[n] = {ring.sum(next_ + n) - mean, ring.sum(next_ + H + n) - mean};
    fft_->forward(work_);
    // Correlate with the chirp, keeping only the band (= the band-pass). The
    // filter is real, so its spectrum at -k is the conjugate of the one at k.
    for (int k = 0; k < NFFT; k++) {
      const int f = k <= NFFT / 2 ? k : NFFT - k;
      if (f < sig_.kLo || f > sig_.kHi) work_[k] = {0, 0};
    }
    for (int k = sig_.kLo; k <= sig_.kHi; k++) {
      work_[k] = cmul(work_[k], tmpl_[k - sig_.kLo]);
      work_[NFFT - k] = cmul(work_[NFFT - k], cconj(tmpl_[k - sig_.kLo]));
    }
    fft_->inverse(work_);
    // Outputs 0..H-1 of each block are free of wrap-around
    scan(work_, false, next_, onChirp, ctx, ring);
    scan(work_, true, next_ + H, onChirp, ctx, ring);
    next_ += 2 * H;
    pairs++;
  }
}

void Detector::scan(const cpx *y, bool imag, uint32_t first, Callback cb, void *ctx,
                    const Ring &ring) {
  const bool armed = blocks_ >= WARMUP_BLOCKS;
  const float thr = threshold * noise_;
  float peak = 0;
  for (int n = 0; n < H; n++) {
    const float v = fabsf(imag ? y[n].im : y[n].re);
    peak = std::max(peak, v);
    if (n % MEDIAN_STEP == 0 && n / MEDIAN_STEP < MEDIAN_N) mag_[n / MEDIAN_STEP] = v;
    if (!armed) continue;

    const uint32_t s = first + n;
    if (candidate_) {
      if (s <= candEnd_) {
        if (v > candVal_) candVal_ = v, candBest_ = s;
        continue;
      }
      // Window over: the best peak in it is the chirp start
      candidate_ = false;
      holdoffUntil_ = candBest_ + uint32_t(holdoffS * FS);
      const Chirp c = {candBest_, candVal_ / noise_};
      if (ring.count() - (c.start - GCC_PRE) <= RING_LEN) {
        chirps_++;
        cb(ctx, c, ring);
      } else {
        overruns_++;
      }
    }
    if (s >= holdoffUntil_ && v > thr) {
      candidate_ = true;
      candBest_ = s;
      candVal_ = v;
      candEnd_ = s + PEAK_WINDOW;
    }
  }

  // Background level = median |correlation|; learn it only from quiet blocks
  std::nth_element(mag_, mag_ + MEDIAN_N / 2, mag_ + MEDIAN_N);
  const float median = mag_[MEDIAN_N / 2];
  if (blocks_ == 0)
    noise_ = median;
  else if (!armed || peak < thr)
    noise_ += (median - noise_) * (armed ? NOISE_ALPHA : 0.5f);
  blocks_++;
}

}  // namespace dsp
