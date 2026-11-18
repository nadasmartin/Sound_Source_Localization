"""Telemetry from the ESP32's on-board localization (firmware env "esp32").

The ESP32 does all the work (chirp detection, GCC-PHAT, arrival times, 3D
position) and sends one JSON line per chirp over the USB serial port. This
script prints them, logs them, and can show them live. No Wi-Fi needed.

Usage:
  python telemetry.py                      # print events until Ctrl+C
  python telemetry.py --play laptop --seconds 12   # play the chirp train, then summarise
  python telemetry.py --plot               # live top/side view of the positions
  python telemetry.py --temp 23.5          # tell the ESP32 the room temperature
  python telemetry.py --verify 3 --play laptop
        # also fetch the raw window of 3 chirps and recompute them in Python
        # (tdoa.py's GCC-PHAT) to check the on-board numbers

Every line received is saved to host/telemetry_logs/tel_<time>.jsonl.
"""

import argparse
import base64
import json
import subprocess
import time
from collections import deque
from datetime import datetime
from pathlib import Path

import numpy as np
import serial

HOST_DIR = Path(__file__).parent
MIC_NAMES = ["Mic1", "Mic2", "Mic3", "Mic4"]


def open_port(port, baud):
    s = serial.Serial()
    s.port, s.baudrate, s.timeout = port, baud, 0.2
    # Leave DTR/RTS released: on ESP32 dev boards they drive EN/IO0, and
    # asserting them would reset the board (or put it in the bootloader).
    s.dtr = False
    s.rts = False
    s.open()
    return s


def send(ser, cmd):
    ser.write((cmd + "\n").encode())


def fmt_event(e):
    if e["type"] == "reject":
        return f"{e['n']:5d} {e['t']:8.2f}s  rejected (snr {e['snr']:.1f})"
    arr = "".join(f"{v:8.1f}" for v in e["arr_us"])
    order = " > ".join(MIC_NAMES[k] for k in np.argsort(e["arr_us"]))
    x, y, z = e["pos_cm"]
    flag = "ok " if e["ok"] else "BAD"
    return (f"{e['n']:5d} {e['t']:8.2f}s {flag} snr{e['snr']:5.0f} {arr}  "
            f"{e['misfit_us']:5.1f}us {e['q']:5.2f}  "
            f"({x:6.1f},{y:6.1f},{z:6.1f})cm  az {e['az']:5.1f} el {e['el']:4.1f}  "
            f"{e['proc_ms']:4.0f}ms  {order}")


HEADER = ("    n     time      snr" + "".join(f"{n:>8}" for n in MIC_NAMES) +
          "  misfit  qual   position x, y, z         direction       proc\n"
          "                         arrival after first mic [us]")


def fmt_status(s):
    return (f"[status] {s['fs']:.0f} Hz/mic  dsp load {s['dsp_load']:.0f}%  "
            f"chirps {s['chirps']}  dropped {s['dropped']}  overruns {s['overruns']}  "
            f"ADC overflows {s['adc_ovf']}  temp {s['temp']:.1f} C  thr {s['thr']:.0f}")


def summarise(events):
    good = [e for e in events if e.get("type") == "event" and e["ok"]]
    allev = [e for e in events if e.get("type") == "event"]
    print(f"\n{len(good)}/{len(allev)} chirps pass the checks (misfit < 10 us, quality > 0.2)")
    if not good:
        return
    T = np.array([e["arr_us"] for e in good])
    T -= T[:, [int(np.argmin(np.median(T, axis=0)))]]
    med, std = np.median(T, axis=0), T.std(axis=0)
    print("\nRESULT (median over good chirps, computed on the ESP32)")
    print(f"{'mic':6}{'arrival [us]':>14}{'+/- std':>10}")
    for k in np.argsort(med):
        print(f"{MIC_NAMES[k]:6}{med[k]:14.1f}{std[k]:10.1f}")
    print("order:", " > ".join(MIC_NAMES[k] for k in np.argsort(med)))
    P = np.array([e["pos_cm"] for e in good])
    m = np.median(P, axis=0)
    r = np.linalg.norm(m)
    print(f"\n3D POSITION ({len(P)} chirps)")
    print(f"{'':12}{'x [cm]':>9}{'y [cm]':>9}{'z [cm]':>9}")
    print(f"{'median':12}" + "".join(f"{v:9.1f}" for v in m))
    print(f"{'spread (std)':12}" + "".join(f"{v:9.1f}" for v in P.std(axis=0)))
    print(f"distance {r:.1f} cm, azimuth {np.degrees(np.arctan2(m[1], m[0])) % 360:.1f} deg, "
          f"elevation {np.degrees(np.arcsin(m[2] / r)) if r else 0:.1f} deg")
    print(f"direction only (far-field model): azimuth "
          f"{np.median([e['dir_az'] for e in good]):.1f} deg, elevation "
          f"{np.median([e['dir_el'] for e in good]):.1f} deg")


def verify(dump, event):
    """Recompute one chirp from its raw window with tdoa.py and compare."""
    import tdoa  # imported lazily: pulls in scipy / matplotlib

    raw = np.frombuffer(base64.b64decode(dump["b64"]), dtype="<u2").reshape(-1, 4)
    x = raw.astype(float)
    xf = tdoa.bandpass(x)
    t, misfit, q, _ = tdoa.arrival_times(xf, dump["pre"], 1500e-6)
    py = t * 1e6
    esp = np.array(event["arr_us"]) if event else None
    print(f"  verify #{dump['n']}: Python arrival [us] " +
          " ".join(f"{v:7.1f}" for v in py) + f"  misfit {misfit * 1e6:.1f} us  q {q:.2f}")
    if esp is not None:
        print("               ESP32 arrival [us] " + " ".join(f"{v:7.1f}" for v in esp) +
              f"  -> max difference {np.abs(py - esp).max():.2f} us")
    out = HOST_DIR / "recordings" / f"window_{datetime.now():%Y%m%d_%H%M%S}_{dump['n']}.npz"
    out.parent.mkdir(exist_ok=True)
    np.savez_compressed(out, x=x, gaps=np.zeros((0, 2)), fs=tdoa.FS)


