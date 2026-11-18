# How to repeat the measurements

Companion to `docs/experiment_log.md`, the notebook of what was run and what came out.
This file lists everything needed to run an experiment again the same way:
- hardware and setup;
- the exact code, and where its copies are;
- every parameter;
- the protocol;
- a dated history of code and parameter changes.

Paths are relative to `/home/nadasmartin/okos_lab_project/`.

---

## 1. Hardware and setup

- **Board:** ESP32 dev board (PlatformIO `board = esp32dev`), USB serial `/dev/ttyUSB0` at 921600 baud.
- **Mics:** 4 analog mic modules on ADC1:

  | Mic  | GPIO   | ADC1 channel | Scan slot |
  |------|--------|--------------|-----------|
  | Mic1 | GPIO34 | 6            | 0         |
  | Mic2 | GPIO35 | 7            | 1         |
  | Mic3 | GPIO32 | 4            | 2         |
  | Mic4 | GPIO33 | 5            | 3         |

  - Attenuation 12 dB (about 0–3.1 V), 12 bit.
  - Quiet level ≈ 1940 counts.
  - (Mic module type and supply: to be filled in.)
- **Array, since 2026-11-16:** each mic in its own mount, square of side a = 30 / 20 / 10 cm (h = a/2).
  - Positions (cm): Mic1 (−h, +h), Mic2 (+h, +h), Mic3 (+h, −h), Mic4 (−h, −h).
  - Origin: centre of the square, in the plane of the capsules. z is up and must be ≥ 0.
  - Before 2026-11-16: 19 cm square with Mic1 (+9.5, −9.5), Mic2 (−9.5, −9.5), Mic3 (−9.5, +9.5), Mic4 (+9.5, +9.5).
- **Sound source:** iPhone (Safari; user agent reports iOS 18.7; Web Audio at 48 kHz), page `http://<laptop>:8765/`.
  - Screen rotation locked in **portrait**.
  - Media volume, set by hand without recording the steps:
    - P1: maximum (lots of room echo);
    - P2: lowered;
    - P3 and later: lowered further.
  - Phone orientation: P1 and P2 lying untilted; P3 and later tilted so the speaker faces the array.
  - Main (bottom) speaker = **left** stereo channel (measured 2026-11-16, see the log under P1). The right channel is the earpiece.
  - The position measured is the speaker opening.
  - Ring/Silent switch: no effect (the page uses the "playback" audio session).
- **Laptop:** Linux, same Wi-Fi as the phone (laptop 192.168.1.76).
  - Firewall rule: `sudo ufw allow from 192.168.1.0/24 to any port 8765 proto tcp`.
  - Python virtual environment in `.venv/`.
- **Room temperature:** not measured so far; 21 °C assumed (c = 344.0 m/s). Pass `--temp` when known.

## 2. Code: which version ran

- Not a git repository. Code versions are kept as copies in `docs/code_snapshots/`.
  - `2026-11-16_P1-P2/`: made by hand right after P2. It is the exact code of the P1 and P2 sweeps (host + firmware). The ESP32 binary was built at 19:28 from these sources.
  - `<date>_<fingerprint>/`: made automatically, since 2026-11-16 ~20:20, the first time a logged command runs with a new code version.
- Every logged run shows `code: <fingerprint>` (host + firmware sources) in `docs/experiment_log.md`.
  Its data file has `code`, `fw`, `snapshot`, `fw_on_esp32` and `argv` in the first line (meta).
- **Firmware fingerprint:** `firmware/fw_version.py` builds a hash of the firmware sources into the binary.
  - The ESP32 reports it as `"fw"` in its status line.
  - bench.py prints whether it equals the sources on disk ("ESP32 firmware … = the firmware sources on disk", or a WARNING).
  - Firmware flashed before 2026-11-16 ~21:00 has no fingerprint.
- **Restoring a version:** copy the snapshot's `host/` and `firmware/` over the project, then flash it (next section).

## 3. Build, flash, run

```
cd /home/nadasmartin/okos_lab_project && source .venv/bin/activate
cd firmware && pio run -e esp32 -t upload        # on-board firmware (env esp32)
cd ../host
python bench.py sweep --label P1 --channel left --array 30 --rot 0 --pos X Y Z [--temp T]
python bench.py report bench_results/run_*.jsonl   # ranking over positions
python bench.py calibrate                          # per-mic delay fit (+ --apply)
python bench.py evaluate <file> --pos X Y Z        # re-score with a corrected position
python series.py --series a10 --array 10 --rot 0 --channel left --temp T --note "phone volume ..."   # a30 / a20 ran with --rot 2.13
                                                   # distance series, plan plans/distance_v2.json, driven from the phone
python analyze_series.py                           # evaluate all series of the plan
```

