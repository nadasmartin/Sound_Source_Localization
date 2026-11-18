"""Live per-mic loudness over the USB cable: which mic is which?

The ESP32 (on-board firmware, env "esp32") sends each mic's loudness 20 times
a second ("levels" command). This shows one bar per mic, measured against that
mic's own quiet level, so a tap / snap / word right at one mic lights up its bar.
After each loud moment it notes which mic was loudest, and by how much.

    python mic_levels.py              # Ctrl+C to quit
    python mic_levels.py --rate 10 --port /dev/ttyUSB0

Columns: dc = average ADC value (about 1000-3000 for a working mic; near 0 or
4095 = unplugged or broken), noise = quiet level (rms counts), level = now, in dB
above that mic's quiet level, clip = samples at the ADC limits (too loud).
"""

import argparse
import json
import math
import sys
import time
from collections import deque

from esp_link import EspLink
from lablog import append

MICS = ["Mic1 GPIO34", "Mic2 GPIO35", "Mic3 GPIO32", "Mic4 GPIO33"]
BAR = 40            # characters for 0..40 dB
HIT_ON_DB = 12      # a "loud moment" starts when a mic is this far above its quiet level
HIT_OFF_DB = 6      # ... and ends when every mic is back below this


def bar(db, peak):
    n = max(0, min(BAR, int(round(db))))
    p = max(0, min(BAR - 1, int(round(peak))))
    cells = ["█" if i < n else "·" for i in range(BAR)]
    if p >= n:
        cells[p] = "|"
    return "".join(cells)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", default="/dev/ttyUSB0")
    ap.add_argument("--rate", type=float, default=20, help="updates per second")
    ap.add_argument("--seconds", type=float, help="stop after this long (default: until Ctrl+C)")
    args = ap.parse_args()

    tty = sys.stdout.isatty()
    esp = EspLink(args.port)
    history = deque(maxlen=int(5 * args.rate))      # recent rms per mic, for the quiet level
    peak = [0.0] * 4
    peak_t = [0.0] * 4
    hit = None                                      # max dB per mic during a loud moment
    hits = deque(maxlen=8)        # shown on screen
    all_hits = []                 # every one, for the experiment log
    drawn = 0
    t_start = time.monotonic()
    try:
        esp.send(f"levels {args.rate:g}")
        seen = 0
        last_rx = time.monotonic()
        while args.seconds is None or time.monotonic() - t_start < args.seconds:
            time.sleep(0.02)
            with esp.lock:
                new = [m for m in esp.messages[seen:] if m.get("type") == "levels"]
                seen = len(esp.messages)
            if not new:
                if time.monotonic() - last_rx > 2:       # board was reset by opening the port
                    esp.send(f"levels {args.rate:g}")
                    last_rx = time.monotonic()
                continue
            last_rx = time.monotonic()
            for m in new:
                rms = m["rms"]
                history.append(rms)
                floor = []
                for k in range(4):
                    vals = sorted(h[k] for h in history)
                    floor.append(max(vals[len(vals) // 10], 0.5))
                db = [20 * math.log10(max(rms[k], 1e-3) / floor[k]) for k in range(4)]
                now = time.monotonic()
                for k in range(4):
                    if db[k] >= peak[k] or now - peak_t[k] > 1.0:
                        peak[k], peak_t[k] = max(db[k], 0), now
                # loud moments: which mic was the loudest?
                if hit is None and max(db) >= HIT_ON_DB:
                    hit = list(db)
                elif hit is not None:
                    hit = [max(a, b) for a, b in zip(hit, db)]
                    if max(db) < HIT_OFF_DB:
                        order = sorted(range(4), key=lambda k: -hit[k])
                        a, b = order[0], order[1]
                        sure = "clear" if hit[a] - hit[b] >= 6 else "UNCLEAR, try closer"
                        hits.appendleft(f"{time.strftime('%H:%M:%S')}  loudest {MICS[a]}  +{hit[a]:.0f} dB, "
                                        f"next {MICS[b]} +{hit[b]:.0f} dB  ({sure})")
                        all_hits.append(hits[0])
                        if not tty:
                            print(hits[0], flush=True)
                        hit = None
                last = (m, floor, db)
            if not tty:
                continue
            m, floor, db = last
            loud = max(range(4), key=lambda k: db[k])
            lines = [f"Live mic levels over USB ({args.rate:g}/s). Tap, snap or speak right at one mic. "
                     "Ctrl+C to quit.", "",
                     f"{'':12} {'dc':>5} {'noise':>6}  {'level (dB above quiet), | = 1 s peak':{BAR + 7}} clip"]
            for k in range(4):
                mark = "  ◀ loudest" if db[k] >= HIT_ON_DB and k == loud else ""
                warn = "  ← no signal? check wiring" if m["dc"][k] < 50 or m["dc"][k] > 4045 else ""
                lines.append(f"{MICS[k]:12} {m['dc'][k]:5.0f} {floor[k]:6.1f}  {bar(db[k], peak[k])} "
                             f"{max(db[k], 0):4.0f}  {m['clip'][k]:4d}{mark}{warn}")
            lines += ["", "Loud moments (newest first):"] + list(hits) + [""] * (hits.maxlen - len(hits))
            out = (f"\x1b[{drawn}F" if drawn else "") + "".join(l + "\x1b[K\n" for l in lines)
            sys.stdout.write(out)
            sys.stdout.flush()
            drawn = len(lines)
    except KeyboardInterrupt:
        pass
    finally:
        if all_hits:     # the experiment log keeps the identification results
            append("mic identification (mic_levels.py)",
                   "Loud moments:\n\n" + "\n".join(f"- {h}" for h in all_hits))
        esp.send("levels 0")
        time.sleep(0.1)
        esp.close()


if __name__ == "__main__":
    main()
