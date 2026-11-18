// On-board version of host/tdoa.py + host/localize.py for one detected chirp
// (the Detector found it and cut out the window around it):
//   1. GCC-PHAT for all 6 mic pairs, sub-sample peak
//   2. least-squares arrival time per mic (+ misfit as a consistency check)
//   3. 3D position (grid search + Levenberg-Marquardt) and far-field direction
#pragma once

#include <stddef.h>
#include <stdint.h>

#include "dsp_config.h"
#include "fft.h"

namespace dsp {

struct TdoaResult {
  bool ok = false;           // passes misfit and quality checks
  float mfSnr = 0;           // matched-filter peak / median (from the Detector)
  float arrival[NUM_MICS];   // s, relative to the earliest mic
  float tau[NUM_PAIRS];      // s, measured pair delays (skew-corrected)
  float quality[NUM_PAIRS];  // GCC-PHAT peak height, ~1 perfect, ~0 no match
  float misfit = 0;          // s, rms inconsistency of the 6 delays
  float minQuality = 0;
  float pos[3];              // m
  float posRms = 0;          // s, how well the position explains the delays
  float range = 0, az = 0, el = 0;    // position in spherical form (m, deg, deg)
  float dirAz = 0, dirEl = 0;         // far-field direction (deg)
  float levelDb = 0;         // in-band level of the window, dB re 2048 ADC counts rms (mean of mics)
  int clipped = 0;           // samples in the window at the ADC limits (0 or 4095): too loud
  float msSpectra = 0, msGcc = 0, msLocalize = 0;  // processing time per stage
};

class TdoaProcessor {
 public:
  // fft: NFFT points. work: NFFT cpx scratch (may be the Detector's, see there).
  // Allocates ~29 KB more; false if out of memory.
  bool begin(const Fft *fft, cpx *work);
  // Length and band of the signal (keep equal to the Detector's)
  void setSignal(const SignalInfo &sig) { sig_ = sig; }
  // Calibration: extra delay of each mic channel (s), e.g. from the analog
  // front end. Subtracted from the measured delays before anything else.
  float micDelay[NUM_MICS] = {0, 0, 0, 0};
  // win: sig.gccLen() sets of raw ADC values, signal starting at GCC_PRE. c: speed of sound (m/s).
  void process(const uint16_t (*win)[NUM_MICS], float c, TdoaResult &r);

 private:
  void micSpectra(const uint16_t (*win)[NUM_MICS], TdoaResult &r);
  void phat(int i, int j, cpx *out);
  float refinePeak(const cpx *cross, int lag0, float *quality);
  void gccPhat2(int p, int q, TdoaResult &r);

  SignalInfo sig_;
  const Fft *fft_ = nullptr;
  cpx *work_ = nullptr;            // NFFT, not owned
  cpx *spec_[NUM_MICS] = {};       // mic spectra, in-band bins
  cpx *cross_[2] = {};             // PHAT-weighted cross spectra of two pairs, in-band bins
};

// Position and direction from the arrival times (fills pos/posRms/range/az/el/dir*)
void localize(const float arrival[NUM_MICS], float c, TdoaResult &r);

// One JSON line describing the result (no trailing newline). Returns length.
// tSeconds: signal start on the sample clock (seconds since sampling began).
int formatEventJson(char *buf, size_t len, uint32_t eventNo, double tSeconds,
                    const TdoaResult &r, float procMs);

}  // namespace dsp
