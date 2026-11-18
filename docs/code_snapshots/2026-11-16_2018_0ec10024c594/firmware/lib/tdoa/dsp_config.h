// Constants shared by the on-board pipeline. They mirror host/tdoa.py,
// host/localize.py and host/test_signal.py, so the ESP32 and the Python
// analysis compute the same thing. Change them together.
#pragma once

#include <stddef.h>
#include <stdint.h>

namespace dsp {

// ----------------------------------------------------------------- sampling
constexpr int NUM_MICS = 4;
constexpr uint32_t FS = 44100;     // samples per second per mic
constexpr uint32_t OVERSAMPLE = 4;
// The ADC converts the mics one after another: mic k is sampled k slots after
// mic 1. 1 slot = 1/(FS*OVERSAMPLE*NUM_MICS) = 1.42 us (see host/tdoa.py).
constexpr float CHANNEL_SKEW_S = 1.0f / (float(FS) * OVERSAMPLE * NUM_MICS);

// ------------------------------------------------------------- test signal
// The signal the detector looks for can be replaced at run time (the host
// uploads a template over serial, see src/main.cpp). This chirp is the one
// loaded at boot, identical to host/test_signal.py.
constexpr int MAX_SIG_LEN = 2205;         // longest template: 50 ms
constexpr float CHIRP_F_START = 1500.0f;  // Hz
constexpr float CHIRP_F_END = 8000.0f;    // Hz
constexpr float CHIRP_SECONDS = 0.05f;
constexpr int CHIRP_LEN = 2205;           // int(CHIRP_SECONDS * FS)
constexpr int CHIRP_FADE = 220;           // int(0.005 * FS)

// --------------------------------------------------------- ring + detector
// The sampling core writes every set into a ring buffer (8 KB chunks: the
// ESP32 heap is fragmented, big blocks are rare). The detector reads it behind
// the writer: it has to find the chirp and copy it out before it is overwritten.
constexpr int RING_CHUNK = 1024;                   // sets per chunk
constexpr int RING_CHUNKS = 12;
constexpr int RING_LEN = RING_CHUNK * RING_CHUNKS; // 12288 sets = 279 ms

// Streaming matched filter (overlap-save): each FFT block of NFFT samples
// gives MF_HOP new correlation values. Two blocks share one complex FFT.
constexpr int MF_HOP = 4096 - MAX_SIG_LEN + 1;     // 1892
constexpr float MF_PEAK_WINDOW_S = 0.005f;         // best peak within 5 ms of the first crossing
constexpr float HOLDOFF_S = 0.3f;                  // as find_peaks(distance=0.3 s) in tdoa.py
constexpr float DEFAULT_MF_THRESHOLD = 12.0f;      // x median; noise-only recordings reach ~8

// --------------------------------------------------------------- analysis
constexpr int NFFT = 4096;
// Analysis band (FFT bins), set together with the template. Default: the
// chirp's 1200..9000 Hz, slightly wider than the sweep itself.
constexpr int DEFAULT_K_LO = 112;   // ceil(1200 * NFFT / FS)
constexpr int DEFAULT_K_HI = 835;   // floor(9000 * NFFT / FS)
constexpr int N_BAND_MAX = 900;     // widest band (~9.7 kHz): sizes the spectrum buffers
constexpr int GCC_PRE = 132;                          // int(0.003 * FS)
constexpr int MAX_GCC_LEN = MAX_SIG_LEN + 2 * GCC_PRE;  // window around the signal
constexpr float MAX_TDOA_S = 1500e-6f;                // largest delay searched
constexpr int MAX_LAG = 66;                           // int(MAX_TDOA_S * FS)
constexpr int INTERP = 16;                            // sub-sample search step 1/16

// Same acceptance checks as tdoa.py
constexpr float MAX_MISFIT_S = 10e-6f;
constexpr float MIN_QUALITY = 0.2f;

// ---------------------------------------------------------------- geometry
// metres, Mic1..Mic4, origin = centre of the square, mics in the z = 0 plane.
// Square of side a (h = a/2), each mic stays in its quarter when the size changes:
//   Mic1 (-h, +h)   Mic2 (+h, +h)   Mic3 (+h, -h)   Mic4 (-h, -h)
// Set at run time with setArraySide() ("array <side cm>" command, kept in flash).
// (Before 2026-11-16: 19 cm square, Mic1 (+,-) Mic2 (-,-) Mic3 (-,+) Mic4 (+,+).)
extern float MICS[NUM_MICS][3];
constexpr float DEFAULT_ARRAY_SIDE = 0.30f;
void setArraySide(float side_m);
float arraySide();
constexpr int NUM_PAIRS = NUM_MICS * (NUM_MICS - 1) / 2;
constexpr float MAX_RANGE = 6.0f;  // m

// The signal currently searched for: its length and analysis band
struct SignalInfo {
  int len = CHIRP_LEN;  // samples
  int kLo = DEFAULT_K_LO, kHi = DEFAULT_K_HI;
  int nBand() const { return kHi - kLo + 1; }
  int gccLen() const { return len + 2 * GCC_PRE; }  // GCC window, signal starts at GCC_PRE
  float fLo() const { return float(kLo) * FS / NFFT; }
  float fHi() const { return float(kHi) * FS / NFFT; }
  bool valid() const {
    return len >= 64 && len <= MAX_SIG_LEN && kLo >= 1 && kHi < NFFT / 2 && kLo <= kHi &&
           nBand() <= N_BAND_MAX;
  }
};

inline float speedOfSound(float tempC) { return 331.3f + 0.606f * tempC; }

}  // namespace dsp
