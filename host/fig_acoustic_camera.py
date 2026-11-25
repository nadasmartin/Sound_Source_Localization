"""Illustration of an acoustic camera for the final report (Hungarian labels).

A simulated example, not a product photo: delay-and-sum beamforming of a broadband
point source (4-12 kHz) on an image plane 2 m in front of the microphones,
(a) for a 64-microphone spiral array (typical of acoustic cameras),
(b) for the 4-microphone 30 cm square of this project. The sound map of (a) is
drawn over a simple pipework scene, as an acoustic camera overlays it on video.

    python fig_acoustic_camera.py   # -> docs/final_report/img/akusztikus_kamera.png
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.patches as mp
import matplotlib.pyplot as plt
import numpy as np

HERE = Path(__file__).resolve().parent
OUT = HERE.parent / "docs" / "final_report" / "img" / "akusztikus_kamera.png"
C = 343.0
DIST = 2.0                      # image plane distance [m]
SRC = np.array([0.32, -0.12])   # leak position on the image plane [m]
FREQS = np.linspace(4000, 12000, 33)


def spiral(n=64, radius=0.17):
    """Sunflower (Fermat) spiral: the usual aperiodic layout, low side lobes."""
    k = np.arange(1, n + 1)
    r = radius * np.sqrt(k / n)
    th = k * np.pi * (3 - np.sqrt(5))
    return np.c_[r * np.cos(th), r * np.sin(th)]


def beam_map(mics, X, Y):
    """Delay-and-sum power [dB re max] over the image plane, broadband average."""
    def dist(px, py):
        return np.sqrt((px[..., None] - mics[:, 0]) ** 2 + (py[..., None] - mics[:, 1]) ** 2 + DIST ** 2)
    d_grid = dist(X, Y)                                       # [ny, nx, m]
    d_src = dist(np.array(SRC[0]), np.array(SRC[1]))          # [m]
    p = np.zeros(X.shape)
    for f in FREQS:
        k = 2 * np.pi * f / C
        steer = np.exp(1j * k * (d_grid - d_src))             # phase of the source as seen per pixel
        p += np.abs(steer.sum(-1)) ** 2
    p /= p.max()
    return 10 * np.log10(p)


def scene(ax):
    """Simple pipework drawn in grey, like the video image under the sound map."""
    g = dict(facecolor="#c9c8c3", edgecolor="#7d7c77", lw=1.2)
    ax.add_patch(mp.Rectangle((-0.9, -0.18), 1.8, 0.12, **g))          # horizontal pipe
    ax.add_patch(mp.Rectangle((-0.45, -0.6), 0.12, 0.45, **g))         # vertical pipe
    ax.add_patch(mp.Rectangle((0.25, -0.24), 0.1, 0.24, **g))          # flange (the leak)
    ax.add_patch(mp.Rectangle((-0.9, 0.25), 1.8, 0.08, **g))           # upper pipe
    ax.add_patch(mp.Circle((-0.39, 0.29), 0.1, **g))                   # valve wheel
    ax.add_patch(mp.Rectangle((0.55, -0.6), 0.25, 0.42, facecolor="#dddcd7", edgecolor="#7d7c77"))  # cabinet


def main():
    x = np.linspace(-0.9, 0.9, 241)
    y = np.linspace(-0.6, 0.6, 161)
    X, Y = np.meshgrid(x, y)
    arrays = {"(a) akusztikus kamera: 64 mikrofon, spirál": spiral(),
              "(b) ez a munka: 4 mikrofon, 30 cm-es négyzet": np.array([[-.15, .15], [.15, .15], [.15, -.15], [-.15, -.15]])}
    plt.rcParams.update({"font.size": 9, "font.family": "DejaVu Sans"})
    fig = plt.figure(figsize=(5.9, 4.4))
    gs = fig.add_gridspec(2, 3, width_ratios=[1.75, 2.85, 0.1], hspace=0.28, wspace=0.06,
                          left=0.01, right=0.86, top=0.93, bottom=0.03)
    for row, (title, mics) in enumerate(arrays.items()):
        axm = fig.add_subplot(gs[row, 0])
        axm.add_patch(mp.Circle((0, 0), 0.2, facecolor="#f2f2f0", edgecolor="#a3a29c"))
        axm.scatter(mics[:, 0], mics[:, 1], s=9 if len(mics) > 4 else 28, color="#0b0b0b")
        axm.set(xlim=(-0.22, 0.22), ylim=(-0.22, 0.22), aspect="equal", xticks=[], yticks=[])
        axm.set_title("mikrofonok" if row == 0 else "", fontsize=8.5)
        for s in axm.spines.values():
            s.set_visible(False)
        ax = fig.add_subplot(gs[row, 1])
        scene(ax)
        b = beam_map(mics, X, Y)
        shown = np.ma.masked_less(b, -6)            # acoustic cameras show the top ~6 dB
        im = ax.imshow(shown, extent=(x[0], x[-1], y[0], y[-1]), origin="lower", cmap="inferno",
                       vmin=-6, vmax=0, alpha=0.8, interpolation="bilinear", zorder=3)
        ax.plot(*SRC, marker="+", color="#1baf7a", ms=10, mew=2, zorder=4)
        ax.set(xlim=(x[0], x[-1]), ylim=(y[0], y[-1]), aspect="equal", xticks=[], yticks=[])
        ax.set_title(title, fontsize=8.5, loc="left")
    cb = fig.colorbar(im, cax=fig.add_subplot(gs[:, 2]))
    cb.set_label("relatív hangteljesítmény [dB]")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=200)
    print(OUT)


if __name__ == "__main__":
    main()
