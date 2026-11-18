"""System identification for the distance series: which model of the measuring chain
explains the measured delays, and what is left over.

Measurement model (per chirp, per mic i):   t_i = |s - m_i| / c + delta_i + e_i
  s        true source position (the grid point, known)
  m_i      mic positions: nominal square, rotated by rot, optionally each mic moved in x, y
  c        speed of sound
  delta_i  constant per-mic delay (cable, ADC, mic phase); one mic is the reference
  e_i      the rest: per position (systematic: echoes, speaker directivity, placement)
           and per chirp (random jitter)
Only differences of t_i are observed (6 pair delays).

Models fitted per array on the point-averaged delays (accepted chirps, z >= 50 cm;
z = 10 is left out because of the floor echo, the y axis is kept: its delays are fine):
  M0 nominal (rot 0, c from 21 C)    M1 + rotation    M2 + rotation + c
  M3 + per-mic delays                M4 per-mic delays + each mic's x, y (c fixed: c and the
                                        array scale cannot both be identified)
Validation: fit on heights 50 and 130 cm, test on 90 and 170 cm (held out), comparing
delay residual and the 3D error of the point-averaged position.
Also: random vs systematic part of the residual, effective timing noise
(measured 3D error / geometric sensitivity), range bias, size scaling.

    python identify_system.py            # prints everything, writes figures to
                                         # bench_results/series/distance_v2/figures/
"""

import json
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

import analyze_series as A
import localize as L
from bench import RESULTS

ROOT = RESULTS / "series" / "distance_v2"
C21 = L.speed_of_sound(21.0)
TRAIN_H, TEST_H = (50, 130), (90, 170)


def load_points(series):
    """Per point: truth [m], mean pair delays [s], per-chirp delays, line, height."""
    data = A.load(ROOT, [series])
    pts = []
    for (_, pid), recs in data.items():
        m, t = recs[0]["meta"], recs[0]["trial"]
        ev = [e for e in t["events"] if e.get("type") == "event" and e["ok"]]
        if len(ev) < 3:
            continue
        taus = np.array([L.pair_delays(np.array(e["arr_us"]) * 1e-6) for e in ev])
        pts.append({"id": pid, "truth": np.array(m["truth_cm"]) / 100, "tau": taus.mean(0), "taus": taus,
                    "h": m["height_cm"], "line": m["line"], "side": m["array_cm"] / 100})
    return pts


def unpack(p, kind, side):
    """Parameter vector -> (mics, c, per-mic delays [s])."""
    rot, c, d, mics = 0.0, C21, np.zeros(4), None
    k = 0
    if kind in ("M1", "M2", "M3"):
        rot = p[k]; k += 1
    if kind in ("M2", "M3"):
        c = C21 * (1 + p[k] * 1e-3); k += 1
    if kind in ("M3", "M4", "M5"):
        d = np.r_[0.0, p[k:k + 3]] * 1e-6; k += 3          # mic 1 is the reference
    mics = L.square(side, rot)
    if kind == "M4":
        mics = mics.copy()
        mics[:, :2] += p[k:k + 8].reshape(4, 2) * 1e-3      # mm
    if kind == "M5":                                        # whole array off the grid origin
        mics = mics.copy()
        mics[:, :2] += p[k:k + 2] * 1e-3
    return mics, c, d


NPAR = {"M0": 0, "M1": 1, "M2": 2, "M3": 5, "M4": 11, "M5": 5}


def residuals(p, kind, pts):
    mics, c, d = unpack(p, kind, pts[0]["side"])
    dd = np.array([d[i] - d[j] for i, j in L.PAIRS])
    return np.concatenate([(q["tau"] - L.model_tdoa(q["truth"], c, mics) - dd) * 1e6 for q in pts])


def fit(kind, pts):
    if NPAR[kind] == 0:
        return np.zeros(0)
    return least_squares(residuals, np.zeros(NPAR[kind]), args=(kind, pts)).x


def rms(x):
    return float(np.sqrt(np.mean(np.square(x))))


def locate_mean(q, mics, c, d):
    """3D position from the point-averaged delays, with the identified model."""
    dd = np.array([d[i] - d[j] for i, j in L.PAIRS])
    taus = q["tau"] - dd
    g = L.GRID
    dist = np.linalg.norm(g[:, None, :] - mics[None], axis=2)
    pred = np.array([dist[:, i] - dist[:, j] for i, j in L.PAIRS]).T / c
    best = None
    for k in np.argsort(((pred - taus) ** 2).sum(1))[:5]:
        f = least_squares(lambda s: (L.model_tdoa(s, c, mics) - taus) * 1e6, g[k],
                          bounds=([-L.MAX_RANGE] * 2 + [0], [L.MAX_RANGE] * 3))
        if best is None or f.cost < best.cost:
            best = f
    return best.x


def pos_errors(pts, mics, c, d):
    return np.array([np.linalg.norm(locate_mean(q, mics, c, d) - q["truth"]) * 100 for q in pts])


