"""Serial link to the ESP32 running the on-board firmware (env "esp32").

A background thread reads the JSON lines; every message gets the host's
arrival time (time.monotonic()) in "_rx", so the bench can tell which events
belong to which trial.
"""

import base64
import json
import queue
import threading
import time

import numpy as np
import serial


class EspLink:
    def __init__(self, port="/dev/ttyUSB0", baud=921600):
        s = serial.Serial()
        s.port, s.baudrate, s.timeout = port, baud, 0.2
        # Released DTR/RTS: asserting them resets the board / enters the bootloader
        s.dtr = False
        s.rts = False
        s.open()
        self.ser = s
        self.messages = []          # every message received, in order
        self.lock = threading.Lock()
        self.replies = queue.Queue()  # "sig" answers
        self.last_status = None
        self._stop = False
        self._thread = threading.Thread(target=self._reader, daemon=True)
        self._thread.start()

    def _reader(self):
        buf = b""
        while not self._stop:
            try:
                buf += self.ser.read(self.ser.in_waiting or 1)
            except serial.SerialException:
                time.sleep(0.5)
                continue
            while b"\n" in buf:
                line, buf = buf.split(b"\n", 1)
                line = line.strip()
                if not line.startswith(b"{"):
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg["_rx"] = time.monotonic()
                with self.lock:
                    self.messages.append(msg)
                if msg.get("type") == "sig":
                    self.replies.put(msg)
                elif msg.get("type") == "status":
                    self.last_status = msg

    def close(self):
        self._stop = True
        self._thread.join(timeout=1)
        self.ser.close()

    def send(self, cmd):
        self.ser.write((cmd + "\n").encode())
        self.ser.flush()

    def since(self, t0, t1=None, types=("event", "reject")):
        """Messages of the given types that arrived in [t0, t1]."""
        with self.lock:
            return [m for m in self.messages
                    if m.get("type") in types and m["_rx"] >= t0 and (t1 is None or m["_rx"] <= t1)]

    def wait_status(self, timeout=5.0):
        t0 = time.monotonic()
        while time.monotonic() - t0 < timeout:
            s = self.last_status
            if s and s["_rx"] > t0:
                return s
            time.sleep(0.05)
        raise TimeoutError("no status line from the ESP32: is the on-board firmware flashed?")

    def set_signal(self, sig, timeout=5.0):
        """Upload sig's template + band; returns the ESP32's confirmation."""
        while not self.replies.empty():
            self.replies.get_nowait()
        tmpl = sig.template()
        k_lo, k_hi = sig.band_bins()
        self.send(f"sig_begin {len(tmpl)} {k_lo} {k_hi}")
        time.sleep(0.02)
        for off in range(0, len(tmpl), 256):
            chunk = tmpl[off:off + 256]
            self.send(f"sig_data {off} {base64.b64encode(chunk.tobytes()).decode()}")
            time.sleep(0.01)  # ~700 bytes = 8 ms at 921600 baud; keep the 4 KB RX buffer happy
        self.send(f"sig_end {int(tmpl.astype(np.int64).sum()) & 0xFFFFFFFF}")
        try:
            reply = self.replies.get(timeout=timeout)
        except queue.Empty:
            raise TimeoutError("ESP32 did not confirm the template upload") from None
        if not reply["ok"] or reply["len"] != len(tmpl) or (reply["k_lo"], reply["k_hi"]) != (k_lo, k_hi):
            raise RuntimeError(f"template upload failed: {reply}")
        return reply

    def set_default_signal(self):
        self.send("sig_default")

