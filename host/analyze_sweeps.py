"""Analysis of a set of sweep runs (bench.py sweep) at different positions.

1. Error models fitted to all positions together (rms timing error after the fit):
   speed of sound, array size, per-mic delays, phone offset, array rotation,
   rotation + shift (+ size), each mic's x/y. Each model also gets the honest
   leave-one-position-out check (fit on the others, test on the one left out).
2. The same rotation fitted per signal group (it is geometry if they agree).
3. Ranking of every signal at 0 and -10 dB over all positions, with the
   nominal square and with the fitted rotation.

Used for the P1-P4 analysis on 2026-11-16 (docs/experiment_log.md):
    python analyze_sweeps.py bench_results/run_20261116_200640_P1.jsonl \\
        bench_results/run_20261116_201657_P2.jsonl bench_results/run_20261116_203451_P3.jsonl \\
        bench_results/run_20261116_204112_P4.jsonl
Fits use the median pair delays of the chirps starting at >= 2 kHz, 50 ms, all volumes.
The measured pair delays do not depend on the geometry the ESP32 used, so the
rotation found is the absolute one: store it with `python bench.py ... --rot <deg>`
and in localize.MEASURED_ROT_DEG (2.13 on 2026-11-18 morning; 0.0 since the distance series a30/a20
fitted -0.15 / -0.05 deg, see the experiment log 2026-11-18 16:45).
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

import localize

P = localize.PAIRS


def load_runs(paths):
    runs = []
    for p in paths:
        lines = [json.loads(l) for l in open(p)]
        meta = lines[0]
        runs.append({"label": meta["label"], "truth": np.array(meta["truth_cm"]) / 100, "c": meta["c"],
                     "side": meta.get("array_cm", 30) / 100, "rot": meta.get("array_rot_deg", 0.0),
                     "trials": lines[1:]})
    return runs


def ok_delays(trial):
    return [localize.pair_delays(np.array(e["arr_us"])) * 1e-6
            for e in trial["events"] if e.get("type") == "event" and e["ok"]]


def median_delays(runs, select):
    out = []
    for r in runs:
        taus = [t for tr in r["trials"] if select(tr) for t in ok_delays(tr)]
        out.append((r["label"], r["truth"], np.median(taus, axis=0), r["c"], len(taus)))
    return out


def locate(tau, c):
    r = localize.locate(tau, c)
    return np.asarray(r[0] if isinstance(r, tuple) else r)


# ------------------------------------------------------------------ models
# parameter blocks: r rotation [deg], t array shift x,y [cm], a side [m],
# c speed of sound, d per-mic delays Mic2..4 [us], o phone offset [cm], m each mic x,y [cm]
X0 = {"r": [0.0], "t": [0.0, 0.0], "a": [0.30], "c": [344.0], "d": [0.0] * 3, "o": [0.0] * 3, "m": [0.0] * 8}


def unpack(p, mode, side):
    k, out = 0, {}
    for block in mode:
        n = len(X0[block])
        out[block] = np.asarray(p[k:k + n], float)
        k += n
    M = localize.square(out["a"][0] if "a" in out else side)
    if "r" in out:
        th = np.radians(out["r"][0])
        R = np.array([[np.cos(th), -np.sin(th)], [np.sin(th), np.cos(th)]])
        M[:, :2] = M[:, :2] @ R.T
    if "t" in out:
        M[:, :2] += out["t"] / 100
    if "m" in out:
        M[:, :2] += out["m"].reshape(4, 2) / 100
    d = np.r_[0.0, out["d"]] * 1e-6 if "d" in out else np.zeros(4)
    off = out["o"] / 100 if "o" in out else np.zeros(3)
    c = out["c"][0] if "c" in out else None
    return M, d, off, c


def residuals(p, mode, data, side):
    M, d, off, c_fit = unpack(p, mode, side)
    corr = np.array([d[i] - d[j] for i, j in P])
    return np.concatenate([(tau - localize.model_tdoa(s + off, c_fit or c, M) - corr) * 1e6
                           for _, s, tau, c, _ in data])


def x0(mode):
    return sum((X0[b] for b in mode), [])


def rms(v):
    return float(np.sqrt(np.mean(np.square(v))))


MODELS = [("c", "speed of sound"), ("a", "array size"), ("d", "per-mic delays (3)"),
          ("o", "common phone offset (3)"), ("r", "array rotation (1)"), ("rt", "rotation + shift (3)"),
          ("rta", "rotation + shift + size (4)"), ("m", "each mic x,y (8)")]


def fit_models(data, side):
    print(f"\nnothing fitted: rms {rms(residuals([], '', data, side)):.2f} us")
    print("model                          in-sample   leave-one-out per position (timing before -> after)")
    best = {}
    for mode, desc in MODELS:
        sol = least_squares(residuals, x0(mode), args=(mode, data, side))
        loo = []
        for k in range(len(data)):
            train = [d for i, d in enumerate(data) if i != k]
            s2 = least_squares(residuals, x0(mode), args=(mode, train, side))
            loo.append(f"{data[k][0]} {rms(residuals(x0(mode), mode, [data[k]], side)):4.1f}->"
                       f"{rms(residuals(s2.x, mode, [data[k]], side)):4.1f}")
        print(f"{desc:30} {rms(sol.fun):6.2f} us   " + "  ".join(loo) + f"   params {np.round(sol.x, 3)}")
        best[mode] = sol.x
    return best


GROUPS = {
    "chirp f_lo < 2k": lambda t: t["kind"] == "chirp" and t["f_lo"] < 2000 and t["dur"] >= 0.05,
    "chirp f_lo 2-4k": lambda t: t["kind"] == "chirp" and 2000 <= t["f_lo"] < 4000 and t["dur"] >= 0.05,
    "chirp f_lo >= 4k": lambda t: t["kind"] == "chirp" and t["f_lo"] >= 4000 and t["dur"] >= 0.05,
    "short chirps": lambda t: t["kind"] == "chirp" and t["dur"] < 0.05,
    "logchirp": lambda t: t["kind"] == "logchirp",
    "noise": lambda t: t["kind"] == "noise",
}


def rank(runs, M, title, gains=(0, -10)):
    localize.set_mics(M)
    stats = defaultdict(dict)
    labels = [r["label"] for r in runs]
    for r in runs:
        true = localize.model_tdoa(r["truth"], r["c"])
        for t in r["trials"]:
            if t["gain_db"] not in gains:
                continue
            T = ok_delays(t)
            key = (t["signal"], t["gain_db"])
            if len(T) < 2:
                stats[key][r["label"]] = None
                continue
            T = np.array(T)
            tau = np.median(T, axis=0)
            p = locate(tau, r["c"])
            u, us = p / np.linalg.norm(p), r["truth"] / np.linalg.norm(r["truth"])
            stats[key][r["label"]] = dict(rms=rms(tau - true) * 1e6, std=T.std(axis=0).mean() * 1e6,
                                          pos=np.linalg.norm(p - r["truth"]) * 100,
                                          ang=np.degrees(np.arccos(np.clip(u @ us, -1, 1))),
                                          ok=len(T) / t["played"])
    rows, unusable = [], []
    for (sig, g), d in stats.items():
        v = [x for x in d.values() if x]
        if len(v) < len(runs):
            unusable.append(f"{sig}@{g:g}")
            continue
        rows.append((sig, g, dict(rms=rms([x["rms"] for x in v]), std=np.median([x["std"] for x in v]),
                                  pos=np.median([x["pos"] for x in v]), posmax=max(x["pos"] for x in v),
                                  ang=np.median([x["ang"] for x in v]), ok=np.mean([x["ok"] for x in v]),
                                  per=[d[l]["pos"] for l in labels])))
    rows.sort(key=lambda r: r[2]["pos"])
    print(f"\n=== {title}: gains {gains}, all {len(runs)} positions, sorted by median position error ===")
    print(f"{'signal':24} {'gain':>4} {'ok%':>4} {'tdoa rms':>8} {'std':>5} {'pos med':>7} {'pos max':>7} {'dir':>4}"
          f"   pos {'/'.join(labels)} [cm]")
    for sig, g, a in rows:
        print(f"{sig:24} {g:4.0f} {a['ok'] * 100:4.0f} {a['rms']:8.1f} {a['std']:5.2f} {a['pos']:7.1f} "
              f"{a['posmax']:7.1f} {a['ang']:4.1f}   " + " ".join(f"{v:5.1f}" for v in a["per"]))
    if unusable:
        print("not usable at every position:", ", ".join(unusable))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="+", type=Path)
    args = ap.parse_args()
    runs = load_runs(args.files)
    side = runs[0]["side"]
    localize.set_mics(localize.square(side))
    main_sel = lambda t: t["kind"] == "chirp" and t["f_lo"] >= 2000 and t["dur"] >= 0.05  # noqa: E731
    data = median_delays(runs, main_sel)

    print("position fitted to the median delays (nominal square):")
    for lab, s, tau, c, n in data:
        p = locate(tau, c)
        print(f"  {lab}: measured {np.round(s * 100, 1)} fit {np.round(p * 100, 1)} "
              f"off {np.linalg.norm(p - s) * 100:4.1f} cm, range {100 * (np.linalg.norm(p) / np.linalg.norm(s) - 1):+5.1f}%, "
              f"direction {np.degrees(np.arccos(p @ s / np.linalg.norm(p) / np.linalg.norm(s))):.1f} deg (n={n})")

    best = fit_models(data, side)

    print("\nrotation fitted per signal group:")
    for g, sel in GROUPS.items():
        d = median_delays(runs, sel)
        sol = least_squares(residuals, [0.0], args=("r", d, side))
        print(f"  {g:18} {sol.x[0]:+5.2f} deg   {rms(residuals([0.0], 'r', d, side)):5.1f} -> {rms(sol.fun):5.1f} us")

    rank(runs, localize.square(side), "nominal square")
    M, *_ = unpack(best["r"], "r", side)
    rank(runs, M, f"square rotated {best['r'][0]:.2f} deg")
    used = sorted({r["rot"] for r in runs})
    print(f"\nrotation fitted: {best['r'][0]:+.2f} deg (runs were localized on the ESP32 with {used} deg; "
          f"localize.MEASURED_ROT_DEG = {localize.MEASURED_ROT_DEG:+.2f})")


if __name__ == "__main__":
    main()
