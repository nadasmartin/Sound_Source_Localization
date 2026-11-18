"""Build the interactive analysis page for the distance series.

Reads every series of a plan (bench_results/series/<plan>/<series>/*.jsonl), localizes
every chirp again on the host with the re-fitted array rotation (default 0 deg, see the
experiment log 2026-11-18 16:45) - accepted AND rejected chirps - and writes one
self-contained HTML page with all the data inside:

    python build_dashboard.py                       # -> docs/dashboard/index.html
    python build_dashboard.py --rot 0 --out ../docs/dashboard/index.html

Data in the page, per chirp: the ESP32's own result (as run, with the rotation the run
used) and the host re-localization (common rotation for all series), arrival times,
quality, misfit, SNR, level, clipping. Every placement is kept (redos too, flagged as
superseded); the statistics use the newest placement of each point, as analyze_series.py
does, and skip the points in excluded.json (they can be shown on the page).
The page needs internet once for Plotly (cdnjs); the data itself is embedded.
"""

import argparse
import datetime as dt
import json
from pathlib import Path

import numpy as np
from scipy.optimize import least_squares

import analyze_series as A
import localize as L
from bench import RESULTS

HERE = Path(__file__).resolve().parent
TEMPLATE = HERE / "dashboard" / "template.html"
MAX_MISFIT_US = 10.0      # firmware/lib/tdoa/dsp_config.h MAX_MISFIT_S
MIN_QUALITY = 0.2         # firmware/lib/tdoa/dsp_config.h MIN_QUALITY


def solver(side_m, rot_deg):
    mics = L.square(side_m, rot_deg)
    d = np.linalg.norm(L.GRID[:, None, :] - mics[None], axis=2)
    grid_dd = np.array([d[:, i] - d[:, j] for i, j in L.PAIRS]).T          # path differences [m]
    A_dir = np.array([-(mics[i] - mics[j])[:2] for i, j in L.PAIRS])

    def solve(arr_us, c):
        taus = L.pair_delays(np.asarray(arr_us, float) * 1e-6)
        best = None
        for k in np.argsort(((grid_dd / c - taus) ** 2).sum(axis=1))[:5]:
            fit = least_squares(lambda s: (L.model_tdoa(s, c, mics) - taus) * 1e6, L.GRID[k],
                                bounds=([-L.MAX_RANGE] * 2 + [0], [L.MAX_RANGE] * 3))
            if best is None or fit.cost < best.cost:
                best = fit
        uxy, *_ = np.linalg.lstsq(A_dir, taus * c, rcond=None)
        h = float(np.linalg.norm(uxy))
        az = float(np.degrees(np.arctan2(uxy[1], uxy[0])) % 360)
        el = float(np.degrees(np.arccos(min(h, 1.0))))
        return best.x * 100, az, el
    return mics, solve


