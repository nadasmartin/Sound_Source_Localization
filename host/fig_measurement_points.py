"""3D figure of the measured source positions for the final report (Hungarian labels).

    python fig_measurement_points.py   # -> docs/final_report/img/meresi_pontok.png
"""
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "docs" / "final_report" / "img" / "meresi_pontok.png"
COL = {"D": "#2a78d6", "Y": "#eb6834", "M": "#1baf7a"}
LAB = {"D": "átló irány (D)", "Y": "y tengely, szimmetriasík (Y)", "M": "köztes pontok (M1–M8)"}

plan = json.loads((HERE / "plans" / "distance_v2.json").read_text())
plt.rcParams.update({"font.size": 9, "font.family": "DejaVu Sans"})
fig = plt.figure(figsize=(7.2, 5.6))
ax = fig.add_subplot(projection="3d")

# the measured eighth of the hemisphere: floor wedge between az 45 and 90 deg
R = 260
th = np.radians(np.linspace(45, 90, 40))
wx, wy = np.r_[0, R * np.cos(th), 0], np.r_[0, R * np.sin(th), 0]
ax.plot_trisurf(np.r_[0, R * np.cos(th)], np.r_[0, R * np.sin(th)], np.zeros(len(th) + 1),
                color="#2a78d6", alpha=0.07, linewidth=0)
ax.plot(wx, wy, 0, color="#a3a29c", lw=1)
# mic square (30 cm layout)
h = 15
sq = np.array([[-h, h], [h, h], [h, -h], [-h, -h], [-h, h]])
ax.plot(sq[:, 0], sq[:, 1], 0, color="#0b0b0b", lw=1.5)
ax.scatter(sq[:4, 0], sq[:4, 1], 0, color="#0b0b0b", s=12)

seen = set()
for p in plan["points"]:
    x, y, z = p["pos_cm"]
    g = p["line"] if p["line"] in COL else "M"
    ax.plot([x, x], [y, y], [0, z], color="#e4e3df", lw=0.6, zorder=1)
    ax.scatter(x, y, z, color=COL[g], s=18, depthshade=False, edgecolor="white", linewidth=0.4,
               label=None if g in seen else LAB[g])
    seen.add(g)

ax.set_xlabel("x [cm]"); ax.set_ylabel("y [cm]"); ax.set_zlabel("z [cm]")
ax.set_xlim(-60, 200); ax.set_ylim(-60, 260); ax.set_zlim(0, 180)
ax.set_box_aspect((260, 320, 180))
ax.view_init(elev=22, azim=-118)
ax.legend(loc="upper left", frameon=False, fontsize=8.5)
ax.text(95, 40, 0, "mért tartomány\n(az = 45°–90°)", color="#52514e", fontsize=8)
fig.tight_layout()
OUT.parent.mkdir(parents=True, exist_ok=True)
fig.savefig(OUT, dpi=200)
print(OUT)