Phone: open `http://192.168.1.76:8765/` and tap "Tap to start audio". After a laptop restart the page reconnects by itself (from 2026-11-16 20:05). If Safari was in the background, reload the page and tap again.

## 4. Parameters

### Firmware constants
`firmware/lib/tdoa/dsp_config.h`, `firmware/src/main.cpp`; the same since the on-board version, unless the history (section 6) says otherwise.

| Parameter | Value | Meaning |
|---|---|---|
| FS | 44100 Hz | samples per mic (measured 44020–44150 Hz) |
| OVERSAMPLE | 4 | ADC readings averaged per sample (ADC runs at 705.6 kHz in total) |
| CHANNEL_SKEW_S | 1.417 us | delay between two scan slots, corrected in every pair delay |
| MAX_SIG_LEN | 2205 samples (50 ms) | longest template |
| default template | linear chirp **3000→12000 Hz**, 50 ms, 5 ms fade; band bins 289–1187 (3111–12780 Hz) | used when none is uploaded. Until 2026-11-18: 1500→8000 Hz, bins 112–835 (1200–9000 Hz) |
| RING | 12 × 1024 sets = 279 ms | audio buffer |
| NFFT | 4096 | FFT size (matched filter + GCC) |
| MF_HOP | 1892 | overlap-save hop of the matched filter |
| DEFAULT_MF_THRESHOLD | 12 × median | detection threshold (`thr` command) |
| MF_PEAK_WINDOW_S | 5 ms | best peak after the first crossing |
| HOLDOFF_S | 0.3 s default | dead time after a detection (`holdoff` command; the sweep uses 0.15 s) |
| analysis band | 0.8·f_lo … 1.125·f_hi as FFT bins, at most 900 bins (~9.7 kHz) | set with each template |
| GCC_PRE | 132 samples (3 ms) | window starts this much before the signal |
| MAX_TDOA_S / MAX_LAG | 1.5 ms / 66 samples | largest delay searched |
| INTERP | 16 | sub-sample step 1/16 sample (band-limited DFT), then a parabola |
| MAX_MISFIT_S | 10 us | consistency check of the 6 pair delays ("ok") |
| MIN_QUALITY | 0.2 | GCC-PHAT peak quality check ("ok") |
| localization | grid 14 ranges (0.15–6 m) × 36 azimuths × 15 elevations, best 5 refined by Levenberg–Marquardt, z ≥ 0 | |
| array (runtime) | 30 cm (saved in flash) | `array <cm>` command |
| array rotation (runtime) | **0°** (since 2026-11-18 16:45; saved in flash; firmware default 0) | `rot <deg>` command / `bench.py --rot` / `series.py --rot`. +2.13° (fitted on P1–P4) was used 2026-11-18 morning–16:27, incl. series a30 and a20; the series data fit −0.15° / −0.05° (`analyze_series.py` prints the fit) |
| micdelay (runtime) | 0, 0, 0, 0 us | `micdelay` command; not used so far on the new array |

### Signals
`host/signals_lib.py`
- **Kinds:**
  - `chirp`: linear sweep (scipy `chirp`, method "linear");
  - `logchirp`: method "logarithmic";
  - `noise`: white noise (numpy default_rng seed 1) built at 48 kHz, FFT bins outside f_lo–f_hi set to 0;
  - `tone`.
- **Fade:** raised cosine, 5 ms in and out; peak normalised to 1.
- **Phone copy:** 48 kHz, 16-bit **stereo** WAV, peak 32000. Channel "left" = signal left and silence right (`?ch=left`).
- **ESP32 template:** the same formula at 44.1 kHz, int16 peak 32000, uploaded with sig_begin/sig_data/sig_end.
- **Volume:** a Web Audio GainNode, gain = 10^(dB/20), relative to the media volume.

### Sweep protocol
`bench.py sweep`; defaults used for P1 and P2.
- **Signals (25):** the order is random (numpy default_rng without a seed); the order played is saved in the meta as `order`.
  - chirp 50 ms: 0.5–4k, 1–5k, 2–6k, 1–8k, 1.5–8k, 3–8k, 1–10k, 2–10k, 3–10k, 3–12k, 4–12k, 5–14k, 6–16k, 8–18k;
  - chirp 2–10k at 10 / 20 / 35 ms;
  - chirp 4–12k at 20 ms;
  - logchirp 1–10k, 1.5–8k, 2–12k (50 ms);
  - noise 1–6k, 1.5–8k, 2–10k, 4–12k (50 ms).
