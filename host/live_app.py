"""Live localization demo: the phone plays the test chirp continuously, the ESP32
measures every chirp, and a browser page shows where the phone is, live.

Position from DIRECTION (the robust quantity, see docs/final_report): the far-field
direction (azimuth, elevation) of each chirp is intersected with the horizontal
plane z = H, where H is the known height of the phone above the mic plane
(default 100 cm, adjustable live on the page). The page can also show, for
comparison, a plane-constrained fit of all 6 delays (z fixed to H) and the free 3D
fit of the ESP32.

    python live_app.py                      # 30 cm array, rotation 0, H = 100 cm
    python live_app.py --array 30 --height 100 --period 0.25
    python live_app.py --demo               # no hardware: replays measured a30 chirps (z = 90 cm)

Then:
  laptop browser:  http://localhost:8766/          (the live view)
  phone:           http://<laptop>:8765/  -> "Tap to start audio", then
                   "Start sound" on the phone or on the laptop page.
Every chirp is also written to host/live_logs/live_<time>.jsonl.
"""

import argparse
import json
import queue
import threading
import time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import numpy as np

import localize as L
import signals_lib as S

HERE = Path(__file__).resolve().parent
PAGE = HERE / "live" / "index.html"
LOGS = HERE / "live_logs"
CHUNK = 240                 # chirps per phone play command (re-issued while sound is on)


class Hub:
    """Shared state + fan-out of messages to the open browser pages (server-sent events)."""

    def __init__(self, config):
        self.config = config
        self.clients = []
        self.lock = threading.Lock()
        self.sound_on = False
        self.n_chirps = 0
        self.recent = []            # receive times of the last chirps (rate)
        self.status = {}

    def subscribe(self):
        q = queue.Queue(maxsize=500)
        with self.lock:
            self.clients.append(q)
        return q

    def unsubscribe(self, q):
        with self.lock:
            if q in self.clients:
                self.clients.remove(q)

    def publish(self, msg):
        data = json.dumps(msg, separators=(",", ":"))
        with self.lock:
            for q in self.clients:
                try:
                    q.put_nowait(data)
                except queue.Full:
                    pass


def make_direction(side_cm, rot_deg):
    mics = L.square(side_cm / 100, rot_deg)
    A = np.array([-(mics[i] - mics[j])[:2] for i, j in L.PAIRS])

    def direction(arr_us, c):
        taus = L.pair_delays(np.asarray(arr_us, float) * 1e-6)
        uxy, *_ = np.linalg.lstsq(A, taus * c, rcond=None)
        h = float(np.linalg.norm(uxy))
        az = float(np.degrees(np.arctan2(uxy[1], uxy[0])) % 360)
        el = float(np.degrees(np.arccos(min(h, 1.0))))
        return az, el, taus * 1e6, h
    return mics, direction


def accept(e, min_q, max_misfit_us):
    """Host-side accept rule for the live view. The ESP32's own flag ("esp_ok") uses the
    firmware limits (q > 0.2, misfit < 10 us), which reject many usable chirps in the room."""
    q, m = e.get("q"), e.get("misfit_us")
    return q is not None and m is not None and q > min_q and m < max_misfit_us


def chirp_message(e, direction, c, t0, min_q=0.12, max_misfit_us=10.0):
    az, el, taus_us, h = direction(e["arr_us"], c)
    return {"type": "chirp", "n": e.get("n"), "t": round(time.monotonic() - t0, 3),
            "ok": accept(e, min_q, max_misfit_us), "esp_ok": bool(e.get("ok")),
            "q": e.get("q"), "misfit_us": e.get("misfit_us"), "snr": e.get("snr"), "lvl_db": e.get("lvl_db"),
            "clip": e.get("clip", 0), "az": round(az, 3), "el": round(el, 3), "h": round(h, 4),
            "taus_us": [round(float(v), 2) for v in taus_us], "esp_pos": e.get("pos_cm"),
            "esp_dir": [e.get("dir_az"), e.get("dir_el")]}


def serve_page(hub, port, on_sound):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, body, ctype="application/json"):
            body = json.dumps(body).encode() if isinstance(body, (dict, list)) else body
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/config":
                self._send(200, hub.config)
            elif self.path == "/events":
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                q = hub.subscribe()
                try:
                    self.wfile.write(f"data: {json.dumps({'type': 'status', **hub.status})}\n\n".encode())
                    self.wfile.flush()
                    while True:
                        try:
                            data = q.get(timeout=10)
                        except queue.Empty:
                            data = None
                        self.wfile.write((f"data: {data}\n\n" if data else ": keepalive\n\n").encode())
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                finally:
                    hub.unsubscribe(q)
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            n = int(self.headers.get("Content-Length", 0))
            try:
                body = json.loads(self.rfile.read(n) or b"{}")
            except json.JSONDecodeError:
                return self._send(400, {"error": "bad json"})
            if self.path == "/sound":
                on_sound(bool(body.get("on")))
                self._send(200, {"ok": True, "sound_on": hub.sound_on})
            else:
                self._send(404, {"error": "not found"})

    httpd = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    httpd.daemon_threads = True
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


