"""Candidate test signals for the precision bench (bench.py).

Each Signal can render itself
  * at the phone's rate (48 kHz) as the WAV the phone plays, and
  * at the ESP32's rate (44.1 kHz) as the matched-filter template uploaded to
    the board, together with the analysis band (FFT bins of the 4096-point FFT).
Both come from the same waveform, so what is played is what is searched for.

Limits set by the firmware (firmware/lib/tdoa/dsp_config.h):
  * at most 50 ms long (MAX_SIG_LEN = 2205 samples)
  * analysis band at most 900 FFT bins wide (~9.7 kHz)

Kinds:
  chirp     linear sweep f_lo -> f_hi (the current default is chirp 1500-8000 Hz, 50 ms)
  logchirp  exponential sweep: equal time per octave, more energy at low frequencies
  noise     band-limited white noise burst (fixed seed): flat spectrum, the
            textbook signal for GCC-PHAT
  tone      sine burst at f_lo: a known-bad control (periodic -> ambiguous delays)
"""

from dataclasses import dataclass, field

import numpy as np
from scipy.signal import chirp, resample_poly

PHONE_RATE = 48000
ESP_RATE = 44100
NFFT = 4096
MAX_SIG_LEN = 2205
N_BAND_MAX = 900
DEFAULT_PERIOD = 0.5     # s between repetitions


