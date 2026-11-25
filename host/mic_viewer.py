"""Live viewer for the 4 microphones: the last seconds of waveform per mic and
its loudness, plus the sample rate actually achieved.

Over the USB cable (on-board firmware): the full 44.1 kHz audio does not fit
through the serial port, so the ESP32 averages every --avg readings into one
("scope" command) and sends that real, slower waveform: --avg 8 -> 5.5 kHz per
mic (shows sound up to ~2.7 kHz), about 60 kB/s. Useful to identify the mics
(tap one) and to check that all four are alive.

Usage:  python mic_viewer.py [--window 5] [--range 2048] [--avg 8] [--port /dev/ttyUSB0]
"""

import argparse
import base64
import json
import threading
import time
from collections import deque

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.animation import FuncAnimation

NUM_MICS = 4
MIC_LABELS = ["Mic 1 (D34)", "Mic 2 (D35)", "Mic 3 (D32)", "Mic 4 (D33)"]
ESP_RATE = 44100

WINDOW_SECONDS = 2.0
LOUDNESS_SECONDS = 0.1        # loudness = RMS over this much recent audio
PLOT_BINS = 1000              # long windows are drawn as min/max per bin
MAX_PLOT_POINTS = 15000       # shorter ones sample by sample


class UsbStreamReader(threading.Thread):
    """Background thread: reads the on-board firmware's "scope" lines (the
    waveform, each value the average of `avg` ADC readings) into a ring buffer."""

    def __init__(self, port, avg, window_s):
        import serial
        super().__init__(daemon=True)
        s = serial.Serial()
        s.port, s.baudrate, s.timeout = port, 921600, 0.2
        s.dtr = False      # released DTR/RTS: asserting them resets the board
        s.rts = False
        s.open()
        self.ser = s
        self.avg = avg
        self.nominal = ESP_RATE / avg
        self.size = int(self.nominal * window_s * 1.2) + 1
        self.ring = np.zeros((self.size, NUM_MICS))
        self.write_pos = 0
        self.filled = 0
        self.lock = threading.Lock()
        self.next_n0 = None
        self.gaps = 0
        self.arrivals = deque()   # (time, n_sets) for the rate measurement
        self.esp_status = {}
        self.last_rx = 0.0
        self.bytes_rx = deque()

    def start_stream(self):
        self.ser.write(f"levels 0\nscope {self.avg}\n".encode())

    def stop_stream(self):
        try:
            self.ser.write(b"scope 0\n")
            self.ser.flush()
        except Exception:
            pass

    def run(self):
        buf = b""
        self.start_stream()
        asked = time.monotonic()
        while True:
            chunk = self.ser.read(self.ser.in_waiting or 1)
            now = time.monotonic()
            self.bytes_rx.append((now, len(chunk)))
            while self.bytes_rx and now - self.bytes_rx[0][0] > 2.0:
                self.bytes_rx.popleft()
            buf += chunk
            if now - self.last_rx > 2 and now - asked > 2:
                self.start_stream()   # opening the port may have reset the board
                asked = now
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                if not line.startswith(b"{"):
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("type") == "scope":
                    self.last_rx = time.monotonic()
                    self._handle(msg)
                elif msg.get("type") == "status":
                    self.esp_status = msg

    def _handle(self, msg):
        sets = np.frombuffer(base64.b64decode(msg["b64"]), "<u2").reshape(-1, NUM_MICS) / 16.0
        with self.lock:
            if self.next_n0 is not None and msg["n0"] != self.next_n0:
                self.gaps += 1      # the ESP32 fell behind and skipped ahead
            idx = (self.write_pos + np.arange(len(sets))) % self.size
            self.ring[idx] = sets
            self.write_pos = (self.write_pos + len(sets)) % self.size
            self.filled = min(self.filled + len(sets), self.size)
            self.next_n0 = msg["n0"] + msg["ns"] * msg["avg"]
            now = time.monotonic()
            self.arrivals.append((now, len(sets)))
            while self.arrivals and now - self.arrivals[0][0] > 2.0:
                self.arrivals.popleft()

    def snapshot(self, n):
        """Return the newest n sets (oldest first) and the measured rate."""
        with self.lock:
            n = min(n, self.filled)
            idx = (self.write_pos - n + np.arange(n)) % self.size
            data = self.ring[idx].copy()
            rate = 0.0
            if len(self.arrivals) > 1:
                span = self.arrivals[-1][0] - self.arrivals[0][0]
                rate = sum(c for _, c in list(self.arrivals)[1:]) / span if span > 0 else 0.0
        return data, rate

    def status(self, rate):
        if time.monotonic() - self.last_rx > 2:
            return "waiting for the ESP32 over USB (is the on-board firmware flashed?)…"
        kbs = sum(b for _, b in self.bytes_rx) / 2.0 / 1000
        return (f"USB  sample rate: {rate:6.0f} Hz per mic (average of {self.avg} readings at "
                f"{rate * self.avg / 1000:4.1f} kHz)   link: {kbs:5.1f} kB/s   gaps: {self.gaps}   "
                f"ADC overflows: {self.esp_status.get('adc_ovf', '-')}")


