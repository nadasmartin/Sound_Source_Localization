"""Time difference of arrival (TDOA) of the test chirp at the 4 microphones.

Pipeline:
  1. record the 4-mic stream from the ESP32 (optionally playing the chirp
     train on the laptop speaker at the same time)
  2. band-pass to the chirp band, find each chirp with a matched filter
  3. for every chirp, GCC-PHAT between every pair of mics -> 6 pairwise delays
  4. least-squares fit of one arrival time per mic to those 6 delays
     (the misfit is a consistency check: t1-t2 + t2-t3 must equal t1-t3)
  5. report the arrival order and times, per chirp and averaged
  6. 3D position and direction of the source for every chirp (localize.py)

Usage:
  python tdoa.py --play laptop          # play chirps on laptop, record, analyse
  python tdoa.py --seconds 12           # just record (play the WAV from your phone)
  python tdoa.py --load recordings/x.npz   # re-analyse a saved recording
"""

import argparse
import socket
import subprocess
import time
from datetime import datetime
from pathlib import Path

import matplotlib
import numpy as np
from scipy.signal import butter, fftconvolve, find_peaks, sosfiltfilt

import localize
import test_signal

HOST_DIR = Path(__file__).parent

# Must match the firmware
TCP_PORT = 3333
FS = 44100                  # samples per second per mic
NUM_MICS = 4
OVERSAMPLE = 4
FRAME_SETS = 128
FRAME_BYTES = 6 + FRAME_SETS * 6
SYNC = b"\xaa\x55"
# The ADC converts the mics one after another, not simultaneously: mic k is
# sampled k conversion-slots after mic 1. 1 slot = 1/(FS*OVERSAMPLE*NUM_MICS)
# = 1.42 us. Small, but known, so we correct for it.
CHANNEL_SKEW_S = 1.0 / (FS * OVERSAMPLE * NUM_MICS)

SPEED_OF_SOUND = 343.0      # m/s at ~20 C
BAND = (1200, 9000)         # Hz, slightly wider than the chirp's 1.5-8 kHz
MIC_NAMES = ["Mic1", "Mic2", "Mic3", "Mic4"]


# ---------------------------------------------------------------- recording

def unpack_sets(payload):
    b = np.frombuffer(payload, dtype=np.uint8).reshape(-1, 3).astype(np.uint16)
    first = b[:, 0] | ((b[:, 1] & 0x0F) << 8)
    second = (b[:, 1] >> 4) | (b[:, 2] << 4)
    return np.stack([first, second], axis=1).reshape(-1, NUM_MICS)


def record(host, seconds, on_connected=None):
    """Record `seconds` of audio. Lost frames are filled with the mean value so
    the timeline stays intact; their positions are returned so chirps that
    overlap a gap can be skipped."""
    sock = socket.create_connection((host, TCP_PORT), timeout=5)
    if on_connected:
        on_connected()
    need = int(seconds * FS)
    chunks, gaps, got = [], [], 0
    pending, last_seq = b"", None
    while got < need:
        data = sock.recv(65536)
        if not data:
            raise ConnectionError("ESP32 closed the connection")
        pending += data
        while True:
            start = pending.find(SYNC)
            if start == -1 or len(pending) < start + FRAME_BYTES:
                pending = pending[start:] if start != -1 else pending[-1:]
                break
            frame = pending[start:start + FRAME_BYTES]
            pending = pending[start + FRAME_BYTES:]
            seq = frame[2] | (frame[3] << 8)
            if last_seq is not None:
                lost = ((seq - last_seq) & 0xFFFF) - 1
                if lost:
                    gaps.append((got, got + lost * FRAME_SETS))
                    chunks.append(np.full((lost * FRAME_SETS, NUM_MICS), 2048, np.uint16))
                    got += lost * FRAME_SETS
            last_seq = seq
            chunks.append(unpack_sets(frame[6:]))
            got += FRAME_SETS
    sock.close()
    return np.concatenate(chunks)[:need].astype(float), gaps


# ----------------------------------------------------------------- analysis

def bandpass(x):
    sos = butter(4, BAND, btype="bandpass", fs=FS, output="sos")
    # filtfilt = forward + backward pass: zero phase, so no added delay
    return sosfiltfilt(sos, x - x.mean(axis=0), axis=0)


def find_chirps(x):
    """Matched filter: correlate with the known chirp, peaks = chirp starts."""
    template = test_signal.chirp_template(FS)
    mixed = x.sum(axis=1)
    score = np.abs(fftconvolve(mixed, template[::-1], mode="valid"))
    noise = np.median(score)
    peaks, props = find_peaks(score, height=max(10 * noise, 0.3 * score.max()),
                              distance=int(0.3 * FS))
    return peaks, score, noise