def main():
    out = {}
    figdir = ROOT / "figures"
    for ser in ("a30", "a20", "a10"):
        allp = load_points(ser)
        P = [q for q in allp if q["h"] >= 50]
        side = P[0]["side"]
        print(f"\n===== {ser} ({side * 100:g} cm): {len(P)} points at z >= 50 cm, "
              f"{sum(len(q['taus']) for q in P)} accepted chirps =====")
        # --- random vs systematic
        rnd = np.concatenate([(q["taus"] - q["tau"]).ravel() for q in P]) * 1e6
        m0 = residuals(np.zeros(0), "M0", P)
        jit_rob = 1.4826 * float(np.median(np.abs(rnd)))
        print(f"per-chirp jitter around the point mean: {rms(rnd):.2f} us rms, robust (1.48 MAD) {jit_rob:.2f} us (random part)")
        # --- models, all points
        res = {}
        for kind in ("M0", "M1", "M2", "M3", "M4", "M5"):
            p = fit(kind, P)
            r = residuals(p, kind, P)
            res[kind] = (p, rms(r))
        print("delay residual of the point means at the true positions, all z >= 50 points:")
        for kind, (p, r) in res.items():
            mics, c, d = unpack(p, kind, side)
            desc = {"M0": "nominal (rot 0, c(21 C))", "M1": "+ rotation", "M2": "+ rotation + c",
                    "M3": "+ rotation + c + per-mic delays", "M4": "per-mic delays + each mic x,y (c fixed)",
                    "M5": "per-mic delays + array offset x,y (c fixed)"}[kind]
            extra = ""
            if kind in ("M1", "M2", "M3"):
                extra += f" rot {p[0]:+.2f} deg"
            if kind in ("M2", "M3"):
                extra += f", c {c:.1f} m/s"
            if kind == "M5":
                extra += f", array centre at ({p[3]:+.1f}, {p[4]:+.1f}) mm"
            if kind in ("M3", "M4", "M5"):
                extra += ", delays M2..M4 " + " ".join(f"{v * 1e6:+.1f}" for v in d[1:]) + " us"
            if kind == "M4":
                extra += ", mic shifts " + " ".join(f"({v[0]:+.1f},{v[1]:+.1f})" for v in p[3:].reshape(4, 2)) + " mm"
            print(f"  {kind} {desc:42} rms {r:5.2f} us  {extra}")
        # --- cross validation
        tr = [q for q in P if q["h"] in TRAIN_H]
        te = [q for q in P if q["h"] in TEST_H]
        te_dm = [q for q in te if q["line"] != "Y"]     # the y axis is a blind plane: no model can fix its distance
        cv = {}
        print(f"held-out test (fit on z {TRAIN_H}, test on z {TEST_H}): delay rms (all) / 3D error of the point mean (D+M)")
        for kind in ("M0", "M1", "M3", "M5", "M4"):
            p = fit(kind, tr)
            mics, c, d = unpack(p, kind, side)
            r_te = rms(residuals(p, kind, te))
            e_te = pos_errors(te_dm, mics, c, d)
            cv[kind] = (r_te, float(np.median(e_te)))
            print(f"  {kind}: test delay rms {r_te:5.2f} us, test 3D error median {np.median(e_te):6.1f} cm "
                  f"(p90 {np.percentile(e_te, 90):6.1f})")
        # --- effective timing noise from the geometry
        mics0 = L.square(side, 0.0)
        ratio = []
        for q in P:
            if q["line"] == "Y":
                continue
            g = A.geom_range_per_us(q["truth"], mics0)
            e = np.linalg.norm(locate_mean(q, mics0, C21, np.zeros(4)) - q["truth"]) * 100
            ratio.append(e / g)
        print(f"effective timing error = 3D error / geometric sensitivity: median {np.median(ratio):.2f} us "
              f"(IQR {np.percentile(ratio, 25):.2f}-{np.percentile(ratio, 75):.2f})")
        # --- range bias (nominal model, point means, D+M)
        rb = []
        for q in P:
            if q["line"] == "Y":
                continue
            s = locate_mean(q, mics0, C21, np.zeros(4))
            rb.append((np.linalg.norm(q["truth"]), np.linalg.norm(s) / np.linalg.norm(q["truth"])))
        rb = np.array(rb)
        print(f"range ratio measured/true (D+M, nominal): median {np.median(rb[:, 1]):.2f} "
              f"(IQR {np.percentile(rb[:, 1], 25):.2f}-{np.percentile(rb[:, 1], 75):.2f})")
        out[ser] = {"side_cm": side * 100, "jitter_us": rms(rnd), "jitter_robust_us": jit_rob, "m0_us": rms(m0),
                    "models": {k: {"rms_us": v[1], "params": [float(x) for x in v[0]]} for k, v in res.items()},
                    "cv": cv, "t_eff_us": float(np.median(ratio)), "range_ratio": float(np.median(rb[:, 1])),
                    "n_points": len(P), "n_chirps": int(sum(len(q["taus"]) for q in P))}
    (figdir / "identification.json").write_text(json.dumps(out, indent=1))
    print(f"\nnumbers: {(figdir / 'identification.json').resolve()}")


if __name__ == "__main__":
    main()