class LivePlot:
    """Top view (x-y) and side view (x-z) of the recent positions."""

    def __init__(self, keep=30):
        import matplotlib.pyplot as plt

        import localize
        self.plt = plt
        self.pts = deque(maxlen=keep)
        self.fig, axes = plt.subplots(1, 2, figsize=(12, 5.5))
        self.fig.canvas.manager.set_window_title("ESP32 sound source position")
        mics = localize.MICS * 100
        self.scat, self.star = [], []
        for ax, (i, j, name) in zip(axes, [(0, 1, "top view (x-y)"), (0, 2, "side view (x-z)")]):
            ax.scatter(mics[:, i], mics[:, j], color="k", marker="s")
            for n, m in enumerate(mics):
                ax.annotate(f"M{n + 1}", (m[i], m[j]), textcoords="offset points", xytext=(4, 4))
            self.scat.append(ax.scatter([], [], color="C3", s=10, alpha=0.4))
            self.star.append(ax.scatter([], [], color="C3", s=150, marker="*"))
            ax.set(xlabel="xyz"[i] + " [cm]", ylabel="xyz"[j] + " [cm]", title=name,
                   xlim=(-100, 100), ylim=(-100, 100) if j == 1 else (-10, 150))
            ax.set_aspect("equal")
            ax.grid(alpha=0.3)
        self.text = self.fig.text(0.01, 0.01, "waiting for chirps...", family="monospace")
        plt.tight_layout()
        plt.ion()
        plt.show()

    def add(self, e):
        if e.get("type") == "event" and e["ok"]:
            self.pts.append(e["pos_cm"])
            P = np.array(self.pts)
            for k, (i, j) in enumerate([(0, 1), (0, 2)]):
                self.scat[k].set_offsets(P[:, [i, j]])
                self.star[k].set_offsets([P[-1, [i, j]]])
            self.text.set_text(f"#{e['n']}  ({e['pos_cm'][0]:.1f}, {e['pos_cm'][1]:.1f}, "
                               f"{e['pos_cm'][2]:.1f}) cm   r {e['r_cm']:.0f} cm   "
                               f"az {e['az']:.0f} deg   el {e['el']:.0f} deg")

    def pump(self):
        self.plt.pause(0.01)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--baud", type=int, default=921600)
    parser.add_argument("--seconds", type=float, help="stop after this long (default: Ctrl+C)")
    parser.add_argument("--temp", type=float, help="room temperature in C (sets the speed of sound)")
    parser.add_argument("--thr", type=float, help="detection threshold (x median correlation)")
    parser.add_argument("--play", choices=["laptop"],
                        help="play the chirp train on the laptop's left speaker")
    parser.add_argument("--plot", action="store_true", help="live position plot")
    parser.add_argument("--verify", type=int, default=0, metavar="N",
                        help="fetch the raw window of N chirps and recompute them in Python")
    parser.add_argument("--status", action="store_true", help="print every status line")
    args = parser.parse_args()

    ser = open_port(args.port, args.baud)
    if args.temp is not None:
        send(ser, f"temp {args.temp}")
    if args.thr is not None:
        send(ser, f"thr {args.thr}")

    log_path = HOST_DIR / "telemetry_logs" / f"tel_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    log_path.parent.mkdir(exist_ok=True)
    log = open(log_path, "w")
    print(f"listening on {args.port}, log: {log_path.resolve()}")

    player = None
    if args.play == "laptop":
        import test_signal
        wav = test_signal.write_wavs(HOST_DIR / "signals")["left"]
        player = subprocess.Popen(["paplay", str(wav)])

    plot = LivePlot() if args.plot else None
    events, last_event, dumps_wanted = [], None, args.verify
    if dumps_wanted:
        send(ser, "dump")
    print(HEADER)
    start, last_status, buf = time.time(), None, b""
    try:
        while args.seconds is None or time.time() - start < args.seconds:
            buf += ser.read(ser.in_waiting or 1)
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line.startswith(b"{"):
                    continue  # boot messages etc.
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") != "dump":
                    log.write(line.decode() + "\n")
                kind = msg.get("type")
                if kind in ("event", "reject"):
                    events.append(msg)
                    last_event = msg
                    print(fmt_event(msg))
                    if plot:
                        plot.add(msg)
                elif kind == "status":
                    if args.status or last_status is None or msg["overruns"] != last_status["overruns"] \
                            or msg["adc_ovf"] != last_status["adc_ovf"]:
                        print(fmt_status(msg))
                    last_status = msg
                elif kind == "dump":
                    verify(msg, last_event if last_event and last_event["n"] == msg["n"] else None)
                    dumps_wanted -= 1
                    if dumps_wanted > 0:
                        send(ser, "dump")
                else:
                    print(f"[{kind}] {msg.get('msg', msg)}")
            if plot:
                plot.pump()
    except KeyboardInterrupt:
        pass
    finally:
        if player:
            player.terminate()
        log.close()
        ser.close()
    if last_status:
        print(fmt_status(last_status))
    summarise(events)


if __name__ == "__main__":
    main()