def gcc_phat(x, y, max_lag_s, interp=16):
    """Delay of x relative to y in seconds (positive = x hears it later).

    Cross-correlation computed in the frequency domain; PHAT divides out the
    magnitude so only phase (= timing) is left, which gives a sharp peak and
    reduces the influence of room resonances. Only the chirp band is used:
    outside it there is just noise. Zero-padding the inverse FFT by `interp`
    interpolates the correlation to 1/interp of a sample.
    """
    n = 1 << int(np.ceil(np.log2(len(x) + len(y))))
    X, Y = np.fft.rfft(x, n), np.fft.rfft(y, n)
    R = X * np.conj(Y)
    R /= np.abs(R) + 1e-12
    freqs = np.fft.rfftfreq(n, 1 / FS)
    R[(freqs < BAND[0]) | (freqs > BAND[1])] = 0
    cc = np.fft.irfft(R, n * interp)
    max_shift = int(max_lag_s * FS * interp)
    cc = np.concatenate([cc[-max_shift:], cc[:max_shift + 1]])
    k = int(np.argmax(cc))
    # parabolic fit through the peak and its neighbours for the last bit
    if 0 < k < len(cc) - 1:
        a, b, c = cc[k - 1], cc[k], cc[k + 1]
        k += 0.5 * (a - c) / (a - 2 * b + c)
    # A perfect match puts all in-band energy into one peak of height
    # 2*n_band/(n*interp) (irfft scaling); dividing by that gives 1.0.
    n_band = np.count_nonzero(R)
    quality = cc.max() * n * interp / (2 * n_band)   # ~1 = perfect, ~0 = no match
    return (k - max_shift) / (FS * interp), quality, cc


def arrival_times(x, start, max_lag_s):
    """Arrival time of one chirp at each mic, relative to the earliest."""
    pre = int(0.003 * FS)
    length = len(test_signal.chirp_template(FS)) + 2 * pre
    seg = x[start - pre:start - pre + length]

    pairs, taus, quals = [], [], []
    for i in range(NUM_MICS):
        for j in range(i + 1, NUM_MICS):
            tau, q, _ = gcc_phat(seg[:, i], seg[:, j], max_lag_s)
            # undo the ADC's sequential sampling (see CHANNEL_SKEW_S)
            tau += (i - j) * CHANNEL_SKEW_S
            pairs.append((i, j)); taus.append(tau); quals.append(q)

    # Solve t_i - t_j = tau_ij for t (6 equations, 4 unknowns, least squares).
    # The sum-to-zero row pins down the arbitrary common offset.
    A = np.zeros((len(pairs) + 1, NUM_MICS))
    for r, (i, j) in enumerate(pairs):
        A[r, i], A[r, j] = 1, -1
    A[-1, :] = 1
    b = np.append(taus, 0)
    t, *_ = np.linalg.lstsq(A, b, rcond=None)
    misfit = np.sqrt(np.mean((A[:-1] @ t - b[:-1]) ** 2))
    return t - t.min(), misfit, min(quals), dict(zip(pairs, taus))


