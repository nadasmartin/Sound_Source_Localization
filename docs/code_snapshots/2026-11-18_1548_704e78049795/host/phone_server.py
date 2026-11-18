"""Lets the laptop tell a phone what to play.

The phone opens http://<laptop-ip>:8765/ in its browser, taps "Start audio"
once (browsers only allow sound after a tap), and from then on the page
long-polls the laptop for commands, plays the requested signal with Web Audio
and reports back what it did.

    python phone_server.py        # run it alone: shows the URL and lets you
                                  # trigger test sounds from the terminal

Protocol (JSON):
  GET  /poll?after=<seq>   -> {"seq": n, "cmd": {...}} or {"seq": after, "cmd": null}
       (held open up to 20 s until there is a newer command)
  POST /report             <- {"seq": n, "state": "ready|playing|done|error", ...}
  GET  /sig/<name>.wav?ch=both|left|right  -> the signal (48 kHz, 16-bit stereo)
  POST /action             <- {"action": "go|skip|redo", "ui": <ui version>}  (buttons on the
                              measurement panel, see set_ui / wait_action)
  /poll answers also carry {"ui": {...}, "uiv": n}: the panel the page shows
  (next position etc.); a poll with uiv=<n> also returns as soon as it changes.
Commands:
  {"action": "play", "url": ..., "name": ..., "gain_db": g, "count": n,
   "period": s, "delay": s}
  {"action": "stop"}
"""

import json
import os
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

PAGE = Path(__file__).parent / "phone" / "index.html"
PORT = 8765