def run_demo(hub, direction, c, period, log, min_q, max_misfit):
    """Replay accepted + rejected chirps of the a30 series at z = 90 cm, point by point."""
    from bench import RESULTS
    files = sorted((RESULTS / "series" / "distance_v2" / "a30").glob("*z090*.jsonl"))
    t0 = time.monotonic()
    hub.status = {"esp": "demo (replay of a30, z = 90 cm)", "phone": "demo", "sound_on": True}
    hub.sound_on = True
    while True:
        for f in files:
            meta, trial = [json.loads(l) for l in f.read_text().splitlines()[:2]]
            hub.publish({"type": "truth", "pos": meta["truth_cm"], "name": meta["point"]})
            for e in trial["events"]:
                if e.get("type") != "event":
                    continue
                while not hub.sound_on:
                    time.sleep(0.1)
                msg = chirp_message(e, direction, c, t0, min_q, max_misfit)
                hub.publish(msg)
                log.write(json.dumps(msg) + "\n")
                time.sleep(period)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--array", type=float, default=30.0, help="mic square side [cm] (default 30)")
    ap.add_argument("--rot", type=float, default=L.MEASURED_ROT_DEG, help="array rotation [deg] (default 0)")
    ap.add_argument("--height", type=float, default=None,
                    help="phone height above the mic plane [cm] (default 100; demo: 90, the replayed height)")
    ap.add_argument("--temp", type=float, default=21.0, help="room temperature [C]")
    ap.add_argument("--period", type=float, default=0.25, help="time between chirps [s]")
    ap.add_argument("--channel", default="left", help="phone speaker channel (left = main speaker)")
    ap.add_argument("--min-q", type=float, default=0.12,
                    help="accept a chirp if its lowest GCC-PHAT quality is above this (firmware: 0.2)")
    ap.add_argument("--max-misfit", type=float, default=10.0,
                    help="... and the 6 delays agree within this rms [us] (firmware: 10)")
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--http-port", type=int, default=8765, help="phone page port")
    ap.add_argument("--view-port", type=int, default=8766, help="live view port")
    ap.add_argument("--demo", action="store_true", help="no hardware: replay recorded chirps")
    args = ap.parse_args()

    if args.height is None:
        args.height = 90.0 if args.demo else 100.0
    c = L.speed_of_sound(args.temp)
    mics, direction = make_direction(args.array, args.rot)
    config = {"array_cm": args.array, "rot_deg": args.rot, "height_cm": args.height, "c": c,
              "mics_cm": (mics * 100).round(2).tolist(), "pairs": L.PAIRS, "period_s": args.period,
              "signal": S.DEFAULT.name, "demo": args.demo,
              "min_q": args.min_q, "max_misfit_us": args.max_misfit,
              "dir_err_deg": 0.62, "note": "direction error: median of the a30 series at z 50-90 cm"}
    hub = Hub(config)
    LOGS.mkdir(exist_ok=True)
    log_path = LOGS / f"live_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
    log = log_path.open("w", buffering=1)
    log.write(json.dumps({"type": "meta", **config, "started": datetime.now().isoformat(timespec="seconds"),
                          "argv": vars(args)}) + "\n")

    phone = None

    def on_sound(on):
        hub.sound_on = on
        hub.status["sound_on"] = on
        if phone is not None:
            if not on:
                phone.command({"action": "stop"})
            update_phone_panel()
        hub.publish({"type": "status", **hub.status})

    def update_phone_panel(last=None):
        if phone is None:
            return
        lines = [f"array {args.array:g} cm · height {args.height:g} cm",
                 "hold the phone flat, speaker towards the array"]
        if last:
            lines.insert(0, last)
        phone.set_ui({"title": "Live localization", "where": "sound ON" if hub.sound_on else "sound off",
                      "lines": lines, "status": "", "buttons": ["go"],
                      "go_label": "Stop sound" if hub.sound_on else "Start sound"})

    try:
        serve_page(hub, args.view_port, on_sound)
    except OSError as e:
        raise SystemExit(f"port {args.view_port} is already in use ({e.strerror}): another live_app.py is "
                         f"probably still running - close it (Ctrl+C in its terminal, or: fuser -k {args.view_port}/tcp)")
    print(f"live view:  http://localhost:{args.view_port}/")

    if args.demo:
        print("DEMO: replaying recorded a30 chirps at z = 90 cm (no ESP32, no phone)")
        threading.Thread(target=run_demo, args=(hub, direction, c, args.period, log, args.min_q, args.max_misfit), daemon=True).start()
        try:
            while True:
                time.sleep(1)
                hub.publish({"type": "status", **hub.status})
        except KeyboardInterrupt:
            print(f"\nlog: {log_path}")
        return

    from bench import setup_geometry
    from esp_link import EspLink
    from lablog import firmware_check
    from phone_server import PhoneServer, print_qr

    try:
        esp = EspLink(args.port)
    except Exception as e:  # serial.SerialException: missing or busy port
        raise SystemExit(f"cannot open the ESP32 on {args.port}: {e}\n"
                         f"  is it plugged in (ls /dev/ttyUSB*)? is another program using it (fuser -v {args.port})?")
    status = None
    for _ in range(3):                  # the board may still be booting: ask, then wait
        esp.send("status")
        try:
            status = esp.wait_status(timeout=5)
        except TimeoutError:
            continue
        if status["fs"] != 0:
            break
    if status is None:
        raise SystemExit("no status line from the ESP32: is it connected and running the on-board firmware?")
    side, rot, status = setup_geometry(esp, status, args.array, args.rot)
    print(firmware_check(status))
    for cmd in ("scope 0", "levels 0", f"temp {args.temp}", f"holdoff {min(0.3, 0.6 * args.period):.2f}"):
        esp.send(cmd)
    esp.set_signal(S.DEFAULT)
    print(f"ESP32: {status['fs']:.0f} Hz/mic, array {side:g} cm, rotation {rot:g} deg, c = {c:.1f} m/s, "
          f"signal {S.DEFAULT.name}")
    hub.status = {"esp": f"ESP32 {status['fs']:.0f} Hz/mic, array {side:g} cm, rot {rot:g}°", "phone": "waiting",
                  "sound_on": False}

    try:
        phone = PhoneServer(port=args.http_port, signal_lookup=S.by_name).start()
    except OSError as e:
        esp.close()
        raise SystemExit(f"port {args.http_port} is already in use ({e.strerror}): another live_app.py, series.py "
                         f"or bench.py is probably running - close it first")
    print(f"phone: open {phone.url} and tap 'Start audio'")
    print_qr(phone.url)
    t0 = time.monotonic()

    def phone_loop():
        """Keeps the phone playing while the sound is on (one command = CHUNK chirps)."""
        seq, was_ready, retry_at = None, False, 0.0
        while True:
            ready = phone.ready()
            if ready != was_ready:
                hub.status["phone"] = f"connected ({phone.client})" if ready else "not connected"
                hub.publish({"type": "status", **hub.status})
                if ready:
                    phone.preload([phone.sig_url(S.DEFAULT, args.channel)])
                    update_phone_panel()
                was_ready = ready
            if ready and hub.sound_on:
                rep = phone.wait_report(seq, ("done", "error"), timeout=0) if seq is not None else None
                if rep is not None and rep.get("state") == "error" and seq is not None:
                    # e.g. iOS paused the audio (screen locked / page in the background): tell the user,
                    # retry in 2 s instead of flooding the phone with play commands
                    hub.status["phone"] = "audio paused on the phone: tap the phone's screen"
                    hub.publish({"type": "status", **hub.status})
                    seq, retry_at = None, time.monotonic() + 2.0
                if (seq is None or rep is not None) and time.monotonic() >= retry_at:
                    seq = phone.play(S.DEFAULT, 0.0, CHUNK, args.period, delay=0.3, channel=args.channel)
                    started = phone.wait_report(seq, ("playing", "error"), timeout=3)
                    if started and started.get("state") == "playing" and "paused" in hub.status.get("phone", ""):
                        hub.status["phone"] = f"connected ({phone.client})"
                        hub.publish({"type": "status", **hub.status})
            elif seq is not None and not hub.sound_on:
                seq = None
            time.sleep(0.2)

    def action_loop():
        # Not phone.wait_action(): that drops a press made on an older panel, and the
        # panel is refreshed every second with the position.
        while True:
            with phone.cond:
                phone.cond.wait_for(lambda: phone.actions, timeout=1.0)
                acts, phone.actions[:] = list(phone.actions), []
            if sum(a.get("action") == "go" for a in acts) % 2:
                on_sound(not hub.sound_on)

    def esp_loop():
        k = 0
        while True:
            with esp.lock:
                new = esp.messages[k:]
                k = len(esp.messages)
            for e in new:
                if e.get("type") != "event" or "arr_us" not in e:
                    continue
                msg = chirp_message(e, direction, c, t0, args.min_q, args.max_misfit)
                hub.publish(msg)
                log.write(json.dumps(msg) + "\n")
                hub.n_chirps += 1
                if msg["ok"] and msg["el"] > 3:
                    d = args.height / np.tan(np.radians(msg["el"]))
                    x, y = d * np.cos(np.radians(msg["az"])), d * np.sin(np.radians(msg["az"]))
                    if hub.n_chirps % 4 == 0:
                        update_phone_panel(f"x {x:+.0f} cm   y {y:+.0f} cm")
            time.sleep(0.02)

    for fn in (phone_loop, action_loop, esp_loop):
        threading.Thread(target=fn, daemon=True).start()
    print("Ctrl+C to stop")
    try:
        while True:
            time.sleep(1)
            hub.publish({"type": "status", **hub.status, "chirps": hub.n_chirps})
    except KeyboardInterrupt:
        pass
    finally:
        if phone.ready():
            phone.command({"action": "stop"})
        esp.close()
        print(f"\n{hub.n_chirps} chirps, log: {log_path}")


if __name__ == "__main__":
    main()