- **Per signal:**
  1. Upload the template.
  2. One phone sequence of 13 plays, 0.25 s apart: a 0 dB lead-in, then 3 × (0, −10, −20, −30 dB) interleaved.
  3. The phone starts 0.35 s after the command. The laptop waits 0.4 s after the last play.
- **ESP32 settings during a sweep:** holdoff 0.15 s, threshold 12, temperature from `--temp` (21 °C).
- **Matching detections to plays:**
  - on the ESP32 clock: the time shift that puts the most detections within ±80 ms of the 0.25 s grid;
  - ties broken by how well the received level follows the played volumes (from 20:25 on 2026-11-16, i.e. used for P1 and P2);
  - unmatched detections count as "extra" at 0 dB.
- **Budget:** 120 s; signals are dropped (randomly) if they don't fit. All 25 fit.
- **Channel check before P1:** `bench.py run --signals chirp_2-10k_50ms --channels left,right --count 6 --period 0.5`, holdoff 0.3 s.

### Metrics
`host/bench.py evaluate()`; only "ok" detections count for the timing and position numbers.
- **tdoa rms:** rms over all ok detections and all 6 pairs of (measured pair delay − delay predicted from the true position).
- **tdoa std:** standard deviation over repetitions, per pair, averaged over pairs (repeatability).
- **pos err:** median / 90th percentile of |ESP32 position − true position|.
- **dir err:** angle between the ESP32's far-field direction and the true direction.
- **snr:** matched-filter peak / median. **lvl:** received level in dB re 2048 counts (Parseval over the analysis band). **clip:** samples at 0 or 4095.

## 5. Experiments and how to repeat each

| When | What | Data | Command | Code |
|---|---|---|---|---|
| 2026-11-14 18:30–18:37 | P1 (old 19 cm array) at 3 positions, suite quick, both channels | `host/bench_results/old_19cm_array/` | `bench.py run --pos X Y Z --label P1 --suite quick` (count 15, period 0.5) | not kept (before snapshots); described in the log |
| 2026-11-16 19:31 | pipeline test, laptop speaker | `host/bench_results/tests/run_20261116_193117_TEST.jsonl` | `bench.py sweep --label TEST --channel both --array 30 --budget 20 --pos 0 50 30` with a stand-in phone script | as P1-P2 |
| 2026-11-16 20:04 | channel check at P1 | `host/bench_results/tests/run_20261116_200432_P1-chk.jsonl` | see sweep protocol | `docs/code_snapshots/2026-11-16_P1-P2/` |
| 2026-11-16 20:06 | sweep P1 (−32, 22.9, 46.5) | `host/bench_results/run_20261116_200640_P1.jsonl` | `bench.py sweep --label P1 --channel left --array 30 --pos -32 22.9 46.5` | `docs/code_snapshots/2026-11-16_P1-P2/` |
| 2026-11-16 20:16 | sweep P2 (33.8, 27.5, 47.0) | `host/bench_results/run_20261116_201657_P2.jsonl` | `bench.py sweep --label P2 --channel left --array 30 --pos 33.8 27.5 47.0` | `docs/code_snapshots/2026-11-16_P1-P2/` |
| 2026-11-16 20:34 | sweep P3 (27.5, −32.3, 42.0); volume lowered further, phone tilted towards the array | `host/bench_results/run_20261116_203451_P3.jsonl` | `bench.py sweep --label P3 --channel left --array 30 --pos 27.5 -32.3 42.0` | code `0ec10024c594` (`docs/code_snapshots/2026-11-16_2018_0ec10024c594/`), firmware `cc8e9c945759` |
| 2026-11-16 20:41 | sweep P4 (−28.3, −31.3, 42.0); same setup as P3 | `host/bench_results/run_20261116_204112_P4.jsonl` | `bench.py sweep --label P4 --channel left --array 30 --pos -28.3 -31.3 42.0` | code `0ec10024c594`, firmware `cc8e9c945759` |
| 2026-11-16 ~20:45 | per-mic delay calibration check over P1–P4 (not applied) | result `host/calibration.json` | `bench.py calibrate` and `bench.py calibrate --signal chirp` | code `0ec10024c594` |
| 2026-11-16 ~20:50 | analysis P1–P4: error models, rotation, signal ranking | (printout in the log) | `python analyze_sweeps.py bench_results/run_20261116_200640_P1.jsonl bench_results/run_20261116_201657_P2.jsonl bench_results/run_20261116_203451_P3.jsonl bench_results/run_20261116_204112_P4.jsonl` (in `host/`) | `host/analyze_sweeps.py`, deterministic |
| 2026-11-18 11:49–12:59 | distance series a30: 30 cm array, 80 points (`plans/distance_v2.json`), z 10–170 cm, 20 × chirp 3–12k each | `host/bench_results/series/distance_v2/a30/` | `python series.py --series a30 --array 30 --rot 2.13 --channel left --temp 21` (in `host/`, phone-driven); evaluate `python analyze_series.py --series a30` | code `d219b4897885` (`docs/code_snapshots/2026-11-18_1139_d219b4897885/`), firmware `9587b9dbc09c` |
| 2026-11-18 15:49–16:27 | distance series a20: 20 cm array, 80 points (`plans/distance_v2.json`), same settings as a30; not re-calibrated | `host/bench_results/series/distance_v2/a20/` | `python series.py --series a20 --array 20 --rot 2.13 --channel left --temp 21` (in `host/`, phone-driven); evaluate `python analyze_series.py --rot 0` (rotation re-fitted to ≈0°, see the log 2026-11-18 16:45) | firmware `9587b9dbc09c`; code: automatic log entry of the run |
| 2026-11-18 16:48–17:48 | distance series a10: 10 cm array, 80 points (`plans/distance_v2.json`), same settings, rotation 0° | `host/bench_results/series/distance_v2/a10/` | `python series.py --series a10 --array 10 --rot 0 --channel left --temp 21` (in `host/`, phone-driven); evaluate all three: `python analyze_series.py --rot 0` | firmware `9587b9dbc09c`; code: automatic log entry of the run |

