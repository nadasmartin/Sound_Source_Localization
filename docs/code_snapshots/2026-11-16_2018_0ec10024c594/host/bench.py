"""Precision bench: which test signal / band / length / volume localizes best?

Setup
  * ESP32 with the on-board firmware (env "esp32") on USB.
  * A phone at a measured position, browser open at the URL this prints
    (same Wi-Fi as the laptop), "Tap to start audio" pressed.
  * Coordinates (cm), the same as host/localize.py and the firmware:
      origin = centre of the mic square, in the plane of the mic capsules
      square of side a (10, 20 or 30 cm; --array), h = a/2:
      Mic1 (-h, +h)   Mic2 (+h, +h)   Mic3 (+h, -h)   Mic4 (-h, -h)
      z = height above the mic plane (must be >= 0)
    Measure to the phone's speaker opening.
    (Runs before 2026-11-16 used a 19 cm square with another mic order; their
    files are in bench_results/old_19cm_array/.)

For every trial (signal + gain) the laptop uploads the signal's template to the
ESP32, tells the phone to play it `count` times, collects the ESP32's results
and compares them with the true position:
  det%      detected / played          extra   detections beyond the played count
  ok%       passed misfit+quality checks / played
  tdoa rms  error of the 6 measured pair delays vs. the ones the true position
            implies [us] - the most direct measure of the timing (10 us ~ 3.4 mm path)
  tdoa std  scatter of those delays between repetitions [us] (precision only)
  pos err   distance between the measured and the true 3D position [cm], median / 90%
  dir err   angle between the measured far-field direction and the true one [deg]
  snr, lvl  matched-filter peak/median and received level [dB re ADC full scale]
  clip      samples at the ADC limits (too loud)

Usage
  python bench.py sweep --label E --channel left --array 30
        # ~2 min: ~25 signals x 4 volumes, random order; you measure the
        # position meanwhile and type it in at the end
  python bench.py evaluate bench_results/run_..._E.jsonl --pos 31.5 18.2 20.4
        # re-score a saved run against a (corrected) position
  python bench.py run --pos 40 -30 15 --label P1 --suite quick
  python bench.py run --pos 40 -30 15 --label P1 --suite all --count 20 --repeat 2
  python bench.py run --pos 40 -30 15 --signals chirp_2-10k_50ms --gains 0,-12,-24
  python bench.py run --pos 0 0 30 --label C --suite speaker   # one source or two?
  python bench.py calibrate                    # fit per-mic channel delays from the runs
  python bench.py calibrate --apply            # ... and store them in the ESP32
  python bench.py report                       # ranking over every saved run
  python bench.py report bench_results/run_*_P1.jsonl
  python signals_lib.py                        # list the suites and signals
Results: host/bench_results/run_<time>_<label>.jsonl (one line per trial, raw events included).
"""

import argparse
import json
import sys
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import numpy as np

import localize
import signals_lib as S
from esp_link import EspLink
from lablog import code_version, firmware_check, record
from phone_server import PhoneServer, print_qr

HOST_DIR = Path(__file__).parent
RESULTS = HOST_DIR / "bench_results"
TAIL_S = 1.5        # wait this long after the last repetition for the ESP32's answer
MIC_NAMES = ["Mic1", "Mic2", "Mic3", "Mic4"]


# ------------------------------------------------------------------ metrics

def evaluate(events, truth_cm, c, played):
    """Compare the ESP32's events of one trial with the true position."""
    ev = [e for e in events if e.get("type") == "event"]
    ok = [e for e in ev if e["ok"]]
    row = {"played": played, "detected": len(ev), "ok": len(ok),
           "det_rate": min(len(ev), played) / played, "ok_rate": min(len(ok), played) / played,
           "extra": max(0, len(ev) - played), "rejected": sum(e.get("type") == "reject" for e in events)}
    if ev:
        row["snr"] = float(np.median([e["snr"] for e in ev]))
        row["lvl_db"] = float(np.median([e.get("lvl_db", np.nan) for e in ev]))
        row["clip"] = int(max(e.get("clip", 0) for e in ev))
    if not ok:
        return row
    truth = np.asarray(truth_cm, float)
    tau_true = localize.model_tdoa(truth / 100, c) * 1e6
    tau = np.array([localize.pair_delays(np.array(e["arr_us"])) for e in ok])
    err = tau - tau_true
    P = np.array([e["pos_cm"] for e in ok])
    perr = np.linalg.norm(P - truth, axis=1)
    u_true = truth / np.linalg.norm(truth)
    az, el = np.radians([e["dir_az"] for e in ok]), np.radians([e["dir_el"] for e in ok])
    U = np.stack([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)], axis=1)
    derr = np.degrees(np.arccos(np.clip(U @ u_true, -1, 1)))
    row.update({
        "tdoa_rms_us": float(np.sqrt(np.mean(err ** 2))),
        "tdoa_bias_us": np.median(err, axis=0).round(2).tolist(),
        "tdoa_std_us": float(err.std(axis=0).mean()),
        "pos_err_med_cm": float(np.median(perr)),
        "pos_err_p90_cm": float(np.percentile(perr, 90)),
        "pos_bias_cm": (np.median(P, axis=0) - truth).round(2).tolist(),
        "pos_std_cm": P.std(axis=0).round(2).tolist(),
        "dir_err_med_deg": float(np.median(derr)),
        "q": float(np.median([e["q"] for e in ok])),
        "misfit_us": float(np.median([e["misfit_us"] for e in ok])),
    })
    return row