def lan_ip():
    """The address the phone should use (the one the default route goes out of)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("192.168.1.1", 9))  # no packet is sent for UDP connect
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class PhoneServer:
    def __init__(self, port=PORT, signal_lookup=None):
        self.port = port
        self.signal_lookup = signal_lookup  # name -> Signal (for /sig/<name>.wav)
        self.cond = threading.Condition()
        self.seq = 0
        self.cmd = None
        # A new id per server start: the page notices a restarted server (its
        # command numbers start again from 0) and re-syncs without a reload.
        self.boot = os.urandom(4).hex()
        self.reports = []          # every report from the phone, with "_rx"
        self.last_seen = 0.0       # monotonic time of the last poll/report
        self.client = None
        self.wav_cache = {}
        self.ui, self.uiv = None, 0          # measurement panel shown on the phone
        self.actions = []                    # button presses from the panel
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _send(self, code, body, ctype="application/json"):
                if isinstance(body, (dict, list)):
                    body = json.dumps(body).encode()
                elif isinstance(body, str):
                    body = body.encode()
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                url = urlparse(self.path)
                server.last_seen = time.monotonic()
                server.client = self.client_address[0]
                if url.path in ("/", "/index.html"):
                    self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
                elif url.path == "/poll":
                    q = parse_qs(url.query)
                    after = int(q.get("after", ["0"])[0])
                    uiv = int(q.get("uiv", ["-1"])[0])
                    self._send(200, server._poll(after, uiv))
                elif url.path.startswith("/sig/") and url.path.endswith(".wav"):
                    name = url.path[5:-4]
                    ch = parse_qs(url.query).get("ch", ["both"])[0]
                    try:
                        if (name, ch) not in server.wav_cache:
                            server.wav_cache[name, ch] = server.signal_lookup(name).wav_bytes(ch)
                        self._send(200, server.wav_cache[name, ch], "audio/wav")
                    except (KeyError, TypeError):
                        self._send(404, {"error": f"unknown signal {name} / channel {ch}"})
                elif url.path == "/state":
                    self._send(200, {"seq": server.seq, "cmd": server.cmd, "boot": server.boot,
                                     "reports": server.reports[-5:]})
                else:
                    self._send(404, {"error": "not found"})

            def do_POST(self):
                server.last_seen = time.monotonic()
                n = int(self.headers.get("Content-Length", 0))
                try:
                    rep = json.loads(self.rfile.read(n) or b"{}")
                except json.JSONDecodeError:
                    return self._send(400, {"error": "bad json"})
                if urlparse(self.path).path == "/report":
                    rep["_rx"] = time.monotonic()
                    with server.cond:
                        server.reports.append(rep)
                        server.cond.notify_all()
                    self._send(200, {"ok": True})
                elif urlparse(self.path).path == "/action":
                    rep["_rx"] = time.monotonic()
                    with server.cond:
                        server.actions.append(rep)
                        server.cond.notify_all()
                    self._send(200, {"ok": True})
                else:
                    self._send(404, {"error": "not found"})

        self.httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
        self.httpd.daemon_threads = True
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)

    # --------------------------------------------------------------- server side
    def _poll(self, after, uiv=-1):
        with self.cond:
            fresh = lambda: self.seq > after or (uiv >= 0 and self.uiv != uiv)  # noqa: E731
            if not fresh():
                self.cond.wait_for(fresh, timeout=20)
            ui = {"ui": self.ui, "uiv": self.uiv}
            if self.seq > after:
                return {"seq": self.seq, "cmd": self.cmd, "boot": self.boot, **ui}
            return {"seq": self.seq, "cmd": None, "boot": self.boot, **ui}

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        self.httpd.shutdown()

    @property
    def url(self):
        return f"http://{lan_ip()}:{self.port}/"

    # ----------------------------------------------------------- laptop side
    def connected(self, within=30.0):
        return time.monotonic() - self.last_seen < within

    def wait_connected(self, timeout=None):
        t0 = time.monotonic()
        while not self.ready():
            if timeout is not None and time.monotonic() - t0 > timeout:
                return False
            time.sleep(0.2)
        return True

    def ready(self):
        """The page is open and audio has been unlocked with a tap."""
        with self.cond:
            ready = [r for r in self.reports if r.get("state") == "ready"]
        return bool(ready) and self.connected()

    def command(self, cmd):
        with self.cond:
            self.seq += 1
            self.cmd = cmd
            self.cond.notify_all()
            return self.seq

    def wait_report(self, seq, states, timeout):
        """The phone's first report for command `seq` with a state in `states`."""
        deadline = time.monotonic() + timeout
        with self.cond:
            while True:
                for r in self.reports:
                    if r.get("seq") == seq and r.get("state") in states:
                        return r
                left = deadline - time.monotonic()
                if left <= 0:
                    return None
                self.cond.wait(timeout=left)

    def set_ui(self, ui):
        """Show a measurement panel on the phone: {"title", "lines": [...], "status",
        "buttons": ["go", "skip", "redo"], "result": [...]} (any of them)."""
        with self.cond:
            self.ui = ui
            self.uiv += 1
            self.cond.notify_all()
            return self.uiv

    def wait_action(self, timeout=None):
        """Next button press on the panel made after the current panel was shown."""
        deadline = None if timeout is None else time.monotonic() + timeout
        with self.cond:
            while True:
                while self.actions:
                    a = self.actions.pop(0)
                    if a.get("ui") == self.uiv:
                        return a.get("action")
                left = None if deadline is None else deadline - time.monotonic()
                if left is not None and left <= 0:
                    return None
                self.cond.wait(timeout=1.0 if left is None else min(left, 1.0))

    @staticmethod
    def sig_url(signal, channel="both"):
        return f"/sig/{signal.name}.wav?ch={channel}"

    def preload(self, urls, timeout=90):
        """Have the phone download + decode every sound now (not during the test)."""
        seq = self.command({"action": "preload", "urls": list(urls)})
        return self.wait_report(seq, ("done", "error"), timeout)

    def play_gains(self, signal, gains, period=0.25, delay=0.35, channel="both"):
        """One repetition per entry of `gains` (dB), `period` apart."""
        label = signal.name + ("" if channel == "both" else f" ({channel} channel)")
        return self.command({"action": "play", "name": label, "url": self.sig_url(signal, channel),
                             "gains": [float(g) for g in gains], "gain_db": 0,
                             "count": len(gains), "period": period, "delay": delay})

    def play(self, signal, gain_db=0.0, count=10, period=0.5, delay=0.6, channel="both"):
        label = signal.name + ("" if channel == "both" else f" ({channel} channel)")
        return self.command({"action": "play", "name": label,
                             "url": f"/sig/{signal.name}.wav?ch={channel}", "gain_db": gain_db,
                             "count": count, "period": period, "delay": delay})


def print_qr(url):
    try:
        import qrcode
    except ImportError:
        return
    qr = qrcode.QRCode(border=1)
    qr.add_data(url)
    qr.print_ascii(invert=True)


if __name__ == "__main__":
    import signals_lib

    srv = PhoneServer(signal_lookup=signals_lib.by_name).start()
    print(f"Open on the phone (same Wi-Fi):  {srv.url}")
    print_qr(srv.url)
    print("waiting for the phone to tap 'Start audio' ...")
    srv.wait_connected()
    print(f"phone ready ({srv.client}). Enter = play 5 default chirps, q = quit")
    while input() != "q":
        seq = srv.play(signals_lib.DEFAULT, count=5)
        print("phone:", (srv.wait_report(seq, ("playing", "error"), 10) or {}).get("state", "no answer"))
