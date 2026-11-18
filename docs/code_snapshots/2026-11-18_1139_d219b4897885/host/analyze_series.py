"""Evaluate a distance series (series.py): how position and direction accuracy
change with distance, elevation, direction and array size.

Per point and series (array size), from every chirp the ESP32 localized:
  ok%        chirps that passed the checks / chirps played (success rate)
  pos mean / p95   3D position error [cm] (mean and 95th percentile)
  range      median signed distance error (measured - true) [cm]
  dir med / p95    direction error [deg]
  geom       range uncertainty the geometry alone predicts for 1 us timing noise per
             mic [cm/us]: how strongly this spot amplifies timing errors (planar array:
             distance is hard to see from steeply above and in the blind plane x=0)
Plus the Fraunhofer distance 2 D^2 / lambda of each array (D = side and diagonal,
lambda at 7.5 kHz, the chirp's centre) for the comparison in the project plan.

    python analyze_series.py                      # plan distance_v2, all series found
    python analyze_series.py --plan distance_v1 --series a30,a20
Figures: bench_results/series/<plan>/figures/
"""

import argparse
import json
from collections import defaultdict
from pathlib import Path

import numpy as np

import localize
from bench import RESULTS

COLORS = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]   # validated categorical order (light surface)
MARKERS = ["o", "s", "^", "D"]
F_CENTRE = 7500.0
C_NOM = 343.0


def load(root, series_filter=None):
    data = defaultdict(list)    # (series, point) -> list of file records
    for f in sorted(root.glob("*/*.jsonl")):
        meta, trial = [json.loads(l) for l in f.read_text().splitlines()[:2]]
        if series_filter and meta["series"] not in series_filter:
            continue
        data[(meta["series"], meta["point"])].append({"meta": meta, "trial": trial, "file": f.name})
    # a redo replaces the earlier measurement of the point: keep the newest only
    return {k: [max(v, key=lambda r: r["meta"].get("started", r["file"]))] for k, v in data.items()}


def geom_range_per_us(s_m, mics, c=C_NOM):
    """Range std [cm] for 1 us independent timing noise on each mic's arrival time."""
    eps = 1e-5
    f0 = localize.model_tdoa(s_m, c, mics)
    J = np.array([(localize.model_tdoa(s_m + eps * e, c, mics) - f0) / eps for e in np.eye(3)]).T
    D = np.zeros((len(localize.PAIRS), 4))
    for k, (i, j) in enumerate(localize.PAIRS):
        D[k, i], D[k, j] = 1, -1
    cov = np.linalg.pinv(J.T @ np.linalg.pinv(1e-12 * D @ D.T) @ J)
    u = s_m / np.linalg.norm(s_m)
    return float(np.sqrt(u @ cov @ u) * 100)


def point_stats(recs):
    meta0 = recs[0]["meta"]
    played = ok_n = 0
    perr, derr, rerr = [], [], []
    for r in recs:
        m, t = r["meta"], r["trial"]
        truth = np.array(m["truth_cm"], float)
        played += m["count"]
        ok = [e for e in t["events"] if e.get("type") == "event" and e["ok"]]
        ok_n += min(len(ok), m["count"])
        if not ok:
            continue
        P = np.array([e["pos_cm"] for e in ok], float)
        perr += list(np.linalg.norm(P - truth, axis=1))
        rerr += list(np.linalg.norm(P, axis=1) - np.linalg.norm(truth))
        az, el = np.radians([e["dir_az"] for e in ok]), np.radians([e["dir_el"] for e in ok])
        U = np.stack([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)], axis=1)
        derr += list(np.degrees(np.arccos(np.clip(U @ (truth / np.linalg.norm(truth)), -1, 1))))
    truth = np.mean([r["meta"]["truth_cm"] for r in recs], axis=0)
    r_cm, az, el = localize.to_spherical(truth)
    mics = np.array(meta0["mics_cm"]) / 100
    st = {"point": meta0["point"], "line": meta0["line"], "array_cm": meta0["array_cm"],
          "height": meta0.get("height_cm", truth[2]), "name": meta0.get("name", meta0["point"]),
          "r": r_cm, "az": az, "el": el, "placements": len(recs), "played": played, "ok": ok_n,
          "ok_rate": ok_n / played if played else 0, "geom": geom_range_per_us(truth / 100, mics)}
    if perr:
        st.update(pos_mean=np.mean(perr), pos_p95=np.percentile(perr, 95), range_med=np.median(rerr),
                  dir_med=np.median(derr), dir_p95=np.percentile(derr, 95))
    if len(recs) > 1:   # placement repeatability: spread of the per-placement median positions
        meds = [np.median([e["pos_cm"] for e in r["trial"]["events"] if e.get("type") == "event" and e["ok"]],
                          axis=0) for r in recs if any(e.get("ok") for e in r["trial"]["events"])]
        if len(meds) > 1:
            st["placement_spread_cm"] = float(np.linalg.norm(np.std(meds, axis=0)))
    return st


