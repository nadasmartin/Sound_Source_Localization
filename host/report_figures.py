"""Figures for the distance-series report (docs/report/).

Every chirp re-localized on the host with rotation 0 (as the analysis page), statistics on
the newest placement of each point, excluded points left out, diagonal + in-between points
(the y axis is a blind plane and is reported separately). Identification numbers from
identify_system.py (run it first: bench_results/series/distance_v2/figures/identification.json).

    python report_figures.py      # -> docs/report/fig_*.svg
"""

import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.ticker as mt
import numpy as np

import analyze_series as A
import localize as L
from bench import RESULTS

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "docs" / "report"
ROOT = RESULTS / "series" / "distance_v2"
COL = {"a30": "#2a78d6", "a20": "#eb6834", "a10": "#1baf7a"}
LAB = {"a30": "30 cm", "a20": "20 cm", "a10": "10 cm"}
INK, INK2, GRID = "#0b0b0b", "#52514e", "#e4e3df"

plt.rcParams.update({"font.size": 8.5, "font.family": "DejaVu Sans", "axes.edgecolor": "#a3a29c",
                     "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
                     "axes.spines.top": False, "axes.spines.right": False, "axes.grid": True,
                     "grid.color": GRID, "grid.linewidth": 0.7, "legend.frameon": False,
                     "svg.fonttype": "none", "lines.linewidth": 2})


def logy(ax, lo, hi):
    ax.set_yscale("log")
    ax.set_ylim(lo, hi)
    ax.yaxis.set_major_locator(mt.LogLocator(base=10, subs=(1, 2, 5)))
    ax.yaxis.set_major_formatter(mt.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.yaxis.set_minor_formatter(mt.NullFormatter())


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    data = A.load(ROOT)
    A.relocalize(data, 0.0)
    st = {}
    for (ser, pid), recs in data.items():
        st[(ser, pid)] = A.point_stats(recs)
    ident = json.loads((ROOT / "figures" / "identification.json").read_text())
    sers = ["a30", "a20", "a10"]
    hs = [10, 50, 90, 130, 170]
    dm = lambda s: [v for (ss, _), v in st.items() if ss == s and v["line"] != "Y"]

    # ---- Fig 1: capability vs height
    fig, ax = plt.subplots(1, 3, figsize=(7.1, 1.95))
    for s in sers:
        P = dm(s)
        pos = [np.median([v["pos_mean"] for v in P if round(v["height"]) == h and "pos_mean" in v]) for h in hs]
        dr = [np.median([v["dir_med"] for v in P if round(v["height"]) == h and "dir_med" in v]) for h in hs]
        ok = [100 * np.mean([v["ok_rate"] for v in P if round(v["height"]) == h]) for h in hs]
        for a, y in zip(ax, (pos, dr, ok)):
            a.plot(hs, y, color=COL[s], marker="o", markersize=4.5, label=LAB[s] + " array")
            if a is ax[0]:
                a.annotate(f"{y[-1]:.0f}", (hs[-1], y[-1]), xytext=(4, 0), textcoords="offset points",
                           va="center", fontsize=7, color=INK2)
    logy(ax[0], 5, 300); logy(ax[1], 0.2, 20)
    ax[2].set_ylim(0, 105)
    for a, t in zip(ax, ("3D position error [cm]", "direction error [°]", "chirps accepted [%]")):
        a.set_title(t, fontsize=8.5, color=INK, loc="left")
        a.set_xticks(hs); a.set_xlabel("source height z above the mics [cm]")
        a.set_xlim(0, 190)
    ax[2].legend(*ax[0].get_legend_handles_labels(), loc="lower left", fontsize=7.5, handlelength=1.5)
    fig.tight_layout(w_pad=1.2)
    fig.savefig(OUT / "fig_capability.svg"); plt.close(fig)

    # ---- Fig 2: measured error vs geometric sensitivity
    fig, ax = plt.subplots(figsize=(3.45, 2.35))
    xs = np.array([0.3, 2000])
    for k, ls, xl in ((1, ":", 500), (2, "--", 60)):
        ax.plot(xs, xs * k, color="#a3a29c", lw=1, ls=ls)
        ax.text(xl, xl * k * 1.25, f"σ = {k} µs", color=INK2, fontsize=7, ha="right", rotation=33)
    for s in sers:
        P = [v for v in dm(s) if "pos_mean" in v and np.isfinite(v["geom"])]
        ax.scatter([v["geom"] for v in P], [v["pos_mean"] for v in P], s=14, color=COL[s], edgecolor="white",
                   linewidth=0.5, label=f"{LAB[s]} (σ ≈ {ident[s]['t_eff_us']:.1f} µs)", zorder=3)
    ax.set_xscale("log"); logy(ax, 1, 1000); ax.set_xlim(0.3, 1000)
    ax.xaxis.set_major_formatter(mt.FuncFormatter(lambda v, _: f"{v:g}"))
    ax.set_xlabel("geometric sensitivity G [cm per µs timing error]")
    ax.set_ylabel("measured 3D error [cm]")
    ax.legend(loc="upper left", fontsize=7, handletextpad=0.2)
    fig.tight_layout()
    fig.savefig(OUT / "fig_geometry.svg"); plt.close(fig)

    # ---- Fig 3: along the ray: measured / true distance
    fig, ax = plt.subplots(figsize=(3.45, 2.35))
    ax.axhline(1, color=INK2, lw=1)
    for s in sers:
        P = [v for v in dm(s) if "range_med" in v and round(v["height"]) >= 50]
        ax.scatter([v["r"] for v in P], [1 + v["range_med"] / v["r"] for v in P], s=14, color=COL[s],
                   edgecolor="white", linewidth=0.5, label=f"{LAB[s]}: {ident[s]['range_ratio']:.2f}", zorder=3)
    ax.set_ylim(0, 1.55); ax.set_xlim(50, 300)
    ax.set_xlabel("true distance [cm]"); ax.set_ylabel("measured / true")
    ax.legend(loc="upper center", fontsize=7, handletextpad=0.1, ncol=3, columnspacing=0.8, title="median ratio",
              title_fontsize=7)
    fig.tight_layout()
    fig.savefig(OUT / "fig_range.svg"); plt.close(fig)

    print("figures in", OUT.resolve())


if __name__ == "__main__":
    main()
