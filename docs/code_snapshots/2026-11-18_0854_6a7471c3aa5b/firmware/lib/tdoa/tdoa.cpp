#include "tdoa.h"
#include "platform.h"

#include <math.h>
#include <stdio.h>
#include <stdlib.h>

#include <algorithm>

namespace dsp {

static constexpr int PAIR_I[NUM_PAIRS] = {0, 0, 0, 1, 1, 2};
static constexpr int PAIR_J[NUM_PAIRS] = {1, 2, 3, 2, 3, 3};
static_assert(MAX_GCC_LEN + MAX_LAG + 1 <= NFFT, "GCC window + max lag must fit the FFT");

static inline cpx cmul(cpx a, cpx b) { return {a.re * b.re - a.im * b.im, a.re * b.im + a.im * b.re}; }
static inline cpx cconj(cpx a) { return {a.re, -a.im}; }

bool TdoaProcessor::begin(const Fft *fft, cpx *work) {
  fft_ = fft;
  work_ = work;
  for (auto &x : cross_) {
    x = static_cast<cpx *>(malloc(sizeof(cpx) * N_BAND_MAX));
    if (!x) return false;
  }
  if (!work_) return false;
  for (auto &s : spec_) {
    s = static_cast<cpx *>(malloc(sizeof(cpx) * N_BAND_MAX));
    if (!s) return false;
  }
  return true;
}

// In-band spectra of the GCC window of every mic. Two real signals share one
// complex FFT (mic a in the real part, mic b in the imaginary part).
void TdoaProcessor::micSpectra(const uint16_t (*win)[NUM_MICS], TdoaResult &r) {
  const int len = sig_.gccLen();
  r.clipped = 0;
  for (int n = 0; n < len; n++)
    for (int m = 0; m < NUM_MICS; m++) r.clipped += win[n][m] == 0 || win[n][m] >= 4095;
  for (int a = 0; a < NUM_MICS; a += 2) {
    const int b = a + 1;
    float ma = 0, mb = 0;
    for (int n = 0; n < len; n++) {
      ma += win[n][a];
      mb += win[n][b];
    }
    ma /= len;
    mb /= len;
    for (int n = 0; n < NFFT; n++)
      work_[n] = n < len ? cpx{win[n][a] - ma, win[n][b] - mb} : cpx{0, 0};
    fft_->forward(work_);
    for (int k = sig_.kLo; k <= sig_.kHi; k++) {
      const cpx z = work_[k], w = cconj(work_[NFFT - k]);
      spec_[a][k - sig_.kLo] = {(z.re + w.re) / 2, (z.im + w.im) / 2};
      // (z - w) / 2i
      spec_[b][k - sig_.kLo] = {(z.im - w.im) / 2, -(z.re - w.re) / 2};
    }
  }
}

// PHAT-weighted cross spectrum of mics i and j: X_i conj(X_j) / |.|.
// PHAT keeps only the phase (= timing), which sharpens the peak and makes it
// less sensitive to room resonances. Same as gcc_phat() in host/tdoa.py.
void TdoaProcessor::phat(int i, int j, cpx *out) {
  for (int k = 0; k < sig_.nBand(); k++) {
    const cpx p = cmul(spec_[i][k], cconj(spec_[j][k]));
    const float inv = 1.0f / (sqrtf(p.re * p.re + p.im * p.im) + 1e-20f);
    out[k] = {p.re * inv, p.im * inv};
  }
}

// Sub-sample peak: evaluate the band-limited cross-correlation directly at
// 1/INTERP sample steps within +-1 sample of the whole-sample peak lag0 (the
// zero-padded IFFT in Python does the same), then a parabola through the top.
// Returns the delay in samples.
float TdoaProcessor::refinePeak(const cpx *cross, int lag0, float *quality) {
  constexpr int STEPS = 2 * INTERP + 1;
  float cc[STEPS];
  int kBest = 0;
  for (int d = 0; d < STEPS; d++) {
    const float tau = lag0 + float(d - INTERP) / INTERP;
    const float th = 2.0f * float(M_PI) * tau / NFFT;
    cpx w = {cosf(th * sig_.kLo), sinf(th * sig_.kLo)};
    const cpx step = {cosf(th), sinf(th)};
    float acc = 0;
    for (int k = 0; k < sig_.nBand(); k++) {
      acc += cross[k].re * w.re - cross[k].im * w.im;
      w = cmul(w, step);
    }
    cc[d] = acc;
    if (acc > cc[kBest]) kBest = d;
  }
  float frac = 0;
  if (kBest > 0 && kBest < STEPS - 1) {
    const float a = cc[kBest - 1], b = cc[kBest], c = cc[kBest + 1];
    const float den = a - 2 * b + c;
    if (den != 0) frac = 0.5f * (a - c) / den;
  }
  // A perfect match puts every in-band bin in phase: sum = number of bins
  *quality = cc[kBest] / sig_.nBand();
  return lag0 + (kBest - INTERP + frac) / INTERP;
}

// GCC-PHAT for pairs p and q at once. Both cross-correlations are real, so
// one inverse FFT computes them together: pair p in the real part, pair q in
// the imaginary part. Result: r.tau (s, positive = i hears it later), r.quality.
void TdoaProcessor::gccPhat2(int p, int q, TdoaResult &r) {
  phat(PAIR_I[p], PAIR_J[p], cross_[0]);
  phat(PAIR_I[q], PAIR_J[q], cross_[1]);
  for (int k = 0; k < NFFT; k++) work_[k] = {0, 0};
  for (int k = sig_.kLo; k <= sig_.kHi; k++) {
    const cpx a = cross_[0][k - sig_.kLo], b = cross_[1][k - sig_.kLo];
    work_[k] = {a.re - b.im, a.im + b.re};          // A + iB
    work_[NFFT - k] = {a.re + b.im, -a.im + b.re};  // conj(A) + i conj(B)
  }
  fft_->inverse(work_);

  const int pairs[2] = {p, q};
  for (int h = 0; h < 2; h++) {
    int lag0 = 0;
    float best = -1e30f;
    for (int lag = -MAX_LAG; lag <= MAX_LAG; lag++) {
      const cpx &v = work_[(lag + NFFT) % NFFT];
      const float x = h ? v.im : v.re;
      if (x > best) best = x, lag0 = lag;
    }
    const int pr = pairs[h];
    const float tau = refinePeak(cross_[h], lag0, &r.quality[pr]) / FS;
    // undo the ADC's sequential sampling (see CHANNEL_SKEW_S)
    // and the calibrated per-channel delays
    r.tau[pr] = tau + (PAIR_I[pr] - PAIR_J[pr]) * CHANNEL_SKEW_S -
                (micDelay[PAIR_I[pr]] - micDelay[PAIR_J[pr]]);
  }
}

void TdoaProcessor::process(const uint16_t (*win)[NUM_MICS], float c, TdoaResult &r) {
  const float snr = r.mfSnr;
  r = TdoaResult{};
  r.mfSnr = snr;
  const int64_t t0 = nowUs();
  micSpectra(win, r);
  // Parseval: band power (both signs of frequency) / N^2 per sample of the window
  double energy = 0;
  for (int m = 0; m < NUM_MICS; m++)
    for (int k = 0; k < sig_.nBand(); k++) energy += double(spec_[m][k].re) * spec_[m][k].re + double(spec_[m][k].im) * spec_[m][k].im;
  const double meanSquare = 2.0 * energy / NUM_MICS / (double(NFFT) * NFFT) * NFFT / sig_.gccLen();
  r.levelDb = 10.0 * log10(meanSquare / (2048.0 * 2048.0) + 1e-20);
  const int64_t t1 = nowUs();
  for (int p = 0; p < NUM_PAIRS; p += 2) gccPhat2(p, p + 1, r);
  const int64_t t2 = nowUs();

  // t_i - t_j = tau_ij (6 equations) + sum(t) = 0. For a complete set of pairs
  // the least-squares solution is simply t_i = mean over j of tau_ij.
  float t[NUM_MICS] = {};
  r.minQuality = 1e9f;
  for (int p = 0; p < NUM_PAIRS; p++) {
    const int i = PAIR_I[p], j = PAIR_J[p];
    r.minQuality = std::min(r.minQuality, r.quality[p]);
    t[i] += r.tau[p] / NUM_MICS;
    t[j] -= r.tau[p] / NUM_MICS;
  }
  float sq = 0;
  for (int p = 0; p < NUM_PAIRS; p++) {
    const float e = t[PAIR_I[p]] - t[PAIR_J[p]] - r.tau[p];
    sq += e * e;
  }
  r.misfit = sqrtf(sq / NUM_PAIRS);
  const float first = *std::min_element(t, t + NUM_MICS);
  for (int m = 0; m < NUM_MICS; m++) r.arrival[m] = t[m] - first;
  r.ok = r.misfit < MAX_MISFIT_S && r.minQuality > MIN_QUALITY;

  localize(r.arrival, c, r);
  r.msSpectra = (t1 - t0) / 1000.0f;
  r.msGcc = (t2 - t1) / 1000.0f;
  r.msLocalize = (nowUs() - t2) / 1000.0f;
}

// --------------------------------------------------------------- geometry

float MICS[NUM_MICS][3];
static float arraySide_ = 0, arrayRot_ = 0;

void setArrayGeometry(float a, float rotDeg) {
  const float h = a / 2;
  const float xy[NUM_MICS][2] = {{-h, h}, {h, h}, {h, -h}, {-h, -h}};
  const float th = rotDeg * float(M_PI) / 180, cs = cosf(th), sn = sinf(th);
  for (int m = 0; m < NUM_MICS; m++) {
    MICS[m][0] = xy[m][0] * cs - xy[m][1] * sn;
    MICS[m][1] = xy[m][0] * sn + xy[m][1] * cs;
    MICS[m][2] = 0;
  }
  arraySide_ = a;
  arrayRot_ = rotDeg;
}
float arraySide() { return arraySide_; }
float arrayRotDeg() { return arrayRot_; }

static struct GeometryInit {
  GeometryInit() { setArrayGeometry(DEFAULT_ARRAY_SIDE, DEFAULT_ARRAY_ROT_DEG); }
} geometryInit;

// --------------------------------------------------------------- localize

// Pair delays (us) predicted for a source at s, and their mismatch to taus
static float residuals(const float s[3], const float taus[NUM_PAIRS], float c,
                       float f[NUM_PAIRS], float J[NUM_PAIRS][3]) {
  float d[NUM_MICS], g[NUM_MICS][3];
  for (int m = 0; m < NUM_MICS; m++) {
    float v[3], sq = 0;
    for (int a = 0; a < 3; a++) v[a] = s[a] - MICS[m][a], sq += v[a] * v[a];
    d[m] = sqrtf(sq);
    if (J) {  // unit vectors from the mics, only needed for the Jacobian
      const float inv = 1.0f / std::max(d[m], 1e-9f);
      for (int a = 0; a < 3; a++) g[m][a] = v[a] * inv;
    }
  }
  float cost = 0;
  const float k = 1e6f / c;
  for (int p = 0; p < NUM_PAIRS; p++) {
    const int i = PAIR_I[p], j = PAIR_J[p];
    f[p] = (d[i] - d[j]) * k - taus[p] * 1e6f;
    cost += f[p] * f[p];
    if (J)
      for (int a = 0; a < 3; a++) J[p][a] = (g[i][a] - g[j][a]) * k;
  }
  return cost;
}

static bool solve3(const float A[3][3], const float b[3], float x[3]) {
  const float det = A[0][0] * (A[1][1] * A[2][2] - A[1][2] * A[2][1]) -
                    A[0][1] * (A[1][0] * A[2][2] - A[1][2] * A[2][0]) +
                    A[0][2] * (A[1][0] * A[2][1] - A[1][1] * A[2][0]);
  if (fabsf(det) < 1e-30f) return false;
  for (int col = 0; col < 3; col++) {
    float M[3][3];
    for (int r = 0; r < 3; r++)
      for (int q = 0; q < 3; q++) M[r][q] = q == col ? b[r] : A[r][q];
    x[col] = (M[0][0] * (M[1][1] * M[2][2] - M[1][2] * M[2][1]) -
              M[0][1] * (M[1][0] * M[2][2] - M[1][2] * M[2][0]) +
              M[0][2] * (M[1][0] * M[2][1] - M[1][1] * M[2][0])) / det;
  }
  return true;
}

static void clampBox(float s[3]) {
  s[0] = std::min(std::max(s[0], -MAX_RANGE), MAX_RANGE);
  s[1] = std::min(std::max(s[1], -MAX_RANGE), MAX_RANGE);
  s[2] = std::min(std::max(s[2], 0.0f), MAX_RANGE);  // nothing below the ground
}

// Levenberg-Marquardt from s; returns the final cost (us^2)
static float refine(float s[3], const float taus[NUM_PAIRS], float c) {
  float f[NUM_PAIRS], J[NUM_PAIRS][3];
  float cost = residuals(s, taus, c, f, J);
  float lambda = 1e-3f;
  for (int it = 0; it < 100; it++) {
    float H[3][3] = {}, g[3] = {};
    for (int p = 0; p < NUM_PAIRS; p++)
      for (int a = 0; a < 3; a++) {
        g[a] -= J[p][a] * f[p];
        for (int b = 0; b < 3; b++) H[a][b] += J[p][a] * J[p][b];
      }
    float A[3][3], delta[3];
    for (int a = 0; a < 3; a++)
      for (int b = 0; b < 3; b++) A[a][b] = H[a][b] + (a == b ? lambda * H[a][a] + 1e-12f : 0);
    if (!solve3(A, g, delta)) break;
    float trial[3] = {s[0] + delta[0], s[1] + delta[1], s[2] + delta[2]};
    clampBox(trial);
    float ft[NUM_PAIRS], Jt[NUM_PAIRS][3];
    const float ct = residuals(trial, taus, c, ft, Jt);
    if (ct < cost) {
      const float gain = cost - ct;
      for (int a = 0; a < 3; a++) s[a] = trial[a];
      for (int p = 0; p < NUM_PAIRS; p++) {
        f[p] = ft[p];
        for (int a = 0; a < 3; a++) J[p][a] = Jt[p][a];
      }
      cost = ct;
      lambda = std::max(lambda / 3, 1e-9f);
      const float step = fabsf(delta[0]) + fabsf(delta[1]) + fabsf(delta[2]);
      if (gain < 1e-7f * cost || step < 1e-7f) break;
    } else {
      lambda *= 4;
      if (lambda > 1e8f) break;
    }
  }
  return cost;
}

void localize(const float arrival[NUM_MICS], float c, TdoaResult &r) {
  float taus[NUM_PAIRS];
  for (int p = 0; p < NUM_PAIRS; p++) taus[p] = arrival[PAIR_I[p]] - arrival[PAIR_J[p]];

  // Grid over the upper half-space (as localize._grid), keep the 5 best
  constexpr int NR = 14, NAZ = 36, NEL = 15, KEEP = 5;
  float bestCost[KEEP], bestPos[KEEP][3];
  for (auto &b : bestCost) b = 1e30f;
  float caz[NAZ], saz[NAZ], cel[NEL], sel[NEL];
  for (int a = 0; a < NAZ; a++) caz[a] = cosf(a * 10 * float(M_PI) / 180), saz[a] = sinf(a * 10 * float(M_PI) / 180);
  for (int e = 0; e < NEL; e++) cel[e] = cosf((2 + 6 * e) * float(M_PI) / 180), sel[e] = sinf((2 + 6 * e) * float(M_PI) / 180);
  float f[NUM_PAIRS];
  for (int ri = 0; ri < NR; ri++) {
    const float rad = 0.15f * powf(MAX_RANGE / 0.15f, float(ri) / (NR - 1));
    for (int a = 0; a < NAZ; a++)
      for (int e = 0; e < NEL; e++) {
        const float s[3] = {rad * cel[e] * caz[a], rad * cel[e] * saz[a], rad * sel[e]};
        const float cost = residuals(s, taus, c, f, nullptr);
        if (cost >= bestCost[KEEP - 1]) continue;
        int k = KEEP - 1;
        for (; k > 0 && bestCost[k - 1] > cost; k--) {
          bestCost[k] = bestCost[k - 1];
          for (int q = 0; q < 3; q++) bestPos[k][q] = bestPos[k - 1][q];
        }
        bestCost[k] = cost;
        for (int q = 0; q < 3; q++) bestPos[k][q] = s[q];
      }
  }
  float best = 1e30f;
  for (int k = 0; k < KEEP; k++) {
    float s[3] = {bestPos[k][0], bestPos[k][1], bestPos[k][2]};
    const float cost = refine(s, taus, c);
    if (cost < best) {
      best = cost;
      for (int q = 0; q < 3; q++) r.pos[q] = s[q];
    }
  }
  r.posRms = sqrtf(best / NUM_PAIRS) * 1e-6f;
  r.range = sqrtf(r.pos[0] * r.pos[0] + r.pos[1] * r.pos[1] + r.pos[2] * r.pos[2]);
  r.az = fmodf(atan2f(r.pos[1], r.pos[0]) * 180 / float(M_PI) + 360, 360);
  r.el = r.range > 0 ? asinf(r.pos[2] / r.range) * 180 / float(M_PI) : 0;

  // Far-field direction: tau_p * c = -(m_i - m_j)_xy . u_xy  (2 unknowns)
  float AtA[2][2] = {}, Atb[2] = {};
  for (int p = 0; p < NUM_PAIRS; p++) {
    const float row[2] = {-(MICS[PAIR_I[p]][0] - MICS[PAIR_J[p]][0]),
                          -(MICS[PAIR_I[p]][1] - MICS[PAIR_J[p]][1])};
    for (int a = 0; a < 2; a++) {
      Atb[a] += row[a] * taus[p] * c;
      for (int b = 0; b < 2; b++) AtA[a][b] += row[a] * row[b];
    }
  }
  const float det = AtA[0][0] * AtA[1][1] - AtA[0][1] * AtA[1][0];
  float ux = (AtA[1][1] * Atb[0] - AtA[0][1] * Atb[1]) / det;
  float uy = (AtA[0][0] * Atb[1] - AtA[1][0] * Atb[0]) / det;
  float h = sqrtf(ux * ux + uy * uy);
  if (h > 1) ux /= h, uy /= h, h = 1;
  r.dirAz = fmodf(atan2f(uy, ux) * 180 / float(M_PI) + 360, 360);
  r.dirEl = acosf(h) * 180 / float(M_PI);
}

int formatEventJson(char *buf, size_t len, uint32_t eventNo, double tSeconds,
                    const TdoaResult &r, float procMs) {
  return snprintf(
      buf, len,
      "{\"type\":\"event\",\"n\":%lu,\"t\":%.3f,\"ok\":%s,\"snr\":%.1f,"
      "\"arr_us\":[%.1f,%.1f,%.1f,%.1f],\"misfit_us\":%.2f,\"q\":%.3f,"
      "\"pos_cm\":[%.1f,%.1f,%.1f],\"fit_us\":%.2f,\"r_cm\":%.1f,\"az\":%.1f,\"el\":%.1f,"
      "\"dir_az\":%.1f,\"dir_el\":%.1f,\"lvl_db\":%.1f,\"clip\":%d,"
      "\"proc_ms\":%.1f,\"stage_ms\":[%.1f,%.1f,%.1f]}",
      (unsigned long)eventNo, tSeconds, r.ok ? "true" : "false", r.mfSnr,
      r.arrival[0] * 1e6f, r.arrival[1] * 1e6f, r.arrival[2] * 1e6f, r.arrival[3] * 1e6f,
      r.misfit * 1e6f, r.minQuality, r.pos[0] * 100, r.pos[1] * 100, r.pos[2] * 100,
      r.posRms * 1e6f, r.range * 100, r.az, r.el, r.dirAz, r.dirEl, r.levelDb, r.clipped, procMs,
      r.msSpectra, r.msGcc, r.msLocalize);
}

}  // namespace dsp