def fmt(v, f):
    return format(v, f) if v is not None and np.isfinite(v) else "-".rjust(len(format(0.0, f)))


def print_table(stats):
    print(f"{'point':16} {'line':4} {'r':>6} {'az':>5} {'el':>5} {'n':>3} {'ok%':>4} {'pos mean':>8} "
          f"{'p95':>6} {'range':>6} {'dir med':>7} {'p95':>5} {'geom':>6}")
    print(f"{'':16} {'':4} {'[cm]':>6} {'[deg]':>5} {'[deg]':>5} {'':>3} {'':>4} {'[cm]':>8} {'[cm]':>6} "
          f"{'[cm]':>6} {'[deg]':>7} {'[deg]':>5} {'cm/us':>6}")
    for s in sorted(stats, key=lambda s: (s["height"], s["line"], s["r"])):
        g = s.get
        print(f"{s['point']:16} {s['line']:4} {s['r']:6.1f} {s['az']:5.1f} {s['el']:5.1f} {s['played']:3d} "
              f"{s['ok_rate'] * 100:4.0f} {fmt(g('pos_mean'), '8.1f')} {fmt(g('pos_p95'), '6.1f')} "
              f"{fmt(g('range_med'), '+6.1f')} {fmt(g('dir_med'), '7.2f')} {fmt(g('dir_p95'), '5.2f')} "
              f"{s['geom']:6.1f}" + (f"   placements {s['placements']}, spread {s['placement_spread_cm']:.1f} cm"
                                       if "placement_spread_cm" in s else ""))


def fraunhofer(side_cm, f=F_CENTRE):
    lam = C_NOM / f
    d_side, d_diag = side_cm / 100, side_cm / 100 * np.sqrt(2)
    return 2 * d_side ** 2 / lam * 100, 2 * d_diag ** 2 / lam * 100


LINE_STYLE = {"Y": ("y axis (blind plane x=0)", "s", "-"), "D": ("diagonal", "o", "-"),
              "M": ("in-between", "^", "none"), "A": ("line A", "o", "-")}


