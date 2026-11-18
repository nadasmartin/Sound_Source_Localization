// Small in-place radix-2 complex FFT (float). Portable: no Arduino or ESP-IDF
// dependencies, so the same code runs on the PC test harness.
#pragma once

#include <stddef.h>

namespace dsp {

struct cpx {
  float re, im;
};

class Fft {
 public:
  // n must be a power of two. Returns false if the twiddle table can't be allocated.
  bool begin(int n);
  ~Fft();
  // X[k] = sum x[n] exp(-2 pi i k n / N)
  void forward(cpx *x) const;
  // Unscaled inverse: x[n] = sum X[k] exp(+2 pi i k n / N)  (N times numpy's ifft)
  void inverse(cpx *x) const;
  int size() const { return n_; }

 private:
  void transform(cpx *x) const;
  cpx twiddle(int k) const;  // exp(-2 pi i k / N), k < N/2
  int n_ = 0;
  float *cos_ = nullptr;  // cos(2 pi k / N), k <= N/4 (quarter wave, 4 KB for N = 4096)
};

}  // namespace dsp