def fmt_row(name, gain, r):
    def f(key, fmt, scale=1):
        v = r.get(key)
        return format(v * scale, fmt) if v is not None and not (isinstance(v, float) and np.isnan(v)) \
            else " " * len(format(0, fmt))
    return (f"{name:24} {gain:5.0f} {f('det_rate', '5.0f', 100)} {f('ok_rate', '5.0f', 100)} "
            f"{r.get('extra', 0):5d} {f('tdoa_rms_us', '8.1f')} {f('tdoa_std_us', '8.2f')} "
            f"{f('pos_err_med_cm', '7.1f')} {f('pos_err_p90_cm', '7.1f')} {f('dir_err_med_deg', '7.1f')} "
            f"{f('snr', '6.0f')} {f('lvl_db', '6.1f')} {r.get('clip', 0):5d}")


HEADER = (f"{'signal':24} {'gain':>5} {'det%':>5} {'ok%':>5} {'extra':>5} {'tdoa rms':>8} "
          f"{'tdoa std':>8} {'pos err':>7} {'p90':>7} {'dir err':>7} {'snr':>6} {'lvl':>6} {'clip':>5}\n"
          f"{'':24} {'[dB]':>5} {'':>5} {'':>5} {'':>5} {'[us]':>8} {'[us]':>8} {'[cm]':>7} "
          f"{'[cm]':>7} {'[deg]':>7} {'':>6} {'[dB]':>6} {'':>5}")


# ---------------------------------------------------------------------- run

def setup_geometry(esp, status, array_cm=None):
    """Mic square: tell the ESP32 if --array is given, else use what it has
    stored. Sets localize.MICS to match. Returns (side_cm, status)."""
    if array_cm:
        esp.send(f"array {array_cm:g}")
        time.sleep(1.2)
        status = esp.wait_status()
    side = status.get("array_cm")
    if side is None:
        raise SystemExit("the ESP32 firmware has no 'array' setting: flash the current firmware")
    if array_cm and abs(side - array_cm) > 0.05:
        raise SystemExit(f"the ESP32 did not take the array size ({side} cm)")
    localize.set_mics(localize.square(side / 100))
    print(f"mic square {side:g} cm: " + "  ".join(
        f"{MIC_NAMES[m]} ({localize.MICS[m][0] * 100:+.1f},{localize.MICS[m][1] * 100:+.1f})" for m in range(4)))
    return side, status


def describe_truth(truth_cm, c):
    t = np.asarray(truth_cm, float)
    d = np.linalg.norm(localize.MICS * 100 - t, axis=1)
    arr = (d - d.min()) / 100 / c * 1e6
    r, az, el = localize.to_spherical(t)
    print(f"true position ({t[0]:.1f}, {t[1]:.1f}, {t[2]:.1f}) cm: distance {r:.1f} cm, "
          f"azimuth {az:.1f} deg, elevation {el:.1f} deg")
    print("expected arrival after first mic [us]: " +
          "  ".join(f"{MIC_NAMES[k]} {arr[k]:.1f}" for k in np.argsort(arr)))
    off_plane = min(az % 90, 90 - az % 90)
    if off_plane < 10:
        print(f"note: {off_plane:.0f} deg from a blind plane (x=0 or y=0): distance is poorly "
              "determined there, direction is fine")


def pick_trials(args):
    if args.signals:
        names = args.signals.split(",")
        gains = [float(g) for g in args.gains.split(",")] if args.gains else [0.0]
        trials = [S.Trial(S.by_name(n), g) for n in names for g in gains]
    else:
        trials = S.SUITES[args.suite]()
        if args.gains:
            trials = [S.Trial(t.signal, float(g), t.channel) for t in dict.fromkeys(
                S.Trial(t.signal, 0, t.channel) for t in trials) for g in args.gains.split(",")]
    if args.channels:
        chans = args.channels.split(",")
        bad = set(chans) - set(S.CHANNELS)
        if bad:
            raise SystemExit(f"unknown channel(s) {bad}; use {', '.join(S.CHANNELS)}")
        trials = list(dict.fromkeys(S.Trial(t.signal, t.gain_db, ch) for t in trials for ch in chans))
    return trials * args.repeat


