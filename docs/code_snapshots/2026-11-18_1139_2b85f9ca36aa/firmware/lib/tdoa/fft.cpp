#include "fft.h"

#include <math.h>
#include <stdlib.h>


namespace dsp {

bool Fft::begin(int n) {
  n_ = n;
  cos_ = static_cast<float *>(malloc(sizeof(float) * (n / 4 + 1)));
  if (!cos_) return false;
  for (int k = 0; k <= n / 4; k++) cos_[k] = float(cos(2.0 * M_PI * k / n));
  return true;
}

Fft::~Fft() { free(cos_); }

cpx Fft::twiddle(int k) const {
  const int q = n_ / 4;
  // angle x = 2 pi k / N in [0, pi): cos x, -sin x from the quarter-wave table
  if (k <= q) return {cos_[k], -cos_[q - k]};
  return {-cos_[n_ / 2 - k], -cos_[k - q]};
}

void Fft::transform(cpx *x) const {
  const int n = n_;
  // bit-reversal permutation
  for (int i = 1, j = 0; i < n; i++) {
    int bit = n >> 1;
    for (; j & bit; bit >>= 1) j ^= bit;
    j ^= bit;
    if (i < j) {
      cpx t = x[i];
      x[i] = x[j];
      x[j] = t;
    }
  }
  // butterflies; the twiddle is looked up once per (stage, k)
  for (int len = 2; len <= n; len <<= 1) {
    const int half = len >> 1;
    const int step = n / len;
    for (int k = 0; k < half; k++) {
      const cpx w = twiddle(k * step);
      for (int i = k; i < n; i += len) {
        cpx &a = x[i];
        cpx &b = x[i + half];
        const float tr = b.re * w.re - b.im * w.im;
        const float ti = b.re * w.im + b.im * w.re;
        b.re = a.re - tr;
        b.im = a.im - ti;
        a.re += tr;
        a.im += ti;
      }
    }
  }
}

void Fft::forward(cpx *x) const { transform(x); }

void Fft::inverse(cpx *x) const {
  // ifft(X) = conj(fft(conj(X)))  (unscaled)
  for (int i = 0; i < n_; i++) x[i].im = -x[i].im;
  transform(x);
  for (int i = 0; i < n_; i++) x[i].im = -x[i].im;
}

}  // namespace dsp