Later runs: the automatic entries in `docs/experiment_log.md` carry the command, code fingerprint and snapshot.

## 6. History of code and parameter changes

- **Before 2026-11-14:** Wi-Fi streaming firmware (`firmware/src/wifi_stream/`, env `esp32_wifi`), analysis on the laptop (`host/tdoa.py`).
- **By 2026-11-14:** all processing moved onto the ESP32 (env `esp32`). Parameters as in section 4.
  - Matched filter instead of an energy trigger.
  - One shared FFT buffer.
  - Ring buffer in IRAM.
- **2026-11-14:** precision bench (`bench.py run/report`), phone page, signals library.
  - iOS fix: audio session "playback" plus a silent keep-alive `<audio>` element.
- **2026-11-14:** speaker channel selection (`--channels`, suite `speaker`).
  - Per-mic delay calibration: firmware `micdelay` command, saved in flash; `bench.py calibrate`.
- **2026-11-16 ~19:00:** firmware `levels <hz>` command (per-mic rms/DC/peak-to-peak/clip); `host/mic_levels.py`.
- **2026-11-16 ~19:10:** firmware `scope <avg>` command: the live waveform averaged over `avg` samples (8 → 5.5 kHz per mic); `host/mic_viewer.py` USB mode. Not used during measurements (switched off by bench.py).
- **2026-11-16 ~19:15:** experiment log (`host/lablog.py` → `docs/experiment_log.md`).
- **2026-11-16 ~19:28:** new geometry and runtime array size.
  - Firmware: `MICS` is no longer a constant; `array <cm>` command, saved in flash, default 30 cm; reported in the status line.
  - Host: `localize.square()`, `set_mics()`; run files store `array_cm` and `mics_cm`.
- **2026-11-16 ~19:30:** `bench.py sweep` and `evaluate`.
  - Phone page: per-play volumes (`gains`), `preload`, left/right test buttons.
  - `signals_lib.sweep_signals()`.
- **2026-11-16 ~19:45:** sweep matching fix: volume pattern as the tie-break.
- **2026-11-16 ~20:00:** the phone page re-syncs after a server restart (server boot id).
- **2026-11-16 ~20:20 (after P2):** reproducibility.
  - Firmware build fingerprint (`fw_version.py`, `"fw"` in the status line).
  - Automatic code snapshots.
  - Code fingerprint, argv and settings in the run files.
  - Firmware re-flashed: fingerprint `cc8e9c945759`. No change in processing.