def run(args):
    truth = [float(v) for v in args.pos]
    if truth[2] < 0:
        raise SystemExit("z must be >= 0 (the array can't tell above from below; see localize.py)")
    c = localize.speed_of_sound(args.temp)
    trials = pick_trials(args)
    est = sum(0.6 + args.count * args.period + TAIL_S + 1.5 for _ in trials) / 60
    print(f"{len(trials)} trials x {args.count} repetitions, about {est:.1f} min\n")

    esp = EspLink(args.port)
    status = esp.wait_status()
    if status["fs"] == 0:          # opening the port restarted the board: wait for a real one
        status = esp.wait_status()
    side, status = setup_geometry(esp, status, args.array)
    print(firmware_check(status))
    micdelay = status.get("micdelay_us", [0, 0, 0, 0])
    print(f"ESP32: {status['fs']:.0f} Hz/mic, threshold {status['thr']}, "
          f"mic delay calibration {micdelay} us" + ("" if any(micdelay) else " (none)"))
    describe_truth(truth, c)
    esp.send(f"temp {args.temp}")
    esp.send(f"holdoff {min(0.3, 0.6 * args.period):.2f}")  # one detection per repetition

    phone = PhoneServer(port=args.http_port, signal_lookup=S.by_name).start()
    print(f"\nOpen on the phone (same Wi-Fi):  {phone.url}")
    print_qr(phone.url)
    print("waiting for the phone to tap 'Start audio' ...")
    phone.wait_connected()
    print(f"phone ready ({phone.client})\n")

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"run_{datetime.now():%Y%m%d_%H%M%S}_{args.label}.jsonl"
    meta = {"type": "meta", "label": args.label, "truth_cm": truth, "temp_c": args.temp, "c": c,
            "count": args.count, "period": args.period, "micdelay_us": micdelay,
            "array_cm": side, "mics_cm": (localize.MICS * 100).round(2).tolist(),
            "fw_on_esp32": status.get("fw"), **code_version(), "argv": sys.argv,
            "started": datetime.now().isoformat()}
    current = None
    with open(out, "w") as f:
        f.write(json.dumps(meta) + "\n")
        print(HEADER)
        try:
            for n, trial in enumerate(trials, 1):
                sig = trial.signal
                if sig != current:
                    esp.set_signal(sig)
                    current = sig
                    time.sleep(0.6)   # detector re-learns the noise level (~4 FFT blocks)
                if not phone.ready():
                    print("phone disconnected - reopen the page and tap 'Start audio' ...")
                    phone.wait_connected()
                t_cmd = time.monotonic()
                seq = phone.play(sig, trial.gain_db, args.count, args.period, delay=0.6,
                                 channel=trial.channel)
                started = phone.wait_report(seq, ("playing", "error"), timeout=10)
                if not started or started["state"] == "error":
                    print(f"{trial.label:24} phone did not play: "
                          f"{started.get('error') if started else 'no answer within 10 s'}")
                    continue
                done = phone.wait_report(seq, ("done", "error"), timeout=args.count * args.period + 10)
                time.sleep(TAIL_S)
                events = esp.since(t_cmd)
                row = evaluate(events, truth, c, args.count)
                print(fmt_row(trial.label, trial.gain_db, row) + ("" if done else "  (no 'done' from phone)"))
                f.write(json.dumps({"type": "trial", "n": n, "signal": sig.name, "label": trial.label,
                                    "channel": trial.channel, "kind": sig.kind,
                                    "f_lo": sig.f_lo, "f_hi": sig.f_hi, "dur": sig.dur,
                                    "gain_db": trial.gain_db, "truth_cm": truth, **row,
                                    "phone": {k: started.get(k) for k in ("sampleRate", "outputLatency", "audioState", "audioSession", "ua")},
                                    "events": [{k: v for k, v in e.items() if k != "_rx"} for e in events]})
                        + "\n")
                f.flush()
                time.sleep(0.5)
        except KeyboardInterrupt:
            phone.command({"action": "stop"})
            print("\ninterrupted")
        finally:
            esp.set_default_signal()
            time.sleep(0.3)
            esp.close()
            phone.stop()
    print(f"\nsaved: {out.resolve()}")
    report([out])


# -------------------------------------------------------------------- sweep

SWEEP_TOL_S = 0.08    # an event belongs to a repetition if it is this close to its slot


def _loudness(e):
    return e["lvl_db"] if e.get("lvl_db") is not None else 20 * np.log10(max(e.get("snr", 1), 1e-3))