@dataclass(frozen=True)
class Signal:
    kind: str
    f_lo: float
    f_hi: float
    dur: float                 # seconds
    fade: float = 0.005        # raised-cosine fade in/out, seconds
    seed: int = 1
    name: str = field(default="", compare=False)

    def __post_init__(self):
        if not self.name:
            f = (f"{self.f_lo / 1000:g}k" if self.kind == "tone"
                 else f"{self.f_lo / 1000:g}-{self.f_hi / 1000:g}k")
            object.__setattr__(self, "name", f"{self.kind}_{f}_{self.dur * 1000:g}ms")
        if not 0.004 < self.dur <= MAX_SIG_LEN / ESP_RATE + 1e-9:
            raise ValueError(f"{self.name}: duration must be <= 50 ms")

    # ------------------------------------------------------------ waveform
    def wave(self, rate=PHONE_RATE):
        """The signal at `rate`, peak 1.0."""
        n = int(round(self.dur * rate))
        t = np.arange(n) / rate
        if self.kind == "chirp":
            x = chirp(t, self.f_lo, self.dur, self.f_hi, method="linear")
        elif self.kind == "logchirp":
            x = chirp(t, self.f_lo, self.dur, self.f_hi, method="logarithmic")
        elif self.kind == "tone":
            x = np.sin(2 * np.pi * self.f_lo * t)
        elif self.kind == "noise":
            # Same noise at every rate: build it at the phone rate, resample
            rng = np.random.default_rng(self.seed)
            m = int(round(self.dur * PHONE_RATE))
            spec = np.fft.rfft(rng.standard_normal(m))
            f = np.fft.rfftfreq(m, 1 / PHONE_RATE)
            spec[(f < self.f_lo) | (f > self.f_hi)] = 0
            x = np.fft.irfft(spec, m)
            if rate != PHONE_RATE:
                x = resample_poly(x, rate, PHONE_RATE)[:n]
        else:
            raise ValueError(self.kind)
        fade = max(2, int(self.fade * rate))
        ramp = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, fade))
        x[:fade] *= ramp
        x[-fade:] *= ramp[::-1]
        return x / np.abs(x).max()

    # ----------------------------------------------------- ESP32 template
    def band_bins(self):
        """Analysis band on the ESP32: the signal band with ~10% margin, as
        tdoa.py uses 1200-9000 Hz for the 1500-8000 Hz chirp."""
        if self.kind == "tone":
            lo, hi = self.f_lo * 0.8, self.f_lo * 1.25
        else:
            lo, hi = self.f_lo * 0.8, self.f_hi * 1.125
        k_lo = max(1, int(np.ceil(lo * NFFT / ESP_RATE)))
        k_hi = min(NFFT // 2 - 1, int(np.floor(hi * NFFT / ESP_RATE)))
        while k_hi - k_lo + 1 > N_BAND_MAX:     # too wide: give up margin evenly
            k_lo += 1
            k_hi -= 1
        return k_lo, k_hi

    def template(self):
        """int16 template at the ESP32 rate, as uploaded with sig_begin/sig_data."""
        x = self.wave(ESP_RATE)[:MAX_SIG_LEN]
        return np.round(x * 32000).astype("<i2")

    def wav_bytes(self, channel="both"):
        """16-bit stereo WAV at the phone rate (gain is applied on the phone).
        channel: "both", "left" or "right" - phones with two speakers (e.g. the
        iPhone's earpiece + bottom speaker) play the channels from different
        places, which is two sources instead of one."""
        import io

        from scipy.io import wavfile
        x = np.round(self.wave() * 32000).astype(np.int16)
        zero = np.zeros_like(x)
        stereo = {"both": (x, x), "left": (x, zero), "right": (zero, x)}[channel]
        buf = io.BytesIO()
        wavfile.write(buf, PHONE_RATE, np.column_stack(stereo))
        return buf.getvalue()


DEFAULT = Signal("chirp", 1500, 8000, 0.05)


CHANNELS = ("both", "left", "right")


@dataclass(frozen=True)
class Trial:
    signal: Signal
    gain_db: float = 0.0       # relative to the phone's full scale at its media volume
    channel: str = "both"      # which stereo channel(s) carry the signal

    @property
    def label(self):
        return self.signal.name + ("" if self.channel == "both" else f"@{self.channel[0].upper()}")


def _chirps(bands, dur=0.05, kind="chirp"):
    return [Signal(kind, lo, hi, dur) for lo, hi in bands]


SUITES = {
    # A few minutes: one of each idea, to check the setup works
    "quick": lambda: [Trial(DEFAULT), Trial(DEFAULT, -12),
                      Trial(Signal("noise", 1500, 8000, 0.05)),
                      Trial(Signal("chirp", 2000, 10000, 0.05)),
                      Trial(Signal("chirp", 1500, 8000, 0.02))],
    # Which frequency range? (all 50 ms linear chirps, full volume)
    "band": lambda: [Trial(s) for s in _chirps(
        [(500, 4000), (1000, 6000), (1500, 8000), (2000, 10000), (3000, 12000),
         (4000, 13000), (1000, 10000), (6000, 15000)])],
    # How long?
    "duration": lambda: [Trial(Signal("chirp", 1500, 8000, d)) for d in (0.01, 0.02, 0.035, 0.05)],
    # Which kind of waveform?
    "type": lambda: [Trial(Signal(k, 1500, 8000, 0.05)) for k in ("chirp", "logchirp", "noise")] +
                    [Trial(Signal("noise", 2000, 10000, 0.05)), Trial(Signal("tone", 4000, 4000, 0.05))],
    # Which speaker? (phones with two speakers: one source or two?)
    "speaker": lambda: [Trial(DEFAULT, 0, ch) for ch in CHANNELS] +
                       [Trial(Signal("chirp", 2000, 10000, 0.05), 0, ch) for ch in CHANNELS],
    # How loud? (the default chirp from full scale down)
    "volume": lambda: [Trial(DEFAULT, g) for g in (0, -6, -12, -18, -24, -30, -36)],
}
# The wide search for `bench.py sweep`: many signals, each played at several
# volumes in one go (see bench.py). Order is shuffled per run.
def sweep_signals():
    chirps = [(500, 4000), (1000, 5000), (2000, 6000), (1000, 8000), (1500, 8000), (3000, 8000),
              (1000, 10000), (2000, 10000), (3000, 10000), (3000, 12000), (4000, 12000),
              (5000, 14000), (6000, 16000), (8000, 18000)]
    out = [Signal("chirp", lo, hi, 0.05) for lo, hi in chirps]
    out += [Signal("chirp", 2000, 10000, d) for d in (0.01, 0.02, 0.035)]
    out += [Signal("chirp", 4000, 12000, 0.02)]
    out += [Signal("logchirp", lo, hi, 0.05) for lo, hi in ((1000, 10000), (1500, 8000), (2000, 12000))]
    out += [Signal("noise", lo, hi, 0.05) for lo, hi in ((1000, 6000), (1500, 8000), (2000, 10000), (4000, 12000))]
    return out


SWEEP_GAINS = (0, -10, -20, -30)


SUITES["all"] = lambda: list(dict.fromkeys(
    t for name in ("band", "duration", "type", "volume") for t in SUITES[name]()))


def by_name(name):
    for s in sweep_signals():
        if s.name == name:
            return s
    for suite in SUITES.values():
        for t in suite():
            if t.signal.name == name:
                return t.signal
    raise KeyError(name)


if __name__ == "__main__":
    for suite, make in SUITES.items():
        print(f"{suite}:")
        for t in make():
            k = t.signal.band_bins()
            print(f"  {t.signal.name:28} {t.gain_db:5.0f} dB   band "
                  f"{k[0] * ESP_RATE / NFFT:6.0f}-{k[1] * ESP_RATE / NFFT:6.0f} Hz "
                  f"({k[1] - k[0] + 1} bins), template {len(t.signal.template())} samples")