- **2026-11-16 ~20:50:** new `host/analyze_sweeps.py`: error models with leave-one-position-out, rotation per signal group, signal ranking with the nominal and the rotated geometry. Analysis only; nothing in the measurement chain changed.
- **2026-11-18 ~08:55:** array rotation and new default test signal (decided after P1–P4).
  - Firmware: `setArrayGeometry(side, rot)` in `firmware/lib/tdoa/tdoa.cpp` turns the nominal square by `rot` deg about its centre (x' = x cos − y sin, y' = x sin + y cos). New `rot <deg>` command (−30…30, saved in flash, key `rot`); the status line reports `array_rot_deg`. Changing `array` keeps the rotation.
  - Firmware boot template: chirp 3000→12000 Hz, 50 ms (was 1500→8000 Hz); default band bins 289–1187 (was 112–835). Identical to `signals_lib.Signal("chirp", 3000, 12000, 0.05)` and its `band_bins()`, i.e. exactly what the sweeps uploaded as `chirp_3-12k_50ms`.
  - Host: `localize.square(side, rot_deg)`, `localize.MEASURED_ROT_DEG = 2.13`; `bench.py run/sweep --rot` (sets the board; without it the board's stored value is used and a NOTE is printed if it differs from the measured one); run files store `array_rot_deg` and the rotated `mics_cm`.
  - `signals_lib.DEFAULT`, `test_signal.py` (F_START/F_END) and the phone page's test buttons now use the 3–12 kHz chirp; `tdoa.py` BAND = 3111–12780 Hz.
  - `analyze_sweeps.py` prints the fitted rotation next to the one the runs used.
  - Firmware fingerprint `9587b9dbc09c`, code `6a7471c3aa5b` (snapshot `docs/code_snapshots/2026-11-18_0854_6a7471c3aa5b/`). **Not flashed yet** (ESP32 not connected at 08:55); after flashing, run once with `--rot 2.13` to store the rotation.
- **2026-11-18 ~09:40:** distance series tooling (no change in the measurement chain).
  - `host/plans/distance_v1.json`: 23 points on rays of fixed elevation (lines A 45°, B 75°, C 90°, spot checks S), see the log entry of 2026-11-18 09:40.
  - `host/series.py`: per point, `signals_lib.DEFAULT` (chirp 3–12k 50 ms) is played `--count` 30 times every `--period` 0.5 s at `--gain` 0 dB; holdoff 0.3 s; threshold as stored on the ESP32. Files go to `host/bench_results/series/<plan>/<series>/<point>_<placement>_<time>.jsonl`, measured positions to `host/plans/<plan>_measured.json`.
  - `host/analyze_series.py`: metrics per point (see its docstring), Fraunhofer distance at 7.5 kHz, c = 343 m/s.
  - Setup for the series: mic plane 4 cm above the floor; phone ≤ 165 cm above the mic plane.
- **2026-11-18 ~11:00:** firmware `9587b9dbc09c` flashed (3–12 kHz default, `rot`); rotation +2.13° stored on the board.
- **2026-11-18 ~11:45:** final distance grid and phone-driven measuring.
- **2026-11-18 13:05:** `series.py --points` to re-measure selected points.
- **2026-11-18 13:25:** `bench_results/series/<plan>/excluded.json` + `analyze_series.py` skips the points listed there (a30 z090-M4, wrong placement). Mic square changed to 20 cm; rotation +2.13° assumed (not re-calibrated).
- **2026-11-18 16:45:** rotation re-fitted on the series a30/a20: ≈0° (−0.15 / −0.05), not +2.13°. `localize.MEASURED_ROT_DEG` = 0.0; `analyze_series.py` gains `fit_rotation` and `--rot` (re-localize on the host). Evaluate a30/a20 with `--rot 0`; run a10 with `--rot 0`.
- **2026-11-18 17:50:** series a10 measured (all three layouts done). `analyze_series.py`: `geom` = ∞ exactly in a blind plane (was 0.0).
- **2026-11-18 18:20:** git repository (`.gitignore` keeps out `.venv`, `.pio`, `wifi_secrets.h`); analysis page `docs/dashboard/index.html` from `host/build_dashboard.py` + `host/dashboard/template.html` (rebuild: `python build_dashboard.py` in `host/`).
  - `host/plans/distance_v2.json` = the user's grid (16 positions × heights z 10/50/90/130/170 cm). `distance_v1.json` was deleted, never used.
  - `host/series.py`: the phone panel drives the session (Ready / Redo previous / Skip, Finish); default `--count 20`; a redo writes `<point>_2_…` and analysis uses the newest.
  - `host/phone_server.py`: `POST /action`, `set_ui()`, `wait_action()`, `ui`/`uiv` in `/poll`. `host/phone/index.html`: measurement panel.
