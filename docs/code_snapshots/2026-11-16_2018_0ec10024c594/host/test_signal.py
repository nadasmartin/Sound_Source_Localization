"""The known test signal: a train of linear chirps (frequency sweeps).

A chirp is broadband, so its cross-correlation has one sharp peak, which is
what GCC-PHAT needs. A pure tone repeats every period and gives many equal
peaks instead. The same parameters are used to build the matched-filter
template in tdoa.py, so the signal and the detector always agree.

Run directly to write the WAV files:
    python test_signal.py      -> host/signals/*.wav
"""

from pathlib import Path

import numpy as np
from scipy.io import wavfile
from scipy.signal import chirp

F_START = 1500      # Hz; small speakers are weak below ~1 kHz
F_END = 8000        # Hz; electret modules roll off above ~10 kHz
CHIRP_SECONDS = 0.05
PERIOD_SECONDS = 0.5   # one chirp every half second
REPEATS = 120         # 60 s: start it on the phone, then measure any time
LEAD_SECONDS = 0.5     # silence before the first chirp
WAV_RATE = 48000


def chirp_template(rate):
    """One chirp sampled at `rate`, with smooth 5 ms fades so it doesn't click."""
    t = np.arange(int(CHIRP_SECONDS * rate)) / rate
    x = chirp(t, F_START, CHIRP_SECONDS, F_END, method="linear")
    fade = int(0.005 * rate)
    ramp = 0.5 - 0.5 * np.cos(np.linspace(0, np.pi, fade))
    x[:fade] *= ramp
    x[-fade:] *= ramp[::-1]
    return x


def chirp_train(rate):
    one = chirp_template(rate)
    period = int(PERIOD_SECONDS * rate)
    out = np.zeros(int(LEAD_SECONDS * rate) + REPEATS * period)
    for k in range(REPEATS):
        start = int(LEAD_SECONDS * rate) + k * period
        out[start:start + len(one)] = one
    return out


def write_wavs(folder):
    folder.mkdir(parents=True, exist_ok=True)
    mono = (chirp_train(WAV_RATE) * 0.9 * 32767).astype(np.int16)
    # Phone: mono. Laptop: left channel only, because two speakers playing the
    # same sound would be two sources and confuse the time differences.
    left_only = np.column_stack([mono, np.zeros_like(mono)])
    paths = {
        "mono": folder / "chirp_train_mono.wav",
        "left": folder / "chirp_train_left_only.wav",
    }
    wavfile.write(paths["mono"], WAV_RATE, mono)
    wavfile.write(paths["left"], WAV_RATE, left_only)
    return paths


if __name__ == "__main__":
    for p in write_wavs(Path(__file__).parent / "signals").values():
        print(p)