def analyse(x, gaps, max_lag_s, plot_path, c):
    xf = bandpass(x)
    peaks, score, noise = find_chirps(xf)
    pre = int(0.003 * FS)
    tlen = len(test_signal.chirp_template(FS))
    print(f"found {len(peaks)} chirps (matched-filter SNR of weakest: "
          f"{(score[peaks].min() / noise if len(peaks) else 0):.0f}x noise)\n")

    rows = []
    header = "chirp   time  " + "".join(f"{n:>9}" for n in MIC_NAMES) + \
             "   misfit  quality  order"
    print(header + "\n" + " " * 14 + "  arrival after first mic [us]")
    for n, p in enumerate(peaks):
        if p - pre < 0 or p + tlen + pre > len(xf):
            continue
        if any(a < p + tlen + pre and p - pre < b for a, b in gaps):
            print(f"{n:5d}  skipped (lost frames)")
            continue
        t, misfit, q, _ = arrival_times(xf, p, max_lag_s)
        order = " > ".join(MIC_NAMES[k] for k in np.argsort(t))
        print(f"{n:5d} {p / FS:6.2f}s " + "".join(f"{v * 1e6:9.1f}" for v in t) +
              f"   {misfit * 1e6:5.1f}us  {q:6.2f}   {order}")
        rows.append((t, misfit, q, p))

    if not rows:
        print("no usable chirps")
        return
    good = [r for r in rows if r[1] < 10e-6 and r[2] > 0.2]
    print(f"\n{len(good)}/{len(rows)} chirps pass the checks "
          f"(misfit < 10 us, quality > 0.2)")
    if not good:
        good = rows
    T = np.array([r[0] for r in good])
    # Re-reference to the mic that is first on average, then summarise
    T -= T[:, [int(np.argmin(np.median(T, axis=0)))]]
    med, std = np.median(T, axis=0), T.std(axis=0)

    print("\nRESULT (median over good chirps)")
    print(f"{'mic':6}{'arrival [us]':>14}{'+/- std':>10}{'samples':>10}{'extra path [cm]':>17}")
    for k in np.argsort(med):
        print(f"{MIC_NAMES[k]:6}{med[k] * 1e6:14.1f}{std[k] * 1e6:10.1f}"
              f"{med[k] * FS:10.2f}{med[k] * SPEED_OF_SOUND * 100:17.1f}")
    print("order:", " > ".join(MIC_NAMES[k] for k in np.argsort(med)))

    plot(xf, good, plot_path)
    report_position(good, c, plot_path.with_name(plot_path.stem + "_3d.png"))


def _expected_error(p, c, sigma):
    """1-sigma position error predicted from the geometry for timing noise
    `sigma`: how much the position must move to change the delays by sigma."""
    h = 1e-5
    J = np.array([(localize.model_tdoa(p + h * e, c) - localize.model_tdoa(p - h * e, c))
                  / (2 * h) for e in np.eye(3)]).T
    eig = np.linalg.eigvalsh(J.T @ J)
    return sigma * np.sqrt(np.sum(1 / np.maximum(eig, 1e-30)))


def report_position(rows, c, path):
    """Locate the source from every good chirp, then summarise."""
    P, D = [], []
    for t, *_ in rows:
        taus = localize.pair_delays(t)
        P.append(localize.locate(taus, c)[0])
        D.append(localize.direction(taus, c))
    P, D = np.array(P) * 100, np.array(D)     # cm, degrees
    med = np.median(P, axis=0)
    r, az, el = localize.to_spherical(med)

    print(f"\n3D POSITION  (speed of sound {c:.1f} m/s, {len(P)} chirps)")
    print(f"{'':12}{'x [cm]':>9}{'y [cm]':>9}{'z [cm]':>9}")
    print(f"{'median':12}" + "".join(f"{v:9.1f}" for v in med))
    print(f"{'spread (std)':12}" + "".join(f"{v:9.1f}" for v in P.std(axis=0)))
    print(f"distance {r:.1f} cm, azimuth {az:.1f} deg, elevation {el:.1f} deg")
    print(f"direction only (far-field model): azimuth {np.median(D[:, 0]):.1f} deg, "
          f"elevation {np.median(D[:, 1]):.1f} deg")

    # How much of that can we believe? Timing noise -> expected position error.
    T = np.array([row[0] for row in rows])
    sigma = max(np.median(T.std(axis=0)[T.std(axis=0) > 0]), 1e-6)
    err = _expected_error(med / 100, c, sigma) * 100
    print(f"expected position error from {sigma * 1e6:.1f} us timing noise: ~{err:.0f} cm")
    off_plane = min(az % 90, 90 - az % 90)
    if off_plane < 10:
        print(f"WARNING: only {off_plane:.0f} deg from a blind plane (x=0 or y=0). "
              "There the delays hardly depend on distance; trust the direction, "
              "not the position.")

    plot_3d(P, med, path)


def plot_3d(P, med, path):
    import matplotlib.pyplot as plt

    mics = localize.MICS * 100
    fig = plt.figure(figsize=(13, 5))
    ax = fig.add_subplot(1, 3, 1, projection="3d")
    ax.scatter(*mics.T, color="k", marker="s", label="mics")
    ax.scatter(*P.T, color="C3", s=8, alpha=0.5, label="per chirp")
    ax.scatter(*med, color="C3", s=80, marker="*", label="median")
    ax.set(xlabel="x [cm]", ylabel="y [cm]", zlabel="z [cm]", title="3D")
    ax.legend(fontsize=8)
    for k, (i, j, name) in enumerate([(0, 1, "top view (x-y)"), (0, 2, "side view (x-z)")]):
        a = fig.add_subplot(1, 3, k + 2)
        a.scatter(mics[:, i], mics[:, j], color="k", marker="s")
        for n, m in enumerate(mics):
            a.annotate(f"M{n + 1}", (m[i], m[j]), textcoords="offset points", xytext=(4, 4))
        a.scatter(P[:, i], P[:, j], color="C3", s=8, alpha=0.5)
        a.scatter(med[i], med[j], color="C3", s=120, marker="*")
        a.set(xlabel="xyz"[i] + " [cm]", ylabel="xyz"[j] + " [cm]", title=name)
        a.set_aspect("equal", adjustable="datalim")
        a.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    print(f"plot: {path.resolve()}")


