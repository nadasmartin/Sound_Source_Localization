// PC test harness for the on-board pipeline (firmware/lib/tdoa).
// Feeds a recording through exactly the same Ring + Detector + TdoaProcessor
// code the ESP32 runs, block by block, and prints the same JSON lines.
//
// Input: raw little-endian uint16, interleaved [n][4] (see run_native.sh).
// Usage: tdoa_native recording.u16 [temp_C] [threshold] [template.i16 k_lo k_hi]
//   template.i16: raw int16 LE samples at FS, uploaded like the host does over serial

#include <chrono>
#include <cstdio>
#include <cstdlib>

#include "detector.h"
#include "tdoa.h"

using namespace dsp;

struct Ctx {
  TdoaProcessor proc;
  float c;
  uint32_t events = 0;
  uint16_t win[MAX_GCC_LEN][NUM_MICS];
  int gccLen = 0;
  Chirp chirp;
  bool pending = false;
};

// As on the ESP32: the callback only copies the window out of the ring, the
// processing runs after poll() returns (they share the FFT work buffer).
static void onChirp(void *p, const Chirp &chirp, const Ring &ring) {
  auto &ctx = *static_cast<Ctx *>(p);
  if (ctx.pending) return;
  ring.copy(chirp.start - GCC_PRE, ctx.gccLen, ctx.win);
  ctx.chirp = chirp;
  ctx.pending = true;
}

static void processPending(Ctx &ctx) {
  if (!ctx.pending) return;
  ctx.pending = false;
  const Chirp &chirp = ctx.chirp;
  TdoaResult r;
  r.mfSnr = chirp.snr;
  const auto t0 = std::chrono::steady_clock::now();
  ctx.proc.process(ctx.win, ctx.c, r);
  const float ms = std::chrono::duration<float, std::milli>(std::chrono::steady_clock::now() - t0).count();
  char line[512];
  formatEventJson(line, sizeof(line), ++ctx.events, double(chirp.start) / FS, r, ms);
  puts(line);
}

int main(int argc, char **argv) {
  if (argc < 2) {
    fprintf(stderr, "usage: %s recording.u16 [temp_C] [threshold]\n", argv[0]);
    return 2;
  }
  FILE *f = fopen(argv[1], "rb");
  if (!f) {
    perror(argv[1]);
    return 1;
  }
  static Fft fft;
  static Ring ring;
  static Detector det;
  static Ctx ctx;
  ctx.c = speedOfSound(argc > 2 ? atof(argv[2]) : 21.0f);
  static cpx work[NFFT];  // shared, as on the ESP32
  if (!fft.begin(NFFT) || !ring.begin() || !det.begin(&fft, work) || !ctx.proc.begin(&fft, work)) {
    fprintf(stderr, "out of memory\n");
    return 1;
  }
  if (argc > 3) det.threshold = atof(argv[3]);
  if (argc > 6) {
    SignalInfo sig;
    sig.kLo = atoi(argv[5]), sig.kHi = atoi(argv[6]);
    FILE *t = fopen(argv[4], "rb");
    if (!t) {
      perror(argv[4]);
      return 1;
    }
    cpx *stage = det.stage();
    int16_t v;
    sig.len = 0;
    while (sig.len < MAX_SIG_LEN && fread(&v, 2, 1, t) == 1) stage[sig.len++].re = v / 32768.0f;
    fclose(t);
    if (!det.setTemplate(sig)) {
      fprintf(stderr, "template rejected (len %d, bins %d..%d)\n", sig.len, sig.kLo, sig.kHi);
      return 1;
    }
  }
  ctx.proc.setSignal(det.signal());
  ctx.gccLen = det.signal().gccLen();

  // Like the firmware: the sampling side pushes 128-set frames, the detector polls
  uint16_t set[NUM_MICS];
  int inFrame = 0;
  while (fread(set, sizeof(set), 1, f) == 1) {
    ring.push(set);
    if (++inFrame == 128) {
      inFrame = 0;
      det.poll(ring, onChirp, &ctx);
      processPending(ctx);
    }
  }
  fclose(f);
  fprintf(stderr, "%lu sets, %lu chirps, noise %.0f, overruns %lu\n", (unsigned long)ring.count(),
          (unsigned long)det.chirps(), det.noise(), (unsigned long)det.overruns());
  return 0;
}