def assign_slots(events, slot_gains, period):
    """Match the ESP32's detections to the played repetitions by their timing
    on the ESP32's own clock ("t"): find the time shift that puts the most
    detections onto the slot grid k * period. If several shifts fit equally
    well (e.g. the first repetition was missed, so everything could be one slot
    earlier), take the one where the received loudness follows the played
    volumes best. Returns (per-slot list, leftovers)."""
    n_slots = len(slot_gains)
    ev = [e for e in events if e.get("type") in ("event", "reject") and "t" in e]
    best, best_shift = None, None
    for e in ev:
        for k in range(n_slots):
            shift = e["t"] - k * period
            hits, err, pairs = 0, 0.0, []
            for f in ev:
                x = (f["t"] - shift) / period
                slot = round(x)
                if 0 <= slot < n_slots and abs(x - slot) * period < SWEEP_TOL_S:
                    hits += 1
                    err += abs(x - slot)
                    pairs.append((slot_gains[slot], _loudness(f)))
            g, l = np.array(pairs).T if pairs else (np.zeros(1), np.zeros(1))
            follow = float(np.corrcoef(g, l)[0, 1]) if len(pairs) > 2 and g.std() > 0 and l.std() > 0 else 0.0
            score = (hits, round(follow, 3), -err)
            if best is None or score > best:
                best, best_shift = score, shift
    slots, extra = [[] for _ in range(n_slots)], []
    for f in ev:
        if best_shift is None:
            extra.append(f)
            continue
        x = (f["t"] - best_shift) / period
        slot = round(x)
        if 0 <= slot < n_slots and abs(x - slot) * period < SWEEP_TOL_S:
            slots[slot].append(f)
        else:
            extra.append(f)
    return slots, extra


def score_trials(trials, truth, c):
    """(Re)compute every trial's metrics from its saved events."""
    for t in trials:
        t["truth_cm"] = list(truth) if truth is not None else None
        if truth is None:
            continue
        row = evaluate(t["events"], truth, c, t["played"])
        for k in [k for k in t if k in ROW_KEYS]:
            del t[k]
        t.update(row)


ROW_KEYS = {"detected", "ok", "det_rate", "ok_rate", "extra", "rejected", "snr", "lvl_db", "clip",
            "tdoa_rms_us", "tdoa_bias_us", "tdoa_std_us", "pos_err_med_cm", "pos_err_p90_cm",
            "pos_bias_cm", "pos_std_cm", "dir_err_med_deg", "q", "misfit_us"}


def ask_position():
    while True:
        try:
            txt = input("\nMeasured speaker position  X Y Z  in cm (e.g. 31.5 18.2 20.4): ")
        except EOFError:
            return None
        try:
            v = [float(x) for x in txt.replace(",", " ").replace(";", " ").split()]
        except ValueError:
            v = []
        if len(v) == 3 and v[2] >= 0:
            return v
        print("  three numbers please, z >= 0")


