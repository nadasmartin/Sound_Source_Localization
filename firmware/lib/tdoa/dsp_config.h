// Constants shared by the on-board pipeline. The geometry and the test signal
// mirror host/localize.py and host/signals_lib.py, so the ESP32 and the Python
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
// mic 1. 1 slot = 1/(FS*OVERSAMPLE*NUM_MICS) = 1.42 us.
constexpr float CHANNEL_SKEW_S = 1.0f / (float(FS) * OVERSAMPLE * NUM_MICS);

// ------------------------------------------------------------- test signal
// The signal the detector looks for can be replaced at run time (the host
// uploads a template over serial, see src/main.cpp). This chirp is the one
// loaded at boot, identical to signals_lib.DEFAULT on the host.
// 3-12 kHz, 50 ms: best signal of the P1-P4 sweeps (2026-11-16, see
// docs/experiment_log.md). Until 2026-11-18 it was 1500-8000 Hz.
constexpr int MAX_SIG_LEN = 2205;         // longest template: 50 ms
constexpr float CHIRP_F_START = 3000.0f;  // Hz
constexpr float CHIRP_F_END = 12000.0f;   // Hz
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
constexpr float HOLDOFF_S = 0.3f;                  // dead time after a detection (echoes)
constexpr float DEFAULT_MF_THRESHOLD = 12.0f;      // x median; noise-only recordings reach ~8

// --------------------------------------------------------------- analysis
constexpr int NFFT = 4096;
// Analysis band (FFT bins), set together with the template. Default: what
// signals_lib.Signal.band_bins() gives the 3-12 kHz chirp (2400..13500 Hz,
// narrowed evenly to the 900-bin limit): bins 289..1187 = 3111..12780 Hz.
// (1500-8000 Hz chirp until 2026-11-18: bins 112..835 = 1200..9000 Hz.)
constexpr int DEFAULT_K_LO = 289;
constexpr int DEFAULT_K_HI = 1187;
constexpr int N_BAND_MAX = 900;     // widest band (~9.7 kHz): sizes the spectrum buffers
constexpr int GCC_PRE = 132;                          // int(0.003 * FS)
constexpr int MAX_GCC_LEN = MAX_SIG_LEN + 2 * GCC_PRE;  // window around the signal
constexpr float MAX_TDOA_S = 1500e-6f;                // largest delay searched
constexpr int MAX_LAG = 66;                           // int(MAX_TDOA_S * FS)
constexpr int INTERP = 16;                            // sub-sample search step 1/16

// Acceptance checks of a detection
constexpr float MAX_MISFIT_S = 10e-6f;
constexpr float MIN_QUALITY = 0.2f;

// ---------------------------------------------------------------- geometry
// metres, Mic1..Mic4, origin = centre of the square, mics in the z = 0 plane.
// Square of side a (h = a/2), each mic stays in its quarter when the size changes:
//   Mic1 (-h, +h)   Mic2 (+h, +h)   Mic3 (+h, -h)   Mic4 (-h, -h)
// The whole square can be turned about its centre by a small angle: the
// measured angle between the mic square and the axes the source positions are
// measured in (counter-clockwise seen from above, +z). Mic positions are the
// nominal ones rotated by it: x' = x cos - y sin, y' = x sin + y cos.
// P1-P4 (2026-11-16) gave +2.13 deg, see docs/experiment_log.md.
// Set at run time: "array <side cm>" and "rot <deg>" commands, both kept in flash.
// (Before 2026-11-16: 19 cm square, Mic1 (+,-) Mic2 (-,-) Mic3 (-,+) Mic4 (+,+).)
extern float MICS[NUM_MICS][3];
constexpr float DEFAULT_ARRAY_SIDE = 0.30f;
constexpr float DEFAULT_ARRAY_ROT_DEG = 0.0f;  // flash holds the measured value
void setArrayGeometry(float side_m, float rot_deg);
float arraySide();
float arrayRotDeg();
inline void setArraySide(float side_m) { setArrayGeometry(side_m, arrayRotDeg()); }  // keeps the rotation
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