def envelope(signal, bins):
    """Min/max per bin, interleaved: draws every peak while plotting few points."""
    usable = len(signal) // bins * bins
    chunks = signal[-usable:].reshape(bins, -1)
    return np.column_stack([chunks.min(axis=1), chunks.max(axis=1)]).ravel()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", default="/dev/ttyUSB0")
    parser.add_argument("--avg", type=int, default=8,
                        help="ADC readings averaged per sample, 6..64 (8 -> 5.5 kHz per mic)")
    parser.add_argument("--range", type=int, default=2048,
                        help="waveform y-axis half-range in ADC counts")
    parser.add_argument("--window", type=float, default=WINDOW_SECONDS, help="seconds of history shown")
    args = parser.parse_args()
    window_s = args.window

    if not 6 <= args.avg <= 64:
        parser.error("--avg must be 6..64 (below 6 the serial port can't keep up)")
    reader = UsbStreamReader(args.port, args.avg, window_s)
    nominal = ESP_RATE / args.avg
    reader.start()

    fig = plt.figure(figsize=(12, 9))
    fig.canvas.manager.set_window_title("ESP32 microphones")
    grid = fig.add_gridspec(NUM_MICS + 1, 2, width_ratios=[5, 1],
                            height_ratios=[1] * NUM_MICS + [0.25])

    wave_lines, level_bars, level_texts = [], [], []
    for m in range(NUM_MICS):
        ax = fig.add_subplot(grid[m, 0])
        (line,) = ax.plot([], [], lw=0.7, color=f"C{m}")
        ax.set(xlim=(-window_s, 0), ylim=(-args.range, args.range), ylabel=MIC_LABELS[m])
        if m < NUM_MICS - 1:
            ax.tick_params(labelbottom=False)
        else:
            ax.set_xlabel("time [s]")
        wave_lines.append(line)

        ax_lvl = fig.add_subplot(grid[m, 1])
        bar = ax_lvl.bar([0], [-60], bottom=0, color=f"C{m}", width=0.6)[0]
        ax_lvl.set(ylim=(-60, 0), xticks=[], ylabel="dBFS")
        txt = ax_lvl.text(0, -5, "", ha="center", va="top", fontsize=9)
        level_bars.append(bar)
        level_texts.append(txt)
    fig.axes[1].set_title("Loudness (RMS)")

    status = fig.add_subplot(grid[NUM_MICS, :])
    status.axis("off")
    status_text = status.text(0.0, 0.5, "waiting for data…", va="center",
                              family="monospace", fontsize=10)
    fig.tight_layout()

    n_window = int(nominal * window_s)

    def update(_):
        data, rate = reader.snapshot(n_window)
        if len(data) < 100:
            status_text.set_text(reader.status(rate))
            return [status_text]

        centred = data - data.mean(axis=0)   # remove each mic's ~1.6 V bias
        n = len(centred)
        r = rate or nominal
        if n <= MAX_PLOT_POINTS:             # every sample
            t = (np.arange(n) - n) / r
            ys = [centred[:, m] for m in range(NUM_MICS)]
        else:                                # min/max per bin, so no peak is lost
            t = np.repeat(np.linspace(-n / r, 0, PLOT_BINS), 2)
            ys = [envelope(centred[:, m], PLOT_BINS) for m in range(NUM_MICS)]
        n_level = max(1, int(r * LOUDNESS_SECONDS))

        for m in range(NUM_MICS):
            wave_lines[m].set_data(t, ys[m])
            rms = np.sqrt(np.mean(centred[-n_level:, m] ** 2))
            db = 20 * np.log10(max(rms, 1e-3) / 2048)   # 0 dB = full ADC swing
            level_bars[m].set_y(-60)                    # bars grow up from -60 dB
            level_bars[m].set_height(max(db, -60) + 60)
            level_texts[m].set_text(f"{db:5.1f} dB")

        status_text.set_text(reader.status(rate))
        return wave_lines + level_bars + level_texts + [status_text]

    _anim = FuncAnimation(fig, update, interval=40, blit=False, cache_frame_data=False)
    t_open = time.monotonic()
    try:
        plt.show()
    finally:
        reader.stop_stream()
        try:   # one line in docs/experiment_log.md (no data, just that it ran and how well)
            from lablog import append
            _, rate = reader.snapshot(1)
            link = f"USB, average of {args.avg} -> {rate:.0f} Hz per mic, gaps {reader.gaps}"
            append("live mic viewer (mic_viewer.py)",
                   f"- open {time.monotonic() - t_open:.0f} s, window {window_s:g} s, {link}")
        except Exception:
            pass


if __name__ == "__main__":
    main()