def plot(by_series, out_dir):
    """Rows: 3D error, direction error, success rate. Columns: heights. x: distance
    from the array centre. Colour = array size, marker = which line of points."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.ticker
    from matplotlib.lines import Line2D
    out_dir.mkdir(parents=True, exist_ok=True)
    heights = sorted({round(s["height"]) for st in by_series.values() for s in st})
    metrics = [("pos_mean", "3D position error, mean [cm]", True),
               ("dir_med", "direction error, median [deg]", True),
               ("ok_rate", "success rate [%]", False)]
    fig, axes = plt.subplots(len(metrics), len(heights), figsize=(3.6 * len(heights), 3.2 * len(metrics)),
                             squeeze=False, sharex=True, sharey="row")
    order = sorted(by_series, key=lambda k: -by_series[k][0]["array_cm"])
    lines_seen = set()
    for col, h in enumerate(heights):
        for row, (key, label, logy) in enumerate(metrics):
            ax = axes[row][col]
            for i, ser in enumerate(order):
                color = COLORS[i % len(COLORS)]
                for line, (lname, marker, ls) in LINE_STYLE.items():
                    pts = sorted((s for s in by_series[ser] if s["line"] == line and round(s["height"]) == h
                                  and (key == "ok_rate" or key in s)), key=lambda s: s["r"])
                    if not pts:
                        continue
                    lines_seen.add(line)
                    y = [s[key] * (100 if key == "ok_rate" else 1) for s in pts]
                    ax.plot([s["r"] for s in pts], y, color=color, marker=marker, markersize=6,
                            linestyle=ls, linewidth=2, markerfacecolor=color if line != "M" else "none",
                            markeredgewidth=1.5)
                if row == 0:
                    fr = fraunhofer(by_series[ser][0]["array_cm"])[0]
                    if fr < 300:
                        ax.axvline(fr, color=color, linestyle=":", linewidth=1.5)
            if logy:
                ax.set_yscale("log")
                ax.yaxis.set_major_locator(matplotlib.ticker.LogLocator(base=10, subs=(1, 2, 5)))
                ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
                ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
            else:
                ax.set_ylim(0, 105)
            ax.set_xlim(0, 300)
            ax.grid(True, color="#e4e3df", linewidth=0.8)
            for sp in ("top", "right"):
                ax.spines[sp].set_visible(False)
            if col == 0:
                ax.set_ylabel(label)
            if row == 0:
                ax.set_title(f"height z = {h} cm")
            if row == len(metrics) - 1:
                ax.set_xlabel("distance from the array centre [cm]")
    handles = [Line2D([], [], color=COLORS[i % len(COLORS)], linewidth=2,
                      label=f"{by_series[ser][0]['array_cm']:g} cm array ({ser})") for i, ser in enumerate(order)]
    handles += [Line2D([], [], color="#52514e", marker=LINE_STYLE[l][1], linestyle=LINE_STYLE[l][2],
                       markerfacecolor="#52514e" if l != "M" else "none", label=LINE_STYLE[l][0])
                for l in LINE_STYLE if l in lines_seen]
    fig.legend(handles=handles, loc="upper center", ncol=len(handles), frameon=False, fontsize=9)
    fig.text(0.01, 0.005, "dotted: Fraunhofer distance 2·side²/λ at 7.5 kHz (if < 3 m)", fontsize=8, color="#52514e")
    fig.tight_layout(rect=(0, 0.02, 1, 0.95))
    path = out_dir / "error_vs_distance.png"
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return [path]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", default="distance_v2")
    ap.add_argument("--series", help="comma-separated series names (default: all)")
    ap.add_argument("--root", type=Path, help="results folder (default bench_results/series/<plan>)")
    args = ap.parse_args()
    root = args.root or RESULTS / "series" / args.plan
    data = load(root, args.series.split(",") if args.series else None)
    if not data:
        raise SystemExit(f"no series results in {root}")
    by_series = defaultdict(list)
    for (ser, _), recs in data.items():
        by_series[ser].append(point_stats(recs))
    for ser, st in sorted(by_series.items(), key=lambda kv: -kv[1][0]["array_cm"]):
        side = st[0]["array_cm"]
        fs, fd = fraunhofer(side)
        print(f"\n=== series {ser}: {side:g} cm array, {len(st)} points; Fraunhofer distance at 7.5 kHz: "
              f"{fs:.0f} cm (D = side), {fd:.0f} cm (D = diagonal) ===")
        print_table(st)
    for p in plot(by_series, root / "figures"):
        print(f"\nfigure: {p.resolve()}")


if __name__ == "__main__":
    main()