def plot(xf, rows, path):
    import matplotlib.pyplot as plt

    # Show the chirp whose result is closest to the median: a typical one
    T = np.array([r[0] for r in rows])
    best = rows[int(np.argmin(np.abs(T - np.median(T, axis=0)).sum(axis=1)))]
    t_arr, _, _, start = best
    pre = int(0.002 * FS)
    seg = xf[start - pre:start + int(0.004 * FS)]
    ms = (np.arange(len(seg)) - pre) / FS * 1000

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8))
    scale = np.abs(seg).max()
    for k in range(NUM_MICS):
        ax1.plot(ms, seg[:, k] / scale - 2.2 * k, color=f"C{k}", lw=1,
                 label=MIC_NAMES[k])
        ax1.axvline(t_arr[k] * 1000 + ms[0] + 2, color=f"C{k}", ls="--", lw=0.8)
    ax1.set(title=f"Chirp start at {start / FS:.2f} s (band-passed). Dashed: estimated arrival",
            xlabel="time [ms]", yticks=[])
    ax1.legend(loc="upper right")

    # Raw GCC-PHAT curves of every mic against the first-arriving mic
    ref = int(np.argmin(t_arr))
    length = len(test_signal.chirp_template(FS)) + 2 * int(0.003 * FS)
    win = xf[start - int(0.003 * FS):start - int(0.003 * FS) + length]
    for k in range(NUM_MICS):
        if k == ref:
            continue
        tau, _, cc = gcc_phat(win[:, k], win[:, ref], 0.0015)
        lags = (np.arange(len(cc)) - len(cc) // 2) / (FS * 16) * 1e6
        ax2.plot(lags, cc, color=f"C{k}", lw=1,
                 label=f"{MIC_NAMES[k]} vs {MIC_NAMES[ref]}: {tau * 1e6:.1f} us")
    ax2.set(title="GCC-PHAT (peak position = time difference)",
            xlabel="lag [us]", ylabel="correlation")
    ax2.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=110)
    print(f"\nplot: {path.resolve()}")


# --------------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="esp32-mics.local")
    parser.add_argument("--seconds", type=float, default=3.0)
    parser.add_argument("--play", choices=["laptop"],
                        help="play the chirp train on the laptop's left speaker")
    parser.add_argument("--load", type=Path, help="analyse a saved recording")
    parser.add_argument("--max-tdoa-us", type=float, default=1500,
                        help="largest delay to search for; > spacing / 343 m/s")
    parser.add_argument("--temp", type=float, default=21.0,
                        help="room temperature in C (sets the speed of sound)")
    parser.add_argument("--show", action="store_true", help="open the plot window")
    args = parser.parse_args()
    if not args.show:
        matplotlib.use("Agg")

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.load:
        rec = np.load(args.load)
        x, gaps = rec["x"], [tuple(g) for g in rec["gaps"]]
    else:
        player = []

        def start_playback():
            if args.play == "laptop":
                wav = test_signal.write_wavs(HOST_DIR / "signals")["left"]
                player.append(subprocess.Popen(["paplay", str(wav)]))

        print(f"recording {args.seconds:.0f} s from {args.host} ...")
        x, gaps = record(args.host, args.seconds, start_playback)
        for p in player:
            p.terminate()
        out = HOST_DIR / "recordings" / f"rec_{stamp}.npz"
        out.parent.mkdir(exist_ok=True)
        np.savez_compressed(out, x=x, gaps=np.array(gaps).reshape(-1, 2), fs=FS)
        print(f"saved: {out.resolve()}  (lost-frame gaps: {len(gaps)})")

    plot_path = HOST_DIR / "results" / f"tdoa_{stamp}.png"
    plot_path.parent.mkdir(exist_ok=True)
    analyse(x, gaps, args.max_tdoa_us * 1e-6, plot_path,
            localize.speed_of_sound(args.temp))
    if args.show:
        import matplotlib.pyplot as plt
        plt.show()


if __name__ == "__main__":
    main()