def r1(v, nd=1):
    return None if v is None or not np.isfinite(v) else round(float(v), nd)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", default="distance_v2")
    ap.add_argument("--rot", type=float, default=L.MEASURED_ROT_DEG,
                    help="array rotation for the host re-localization [deg] (default: localize.MEASURED_ROT_DEG)")
    ap.add_argument("--out", type=Path, default=HERE.parent / "docs" / "dashboard" / "index.html")
    args = ap.parse_args()

    root = RESULTS / "series" / args.plan
    plan = json.loads((HERE / "plans" / f"{args.plan}.json").read_text())
    excluded = A.load_excluded(root)

    files = []
    for f in sorted(root.glob("*/*.jsonl")):
        meta, trial = [json.loads(l) for l in f.read_text().splitlines()[:2]]
        files.append((f, meta, trial))
    newest = {}
    for f, m, _ in files:
        k = (m["series"], m["point"])
        key = m.get("started", f.name)
        if k not in newest or key > newest[k][0]:
            newest[k] = (key, f.name)

    series_ids = sorted({m["series"] for _, m, _ in files}, key=lambda s: -next(
        m["array_cm"] for _, m, _ in files if m["series"] == s))
    data_newest = A.load(root)          # for the rotation fit (newest placement, minus exclusions)
    solvers, series = {}, []
    for s in series_ids:
        m0 = next(m for _, m, _ in files if m["series"] == s)
        side = m0["array_cm"]
        rot_fit, rms_fit, rms_run, rot_run, n_fit = A.fit_rotation(data_newest, s)
        mics0, solve = solver(side / 100, args.rot)
        solvers[s] = solve
        fs, fd = A.fraunhofer(side)
        series.append({"id": s, "side_cm": side, "rot_run": rot_run, "rot_fit": round(rot_fit, 2),
                       "rms_fit_us": round(rms_fit, 2), "rms_run_us": round(rms_run, 2), "n_fit": n_fit,
                       "mics_run_cm": [[round(v, 2) for v in r] for r in m0["mics_cm"]],
                       "mics_host_cm": [[round(v * 100, 2) for v in r] for r in mics0],
                       "fraunhofer_cm": [round(fs, 1), round(fd, 1)], "fw": m0.get("fw"),
                       "code_version": m0.get("code_version"), "note": m0.get("note", "")})
        print(f"{s}: side {side:g} cm, run rotation {rot_run:+.2f}, fitted {rot_fit:+.2f} deg")

    points = []
    for p in plan["points"]:
        truth = np.array(p["pos_cm"], float)
        r, az, el = L.to_spherical(truth)
        geom = {}
        for s in series:
            g = A.geom_range_per_us(truth / 100, np.array(s["mics_host_cm"]) / 100)
            geom[s["id"]] = r1(g, 2)
        points.append({"id": p["id"], "name": p["name"], "line": p["line"], "h": p["height_cm"],
                       "truth": [round(v, 1) for v in truth], "r": round(r, 1), "az": round(az, 2),
                       "el": round(el, 2), "geom": geom})

    placements, events = [], []
    n_total = sum(len(t["events"]) for _, _, t in files)
    done = 0
    for f, m, t in files:
        k = (m["series"], m["point"])
        pl = {"i": len(placements), "series": m["series"], "point": m["point"], "file": f.name,
              "started": m.get("started"), "redo": bool(m.get("redo")),
              "current": newest[k][1] == f.name, "excluded": excluded.get(k),
              "count": m["count"], "temp": m.get("temp"), "c": m.get("c"), "truth": m["truth_cm"],
              "rot_run": m.get("array_rot_deg", 0.0)}
        placements.append(pl)
        solve = solvers[m["series"]]
        for e in t["events"]:
            done += 1
            if e.get("type") != "event":
                continue
            hp, haz, hel = solve(e["arr_us"], m["c"])
            ep = e.get("pos_cm") or [np.nan] * 3
            events.append([pl["i"], e.get("n"), int(bool(e["ok"])), r1(e.get("q"), 3), r1(e.get("misfit_us"), 2),
                           r1(e.get("snr"), 1), r1(e.get("lvl_db"), 1), int(e.get("clip", 0)),
                           [r1(v, 1) for v in e["arr_us"]],
                           [r1(v, 1) for v in ep], r1(e.get("dir_az"), 2), r1(e.get("dir_el"), 2),
                           [r1(v, 1) for v in hp], r1(haz, 2), r1(hel, 2)])
        if len(placements) % 25 == 0 or done == n_total:
            print(f"  re-localized {done}/{n_total} chirps", flush=True)
    print()

    data = {
        "meta": {"plan": args.plan, "plan_doc": plan.get("description", ""),
                 "generated": dt.datetime.now().isoformat(timespec="seconds"),
                 "host_rot_deg": args.rot, "max_misfit_us": MAX_MISFIT_US, "min_quality": MIN_QUALITY,
                 "signal": "chirp 3-12 kHz, 50 ms", "f_centre_hz": A.F_CENTRE,
                 "mic_plane_above_floor_cm": 4.0,
                 "excluded": [{"series": s, "point": p, "reason": r} for (s, p), r in sorted(excluded.items())]},
        "series": series, "points": points, "placements": placements,
        "event_fields": ["pl", "n", "ok", "q", "misfit_us", "snr", "lvl_db", "clip", "arr_us",
                         "esp_pos", "esp_az", "esp_el", "host_pos", "host_az", "host_el"],
        "events": events,
    }
    blob = json.dumps(data, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    html = TEMPLATE.read_text().replace("/*__DATA__*/null", blob)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(html)
    print(f"{len(placements)} placements, {len(events)} chirps -> {args.out.resolve()} "
          f"({args.out.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
