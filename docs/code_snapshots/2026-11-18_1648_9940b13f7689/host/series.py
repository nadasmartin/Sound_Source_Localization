"""Distance series, driven from the phone: one array layout in one go.

The plan (plans/*.json) lists the points in the order they are measured, each
with its position (the phone's speaker opening, cm, origin = array centre,
z above the mic plane). The phone page shows the next point (position and
height) and three buttons:
  Ready – measure   the phone is in place: play the test signal, record, score, save
  Redo previous     measure the previous point again (the new one replaces it)
  Skip this one     leave this point out (it stays "to do" for a later run)
Only the fixed test signal is used: signals_lib.DEFAULT (chirp 3-12 kHz, 50 ms,
the best of the P1-P4 sweeps), `--count` times every `--period` s, fixed gain.

    python series.py --series a30 --array 30 --rot 2.13 --channel left --temp 21.5 --note "volume ..."
    python series.py --series a20 --array 20 ...        # next layout, same points
    python series.py --list --series a30                # the plan and what is done
Resumes by itself (done points are skipped); Ctrl+C on the laptop stops.
Results: bench_results/series/<plan>/<series>/<point>_<k>_<time>.jsonl (same
format as bench.py run: one meta line, one trial line; k = 1, or 2, 3.. after
a redo - analyze_series.py uses the newest). Evaluate with analyze_series.py.
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np

import localize
import signals_lib as S
from bench import HEADER, RESULTS, describe_truth, evaluate, fmt_row, setup_geometry
from esp_link import EspLink
from lablog import code_version, firmware_check, record
from phone_server import PhoneServer, print_qr

HOST_DIR = Path(__file__).parent
PLANS = HOST_DIR / "plans"
TAIL_S = 1.5


def load_plan(path):
    return json.loads(Path(path).read_text())


def series_dir(plan, series):
    return RESULTS / "series" / plan["name"] / series


def done_count(plan, series, pid):
    d = series_dir(plan, series)
    return len(list(d.glob(f"{pid}_*.jsonl"))) if d.exists() else 0


def fmt_pos(p):
    return f"x {p[0]:g}   y {p[1]:g}   z {p[2]:g} cm"


def print_plan(plan, series):
    print(f"plan {plan['name']}: {plan['description']}\n")
    for i, p in enumerate(plan["points"], 1):
        r, az, el = localize.to_spherical(np.array(p["pos_cm"]))
        n = done_count(plan, series, p["id"]) if series else "-"
        print(f"{i:3d} {p['id']:12} {p['name']:18} ({fmt_pos(p['pos_cm'])})  r {r:5.1f} az {az:5.1f} "
              f"el {el:4.1f}   done {n}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", type=Path, default=PLANS / "distance_v2.json")
    ap.add_argument("--series", help="name of this layout's pass, e.g. a30 / a20 / a10")
    ap.add_argument("--points", help="comma-separated point ids to measure (again), e.g. z090-M4; "
                    "default: every point without a file yet. A new file supersedes the old one")
    ap.add_argument("--list", action="store_true", help="show the plan and what is done, then exit")
    ap.add_argument("--channel", choices=S.CHANNELS, default="left",
                    help="speaker channel of the phone's main speaker (iPhone: left)")
    ap.add_argument("--array", type=float, help="mic square side in cm; default: what the ESP32 has stored")
    ap.add_argument("--rot", type=float, help=f"array rotation in deg (measured {localize.MEASURED_ROT_DEG:g}); "
                                              "default: what the ESP32 has stored")
    ap.add_argument("--count", type=int, default=20, help="chirps per point (default 20)")
    ap.add_argument("--period", type=float, default=0.5, help="seconds between chirps")
    ap.add_argument("--gain", type=float, default=0.0, help="dB relative to the phone's volume (keep fixed!)")
    ap.add_argument("--temp", type=float, default=21.0, help="room temperature in C")
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--http-port", type=int, default=8765)
    ap.add_argument("--note", default="", help="free text for the log: phone volume, tilt, ...")
    args = ap.parse_args()
    plan = load_plan(args.plan)
    if args.list:
        print_plan(plan, args.series)
        return
    if not args.series:
        raise SystemExit("--series is required (e.g. a30)")
    with record(f"distance series {plan['name']} / {args.series} (array {args.array or 'as stored'} cm)",
                args.note):
        run_series(plan, args)


def run_series(plan, args):
    sig = S.DEFAULT
    allpts = plan["points"]
    index = {p["id"]: i for i, p in enumerate(allpts)}
    if args.points:
        want = args.points.split(",")
        unknown = set(want) - {p["id"] for p in allpts}
        if unknown:
            raise SystemExit(f"unknown point id(s): {', '.join(sorted(unknown))}")
        todo = [p for p in allpts if p["id"] in want]
    else:
        todo = [p for p in allpts if done_count(plan, args.series, p["id"]) == 0]
    print(f"plan {plan['name']}, series {args.series}: {len(todo)} of {len(allpts)} points to measure; "
          f"signal {sig.name}, {args.count} x every {args.period} s, gain {args.gain:g} dB, "
          f"channel {args.channel}")
    if not todo:
        return

    esp = EspLink(args.port)
    status = esp.wait_status()
    if status["fs"] == 0:
        status = esp.wait_status()
    side, rot, status = setup_geometry(esp, status, args.array, args.rot)
    print(firmware_check(status))
    micdelay = status.get("micdelay_us", [0, 0, 0, 0])
    c = localize.speed_of_sound(args.temp)
    print(f"ESP32: {status['fs']:.0f} Hz/mic, mic delays {micdelay} us, {args.temp:g} C -> c = {c:.1f} m/s")
    for cmd in ("scope 0", "levels 0", f"temp {args.temp}", f"holdoff {min(0.3, 0.6 * args.period):.2f}"):
        esp.send(cmd)
    esp.set_signal(sig)

    phone = PhoneServer(port=args.http_port, signal_lookup=S.by_name).start()
    print(f"\nOpen on the phone (same Wi-Fi):  {phone.url}")
    print_qr(phone.url)
    print("waiting for the phone to tap 'Start audio' ...")
    phone.wait_connected()
    print(f"phone ready ({phone.client})")
    phone.preload([phone.sig_url(sig, args.channel)])

    out_dir = series_dir(plan, args.series)
    out_dir.mkdir(parents=True, exist_ok=True)
    head = f"{args.series}: {side:g} cm array"
    summary, last_result, prev, prev_height = [], [], None, None

    def measure(p, redo):
        truth = list(map(float, p["pos_cm"]))
        k = done_count(plan, args.series, p["id"]) + 1
        print(f"\n[{index[p['id']] + 1}/{len(allpts)}] {p['id']}  {p['name']}, height {p['height_cm']:g} cm"
              + ("  (REDO)" if redo else ""))
        describe_truth(truth, c)
        phone.set_ui({"title": f"{head} · point {index[p['id']] + 1}/{len(allpts)}", "where": p["name"],
                      "lines": [fmt_pos(truth)], "status": "MEASURING – keep still and quiet", "buttons": []})
        if not phone.ready():
            print("  phone disconnected - reopen the page and tap 'Start audio' ...")
            phone.wait_connected()
        t_cmd = time.monotonic()
        seq = phone.play(sig, args.gain, args.count, args.period, delay=0.6, channel=args.channel)
        started = phone.wait_report(seq, ("playing", "error"), timeout=10)
        if not started or started["state"] == "error":
            msg = f"phone did not play: {started.get('error') if started else 'no answer'}"
            print("  " + msg + "; not saved")
            return [f"{p['name']}, z {p['height_cm']:g}: {msg} – not saved, press Ready again"], False
        done = phone.wait_report(seq, ("done", "error"), timeout=args.count * args.period + 10)
        time.sleep(TAIL_S)
        events = [{kk: v for kk, v in e.items() if kk != "_rx"} for e in esp.since(t_cmd)]
        row = evaluate(events, truth, c, args.count)
        print(HEADER)
        print(fmt_row(sig.name, args.gain, row) + ("" if done else "  (no 'done' from phone)"))
        r_cm, az, el = localize.to_spherical(np.array(truth))
        meta = {"type": "meta", "mode": "series", "plan": plan["name"], "series": args.series,
                "point": p["id"], "line": p["line"], "name": p["name"], "height_cm": p["height_cm"],
                "placement": k, "redo": redo, "label": f"{args.series}_{p['id']}", "truth_cm": truth,
                "truth_sph": [round(r_cm, 2), round(az, 2), round(el, 2)],
                "temp_c": args.temp, "c": c, "count": args.count, "period": args.period,
                "gain_db": args.gain, "channel": args.channel, "micdelay_us": micdelay,
                "array_cm": side, "array_rot_deg": rot,
                "mics_cm": (localize.MICS * 100).round(2).tolist(), "note": args.note,
                "fw_on_esp32": status.get("fw"), **code_version(), "argv": sys.argv,
                "started": datetime.now().isoformat()}
        trial = {"type": "trial", "n": 1, "signal": sig.name, "label": sig.name, "channel": args.channel,
                 "kind": sig.kind, "f_lo": sig.f_lo, "f_hi": sig.f_hi, "dur": sig.dur,
                 "gain_db": args.gain, "truth_cm": truth, **row,
                 "phone": {kk: started.get(kk) for kk in ("sampleRate", "outputLatency", "audioState",
                                                          "audioSession", "ua")},
                 "events": events}
        out = out_dir / f"{p['id']}_{k}_{datetime.now():%Y%m%d_%H%M%S}.jsonl"
        out.write_text(json.dumps(meta) + "\n" + json.dumps(trial) + "\n")
        g = row.get
        line = (f"{p['id']:12} {p['name']:16} z {p['height_cm']:3g}: ok {row['ok']:2d}/{args.count}"
                + (f"  pos err {g('pos_err_med_cm'):5.1f} cm (p90 {g('pos_err_p90_cm'):5.1f})"
                   f"  dir err {g('dir_err_med_deg'):5.2f} deg" if row["ok"] else "  NO GOOD DETECTION")
                + ("  [redo]" if redo else ""))
        summary.append(line)
        res = [f"last: {p['name']}, z {p['height_cm']:g} cm" + (" (redo)" if redo else ""),
               f"heard {row['detected']}/{args.count}, good {row['ok']}/{args.count}"]
        if row["ok"]:
            res.append(f"position error {g('pos_err_med_cm'):.1f} cm, direction error {g('dir_err_med_deg'):.1f}°")
        if row.get("clip"):
            res.append(f"CLIPPING ({row['clip']} samples): too loud")
        return res, True

    i = 0
    try:
        while i < len(todo):
            p = todo[i]
            pos = p["pos_cm"]
            lines = [fmt_pos(pos)]
            if prev_height is not None and p["height_cm"] != prev_height:
                lines.insert(0, f"NEW HEIGHT: z = {p['height_cm']:g} cm")
            buttons = ["go", "skip"] + (["redo"] if prev else [])
            phone.set_ui({"title": f"{head} · next point {index[p['id']] + 1}/{len(allpts)}",
                          "where": f"{p['name']}, height {p['height_cm']:g} cm", "lines": lines,
                          "status": "Place the phone, aim the speaker at the array, then press Ready",
                          "buttons": buttons, "result": last_result})
            print(f"\nnext: [{index[p['id']] + 1}/{len(allpts)}] {p['name']}, height {p['height_cm']:g} cm "
                  f"({fmt_pos(pos)}) - waiting for the phone button")
            action = phone.wait_action()
            if action == "skip":
                print(f"  skipped {p['id']}")
                summary.append(f"{p['id']:12} skipped")
                last_result = [f"skipped: {p['name']}, z {p['height_cm']:g} cm"]
                i += 1
                continue
            if action == "redo" and prev:
                last_result, _ = measure(prev, redo=True)
                continue
            if action != "go":
                continue
            last_result, ok = measure(p, redo=False)
            if ok:
                prev, prev_height = p, p["height_cm"]
                i += 1
        while prev:     # last chance to redo the last point
            phone.set_ui({"title": head, "where": "All points of this layout done",
                          "lines": ["Redo the last point if something went wrong, else Finish."],
                          "status": "", "buttons": ["go", "redo"], "go_label": "Finish", "result": last_result})
            print("\nall points done - waiting for Finish (or Redo previous) on the phone")
            if phone.wait_action() != "redo":
                break
            last_result, _ = measure(prev, redo=True)
        phone.set_ui({"title": head, "where": "Layout finished",
                      "lines": ["Change the array layout, then start the next series on the laptop."],
                      "status": "", "buttons": [], "result": last_result})
        print("\nseries finished")
    except KeyboardInterrupt:
        phone.command({"action": "stop"})
        phone.set_ui({"title": head, "where": "Stopped on the laptop", "lines": [], "status": "",
                      "buttons": [], "result": last_result})
        print("\nstopped - run the same command again to continue where you left off")
    finally:
        esp.set_default_signal()
        time.sleep(0.3)
        esp.close()
        time.sleep(1.0)      # let the phone fetch the final panel
        phone.stop()
    if summary:
        print("\nmeasured in this session:")
        print("\n".join(summary))


if __name__ == "__main__":
    main()