def sweep(args):
    rng = np.random.default_rng()
    gains = [float(g) for g in args.gains.split(",")] if args.gains else list(S.SWEEP_GAINS)
    # one sequence per signal: a full-volume lead-in, then the volumes interleaved
    slots_gain = [0.0] + [g for _ in range(args.reps) for g in gains]
    n_slots = len(slots_gain)
    per_signal = 0.45 + args.delay + n_slots * args.period + args.tail
    signals = S.sweep_signals()
    rng.shuffle(signals)
    fit = max(1, int(args.budget // per_signal))
    if fit < len(signals):
        print(f"time budget {args.budget:.0f} s: {fit} of {len(signals)} signals (random pick)")
        signals = signals[:fit]
    print(f"{len(signals)} signals x {len(gains)} volumes ({', '.join(f'{g:g}' for g in gains)} dB) x "
          f"{args.reps} repetitions, every {args.period} s, speaker channel '{args.channel}': "
          f"about {len(signals) * per_signal:.0f} s")

    esp = EspLink(args.port)
    status = esp.wait_status()
    if status["fs"] == 0:
        status = esp.wait_status()
    side, status = setup_geometry(esp, status, args.array)
    print(firmware_check(status))
    micdelay = status.get("micdelay_us", [0, 0, 0, 0])
    c = localize.speed_of_sound(args.temp)
    print(f"ESP32: {status['fs']:.0f} Hz/mic, mic delay calibration {micdelay} us"
          + ("" if any(micdelay) else " (none)") + f", {args.temp:g} C -> c = {c:.1f} m/s")
    esp.send("scope 0")
    esp.send("levels 0")
    esp.send(f"temp {args.temp}")
    esp.send(f"holdoff {0.6 * args.period:.2f}")

    phone = PhoneServer(port=args.http_port, signal_lookup=S.by_name).start()
    print(f"\nOpen on the phone (same Wi-Fi):  {phone.url}")
    print_qr(phone.url)
    print("waiting for the phone to tap 'Start audio' ...")
    phone.wait_connected()
    print(f"phone ready ({phone.client}), loading {len(signals)} sounds ...")
    pre = phone.preload([phone.sig_url(s, args.channel) for s in signals])
    if not pre or pre.get("state") != "done":
        print(f"preload problem: {pre}; continuing (sounds load on first use)")
    print("\n>>> PLAYING NOW. Measure the speaker position; don't block the path between the phone "
          "and the mics, and don't touch the phone. <<<\n")

    raw, phone_info = [], {}
    t_start = time.monotonic()
    try:
        for n, sig in enumerate(signals, 1):
            esp.set_signal(sig)
            if not phone.ready():
                print("phone disconnected - reopen the page and tap 'Start audio' ...")
                phone.wait_connected()
            t_cmd = time.monotonic()
            seq = phone.play_gains(sig, slots_gain, args.period, args.delay, args.channel)
            started = phone.wait_report(seq, ("playing", "error"), timeout=10)
            if not started or started["state"] == "error":
                print(f"{n:3d}/{len(signals)} {sig.name:24} phone did not play: "
                      f"{started.get('error') if started else 'no answer'}")
                continue
            phone_info = {k: started.get(k) for k in ("sampleRate", "outputLatency", "audioState",
                                                       "audioSession", "ua")}
            time.sleep(max(0.0, args.delay + n_slots * args.period + args.tail
                           - (time.monotonic() - started["_rx"])))
            events = [{k: v for k, v in e.items() if k != "_rx"} for e in esp.since(t_cmd)]
            slots, extra = assign_slots(events, slots_gain, args.period)
            got = sum(1 for sl in slots if sl)
            per_gain = "  ".join(f"{g:g}dB {sum(1 for k, sl in enumerate(slots) if sl and slots_gain[k] == g)}"
                                 f"/{slots_gain.count(g)}" for g in gains)
            print(f"{n:3d}/{len(signals)} {time.monotonic() - t_start:5.0f}s {sig.name:24} "
                  f"heard {got:2d}/{n_slots}   {per_gain}" + (f"   +{len(extra)} extra" if extra else ""))
            raw.append((sig, slots, extra))
    except KeyboardInterrupt:
        phone.command({"action": "stop"})
        print("\ninterrupted - keeping what was measured")
    finally:
        esp.set_default_signal()
        time.sleep(0.3)
        esp.close()
        phone.stop()

    truth = [float(v) for v in args.pos] if args.pos else ask_position()
    if truth is not None and truth[2] < 0:
        truth = None

    trials = []
    for sig, slots, extra in raw:
        tr = S.Trial(sig, 0, args.channel)
        for g in gains:
            idx = [k for k in range(n_slots) if slots_gain[k] == g]
            evs = [e for k in idx for e in slots[k]]
            if g == 0:
                evs += extra      # unmatched detections count against full volume
            trials.append({"type": "trial", "signal": sig.name, "label": tr.label, "channel": args.channel,
                           "kind": sig.kind, "f_lo": sig.f_lo, "f_hi": sig.f_hi, "dur": sig.dur,
                           "gain_db": g, "played": len(idx), "slots": idx, "phone": phone_info,
                           "events": evs})
    score_trials(trials, truth, c)

    RESULTS.mkdir(exist_ok=True)
    out = RESULTS / f"run_{datetime.now():%Y%m%d_%H%M%S}_{args.label}.jsonl"
    meta = {"type": "meta", "mode": "sweep", "label": args.label, "truth_cm": truth, "temp_c": args.temp,
            "c": c, "period": args.period, "reps": args.reps, "gains": gains, "sequence_gains": slots_gain,
            "channel": args.channel, "micdelay_us": micdelay, "array_cm": side,
            "mics_cm": (localize.MICS * 100).round(2).tolist(), "order": [s.name for s, _, _ in raw],
            "phone": phone_info, "started": datetime.now().isoformat(), "note": args.note,
            "fw_on_esp32": status.get("fw"), **code_version(), "argv": sys.argv,
            "settings": {"budget": args.budget, "delay": args.delay, "tail": args.tail,
                         "holdoff": round(0.6 * args.period, 2), "threshold": status.get("thr"),
                         "signal_defs": [vars(s) for s, _, _ in raw]}}
    with open(out, "w") as f:
        f.write(json.dumps(meta) + "\n")
        for t in trials:
            f.write(json.dumps(t) + "\n")
    print(f"\nsaved: {out.resolve()}")
    if truth is None:
        print("no position entered: score it later with\n"
              f"  python bench.py evaluate {out} --pos X Y Z")
        return
    describe_truth(truth, c)
    report([out])


def evaluate_file(args):
    """Re-score a saved run against a (corrected) true position."""
    lines = [json.loads(l) for l in open(args.file)]
    meta = lines[0]
    truth = [float(v) for v in args.pos]
    localize.set_mics(np.array(meta["mics_cm"]) / 100 if "mics_cm" in meta else localize.OLD_19CM)
    trials = [r for r in lines[1:] if r.get("type") == "trial"]
    for t in trials:
        t.setdefault("played", meta.get("count", 0))
    old = meta.get("truth_cm")
    meta["truth_cm"] = truth
    meta.setdefault("truth_history", []).append({"old": old, "new": truth, "at": datetime.now().isoformat()})
    score_trials(trials, truth, meta["c"])
    with open(args.file, "w") as f:
        for r in [meta] + trials:
            f.write(json.dumps(r) + "\n")
    print(f"position {old} -> {truth} cm, re-scored {len(trials)} trials in {Path(args.file).resolve()}")
    describe_truth(truth, meta["c"])
    report([args.file])


# ------------------------------------------------------------------- report

def report(paths):
    rows = []
    for p in paths:
        cal = None
        for line in open(p):
            r = json.loads(line)
            if r.get("type") == "meta":
                cal = any(r.get("micdelay_us", [0]))
            if r.get("type") == "trial" and "detected" in r:   # scored (position known)
                r["_file"] = Path(p).name
                r["_cal"] = cal
                rows.append(r)
    if not rows:
        print("no trials found")
        return
    groups = defaultdict(list)
    for r in rows:
        name = r.get("label", r["signal"]) + (" +cal" if r["_cal"] else "")
        groups[(name, r["gain_db"])].append(r)
    positions = {tuple(r["truth_cm"]) for r in rows}

    def agg(rs, key, fn=np.median):
        v = [r[key] for r in rs if r.get(key) is not None]
        return float(fn(v)) if v else None

    table = []
    for (name, gain), rs in groups.items():
        played = sum(r["played"] for r in rs)
        a = {"det_rate": sum(min(r["detected"], r["played"]) for r in rs) / played,
             "ok_rate": sum(min(r["ok"], r["played"]) for r in rs) / played,
             "extra": sum(r["extra"] for r in rs),
             # timing error pooled as rms over trials; others as medians over trials
             "tdoa_rms_us": agg(rs, "tdoa_rms_us", lambda v: np.sqrt(np.mean(np.square(v)))),
             "tdoa_std_us": agg(rs, "tdoa_std_us"),
             "pos_err_med_cm": agg(rs, "pos_err_med_cm"),
             "pos_err_p90_cm": agg(rs, "pos_err_p90_cm", np.max),
             "dir_err_med_deg": agg(rs, "dir_err_med_deg"),
             "snr": agg(rs, "snr"), "lvl_db": agg(rs, "lvl_db"),
             "clip": int(max(r.get("clip", 0) for r in rs))}
        table.append((name, gain, a, len(rs)))

    # Best first: reliable detection, then the smallest timing error
    def key(t):
        a = t[2]
        return (a["ok_rate"] < 0.9, a["tdoa_rms_us"] if a["tdoa_rms_us"] is not None else 1e9)
    table.sort(key=key)
    print(f"\nRANKING over {len(rows)} trials, {len(positions)} position(s) "
          f"(reliable first, i.e. ok% >= 90, then by tdoa rms)")
    print(HEADER + "  trials")
    for name, gain, a, n in table:
        print(fmt_row(name, gain, a) + f"  {n:5d}")


# ---------------------------------------------------------------- calibrate

CAL_FILE = HOST_DIR / "calibration.json"


def load_trials(paths, signal_filter=None, channel=None):
    """Per trial: true position, speed of sound, and the median *raw* pair
    delays (any calibration that was active in the firmware added back)."""
    out = []
    for p in paths:
        meta = {}
        for line in open(p):
            r = json.loads(line)
            if r.get("type") == "meta":
                meta = r
                continue
            if r.get("type") != "trial":
                continue
            if signal_filter and signal_filter not in r["signal"]:
                continue
            if channel and r.get("channel", "both") != channel:
                continue
            ok = [e for e in r["events"] if e.get("type") == "event" and e["ok"]]
            if len(ok) < 3:
                continue
            d = np.array(meta.get("micdelay_us", [0, 0, 0, 0])) * 1e-6
            undo = np.array([d[i] - d[j] for i, j in localize.PAIRS])
            tau = np.median([localize.pair_delays(np.array(e["arr_us"])) * 1e-6 for e in ok], axis=0)
            if r.get("truth_cm") is None:
                continue
            mics = np.array(meta["mics_cm"]) / 100 if "mics_cm" in meta else localize.OLD_19CM
            out.append({"truth": np.array(r["truth_cm"]) / 100, "c": meta.get("c", 343.0),
                        "tau": tau + undo, "signal": r.get("label", r["signal"]), "mics": mics})
    return out


def fit_delays(trials):
    """Per-mic channel delays (s, Mic1 = 0) that best explain the measured
    pair delays given the true positions. Linear least squares:
        tau_ij - model_ij(truth) = d_i - d_j"""
    A, b = [], []
    for t in trials:
        resid = t["tau"] - localize.model_tdoa(t["truth"], t["c"], t["mics"])
        for (i, j), r in zip(localize.PAIRS, resid):
            row = np.zeros(4)
            row[i], row[j] = 1, -1
            A.append(row[1:])          # Mic1 is the reference (d1 = 0)
            b.append(r)
    d, *_ = np.linalg.lstsq(np.array(A), np.array(b), rcond=None)
    return np.r_[0.0, d]


def tdoa_rms(trials, d):
    corr = np.array([d[i] - d[j] for i, j in localize.PAIRS])
    e = [t["tau"] - corr - localize.model_tdoa(t["truth"], t["c"], t["mics"]) for t in trials]
    return float(np.sqrt(np.mean(np.square(e)))) * 1e6


def calibrate(args):
    paths = args.files or sorted(RESULTS.glob("run_*.jsonl"))
    trials = load_trials(paths, args.signal, args.channel)
    if not trials:
        raise SystemExit("no usable trials (need runs with >= 3 good detections)")
    positions = sorted({tuple(np.round(t["truth"] * 100, 1)) for t in trials})
    sizes = sorted({round(float(np.ptp(t["mics"][:, 0])) * 100, 1) for t in trials})
    print(f"mic square size(s) in these runs: {', '.join(f'{v:g} cm' for v in sizes)}")
    sectors = {int(((np.degrees(np.arctan2(p[1], p[0])) % 360) + 45) // 90) % 4 for p in positions}
    print(f"{len(trials)} trials, {len(positions)} positions, "
          f"{len(sectors)} of 4 sides of the array (+x, +y, -x, -y) covered")

    d = fit_delays(trials)
    print(f"\nper-mic channel delay (relative to Mic1) [us]: " +
          "  ".join(f"{MIC_NAMES[m]} {d[m] * 1e6:+.1f}" for m in range(4)))
    print(f"timing error vs. truth: {tdoa_rms(trials, np.zeros(4)):.1f} us -> {tdoa_rms(trials, d):.1f} us "
          "(in-sample)")

    print("\nsame fit per signal (should agree if it is the electronics):")
    for name in sorted({t["signal"] for t in trials}):
        sub_t = [t for t in trials if t["signal"] == name]
        ds = fit_delays(sub_t)
        print(f"  {name:28} " + "  ".join(f"{ds[m] * 1e6:+6.1f}" for m in range(1, 4)) +
              f"   ({len(sub_t)} trials)")

    if len(positions) >= 2:
        print("\nleave one position out (fit on the others, test here) - the honest check:")
        for pos in positions:
            train = [t for t in trials if tuple(np.round(t["truth"] * 100, 1)) != pos]
            test = [t for t in trials if tuple(np.round(t["truth"] * 100, 1)) == pos]
            dl = fit_delays(train)
            corr = np.array([dl[i] - dl[j] for i, j in localize.PAIRS])
            before, after = [], []
            for t in test:
                localize.set_mics(t["mics"])
                before.append(np.linalg.norm(localize.locate(t["tau"], t["c"])[0] - t["truth"]) * 100)
                after.append(np.linalg.norm(localize.locate(t["tau"] - corr, t["c"])[0] - t["truth"]) * 100)
            print(f"  ({pos[0]:6.1f},{pos[1]:6.1f},{pos[2]:6.1f}) cm: timing {tdoa_rms(test, np.zeros(4)):5.1f}"
                  f" -> {tdoa_rms(test, dl):5.1f} us, position error {np.median(before):5.1f} -> "
                  f"{np.median(after):5.1f} cm")
    if len(sectors) < 3:
        print("\nWARNING: the positions cover fewer than 3 sides of the array. A delay and a"
              "\nsource-position error look alike from one side; measure positions all around"
              "\n(and one straight above the centre, where every true delay is 0) before trusting this.")

    CAL_FILE.write_text(json.dumps({
        "micdelay_us": [round(float(v) * 1e6, 2) for v in d], "trials": len(trials),
        "positions": [list(p) for p in positions], "files": [Path(p).name for p in paths],
        "signal_filter": args.signal, "channel": args.channel,
        "created": datetime.now().isoformat()}, indent=2) + "\n")
    print(f"\nsaved: {CAL_FILE.resolve()}")
    if args.apply:
        send_micdelay(args.port, [float(v) * 1e6 for v in d])


def send_micdelay(port, d_us):
    esp = EspLink(port)
    try:
        esp.wait_status()
        esp.send("micdelay " + " ".join(f"{v:.2f}" for v in d_us))
        time.sleep(1.2)
        st = esp.wait_status()
        print(f"ESP32 now uses mic delays {st.get('micdelay_us')} us (stored in its flash)")
    finally:
        esp.close()


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="measure at one known position")
    r.add_argument("--pos", nargs=3, required=True, metavar=("X", "Y", "Z"),
                   help="true speaker position in cm (see coordinates above)")
    r.add_argument("--label", default="pos", help="name for this position, used in the file name")
    r.add_argument("--suite", default="quick", choices=sorted(S.SUITES))
    r.add_argument("--signals", help="comma-separated signal names instead of a suite")
    r.add_argument("--gains", help="comma-separated gains in dB (overrides the suite's)")
    r.add_argument("--count", type=int, default=15, help="repetitions per trial")
    r.add_argument("--period", type=float, default=S.DEFAULT_PERIOD, help="seconds between repetitions")
    r.add_argument("--repeat", type=int, default=1, help="run the whole list this many times")
    r.add_argument("--temp", type=float, default=21.0, help="room temperature in C")
    r.add_argument("--port", default="/dev/ttyUSB0")
    r.add_argument("--http-port", type=int, default=8765)
    r.add_argument("--channels", help="comma-separated speaker channels: both,left,right "
                                      "(phones with two speakers)")
    r.add_argument("--note", default="", help="free text for the experiment log (setup, phone orientation, ...)")
    r.add_argument("--array", type=float, help="mic square side in cm (10, 20, 30); default: what the ESP32 has stored")
    sw = sub.add_parser("sweep", help="~2 min: many signals x volumes at one position (type the position at the end)")
    sw.add_argument("--label", required=True, help="name of this position, e.g. E, N, W, S")
    sw.add_argument("--channel", required=True, choices=S.CHANNELS,
                    help="speaker channel: the one that plays from the phone's main speaker")
    sw.add_argument("--array", type=float, help="mic square side in cm (10, 20, 30); default: what the ESP32 has stored")
    sw.add_argument("--pos", nargs=3, metavar=("X", "Y", "Z"), help="true position in cm, if already measured")
    sw.add_argument("--budget", type=float, default=120, help="seconds of playing (default 120)")
    sw.add_argument("--gains", help="comma-separated volumes in dB (default 0,-10,-20,-30)")
    sw.add_argument("--reps", type=int, default=3, help="repetitions per signal and volume")
    sw.add_argument("--period", type=float, default=0.25, help="seconds between repetitions")
    sw.add_argument("--delay", type=float, default=0.35, help="phone start delay per signal")
    sw.add_argument("--tail", type=float, default=0.4, help="wait after the last repetition")
    sw.add_argument("--temp", type=float, default=21.0, help="room temperature in C")
    sw.add_argument("--port", default="/dev/ttyUSB0")
    sw.add_argument("--http-port", type=int, default=8765)
    sw.add_argument("--note", default="", help="free text for the experiment log")
    ev = sub.add_parser("evaluate", help="re-score a saved run against a (corrected) position")
    ev.add_argument("file", type=Path)
    ev.add_argument("--pos", nargs=3, required=True, metavar=("X", "Y", "Z"))
    rp = sub.add_parser("report", help="rank signals over saved runs")
    rp.add_argument("files", nargs="*", type=Path)
    cp = sub.add_parser("calibrate", help="fit per-mic channel delays from saved runs")
    cp.add_argument("files", nargs="*", type=Path)
    cp.add_argument("--signal", help="only trials whose signal name contains this")
    cp.add_argument("--channel", choices=S.CHANNELS, help="only trials with this speaker channel")
    cp.add_argument("--apply", action="store_true", help="send the result to the ESP32 (saved in its flash)")
    cp.add_argument("--clear", action="store_true", help="set the ESP32's mic delays back to 0")
    cp.add_argument("--port", default="/dev/ttyUSB0")
    cp.add_argument("--note", default="", help="free text for the experiment log")
    args = p.parse_args()
    # run and calibrate are written to docs/experiment_log.md (command + printed results)
    if args.cmd == "sweep":
        with record(f"bench sweep {args.label} ({args.channel} channel, array {args.array or 'as stored'} cm)",
                    args.note):
            sweep(args)
    elif args.cmd == "evaluate":
        with record(f"bench evaluate {args.file.name} at {tuple(args.pos)} cm"):
            evaluate_file(args)
    elif args.cmd == "run":
        with record(f"bench run {args.label} at {tuple(args.pos)} cm", args.note):
            run(args)
    elif args.cmd == "calibrate":
        with record("bench calibrate" + (" --clear" if args.clear else " --apply" if args.apply else ""),
                    args.note):
            if args.clear:
                send_micdelay(args.port, [0, 0, 0, 0])
            else:
                calibrate(args)
    else:
        report(args.files or sorted(RESULTS.glob("run_*.jsonl")))


if __name__ == "__main__":
    main()
