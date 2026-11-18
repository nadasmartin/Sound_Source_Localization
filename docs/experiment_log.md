# Experiment log — 4-mic TDOA sound localization (ESP32)

Raw notebook, newest at the bottom. Not polished: source material for the
documentation later. Raw data is NOT in here, only what was run and what came
out; entries name the data file where there is one.

Written automatically by:
- `host/bench.py run` / `calibrate` (command, ESP32 state, phone, result table)
- `host/mic_levels.py` (mic identification: which mic was loudest)
- `host/mic_viewer.py` (that a viewer session ran, sample rate, gaps)

Written by hand / by Claude: setup changes, analyses, decisions, firmware changes.

Paths are relative to `/home/nadasmartin/okos_lab_project/`.

---

## Background (before this log was started)

- 2026-11-02 … 11-03: Wi-Fi era. Firmware env `esp32_wifi` streamed the raw
  4-mic audio over TCP; analysis on the laptop (`host/tdoa.py`,
  `host/localize.py`, viewer `host/mic_viewer.py`). Recordings in
  `host/recordings/rec_202611*.npz`.
- Before 2026-11-14: moved all computation onto the ESP32 (firmware env
  `esp32`, `firmware/src/main.cpp` + `firmware/lib/tdoa/`); only results go to
  the laptop as JSON lines over USB serial (921600 baud). Viewer/logger
  `host/telemetry.py`, logs in `host/telemetry_logs/`.
  - Sampling: 4 mics on ADC1 (GPIO34, 35, 32, 33), 44.1 kHz per mic, each
    sample the average of 4 ADC readings. Core 1 samples, core 0 does DSP.
  - Detection: streaming matched filter (an energy trigger did not work: the
    chirp is below the per-sample noise; the 50 ms sweep gives ~25 dB gain).
  - Timing: GCC-PHAT on all 6 mic pairs, sub-sample refinement (1/16 sample),
    ADC channel-skew correction 1.42 us per channel slot.
  - Position: grid search + Levenberg–Marquardt, z >= 0; direction from a
    far-field fit. Processing ~72 ms per detection.
  - Memory problems solved on the way (fragmented heap, float loads from IRAM
    crash, ADC needs DMA RAM first).
- Array at that time: 19 cm square. Mic1 (+9.5,−9.5), Mic2 (−9.5,−9.5),
  Mic3 (−9.5,+9.5), Mic4 (+9.5,+9.5) cm, origin in the centre, z up.

## 2026-11-14 — Precision bench built

- Goal: find the best test signal (type, band, length, volume) and measure
  precision against a measured ground-truth position.
- Phone (iPhone, Safari, 48 kHz) opens `http://<laptop>:8765/` and plays what
  the laptop says (`host/phone_server.py`, `host/phone/index.html`). The laptop
  uploads the same signal as the matched-filter template to the ESP32
  (`host/signals_lib.py`, `host/esp_link.py`), then compares the ESP32's
  results with the truth (`host/bench.py`).
- Metrics: det% / ok%, tdoa rms (error of the 6 pair delays vs. truth), tdoa
  std (repeatability), position error median / p90, direction error, snr,
  received level, clipping.
- Problem: first run, the iPhone played nothing (0 % detected). Cause: iOS
  mutes Web Audio with the Ring/Silent switch. Fix: audio session "playback" +
  a looping silent `<audio>` element. Afterwards the phone played fine.
- `host/bench_results/run_20261114_183001_P1.jsonl`: aborted after start, no trials.

## 2026-11-14 18:30 — bench run P1 at (30, −50, 35) cm, suite quick

- Phone: iPhone (iOS 18.7), sampleRate 48000, outputLatency 12 ms, audio session playback.
- Count 15 per trial, period 0.5 s, temp 21 °C, no mic-delay calibration.
- Data: `host/bench_results/run_20261114_183021_P1.jsonl`

```
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]
chirp_2-10k_50ms             0   100   100     0      7.1     0.35    13.5    14.0     0.7   1219  -23.6     0
noise_1.5-8k_50ms            0   100   100     0      8.8     0.63    10.1    11.0     1.1     35  -34.8     0
chirp_1.5-8k_20ms            0   100   100     0      9.7     0.61    12.7    13.7     1.1    809  -24.1     0
chirp_1.5-8k_50ms          -12   100   100     0     10.2     0.42    12.0    12.6     1.2    675  -26.3     0
chirp_1.5-8k_50ms            0   100    87     0     10.2     0.67    12.0    12.8     1.2    963  -22.7     0
```

## 2026-11-14 18:35 — bench run P1 at (30, −50, 25) cm, suite quick

- Same settings. Data: `host/bench_results/run_20261114_183519_P1.jsonl`

```
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
chirp_2-10k_50ms             0   100   100     0      7.1     0.28    13.8    14.0     0.2   1045  -23.2     0
noise_1.5-8k_50ms            0   100   100     0      9.8     0.68    15.4    15.8     0.8     29  -34.0     0
chirp_1.5-8k_20ms            0   100   100     0     11.2     0.34    17.5    17.8     0.9    796  -23.2     0
chirp_1.5-8k_50ms          -12   100   100     0     11.4     0.57    17.6    18.8     0.8    550  -26.4     0
chirp_1.5-8k_50ms            0   100   100     0     11.6     0.36    18.5    18.7     0.8    866  -22.6     0
```

## 2026-11-14 18:37 — bench run P1 at (10, −26, 5) cm, suite quick

- Same settings. Data: `host/bench_results/run_20261114_183734_P1.jsonl`

```
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
chirp_2-10k_50ms             0   100   100     0     11.0     0.21     7.3     7.4     8.7   1780  -17.0     0
chirp_1.5-8k_50ms            0   100    93     0     12.4     0.22     5.7     5.8     9.3   1468  -16.3     0
chirp_1.5-8k_50ms          -12   100   100     0     12.7     0.25     5.9     6.1     9.3   1193  -20.3     0
chirp_1.5-8k_20ms            0   100   100     0     12.8     0.24     5.8     6.0     9.5   1230  -16.6     0
noise_1.5-8k_50ms            0   100   100     0     13.2     0.23     7.4     7.5    10.1     61  -27.9     0
```

## 2026-11-14 — Analysis: why the position errors are so big

- Observations over the 3 runs:
  - Repeatability is excellent: tdoa std 0.2–0.7 us.
  - The error is a constant timing bias: tdoa rms 7–13 us, about the same for every signal and volume.
  - Direction is right (~1° at the far positions); positions come out 15–30 % too close (radial shrink).
  - Pair Mic1–Mic2 is about −17 us off at every position.
  - Best signal in all 3 runs: chirp 2–10 kHz 50 ms (lowest tdoa rms). Noise burst: lowest snr, highest std.
- Fitted explanations (tdoa rms after the fit, all 3 positions together):
  - none: 10.8 us
  - wrong speed of sound: 10.7 us (ruled out)
  - wrong array scale: 10.5 us (ruled out)
  - **fixed per-mic channel delay: 4.2 us**, with Mic2 +16.5, Mic3 +4.4, Mic4 +8.1 us vs. Mic1
  - wrong mic positions: 3.0 us, but needs an unphysical 5 cm shift
- Per-signal delay fits agree roughly (Mic2 12–18, Mic3 3–5, Mic4 8–9 us), which points to
  the analog front ends (mic modules / amplifiers), slightly frequency-dependent.
- Leave-one-position-out (fit on 2 positions, test on the 3rd), position error:
  - (10,−26,5): 6.0 → 2.8 cm
  - (30,−50,25): 17.5 → 4.6 cm
  - (30,−50,35): 11.9 → 24.7 cm (worse)
- Limitation: all 3 positions are on the same side of the array (Mic1 closest),
  so a channel delay and a source-position error can't be told apart.
- Two-speaker phone (earpiece + bottom speaker playing the same sound) is a
  possible cause of the remaining 2–4 us: at the two far positions the 6 delays
  disagree with each other by 2–6 us, at the near one only 0.2–0.7 us.
- Tools added:
  - Speaker channel selection: `--channels both,left,right` and suite `speaker`.
  - `bench.py calibrate [--apply|--clear]`: fits per-mic delays, checks leave-one-out,
    warns when not all 4 sides are covered. `--apply` stores them in the ESP32's flash
    (`micdelay` command); runs record the active calibration and the report marks them "+cal".
- Plan: positions on all 4 sides of the array (30° off the x/y axes, which are blind
  planes for distance), plus one straight above the centre (all true delays = 0), then calibrate.
- Calibration NOT applied; the ESP32 has micdelay = 0.

## 2026-11-16 — Array rebuilt

- Each mic now sits in its own mount. Square placement switchable between 10, 20 and 30 cm side length.
- Which mic (GPIO) is at which corner is unknown after the rebuild → identify first.
- The old runs (19 cm array) must not be mixed into the new calibration.
- The code still assumes the 19 cm square (`firmware/lib/tdoa/dsp_config.h`,
  `host/localize.py`) until the new geometry is entered.

## 2026-11-16 — Live mic tools over USB (firmware change)

- Firmware (`firmware/src/main.cpp`) gets two new commands:
  - `levels <hz>`: per-mic AC rms, DC, peak-to-peak and clipping, N times a second.
  - `scope <avg>`: the live waveform, each value the average of `<avg>` ADC samples.
    The full 44.1 kHz × 4 mics (~350 kB/s) does not fit through the 921600 baud serial port
    (~90 kB/s). `avg 8` → 5.5 kHz per mic, ~54 kB/s.
- Laptop:
  - `host/mic_levels.py`: terminal meter, notes which mic was loudest at each loud moment.
  - `host/mic_viewer.py`: the old waveform + loudness viewer, now over USB by default (`--wifi` for the old stream).
- Check (all 4 mics, quiet room with some background noise):
  - DC ≈ 1937–1946 counts on every mic (mid-scale, so all connected), noise rms ≈ 13–20 counts.
  - Scope stream measured 5523 Hz per mic, 53.7 kB/s, 0 gaps, 0 ADC overflows.
- Experiment logging added (this file, `host/lablog.py`).

## 2026-11-16 19:31 — bench sweep TEST (both channel, array 30.0 cm)

- command (in `/home/nadasmartin/okos_lab_project/host`): `python bench.py sweep --label TEST --channel both --array 30 --budget 20 --pos 0 50 30 --note 'pipeline test with laptop speaker, not a real measurement'`
- duration: 24 s, finished
- notes: pipeline test with laptop speaker, not a real measurement

```
time budget 20 s: 4 of 25 signals (random pick)
4 signals x 4 volumes (0, -10, -20, -30 dB) x 3 repetitions, every 0.25 s, speaker channel 'both': about 18 s
mic square 30 cm: Mic1 (-15.0,+15.0)  Mic2 (+15.0,+15.0)  Mic3 (+15.0,-15.0)  Mic4 (-15.0,-15.0)
ESP32: 44151 Hz/mic, mic delay calibration [0.0, 0.0, 0.0, 0.0] us (none), 21 C -> c = 344.0 m/s

Open on the phone (same Wi-Fi):  http://192.168.1.76:8765/
waiting for the phone to tap 'Start audio' ...
phone ready (127.0.0.1), loading 4 sounds ...

>>> PLAYING NOW. Measure the speaker position; don't block the path between the phone and the mics, and don't touch the phone. <<<

  1/4     4s noise_1.5-8k_50ms        heard  4/13   0dB 4/4  -10dB 0/3  -20dB 0/3  -30dB 0/3
  2/4     9s noise_1-6k_50ms          heard  4/13   0dB 4/4  -10dB 0/3  -20dB 0/3  -30dB 0/3
  3/4    13s chirp_1-5k_50ms          heard  7/13   0dB 4/4  -10dB 3/3  -20dB 0/3  -30dB 0/3
  4/4    17s chirp_8-18k_50ms         heard  0/13   0dB 0/4  -10dB 0/3  -20dB 0/3  -30dB 0/3

saved: /home/nadasmartin/okos_lab_project/host/bench_results/run_20261116_193117_TEST.jsonl
true position (0.0, 50.0, 30.0) cm: distance 58.3 cm, azimuth 90.0 deg, elevation 31.0 deg
expected arrival after first mic [us]: Mic1 0.0  Mic2 0.0  Mic3 717.0  Mic4 717.0
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine

RANKING over 16 trials, 1 position(s) (reliable first, i.e. ok% >= 90, then by tdoa rms)
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]        trials
noise_1.5-8k_50ms            0   100     0     0                                               13  -43.5     0      1
noise_1.5-8k_50ms          -10     0     0     0                                                             0      1
noise_1.5-8k_50ms          -20     0     0     0                                                             0      1
noise_1.5-8k_50ms          -30     0     0     0                                                             0      1
noise_1-6k_50ms              0   100     0     0                                               14  -41.4     0      1
noise_1-6k_50ms            -10     0     0     0                                                             0      1
noise_1-6k_50ms            -20     0     0     0                                                             0      1
noise_1-6k_50ms            -30     0     0     0                                                             0      1
chirp_1-5k_50ms              0   100     0     0                                               63  -31.8     0      1
chirp_1-5k_50ms            -10   100     0     0                                               18  -41.4     0      1
chirp_1-5k_50ms            -20     0     0     0                                                             0      1
chirp_1-5k_50ms            -30     0     0     0                                                             0      1
chirp_8-18k_50ms             0     0     0     0                                                             0      1
chirp_8-18k_50ms           -10     0     0     0                                                             0      1
chirp_8-18k_50ms           -20     0     0     0                                                             0      1
chirp_8-18k_50ms           -30     0     0     0                                                             0      1
```

## 2026-11-16 — Mics identified, new geometry (by hand)

- Identified by the user with the live tools. Mic numbers = firmware channels (Mic1 GPIO34, Mic2 GPIO35, Mic3 GPIO32, Mic4 GPIO33).
- Square, each mic stays in its own quarter; side a = 30, 20 or 10 cm (h = a/2 = 15, 10, 5 cm):
  - Mic1 (−h, +h)
  - Mic2 (+h, +h)
  - Mic3 (+h, −h)
  - Mic4 (−h, −h)
  - So the mic order is different from the old 19 cm array (old: Mic1 (+,−), Mic2 (−,−), Mic3 (−,+), Mic4 (+,+)).
- Firmware: the geometry is now a setting, `array <side cm>` (5–60), saved in flash and reported in the status line as `array_cm`.
  Default 30 cm. `firmware/lib/tdoa/dsp_config.h` (MICS, setArraySide), `firmware/lib/tdoa/tdoa.cpp`, `firmware/src/main.cpp`.
  - Check: MAX_LAG (1.5 ms) still covers the 30 cm square's diagonal (42.4 cm = 1.23 ms).
- Host: `host/localize.py` gets `square(side)` and `set_mics()`. bench.py sets it from the ESP32 (or `--array`) and stores `array_cm` + `mics_cm` in every run file.
  calibrate/evaluate use each file's own geometry; files without it are treated as the old 19 cm array.
- Old runs moved to `host/bench_results/old_19cm_array/` so they don't mix into the new analysis.

## 2026-11-16 — Plan: signal search, take 2 (by hand)

- Goal: best signal / band / length / volume, measured seriously.
  - The user measures the phone position as precisely as possible.
  - Main (bottom) speaker only: one stereo channel. Which channel is found with buttons on the phone page; screen rotation locked in portrait.
  - 4 directions around the array (one per side), each a full sweep.
- New `bench.py sweep` (`host/bench.py`):
  - ~2 min per position, 25 signals in random order, a subset if the budget is shorter.
    - 14 linear chirps 50 ms from 0.5–4k up to 8–18 kHz;
    - 2–10k chirp at 10 / 20 / 35 ms, plus 4–12k at 20 ms;
    - 3 log chirps;
    - 4 noise bursts.
  - Each signal is ONE phone sequence: a 0 dB lead-in, then volumes 0 / −10 / −20 / −30 dB interleaved, 3 repetitions each (13 plays, 0.25 s apart).
    Detections are matched to repetitions by their timing on the ESP32 clock (time-shift search, ±80 ms).
  - The position is typed in at the end (the user measures while it plays). `bench.py evaluate FILE --pos X Y Z` re-scores a run if the position is corrected later.
  - All sounds are preloaded on the phone before the timed part.
- Phone page (`host/phone/index.html`): per-repetition volumes (`gains`), `preload` command, "Beep LEFT / RIGHT channel only" buttons.
  Server helpers `play_gains`, `preload` in `host/phone_server.py`. Signal list `sweep_signals()` in `host/signals_lib.py`.

## 2026-11-16 19:31 — Pipeline test of the sweep with the laptop speaker (by hand)

- The automatic entry is above (TEST). A stand-in "phone" script (same HTTP protocol, plays through the laptop speaker) was used, so this is NOT a measurement; the laptop position was unknown (dummy 0 50 30).
  Data moved to `host/bench_results/tests/run_20261116_193117_TEST.jsonl`.
- Works: preload, sequences, matching detections to repetitions, scoring, saving, report.
- Finding: every detection failed the checks (misfit 50–800 us, GCC quality 0.10–0.28, limit 0.2).
  - Laptop at 100 % volume: matched-filter snr ~13–64, received level −32 to −43 dB.
  - On 2026-11-14 (old array) laptop tests gave snr ~900, quality ~0.5, 100 % ok.
- Python cross-check of raw windows (`telemetry.py --verify`): ESP32 arrival times agree with Python within 1.5–2.3 us, so the computation is correct; the input is the problem (low SNR / low coherence between mics).
  - Per-pair GCC quality from 2 raw windows: 0.14–0.28 on every pair; no single mic stands out.
  - Mic signal rms ~35–47 counts vs. ~13–20 counts quiet.
- Open question: is the laptop now just far from the array, or did the rebuild (mounts, longer wires) cost sensitivity / add noise? → the phone sweep will show it (on 2026-11-14 the phone gave snr 600–1800, level −16 to −34 dB).
- Also seen: chirp 8–18 kHz was not detected at all from the laptop speaker (laptop speakers are weak up there; check with the phone).

## 2026-11-16 — Fix in the sweep's repetition matching (by hand)

- Synthetic test showed: if the 0 dB lead-in is not detected, shifting everything by one repetition fits the timing equally well → volumes would be mislabelled.
- Fix (`host/bench.py` `assign_slots`): ties are broken by how well the received level (lvl_db) follows the played volume pattern (0/−10/−20/−30 interleaved).
- Synthetic check: lead-in missing, two gaps, first quiet ones missing, nothing missing → all assigned correctly, no leftovers.

## 2026-11-16 20:04 — bench run P1-chk at ('-32', '22.9', '46.5') cm

- command (in `/home/nadasmartin/okos_lab_project/host`): `python bench.py run --pos -32 22.9 46.5 --label P1-chk --signals chirp_2-10k_50ms --channels left,right --count 6 --period 0.5 --array 30 --note 'which stereo channel is the main speaker (louder at the mics)'`
- duration: 55 s, finished
- notes: which stereo channel is the main speaker (louder at the mics)

```
2 trials x 6 repetitions, about 0.2 min

mic square 30 cm: Mic1 (-15.0,+15.0)  Mic2 (+15.0,+15.0)  Mic3 (+15.0,-15.0)  Mic4 (-15.0,-15.0)
ESP32: 44151 Hz/mic, threshold 12.0, mic delay calibration [0.0, 0.0, 0.0, 0.0] us (none)
true position (-32.0, 22.9, 46.5) cm: distance 60.9 cm, azimuth 144.4 deg, elevation 49.8 deg
expected arrival after first mic [us]: Mic1 0.0  Mic4 355.1  Mic2 478.1  Mic3 757.8

Open on the phone (same Wi-Fi):  http://192.168.1.76:8765/
waiting for the phone to tap 'Start audio' ...
phone ready (192.168.1.97)

signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_2-10k_50ms@L           0   100    83     0     25.0     0.50    13.3    14.8     3.2    652  -23.1     0
chirp_2-10k_50ms@R           0   100    83     3     22.9     2.00    20.5    22.3     3.0    435  -25.3     0

saved: /home/nadasmartin/okos_lab_project/host/bench_results/run_20261116_200432_P1-chk.jsonl

RANKING over 2 trials, 1 position(s) (reliable first, i.e. ok% >= 90, then by tdoa rms)
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]        trials
chirp_2-10k_50ms@R           0   100    83     3     22.9     2.00    20.5    22.3     3.0    435  -25.3     0      1
chirp_2-10k_50ms@L           0   100    83     0     25.0     0.50    13.3    14.8     3.2    652  -23.1     0      1
```

## 2026-11-16 20:06 — bench sweep P1 (left channel, array 30.0 cm)

- command (in `/home/nadasmartin/okos_lab_project/host`): `python bench.py sweep --label P1 --channel left --array 30 --pos -32 22.9 46.5 --note 'first of 4 directions; position measured by the user; channel left chosen as the louder one in the check'`
- duration: 114 s, finished
- notes: first of 4 directions; position measured by the user; channel left chosen as the louder one in the check

```
25 signals x 4 volumes (0, -10, -20, -30 dB) x 3 repetitions, every 0.25 s, speaker channel 'left': about 111 s
mic square 30 cm: Mic1 (-15.0,+15.0)  Mic2 (+15.0,+15.0)  Mic3 (+15.0,-15.0)  Mic4 (-15.0,-15.0)
ESP32: 44024 Hz/mic, mic delay calibration [0.0, 0.0, 0.0, 0.0] us (none), 21 C -> c = 344.0 m/s

Open on the phone (same Wi-Fi):  http://192.168.1.76:8765/
waiting for the phone to tap 'Start audio' ...
phone ready (192.168.1.97), loading 25 sounds ...

>>> PLAYING NOW. Measure the speaker position; don't block the path between the phone and the mics, and don't touch the phone. <<<

  1/25     4s chirp_3-8k_50ms          heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3   +2 extra
  2/25     9s chirp_2-10k_35ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3   +1 extra
  3/25    13s chirp_5-14k_50ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
  4/25    17s chirp_2-10k_20ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
  5/25    22s chirp_3-10k_50ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3   +1 extra
  6/25    26s chirp_6-16k_50ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
  7/25    30s logchirp_2-12k_50ms      heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
  8/25    35s noise_2-10k_50ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3   +4 extra
  9/25    39s chirp_2-6k_50ms          heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3   +2 extra
 10/25    43s chirp_8-18k_50ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
 11/25    47s chirp_1-8k_50ms          heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
 12/25    52s chirp_4-12k_50ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
 13/25    56s chirp_3-12k_50ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
 14/25    60s chirp_2-10k_10ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
 15/25    65s noise_1-6k_50ms          heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
 16/25    69s logchirp_1.5-8k_50ms     heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3   +1 extra
 17/25    73s chirp_0.5-4k_50ms        heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
 18/25    78s chirp_2-10k_50ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3   +1 extra
 19/25    82s chirp_4-12k_20ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
 20/25    86s chirp_1-5k_50ms          heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
 21/25    90s noise_1.5-8k_50ms        heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3   +2 extra
 22/25    95s chirp_1.5-8k_50ms        heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3   +1 extra
 23/25    99s logchirp_1-10k_50ms      heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
 24/25   103s chirp_1-10k_50ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
 25/25   108s noise_4-12k_50ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3   +4 extra

saved: /home/nadasmartin/okos_lab_project/host/bench_results/run_20261116_200640_P1.jsonl
true position (-32.0, 22.9, 46.5) cm: distance 60.9 cm, azimuth 144.4 deg, elevation 49.8 deg
expected arrival after first mic [us]: Mic1 0.0  Mic4 355.1  Mic2 478.1  Mic3 757.8

RANKING over 100 trials, 1 position(s) (reliable first, i.e. ok% >= 90, then by tdoa rms)
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]        trials
noise_4-12k_50ms@L         -30   100   100     0     21.9     0.48    11.3    11.8     2.9     14  -45.5     0      1
noise_4-12k_50ms@L         -10   100   100     0     21.9     0.50     9.2     9.9     2.9     89  -31.2     0      1
noise_4-12k_50ms@L           0   100   100     4     22.2     0.53     9.0     9.2     3.1     20  -42.5     0      1
noise_4-12k_50ms@L         -20   100   100     0     22.3     0.58    11.5    11.9     3.0     26  -39.3     0      1
chirp_4-12k_20ms@L         -20   100   100     0     22.4     0.36     7.9     8.7     3.1    165  -33.8     0      1
chirp_3-12k_50ms@L         -30   100   100     0     22.6     0.32     8.6     9.2     3.1     80  -40.3     0      1
chirp_4-12k_20ms@L           0   100   100     0     22.6     0.32     8.2     8.9     3.1    467  -24.9     0      1
chirp_4-12k_20ms@L         -10   100   100     0     22.7     0.26     7.6     7.9     3.1    359  -27.3     0      1
chirp_5-14k_50ms@L         -20   100   100     0     22.7     0.33     5.7     6.1     3.1    176  -34.9     0      1
logchirp_2-12k_50ms@L      -30   100   100     0     22.7     0.58    13.2    13.3     3.1     89  -37.3     0      1
chirp_4-12k_50ms@L           0   100   100     0     22.8     0.36     8.0     8.3     3.1    733  -23.1     0      1
chirp_5-14k_50ms@L         -30   100   100     0     22.8     0.52     5.9     7.5     3.1     65  -44.3     0      1
chirp_4-12k_50ms@L         -20   100   100     0     22.8     0.19     8.2     8.2     3.1    233  -32.5     0      1
chirp_5-14k_50ms@L           0   100   100     0     22.8     0.31     5.3     6.0     3.1    452  -25.9     0      1
chirp_3-12k_50ms@L         -20   100   100     0     22.8     0.27     8.9     9.7     3.1    210  -33.0     0      1
chirp_4-12k_20ms@L         -30   100   100     0     22.9     0.64    10.1    10.2     3.1     53  -43.4     0      1
chirp_3-12k_50ms@L         -10   100   100     0     22.9     0.26     9.0     9.1     3.1    467  -26.3     0      1
logchirp_2-12k_50ms@L      -10   100   100     0     22.9     0.35    10.1    11.6     3.1    324  -25.7     0      1
chirp_1-5k_50ms@L            0   100   100     0     22.9     0.50    32.6    35.3     2.9    272  -25.4     0      1
chirp_3-12k_50ms@L           0   100   100     0     23.0     0.26     8.1     8.4     3.1    651  -24.3     0      1
logchirp_2-12k_50ms@L      -20   100   100     0     23.0     0.13    10.6    10.7     3.1    184  -29.8     0      1
logchirp_2-12k_50ms@L        0   100   100     0     23.0     0.36     9.9    10.7     3.1    206  -24.2     0      1
chirp_6-16k_50ms@L           0   100   100     0     23.0     0.32     4.2     4.6     3.2    321  -33.5     0      1
chirp_5-14k_50ms@L         -10   100   100     0     23.0     0.33     5.2     5.6     3.2    368  -28.2     0      1
chirp_4-12k_50ms@L         -10   100   100     0     23.0     0.19     8.1     8.7     3.1    520  -26.1     0      1
noise_2-10k_50ms@L         -30   100   100     0     23.1     0.91    14.0    14.6     3.0     13  -42.1     0      1
noise_1-6k_50ms@L            0   100   100     0     23.1     2.03    27.7    29.0     3.0     16  -31.4     0      1
chirp_4-12k_50ms@L         -30   100   100     0     23.2     0.36     9.6     9.8     3.1     78  -41.7     0      1
chirp_2-10k_20ms@L           0   100   100     0     23.4     0.58    13.8    14.9     3.0    497  -24.4     0      1
chirp_1-5k_50ms@L          -10   100   100     0     23.4     0.41    33.6    34.5     3.0    205  -26.6     0      1
chirp_6-16k_50ms@L         -20   100   100     0     23.5     0.21     4.6     4.6     3.2    162  -38.8     0      1
chirp_6-16k_50ms@L         -10   100   100     0     23.5     0.38     4.0     4.6     3.2    279  -34.1     0      1
chirp_6-16k_50ms@L         -30   100   100     0     23.5     0.53     6.0     8.1     3.2     56  -48.1     0      1
chirp_2-10k_50ms@L         -10   100   100     0     23.8     0.36    12.3    13.9     3.1    451  -25.6     0      1
chirp_1-10k_50ms@L           0   100   100     0     23.9     0.20    11.3    11.4     3.1    387  -24.4     0      1
chirp_2-10k_20ms@L         -10   100   100     0     24.0     0.31    16.5    17.4     3.1    388  -26.0     0      1
noise_1-6k_50ms@L          -30   100   100     0     24.1     0.91    28.3    29.5     3.1     14  -40.4     0      1
noise_2-10k_50ms@L           0   100   100     4     24.1     0.74    10.2    12.0     3.1     19  -39.2     0      1
chirp_1-10k_50ms@L         -10   100   100     0     24.2     0.34    11.2    12.0     3.1    287  -26.4     0      1
logchirp_1-10k_50ms@L        0   100   100     0     24.2     0.29    16.7    17.0     3.1    179  -25.5     0      1
chirp_1-5k_50ms@L          -30   100   100     0     24.3     0.69    27.7    30.1     3.1    101  -34.7     0      1
chirp_2-10k_50ms@L         -20   100   100     0     24.3     0.30    12.4    13.0     3.1    216  -31.5     0      1
chirp_2-10k_20ms@L         -20   100   100     0     24.3     0.72    17.1    18.3     3.2    184  -32.4     0      1
chirp_3-10k_50ms@L         -10   100   100     0     24.3     0.30    12.6    12.6     3.2    562  -25.2     0      1
noise_1-6k_50ms@L          -20   100   100     0     24.4     0.85    30.1    30.7     2.8     18  -35.6     0      1
logchirp_1-10k_50ms@L      -10   100   100     0     24.4     0.44    18.6    18.6     3.1    139  -26.9     0      1
noise_2-10k_50ms@L         -20   100   100     0     24.4     0.95    10.7    12.6     3.2     21  -36.6     0      1
chirp_2-10k_35ms@L         -20   100   100     0     24.5     0.44    16.1    16.2     3.1    195  -31.7     0      1
chirp_2-10k_35ms@L         -30   100   100     0     24.5     0.75    14.1    14.9     3.1     91  -37.7     0      1
chirp_1-5k_50ms@L          -20   100   100     0     24.6     0.80    28.3    29.6     3.2    145  -30.4     0      1
noise_2-10k_50ms@L         -10   100   100     0     24.6     0.77     8.8    11.0     3.1     79  -26.9     0      1
chirp_1-10k_50ms@L         -20   100   100     0     24.6     0.21    10.7    11.4     3.1    125  -32.7     0      1
chirp_2-10k_10ms@L         -10   100   100     0     24.6     1.01    21.5    24.7     3.1    330  -27.0     0      1
chirp_2-10k_50ms@L         -30   100   100     0     24.7     0.47    12.9    13.2     3.1     91  -37.8     0      1
logchirp_1.5-8k_50ms@L     -20   100   100     0     24.7     0.30    29.7    30.6     3.1    117  -31.6     0      1
chirp_1.5-8k_50ms@L        -30   100   100     0     24.7     0.38    26.0    26.9     3.1    113  -36.0     0      1
chirp_1-8k_50ms@L          -30   100   100     0     24.8     0.60    23.8    26.7     3.1     84  -36.3     0      1
noise_1.5-8k_50ms@L        -30   100   100     0     24.8     0.55    24.2    24.8     3.1     14  -41.7     0      1
noise_1-6k_50ms@L          -10   100   100     0     24.9     1.91    30.1    31.8     2.9     18  -31.0     0      1
logchirp_1.5-8k_50ms@L     -10   100   100     0     24.9     0.60    30.9    34.3     3.1    185  -25.9     0      1
chirp_0.5-4k_50ms@L        -10   100   100     0     24.9     0.96    17.6    21.4     3.1    122  -28.9     0      1
chirp_3-8k_50ms@L          -30   100   100     0     25.0     0.97    28.6    30.5     3.1    103  -38.4     0      1
logchirp_1.5-8k_50ms@L     -30   100   100     0     25.0     0.44    30.2    30.9     3.0     97  -35.4     0      1
chirp_2-6k_50ms@L          -30   100   100     0     25.0     0.71    34.8    37.3     2.8    172  -34.4     0      1
chirp_3-10k_50ms@L         -20   100   100     0     25.0     0.42    12.1    12.1     3.2    257  -31.7     0      1
chirp_1-10k_50ms@L         -30   100   100     0     25.1     0.55    14.0    14.1     3.1     70  -37.6     0      1
chirp_3-10k_50ms@L         -30   100   100     0     25.2     0.85    12.3    13.1     3.2    106  -38.7     0      1
chirp_0.5-4k_50ms@L        -20   100   100     0     25.3     1.14    19.4    21.8     3.1    141  -28.9     0      1
chirp_0.5-4k_50ms@L          0   100   100     0     25.3     0.66    23.7    24.6     3.1    146  -27.9     0      1
chirp_2-10k_10ms@L           0   100   100     0     25.3     1.00    22.6    24.1     3.1    394  -26.2     0      1
chirp_0.5-4k_50ms@L        -30   100   100     0     25.3     1.28    18.2    22.7     3.2     63  -35.8     0      1
chirp_1-8k_50ms@L          -20   100   100     0     25.3     0.40    28.4    29.4     3.1    141  -31.1     0      1
logchirp_1-10k_50ms@L      -20   100   100     0     25.4     0.76    19.9    21.1     3.2    120  -30.4     0      1
chirp_1.5-8k_50ms@L        -20   100   100     0     25.5     0.45    31.9    31.9     3.1    260  -28.8     0      1
chirp_2-10k_10ms@L         -30   100   100     0     25.5     0.82    27.9    28.2     3.1     58  -40.9     0      1
noise_1.5-8k_50ms@L          0   100   100     2     25.6     0.49    31.5    31.9     3.1     16  -32.5     0      1
chirp_2-10k_10ms@L         -20   100   100     0     25.6     0.96    24.5    27.3     3.1    185  -31.8     0      1
chirp_1-8k_50ms@L            0   100   100     0     25.6     0.36    31.0    32.3     3.1    408  -23.6     0      1
noise_1.5-8k_50ms@L        -20   100   100     0     25.6     0.62    26.6    30.7     3.1     19  -36.8     0      1
logchirp_1-10k_50ms@L      -30   100   100     0     25.6     1.31    20.8    22.8     3.2     64  -36.5     0      1
chirp_2-10k_20ms@L         -30   100   100     0     25.8     0.93    17.2    20.9     3.2     78  -39.0     0      1
chirp_1-8k_50ms@L          -10   100   100     0     25.9     0.60    34.0    35.3     3.1    288  -25.5     0      1
chirp_2-6k_50ms@L          -20   100   100     0     26.0     0.69    34.9    34.9     2.9    407  -27.2     0      1
chirp_1.5-8k_50ms@L          0   100   100     1     26.0     1.77    28.3    30.0     3.1    445  -23.3     0      1
noise_1.5-8k_50ms@L        -10   100   100     0     26.1     1.41    27.4    30.9     3.2     20  -32.6     0      1
chirp_3-8k_50ms@L          -20   100   100     0     26.1     1.08    32.6    38.6     3.2    252  -30.7     0      1
chirp_2-10k_35ms@L           0   100   100     1     26.4     6.08    18.9    64.7     3.0    542  -23.5     0      1
chirp_8-18k_50ms@L         -20   100    33     0     20.7     0.00     2.5     2.5     3.0    137  -43.9     0      1
chirp_8-18k_50ms@L           0   100    25     0     21.9     0.00     2.1     2.1     3.1    242  -39.1     0      1
logchirp_1.5-8k_50ms@L       0   100    25     1     23.1     0.00    16.4    16.4     3.0     18  -36.0     0      1
chirp_2-10k_35ms@L         -10   100    67     0     23.3     0.39    13.9    14.2     3.0    420  -25.4     0      1
chirp_3-10k_50ms@L           0   100    75     1     23.9     0.34    12.2    13.0     3.1    604  -23.4     0      1
chirp_8-18k_50ms@L         -10   100    33     0     23.9     0.00     2.9     2.9     3.1    238  -39.3     0      1
chirp_2-10k_50ms@L           0   100    75     1     24.0     0.24    11.8    12.9     3.1    502  -23.8     0      1
chirp_2-6k_50ms@L          -10   100    67     0     24.8     0.21    31.5    31.7     2.8    433  -24.2     0      1
chirp_2-6k_50ms@L            0   100    75     2     25.6     0.58    32.7    36.4     2.9    311  -26.8     0      1
chirp_1.5-8k_50ms@L        -10   100    67     0     25.6     0.20    30.6    30.7     3.1    366  -25.0     0      1
chirp_3-8k_50ms@L            0   100    75     2     26.1     0.52    33.6    35.1     3.1    368  -27.1     0      1
chirp_3-8k_50ms@L          -10   100    67     0     26.1     0.28    36.2    37.1     3.1    586  -25.5     0      1
chirp_8-18k_50ms@L         -30   100     0     0                                               45  -52.8     0      1
```

## 2026-11-16 20:04 — P1: channel check + first sweep, analysis (by hand)

- Setup: array 30 cm; phone (iPhone, portrait locked, media volume max) speaker at (−32, 22.9, 46.5) cm, measured by the user.
  - Distance 60.9 cm, azimuth 144°, elevation 50° (the −x side, between the Mic1 and Mic4 quarters).
  - Temperature not measured, 21 °C assumed.
- Channel check (`chirp_2-10k_50ms`, 6×, left only then right only):
  - left: snr 652, level −23.1 dB, tdoa std 0.50 us, 0 extra
  - right: snr 435, level −25.3 dB, tdoa std 2.00 us, 3 extra detections
  - → **left = main (bottom) speaker**; right looks like the earpiece (quieter, less consistent).
  - Data: `host/bench_results/tests/run_20261116_200432_P1-chk.jsonl` (kept out of the main analysis).
- Sweep: `host/bench_results/run_20261116_200640_P1.jsonl` (full table in the automatic entry above).
  - Hardware OK: all 25 signals heard 13/13 at every volume down to −30 dB (snr 13–733). Matched-filter snr in the hundreds for chirps.
    The bad laptop test earlier in the day was the laptop speaker, not the rebuilt array.
  - Accuracy: tdoa rms 21–26 us for EVERY signal and volume → a fixed bias, not noise. Direction error ~3° everywhere.
  - Bias per pair (us, median over all signals): 1-2 +30.1, 1-3 +5.8, 1-4 −10.4, 2-3 −24.9, 2-4 −40.0, 3-4 −15.8.
  - It fits per-mic offsets almost perfectly: Mic2 −30.1, Mic3 −5.6, Mic4 +10.2 us vs Mic1, residual 0.24 us.
  - But it fits equally well (residual 0.3 us) a source at (−37.5, 30.0, 59.5) cm, i.e. 16 cm further out along the same direction.
    From one position the two can't be told apart → the 4 directions + calibrate decide. A 13 cm error in the measured height is unlikely, so per-mic offsets are the main suspect (as with the old array, now different values).
  - Speed of sound doesn't explain it (c 340/344/348 → 26.3/24.2/23.2 us).
  - Offsets are slightly frequency dependent: pair 2-3 bias −30 us for 0.5–8 kHz chirps vs −17 us for 5–16 kHz ones (analog phase response of the mic modules?).
- Precision (tdoa std, repeatability):
  - best: chirps with a high band, 50 ms — 4–12k 0.19–0.36, 3–12k 0.26–0.32, 5–14k 0.31–0.52, 6–16k 0.21–0.53 us;
  - worse: low bands (0.5–4k 0.66–1.28 us), 10 ms chirps (0.8–1.0 us), noise bursts (0.5–2.0 us, snr only 13–90);
  - 8–18k: detected, but mostly fails the quality checks (ok 0–33 %): the mics/speaker are weak up there.
- Volume: −30 dB still 100 % detected for every chirp except 8–18k; std grows ~1.5–2× from 0 to −30 dB. No clipping anywhere.
- Position error at P1 (before calibration) depends on the band: 2–6 cm for 5–16 kHz chirps, 25–35 cm for <8 kHz.
  Probably because the bias pattern differs with frequency (see above), not a real accuracy ranking yet — judge after calibration.

## 2026-11-16 20:16 — bench sweep P2 (left channel, array 30.0 cm)

- command (in `/home/nadasmartin/okos_lab_project/host`): `python bench.py sweep --label P2 --channel left --array 30 --pos 33.8 27.5 47.0 --note 'second of 4 directions; position measured by the user; same phone/channel/volume as P1'`
- duration: 161 s, finished
- notes: second of 4 directions; position measured by the user; same phone/channel/volume as P1

```
25 signals x 4 volumes (0, -10, -20, -30 dB) x 3 repetitions, every 0.25 s, speaker channel 'left': about 111 s
mic square 30 cm: Mic1 (-15.0,+15.0)  Mic2 (+15.0,+15.0)  Mic3 (+15.0,-15.0)  Mic4 (-15.0,-15.0)
ESP32: 44151 Hz/mic, mic delay calibration [0.0, 0.0, 0.0, 0.0] us (none), 21 C -> c = 344.0 m/s

Open on the phone (same Wi-Fi):  http://192.168.1.76:8765/
waiting for the phone to tap 'Start audio' ...
phone ready (192.168.1.97), loading 25 sounds ...

>>> PLAYING NOW. Measure the speaker position; don't block the path between the phone and the mics, and don't touch the phone. <<<

  1/25     4s chirp_4-12k_50ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
  2/25     9s noise_1.5-8k_50ms        heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
  3/25    13s chirp_2-10k_20ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
  4/25    17s noise_1-6k_50ms          heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
  5/25    21s chirp_1-10k_50ms         heard 12/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 2/3
  6/25    26s chirp_2-10k_35ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
  7/25    30s logchirp_1.5-8k_50ms     heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
  8/25    34s chirp_2-6k_50ms          heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
  9/25    39s chirp_6-16k_50ms         heard 11/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 1/3
 10/25    43s chirp_0.5-4k_50ms        heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 11/25    47s chirp_3-8k_50ms          heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
 12/25    52s chirp_1-5k_50ms          heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
 13/25    56s chirp_2-10k_50ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
 14/25    60s chirp_1-8k_50ms          heard 11/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 1/3
 15/25    65s noise_2-10k_50ms         heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 16/25    69s chirp_5-14k_50ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
 17/25    73s noise_4-12k_50ms         heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 18/25    78s chirp_1.5-8k_50ms        heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
 19/25    82s chirp_8-18k_50ms         heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 20/25    86s logchirp_2-12k_50ms      heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
 21/25    90s chirp_3-10k_50ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
 22/25    95s chirp_2-10k_10ms         heard 11/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 1/3
 23/25    99s logchirp_1-10k_50ms      heard 11/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 1/3
 24/25   103s chirp_3-12k_50ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3
 25/25   107s chirp_4-12k_20ms         heard 13/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 3/3

saved: /home/nadasmartin/okos_lab_project/host/bench_results/run_20261116_201657_P2.jsonl
true position (33.8, 27.5, 47.0) cm: distance 64.1 cm, azimuth 39.1 deg, elevation 47.2 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 405.6  Mic1 487.0  Mic4 809.2

RANKING over 100 trials, 1 position(s) (reliable first, i.e. ok% >= 90, then by tdoa rms)
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]        trials
chirp_0.5-4k_50ms@L        -10   100   100     0      8.3     0.74     1.5     2.2     1.7     85  -32.4     0      1
chirp_1-5k_50ms@L          -20   100   100     0      9.2     0.76     3.6     4.5     2.0     44  -41.1     0      1
chirp_0.5-4k_50ms@L          0   100   100     0      9.3     1.07     1.1     1.6     1.6    116  -30.4     0      1
chirp_2-6k_50ms@L          -30   100   100     0     10.0     1.40     5.0     6.1     1.1     20  -50.0     0      1
chirp_1-5k_50ms@L          -10   100   100     0     10.0     0.81     1.5     3.1     2.0    103  -33.1     0      1
chirp_0.5-4k_50ms@L        -20   100   100     0     10.2     2.00     1.6     5.2     1.7     27  -41.7     0      1
noise_1-6k_50ms@L          -10   100   100     0     10.4     1.66     1.6     1.6     1.2     16  -37.6     0      1
chirp_2-6k_50ms@L          -20   100   100     0     10.6     0.50     1.7     2.6     1.1     61  -41.1     0      1
chirp_1-5k_50ms@L            0   100   100     0     10.9     0.90     2.1     2.4     1.8    132  -30.9     0      1
noise_1-6k_50ms@L          -20   100   100     0     11.0     0.77     1.3     1.6     1.1     20  -44.7     0      1
noise_1-6k_50ms@L            0   100   100     0     11.5     0.76     2.9     3.7     1.0     13  -36.4     0      1
chirp_4-12k_50ms@L         -20   100   100     0     12.6     0.99     2.8     3.0     1.9     40  -47.1     0      1
chirp_2-6k_50ms@L            0   100   100     0     12.6     0.96     1.7     2.1     1.1    366  -27.8     0      1
chirp_2-6k_50ms@L          -10   100   100     0     12.8     0.55     2.2     2.2     1.2    200  -31.1     0      1
chirp_2-10k_10ms@L         -10   100   100     0     13.0     0.71     1.7     2.5     1.4     90  -36.8     0      1
noise_4-12k_50ms@L         -10   100   100     0     13.2     0.87     2.7     3.2     1.9     13  -44.2     0      1
chirp_3-12k_50ms@L         -30   100   100     0     13.3     1.18     1.7     2.3     1.8     16  -53.4     0      1
logchirp_2-12k_50ms@L      -30   100   100     0     13.3     1.46     2.7     3.4     1.5     17  -51.9     0      1
chirp_3-12k_50ms@L         -20   100   100     0     13.4     0.52     2.4     3.7     1.9     52  -45.4     0      1
logchirp_2-12k_50ms@L      -10   100   100     0     13.4     0.28     2.9     3.3     1.8    149  -33.3     0      1
chirp_4-12k_20ms@L         -10   100   100     0     13.4     0.70     3.7     4.1     2.0    112  -38.7     0      1
noise_4-12k_50ms@L         -20   100   100     0     13.5     0.94     3.1     4.6     1.8     32  -49.3     0      1
chirp_4-12k_50ms@L           0   100   100     0     13.6     0.29     3.5     3.8     2.0    300  -30.2     0      1
chirp_2-10k_35ms@L         -30   100   100     0     13.6     1.51     2.7     3.9     1.3     14  -51.5     0      1
chirp_2-10k_20ms@L         -30   100   100     0     13.6     1.84     2.4     4.6     1.4     15  -50.4     0      1
logchirp_2-12k_50ms@L        0   100   100     0     13.6     0.27     2.8     3.0     1.9    244  -30.1     0      1
chirp_4-12k_20ms@L           0   100   100     0     13.7     0.56     2.9     3.4     2.0    247  -31.2     0      1
chirp_3-12k_50ms@L           0   100   100     0     13.7     0.28     2.6     2.8     2.0    293  -31.5     0      1
chirp_3-12k_50ms@L         -10   100   100     0     13.7     0.27     2.7     2.9     2.0    161  -35.9     0      1
chirp_5-14k_50ms@L         -10   100   100     0     13.7     0.44     2.6     2.7     2.0    133  -39.5     0      1
chirp_5-14k_50ms@L         -20   100   100     0     13.7     0.60     3.1     3.7     2.0     42  -48.9     0      1
chirp_2-10k_50ms@L         -30   100   100     0     13.7     1.17     1.5     1.8     1.5     14  -51.4     0      1
logchirp_2-12k_50ms@L      -20   100   100     0     13.7     0.62     2.8     3.0     1.7     44  -43.5     0      1
chirp_6-16k_50ms@L         -20   100   100     0     13.8     1.57     2.5     4.1     2.2     37  -51.9     0      1
noise_4-12k_50ms@L           0   100   100     0     13.8     0.57     2.0     3.4     1.9     19  -38.9     0      1
chirp_4-12k_50ms@L         -10   100   100     0     13.8     0.55     3.5     3.8     2.0    112  -39.4     0      1
chirp_2-10k_10ms@L           0   100   100     0     14.0     1.40     2.5     3.0     1.5    178  -31.4     0      1
noise_2-10k_50ms@L         -20   100   100     0     14.0     1.51     1.9     3.0     1.5     20  -47.3     0      1
logchirp_1-10k_50ms@L      -10   100   100     0     14.1     0.86     3.0     3.1     1.5     86  -32.7     0      1
chirp_5-14k_50ms@L           0   100   100     0     14.1     0.44     2.4     2.7     2.0    282  -32.3     0      1
chirp_6-16k_50ms@L         -10   100   100     0     14.1     0.54     3.2     3.6     2.2    109  -42.9     0      1
chirp_2-10k_50ms@L         -20   100   100     0     14.2     0.64     2.1     2.1     1.6     44  -43.1     0      1
chirp_6-16k_50ms@L           0   100   100     0     14.2     0.28     2.2     2.4     2.2    269  -35.2     0      1
chirp_3-10k_50ms@L           0   100   100     0     14.3     0.52     2.9     3.5     1.7    292  -31.2     0      1
chirp_2-10k_20ms@L         -10   100   100     0     14.3     0.37     2.1     2.6     1.6    117  -34.8     0      1
chirp_2-10k_20ms@L           0   100   100     0     14.3     0.86     2.7     3.4     1.7    179  -31.4     0      1
chirp_3-10k_50ms@L         -30   100   100     0     14.3     2.16     2.5     4.3     1.4     17  -52.6     0      1
chirp_2-10k_35ms@L           0   100   100     0     14.3     0.44     2.4     2.8     1.7    212  -31.6     0      1
chirp_1-10k_50ms@L         -10   100   100     0     14.4     0.36     3.0     3.4     1.7    106  -33.0     0      1
chirp_4-12k_20ms@L         -20   100   100     0     14.4     0.65     3.6     5.0     1.9     35  -48.2     0      1
chirp_3-8k_50ms@L          -30   100   100     0     14.5     0.90     1.7     1.7     1.2     20  -51.3     0      1
chirp_2-10k_10ms@L         -20   100   100     0     14.5     3.19     3.7     4.0     1.5     30  -46.0     0      1
logchirp_1.5-8k_50ms@L     -30   100   100     0     14.5     1.38     5.3     5.3     1.3     16  -50.1     0      1
chirp_2-10k_50ms@L         -10   100   100     0     14.5     0.24     3.1     3.4     1.7    145  -33.2     0      1
chirp_2-10k_50ms@L           0   100   100     0     14.5     0.54     2.5     2.8     1.7    227  -31.1     0      1
logchirp_1-10k_50ms@L        0   100   100     0     14.6     0.35     2.7     3.1     1.6    108  -30.8     0      1
noise_2-10k_50ms@L           0   100   100     0     14.6     0.77     2.8     3.3     1.6     18  -38.1     0      1
chirp_2-10k_35ms@L         -20   100   100     0     14.6     0.49     2.3     2.3     1.6     46  -43.3     0      1
logchirp_1-10k_50ms@L      -20   100   100     0     14.6     0.48     1.7     2.3     1.5     31  -42.0     0      1
chirp_1-10k_50ms@L           0   100   100     0     14.6     0.32     2.7     2.9     1.7    148  -32.1     0      1
noise_2-10k_50ms@L         -10   100   100     0     14.6     1.09     1.9     2.4     1.7     13  -42.8     0      1
chirp_2-10k_35ms@L         -10   100   100     0     14.6     0.42     3.4     3.4     1.7    146  -33.7     0      1
chirp_3-10k_50ms@L         -20   100   100     0     14.6     0.52     3.2     3.2     1.7     55  -44.2     0      1
chirp_3-10k_50ms@L         -10   100   100     0     14.7     0.49     2.8     3.3     1.8    172  -34.7     0      1
chirp_1-10k_50ms@L         -20   100   100     0     14.7     0.22     3.1     3.3     1.7     33  -42.6     0      1
logchirp_1.5-8k_50ms@L     -10   100   100     0     14.8     0.50     2.7     2.7     1.3    137  -31.7     0      1
chirp_3-8k_50ms@L          -20   100   100     0     14.8     0.75     1.6     2.8     1.3     61  -42.6     0      1
chirp_2-10k_20ms@L         -20   100   100     0     14.8     0.76     2.6     2.6     1.5     46  -42.3     0      1
logchirp_1.5-8k_50ms@L     -20   100   100     0     14.8     1.29     3.7     4.1     1.2     45  -41.6     0      1
logchirp_1.5-8k_50ms@L       0   100   100     0     14.9     0.62     2.7     3.5     1.3    101  -32.0     0      1
chirp_1-8k_50ms@L          -20   100   100     0     15.0     1.21     1.6     1.7     1.2     33  -41.9     0      1
chirp_1-8k_50ms@L            0   100   100     0     15.0     0.37     1.8     2.0     1.3    135  -30.7     0      1
chirp_1.5-8k_50ms@L        -20   100   100     0     15.0     0.42     1.7     1.8     1.2     50  -41.6     0      1
chirp_1.5-8k_50ms@L          0   100   100     0     15.1     0.77     1.8     2.1     1.2    170  -31.1     0      1
chirp_1-8k_50ms@L          -10   100   100     0     15.1     0.64     2.4     2.4     1.3     91  -33.5     0      1
chirp_1.5-8k_50ms@L        -30   100   100     0     15.2     1.11     1.6     3.8     1.3     18  -50.1     0      1
chirp_3-8k_50ms@L          -10   100   100     0     15.2     0.40     1.7     1.9     1.4    198  -33.0     0      1
chirp_1.5-8k_50ms@L        -10   100   100     0     15.2     0.73     1.6     2.8     1.3    148  -31.9     0      1
noise_1.5-8k_50ms@L        -10   100   100     0     15.3     0.41     2.7     2.9     1.3     15  -41.5     0      1
chirp_3-8k_50ms@L            0   100   100     0     15.3     0.48     1.8     2.5     1.3    310  -30.4     0      1
noise_1.5-8k_50ms@L          0   100   100     0     15.4     0.70     2.2     3.5     1.3     24  -37.2     0      1
noise_1.5-8k_50ms@L        -20   100   100     0     15.4     1.06     4.3     5.0     1.3     21  -46.6     0      1
chirp_1-5k_50ms@L          -30   100    67     0      8.2     0.67     6.1     7.2     1.9     13  -49.0     0      1
chirp_8-18k_50ms@L         -10   100    33     0     13.5     0.00     3.9     3.9     2.2     53  -48.1     0      1
chirp_4-12k_50ms@L         -30   100    33     0     14.0     0.00     6.0     6.0     1.7     14  -54.6     0      1
chirp_8-18k_50ms@L           0   100    75     0     14.2     0.65     2.3     2.6     2.2    123  -41.3     0      1
chirp_5-14k_50ms@L         -30   100    67     0     14.4     0.80     4.4     4.6     1.8     15  -55.6     0      1
logchirp_1-10k_50ms@L      -30    33    33     0     14.7     0.00     2.5     2.5     1.5     13  -48.5     0      1
chirp_1-8k_50ms@L          -30    33    33     0     15.0     0.00     2.3     2.3     1.1     13  -50.1     0      1
chirp_1-10k_50ms@L         -30    67    67     0     15.1     0.67     3.0     3.9     1.4     14  -49.6     0      1
chirp_4-12k_20ms@L         -30   100    33     0     15.2     0.00     8.9     8.9     1.7     13  -54.8     0      1
noise_1.5-8k_50ms@L        -30     0     0     0                                                             0      1
noise_1-6k_50ms@L          -30     0     0     0                                                             0      1
chirp_6-16k_50ms@L         -30    33     0     0                                               13  -57.3     0      1
chirp_0.5-4k_50ms@L        -30     0     0     0                                                             0      1
noise_2-10k_50ms@L         -30     0     0     0                                                             0      1
noise_4-12k_50ms@L         -30     0     0     0                                                             0      1
chirp_8-18k_50ms@L         -20   100     0     0                                               18  -55.6     0      1
chirp_8-18k_50ms@L         -30     0     0     0                                                             0      1
chirp_2-10k_10ms@L         -30    33     0     0                                               13  -52.0     0      1
```

## 2026-11-16 20:16 — P2 sweep + analysis of P1 and P2 together (by hand)

- Setup: same as P1 (array 30 cm, left channel = main speaker, portrait, max volume, 21 °C assumed). Phone speaker at (33.8, 27.5, 47.0) cm.
  - Distance 64.1 cm, azimuth 39°, elevation 47° (between the Mic2 and Mic3 quarters, roughly opposite P1).
- Data: `host/bench_results/run_20261116_201657_P2.jsonl`; full table in the automatic entry above. Code: `docs/code_snapshots/2026-11-16_P1-P2/`.
- Detection: 100 % at 0 / −10 / −20 dB for all 25 signals.
  - At −30 dB some sounds were missed: noise bursts, 0.5–4k, 8–18k, and partly 6–16k, 1–8k, 1–10k, 2–10k 10 ms, logchirp 1–10k.
  - Received level about 7 dB lower than at P1 (0 dB: −27 to −31 dB vs −23 to −26 dB).
- Accuracy at P2 is much better than at P1: tdoa rms 8–14 us, position error 1–5 cm (P1: 21–26 us, 2–35 cm).
  - The ranking turned around: at P2 the LOW bands are best (0.5–4k, 1–5k, 2–6k: 1–2 cm, 8–11 us).
  - At P1 the HIGH bands were best (5–14k, 6–16k: 4–6 cm).
- Position fitted to the median delays of the ≥2 kHz 50 ms chirps:
  - P1: (−34.4, 27.4, 54.1) vs measured (−32, 22.9, 46.5) → 9 cm off, range +14 %, direction 2.2°.
  - P2: (33.6, 25.7, 45.2) vs measured (33.8, 27.5, 47.0) → 2.5 cm off, range −3.4 %, direction 1.2°.
- Explanations tested with both positions together (rms timing error after the fit, ≥2 kHz 50 ms chirps):
  - none 19.1 us
  - speed of sound 18.8 us
  - array size 18.8 us (fit 29.8 cm)
  - fixed per-mic delays 12.4 us
  - array size + delays 11.2 us
  - range scale per position 18.6 us
  - a common offset of the source point 7.9 us (fit 1.9, 0.5, 0.8 cm)
  - → no single simple cause yet.
- **CORRECTION to the P1 entry:** "the bias fits per-mic offsets almost perfectly (residual 0.24 us)" proves nothing.
  - Pair delays come from per-mic arrival times, so a per-mic fit at ONE position always succeeds.
  - Fitted separately, the offsets at P1 (Mic2 −30, Mic3 −6, Mic4 +10 us) and at P2 (Mic2 −14, Mic3 −24, Mic4 −12 us) disagree by 15–27 us.
  - → a fixed per-mic electronic delay is NOT the main cause on the new array.
- Current hypotheses:
  - (a) the P1 position measurement is off (mostly height/y);
  - (b) direction-dependent acoustics: mic mounts, capsule directivity, reflections from the table/mounts, phone speaker radiation. This fits the band ranking flipping between positions.
  - P3/P4 will tell.
- Precision (tdoa std) at P2: 0.3–2 us, larger than at P1 because the received level is lower.

## 2026-11-16 ~20:20 — Reproducibility added (by hand)

- New `docs/reproduce.md`: hardware, setup, all parameters, the sweep protocol, metric definitions, a table of every experiment with its command/data/code, and the dated history of code and parameter changes.
- Code copies in `docs/code_snapshots/`:
  - `2026-11-16_P1-P2/` = exact code of P1/P2 (made by hand; the firmware binary was built from these sources at 19:28);
  - from now on automatic per code version (`<date>_<fingerprint>/`).
- Every logged command now writes `code: <fingerprint>` into this log; run files store `code`, `fw`, `snapshot`, `fw_on_esp32`, `argv`, and for sweeps the full signal definitions and settings.
- Firmware: build fingerprint of the sources (`firmware/fw_version.py`), reported as `"fw"` in the status line; bench.py prints whether it matches the sources on disk.
  - Flashed: `cc8e9c945759`; verified on the board; array setting still 30 cm. No change in processing.

## 2026-11-16 — Setup changes reported by the user (by hand)

- iPhone media volume (by hand, exact steps not recorded):
  - P1: maximum. The user heard a lot of echo in the room.
  - P2: lowered by hand → "much better", less echo.
    The ~7 dB lower received level at P2 is (at least partly) this, not only the position.
    **Correction to `docs/reproduce.md` §1: the media volume was NOT kept at max for P2.**
  - P3: lowered further.
- P3: phone tilted so its speaker faces the mic array directly (P1, P2: not tilted).
- The user confirms the P1 height (46.5 cm) was measured correctly → hypothesis (a) "P1 position wrong in z" is unlikely;
  the P1 discrepancy (fit (−34.4, 27.4, 54.1)) needs another explanation.
- Plan: finish all 4 positions, then look for the reasons.

## 2026-11-16 20:34 — bench sweep P3 (left channel, array 30.0 cm)

- command (in `/home/nadasmartin/okos_lab_project/host`): `python bench.py sweep --label P3 --channel left --array 30 --pos 27.5 -32.3 42.0 --note 'third of 4 directions; iPhone media volume lowered further by hand (P1 = max, P2 = lowered, P3 = lower still; exact steps unknown); phone tilted so the speaker faces the array'`
- duration: 114 s, finished
- code: `0ec10024c594` (copy: `docs/code_snapshots/2026-11-16_2018_0ec10024c594/`)
- notes: third of 4 directions; iPhone media volume lowered further by hand (P1 = max, P2 = lowered, P3 = lower still; exact steps unknown); phone tilted so the speaker faces the array

```
25 signals x 4 volumes (0, -10, -20, -30 dB) x 3 repetitions, every 0.25 s, speaker channel 'left': about 111 s
mic square 30 cm: Mic1 (-15.0,+15.0)  Mic2 (+15.0,+15.0)  Mic3 (+15.0,-15.0)  Mic4 (-15.0,-15.0)
ESP32 firmware cc8e9c945759 = the firmware sources on disk
ESP32: 44024 Hz/mic, mic delay calibration [0.0, 0.0, 0.0, 0.0] us (none), 21 C -> c = 344.0 m/s

Open on the phone (same Wi-Fi):  http://192.168.1.76:8765/
waiting for the phone to tap 'Start audio' ...
phone ready (192.168.1.97), loading 25 sounds ...

>>> PLAYING NOW. Measure the speaker position; don't block the path between the phone and the mics, and don't touch the phone. <<<

  1/25     4s chirp_1-8k_50ms          heard  4/13   0dB 3/4  -10dB 1/3  -20dB 0/3  -30dB 0/3
  2/25     9s chirp_3-8k_50ms          heard  9/13   0dB 4/4  -10dB 3/3  -20dB 2/3  -30dB 0/3
  3/25    13s chirp_5-14k_50ms         heard  7/13   0dB 4/4  -10dB 3/3  -20dB 0/3  -30dB 0/3
  4/25    17s chirp_0.5-4k_50ms        heard  7/13   0dB 4/4  -10dB 3/3  -20dB 0/3  -30dB 0/3
  5/25    22s logchirp_1.5-8k_50ms     heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
  6/25    26s chirp_8-18k_50ms         heard  7/13   0dB 4/4  -10dB 3/3  -20dB 0/3  -30dB 0/3
  7/25    30s chirp_6-16k_50ms         heard  7/13   0dB 4/4  -10dB 3/3  -20dB 0/3  -30dB 0/3
  8/25    35s noise_4-12k_50ms         heard  7/13   0dB 4/4  -10dB 3/3  -20dB 0/3  -30dB 0/3
  9/25    39s chirp_2-10k_10ms         heard  7/13   0dB 4/4  -10dB 3/3  -20dB 0/3  -30dB 0/3
 10/25    43s chirp_2-10k_50ms         heard  8/13   0dB 4/4  -10dB 3/3  -20dB 1/3  -30dB 0/3
 11/25    48s chirp_2-6k_50ms          heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 12/25    52s noise_1.5-8k_50ms        heard  7/13   0dB 4/4  -10dB 3/3  -20dB 0/3  -30dB 0/3
 13/25    56s chirp_2-10k_35ms         heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 14/25    61s logchirp_1-10k_50ms      heard  7/13   0dB 4/4  -10dB 3/3  -20dB 0/3  -30dB 0/3
 15/25    65s logchirp_2-12k_50ms      heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 16/25    69s noise_1-6k_50ms          heard  7/13   0dB 4/4  -10dB 3/3  -20dB 0/3  -30dB 0/3
 17/25    74s chirp_1.5-8k_50ms        heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 18/25    78s chirp_3-12k_50ms         heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 19/25    83s chirp_3-10k_50ms         heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 20/25    87s chirp_4-12k_20ms         heard  7/13   0dB 4/4  -10dB 3/3  -20dB 0/3  -30dB 0/3
 21/25    91s noise_2-10k_50ms         heard  7/13   0dB 4/4  -10dB 3/3  -20dB 0/3  -30dB 0/3
 22/25    96s chirp_4-12k_50ms         heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 23/25   100s chirp_2-10k_20ms         heard  8/13   0dB 4/4  -10dB 3/3  -20dB 1/3  -30dB 0/3
 24/25   104s chirp_1-5k_50ms          heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 25/25   109s chirp_1-10k_50ms         heard  8/13   0dB 4/4  -10dB 3/3  -20dB 1/3  -30dB 0/3

saved: /home/nadasmartin/okos_lab_project/host/bench_results/run_20261116_203451_P3.jsonl
true position (27.5, -32.3, 42.0) cm: distance 59.7 cm, azimuth 310.4 deg, elevation 44.7 deg
expected arrival after first mic [us]: Mic3 0.0  Mic4 438.7  Mic2 504.8  Mic1 845.7

RANKING over 100 trials, 1 position(s) (reliable first, i.e. ok% >= 90, then by tdoa rms)
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]        trials
chirp_2-10k_10ms@L         -10   100   100     0     13.5     1.66     7.5     9.2     1.6     35  -45.6     0      1
chirp_2-6k_50ms@L          -20   100   100     0     14.0     0.63    14.6    15.9     1.1     20  -51.6     0      1
chirp_2-6k_50ms@L            0   100   100     0     14.2     0.93    12.1    13.2     1.1    148  -36.7     0      1
noise_1-6k_50ms@L            0   100   100     0     14.2     0.79    10.1    10.7     1.4     39  -40.9     0      1
chirp_3-8k_50ms@L          -10   100   100     0     14.3     1.07     8.1     9.3     1.6     46  -46.9     0      1
chirp_2-6k_50ms@L          -10   100   100     0     14.3     0.83    11.9    12.7     1.1     62  -43.1     0      1
chirp_1.5-8k_50ms@L          0   100   100     0     14.5     0.69     8.8     9.2     1.6     97  -37.5     0      1
logchirp_1-10k_50ms@L      -10   100   100     0     14.6     1.23    10.8    11.7     1.7     28  -44.2     0      1
chirp_1.5-8k_50ms@L        -10   100   100     0     14.7     0.62     9.9    10.9     1.5     42  -43.5     0      1
logchirp_1.5-8k_50ms@L     -10   100   100     0     14.8     1.03     8.7     9.9     1.4     44  -43.6     0      1
chirp_3-8k_50ms@L            0   100   100     0     15.0     0.51     9.4    10.1     1.5    130  -37.7     0      1
chirp_1.5-8k_50ms@L        -20   100   100     0     15.2     1.10    10.4    11.0     1.3     14  -51.5     0      1
logchirp_1.5-8k_50ms@L       0   100   100     0     15.2     1.07     8.6     9.0     1.5    105  -37.5     0      1
chirp_2-10k_35ms@L         -20   100   100     0     15.5     1.40    17.8    18.3     1.5     12  -52.0     0      1
chirp_0.5-4k_50ms@L        -10   100   100     0     15.6     2.76    26.0    26.1     2.3     24  -44.3     0      1
noise_1.5-8k_50ms@L          0   100   100     0     15.7     0.68    10.1    10.7     1.6     14  -42.4     0      1
chirp_2-10k_10ms@L           0   100   100     0     15.8     1.30    11.3    12.0     1.7     65  -40.3     0      1
chirp_2-10k_20ms@L         -10   100   100     0     15.8     1.50     7.3    11.8     1.8     28  -45.1     0      1
noise_1.5-8k_50ms@L        -10   100   100     0     15.9     1.26    12.4    15.0     1.5     20  -48.9     0      1
logchirp_1-10k_50ms@L        0   100   100     0     16.0     0.92    11.2    11.4     1.9     46  -39.8     0      1
chirp_2-10k_35ms@L         -10   100   100     0     16.1     1.14    13.0    13.9     1.9     36  -44.2     0      1
chirp_5-14k_50ms@L         -10   100   100     0     16.2     1.06     1.9     2.5     2.3     32  -51.8     0      1
noise_2-10k_50ms@L           0   100   100     0     16.2     0.74     9.0    10.1     2.0     13  -43.5     0      1
chirp_1-10k_50ms@L         -10   100   100     0     16.3     1.34     9.6    12.1     1.9     29  -44.9     0      1
chirp_3-12k_50ms@L         -10   100   100     0     16.3     0.62     1.8     2.5     2.2     48  -46.7     0      1
chirp_0.5-4k_50ms@L          0   100   100     0     16.3     1.63    26.2    28.6     2.2     47  -39.6     0      1
noise_2-10k_50ms@L         -10   100   100     0     16.3     2.32    10.6    17.3     1.7     20  -48.3     0      1
chirp_1-10k_50ms@L           0   100   100     0     16.3     0.36    11.0    11.4     2.0     76  -38.3     0      1
logchirp_2-12k_50ms@L      -10   100   100     0     16.3     0.82     6.1     7.1     2.0     36  -45.3     0      1
chirp_1-5k_50ms@L            0   100   100     0     16.4     1.14    25.7    28.2     1.3     72  -39.1     0      1
logchirp_2-12k_50ms@L        0   100   100     0     16.4     0.70     5.3     6.4     2.1     78  -39.0     0      1
chirp_2-10k_20ms@L           0   100   100     0     16.4     2.08    12.6    15.0     2.0     68  -38.5     0      1
chirp_4-12k_50ms@L         -10   100   100     0     16.5     0.64     1.5     1.7     2.2     51  -47.6     0      1
chirp_1-5k_50ms@L          -10   100   100     0     16.5     1.08    24.2    26.2     1.4     46  -42.6     0      1
chirp_4-12k_50ms@L           0   100   100     0     16.6     0.44     1.5     1.6     2.3    115  -40.0     0      1
noise_4-12k_50ms@L           0   100   100     0     16.7     1.09     1.8     2.1     2.2     13  -45.3     0      1
chirp_3-12k_50ms@L           0   100   100     0     16.8     0.45     2.6     2.8     2.3     98  -39.3     0      1
chirp_2-10k_35ms@L           0   100   100     0     16.8     0.72    11.3    12.9     2.0     72  -37.9     0      1
chirp_3-10k_50ms@L         -10   100   100     0     16.9     0.67    12.2    13.0     1.9     44  -45.7     0      1
chirp_2-10k_50ms@L           0   100   100     0     16.9     1.13    10.1    11.8     2.1     82  -38.0     0      1
chirp_4-12k_20ms@L           0   100   100     0     17.0     0.87     1.9     2.1     2.3     56  -43.2     0      1
chirp_4-12k_20ms@L         -10   100   100     0     17.1     0.65     2.3     3.4     2.2     24  -50.2     0      1
chirp_5-14k_50ms@L           0   100   100     0     17.1     0.67     1.9     2.0     2.4     80  -44.8     0      1
chirp_3-10k_50ms@L           0   100   100     0     17.2     0.56     9.8    10.8     2.2    101  -38.6     0      1
chirp_6-16k_50ms@L         -10   100   100     0     17.2     0.72     2.3     2.4     2.4     22  -53.8     0      1
chirp_1-5k_50ms@L          -20   100    33     0     12.9     0.00    11.5    11.5     1.1     14  -50.5     0      1
noise_1-6k_50ms@L          -10   100    67     0     13.6     1.13    11.0    12.7     1.2     16  -47.5     0      1
chirp_3-10k_50ms@L         -20   100    67     0     14.0     2.22     8.8     9.8     1.6     14  -53.2     0      1
chirp_1-8k_50ms@L          -10    33    33     0     14.2     0.00    12.2    12.2     1.5     40  -43.1     0      1
chirp_1-8k_50ms@L            0    75    75     0     14.6     1.02     8.8     9.7     1.6    141  -32.2     0      1
chirp_3-8k_50ms@L          -20    67    67     0     14.9     1.60     5.1     5.6     1.6     20  -53.7     0      1
chirp_2-10k_50ms@L         -20    33    33     0     15.7     0.00    11.8    11.8     1.7     19  -50.4     0      1
noise_4-12k_50ms@L         -10   100    67     0     16.5     0.81     1.5     1.5     2.0     30  -50.6     0      1
logchirp_1.5-8k_50ms@L     -20   100    67     0     16.5     1.99    10.9    14.1     1.3     16  -51.5     0      1
chirp_2-10k_50ms@L         -10   100    67     0     17.0     0.63    10.8    11.7     2.0     36  -41.9     0      1
chirp_2-10k_20ms@L         -20    33    33     0     17.2     0.00    14.9    14.9     1.3     12  -51.8     0      1
chirp_6-16k_50ms@L           0   100    50     0     17.7     0.97     2.0     2.2     2.4     55  -47.2     0      1
chirp_1-8k_50ms@L          -20     0     0     0                                                             0      1
chirp_1-8k_50ms@L          -30     0     0     0                                                             0      1
chirp_3-8k_50ms@L          -30     0     0     0                                                             0      1
chirp_5-14k_50ms@L         -20     0     0     0                                                             0      1
chirp_5-14k_50ms@L         -30     0     0     0                                                             0      1
chirp_0.5-4k_50ms@L        -20     0     0     0                                                             0      1
chirp_0.5-4k_50ms@L        -30     0     0     0                                                             0      1
logchirp_1.5-8k_50ms@L     -30     0     0     0                                                             0      1
chirp_8-18k_50ms@L           0   100     0     0                                               37  -51.8     0      1
chirp_8-18k_50ms@L         -10   100     0     0                                               16  -56.3     0      1
chirp_8-18k_50ms@L         -20     0     0     0                                                             0      1
chirp_8-18k_50ms@L         -30     0     0     0                                                             0      1
chirp_6-16k_50ms@L         -20     0     0     0                                                             0      1
chirp_6-16k_50ms@L         -30     0     0     0                                                             0      1
noise_4-12k_50ms@L         -20     0     0     0                                                             0      1
noise_4-12k_50ms@L         -30     0     0     0                                                             0      1
chirp_2-10k_10ms@L         -20     0     0     0                                                             0      1
chirp_2-10k_10ms@L         -30     0     0     0                                                             0      1
chirp_2-10k_50ms@L         -30     0     0     0                                                             0      1
chirp_2-6k_50ms@L          -30     0     0     0                                                             0      1
noise_1.5-8k_50ms@L        -20     0     0     0                                                             0      1
noise_1.5-8k_50ms@L        -30     0     0     0                                                             0      1
chirp_2-10k_35ms@L         -30     0     0     0                                                             0      1
logchirp_1-10k_50ms@L      -20     0     0     0                                                             0      1
logchirp_1-10k_50ms@L      -30     0     0     0                                                             0      1
logchirp_2-12k_50ms@L      -20   100     0     0                                               12  -52.8     0      1
logchirp_2-12k_50ms@L      -30     0     0     0                                                             0      1
noise_1-6k_50ms@L          -20     0     0     0                                                             0      1
noise_1-6k_50ms@L          -30     0     0     0                                                             0      1
chirp_1.5-8k_50ms@L        -30     0     0     0                                                             0      1
chirp_3-12k_50ms@L         -20   100     0     0                                               14  -54.2     0      1
chirp_3-12k_50ms@L         -30     0     0     0                                                             0      1
chirp_3-10k_50ms@L         -30     0     0     0                                                             0      1
chirp_4-12k_20ms@L         -20     0     0     0                                                             0      1
chirp_4-12k_20ms@L         -30     0     0     0                                                             0      1
noise_2-10k_50ms@L         -20     0     0     0                                                             0      1
noise_2-10k_50ms@L         -30     0     0     0                                                             0      1
chirp_4-12k_50ms@L         -20   100     0     0                                               16  -54.0     0      1
chirp_4-12k_50ms@L         -30     0     0     0                                                             0      1
chirp_2-10k_20ms@L         -30     0     0     0                                                             0      1
chirp_1-5k_50ms@L          -30     0     0     0                                                             0      1
chirp_1-10k_50ms@L         -20    33     0     0                                               12  -51.6     0      1
chirp_1-10k_50ms@L         -30     0     0     0                                                             0      1
```

## 2026-11-16 20:34 — P3 sweep (by hand)

- Setup: array 30 cm, left channel, phone tilted towards the array, media volume lowered further (see the setup-change entry).
  Phone speaker at (27.5, −32.3, 42.0) cm: distance 59.7 cm, azimuth 310°, elevation 45°. Firmware `cc8e9c945759` (= the sources).
- Data: `host/bench_results/run_20261116_203451_P3.jsonl`; full table in the automatic entry above.
- Received level at 0 dB: median −39 dB (P1 −25.5, P2 −31.4) → the lower phone volume costs ~14 dB vs. P1.
  - 0 dB 100 % and −10 dB ~100 % detected (chirp 1–8k: only 3/4 and 1/3);
  - −20 dB only for some 50 ms chirps (2–6k, 3–10k, 3–12k, 4–12k, 1.5–8k, 1–5k, logchirps);
  - −30 dB: nothing.
  - → the volume results of P3 are NOT comparable with P1/P2 (different absolute level).
- Accuracy: tdoa rms 13.5–17 us, direction 1.1–1.7°, position error 7.5–15 cm.
- Position fitted to the median delays of the ≥2 kHz 50 ms chirps:

  | Position | Fit (cm) | Measured (cm) | Off by | Range | Direction |
  |---|---|---|---|---|---|
  | P3 | (29.1, −36.4, 46.3) | (27.5, −32.3, 42.0) | 6.2 cm | +10 % | 1.3° |
  | P1 | (−34.4, 27.4, 54.1) | (−32, 22.9, 46.5) | 9.1 cm | +14 % | 2.2° |
  | P2 | (33.6, 25.7, 45.2) | (33.8, 27.5, 47.0) | 2.5 cm | −3 % | 1.2° |

  - Pattern so far: direction always within ~1–2°; the error is mostly in RANGE (distance), +14 / −3 / +10 %.
- Best at P3 by tdoa rms: low/mid bands 50 ms (2–6k, 1.5–8k, 3–8k chirps, noise 1–6k) and 2–10k 10 ms at −10 dB; 14–15 us.

## 2026-11-16 20:41 — bench sweep P4 (left channel, array 30.0 cm)

- command (in `/home/nadasmartin/okos_lab_project/host`): `python bench.py sweep --label P4 --channel left --array 30 --pos -28.3 -31.3 42.0 --note 'fourth of 4 directions; same setup as P3 (lowered media volume, phone tilted towards the array)'`
- duration: 123 s, finished
- code: `0ec10024c594` (copy: `docs/code_snapshots/2026-11-16_2018_0ec10024c594/`)
- notes: fourth of 4 directions; same setup as P3 (lowered media volume, phone tilted towards the array)

```
25 signals x 4 volumes (0, -10, -20, -30 dB) x 3 repetitions, every 0.25 s, speaker channel 'left': about 111 s
mic square 30 cm: Mic1 (-15.0,+15.0)  Mic2 (+15.0,+15.0)  Mic3 (+15.0,-15.0)  Mic4 (-15.0,-15.0)
ESP32 firmware cc8e9c945759 = the firmware sources on disk
ESP32: 44104 Hz/mic, mic delay calibration [0.0, 0.0, 0.0, 0.0] us (none), 21 C -> c = 344.0 m/s

Open on the phone (same Wi-Fi):  http://192.168.1.76:8765/
waiting for the phone to tap 'Start audio' ...
phone ready (192.168.1.97), loading 25 sounds ...

>>> PLAYING NOW. Measure the speaker position; don't block the path between the phone and the mics, and don't touch the phone. <<<

  1/25     4s noise_4-12k_50ms         heard  9/13   0dB 4/4  -10dB 3/3  -20dB 2/3  -30dB 0/3
  2/25     8s chirp_2-10k_10ms         heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
  3/25    13s chirp_1.5-8k_50ms        heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
  4/25    17s chirp_1-10k_50ms         heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
  5/25    21s chirp_2-10k_50ms         heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
  6/25    26s noise_1.5-8k_50ms        heard  7/13   0dB 4/4  -10dB 3/3  -20dB 0/3  -30dB 0/3
  7/25    30s chirp_8-18k_50ms         heard  7/13   0dB 4/4  -10dB 3/3  -20dB 0/3  -30dB 0/3
  8/25    34s chirp_4-12k_20ms         heard  8/13   0dB 4/4  -10dB 3/3  -20dB 1/3  -30dB 0/3
  9/25    39s chirp_5-14k_50ms         heard  9/13   0dB 4/4  -10dB 3/3  -20dB 2/3  -30dB 0/3
 10/25    43s chirp_6-16k_50ms         heard  7/13   0dB 4/4  -10dB 3/3  -20dB 0/3  -30dB 0/3
 11/25    47s chirp_2-10k_35ms         heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 12/25    52s chirp_1-8k_50ms          heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 13/25    56s chirp_4-12k_50ms         heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 14/25    60s chirp_2-6k_50ms          heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 15/25    65s noise_1-6k_50ms          heard  7/13   0dB 4/4  -10dB 3/3  -20dB 0/3  -30dB 0/3
 16/25    69s chirp_0.5-4k_50ms        heard  8/13   0dB 4/4  -10dB 3/3  -20dB 1/3  -30dB 0/3
 17/25    73s chirp_3-12k_50ms         heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 18/25    78s chirp_1-5k_50ms          heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 19/25    82s chirp_3-10k_50ms         heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 20/25    86s chirp_2-10k_20ms         heard  8/13   0dB 4/4  -10dB 3/3  -20dB 1/3  -30dB 0/3
 21/25    91s noise_2-10k_50ms         heard  7/13   0dB 1/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 22/25    95s logchirp_1-10k_50ms      heard  8/13   0dB 4/4  -10dB 3/3  -20dB 1/3  -30dB 0/3
 23/25    99s logchirp_1.5-8k_50ms     heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 24/25   104s chirp_3-8k_50ms          heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3
 25/25   108s logchirp_2-12k_50ms      heard 10/13   0dB 4/4  -10dB 3/3  -20dB 3/3  -30dB 0/3

saved: /home/nadasmartin/okos_lab_project/host/bench_results/run_20261116_204112_P4.jsonl
true position (-28.3, -31.3, 42.0) cm: distance 59.5 cm, azimuth 227.9 deg, elevation 44.9 deg
expected arrival after first mic [us]: Mic4 0.0  Mic3 450.9  Mic1 492.3  Mic2 845.0

RANKING over 100 trials, 1 position(s) (reliable first, i.e. ok% >= 90, then by tdoa rms)
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]        trials
noise_4-12k_50ms@L           0   100   100     0     17.8     1.35     4.2     6.5     2.2     13  -46.7     0      1
noise_1.5-8k_50ms@L          0   100   100     0     17.9     0.63     3.9     5.0     2.0     13  -44.1     0      1
logchirp_2-12k_50ms@L      -10   100   100     0     18.0     1.21     5.0     5.1     2.2     53  -44.9     0      1
chirp_4-12k_20ms@L         -10   100   100     0     18.1     1.52     3.0     3.2     2.3     35  -49.3     0      1
chirp_3-8k_50ms@L          -10   100   100     0     18.2     0.48     3.4     3.9     2.0     76  -44.0     0      1
chirp_3-10k_50ms@L         -10   100   100     0     18.2     1.00     1.9     2.0     2.2     63  -45.3     0      1
chirp_3-12k_50ms@L         -10   100   100     0     18.3     1.00     4.7     5.2     2.3     66  -46.3     0      1
chirp_3-8k_50ms@L            0   100   100     0     18.3     0.57     4.6     5.0     2.1    182  -37.3     0      1
chirp_2-10k_10ms@L         -10   100   100     0     18.4     1.72     2.0     2.4     2.2     42  -44.6     0      1
chirp_1.5-8k_50ms@L          0   100   100     0     18.4     0.69     4.5     5.0     2.0    112  -37.0     0      1
chirp_2-10k_10ms@L           0   100   100     0     18.5     2.16     2.2     3.3     2.1     75  -39.7     0      1
chirp_1.5-8k_50ms@L        -10   100   100     0     18.5     1.02     5.2     6.2     2.0     49  -43.2     0      1
chirp_1-10k_50ms@L         -10   100   100     0     18.5     1.26     1.8     2.0     2.0     37  -44.6     0      1
chirp_2-10k_35ms@L         -10   100   100     0     18.6     1.65     2.5     3.5     2.2     53  -44.7     0      1
chirp_4-12k_50ms@L           0   100   100     0     18.6     0.62     3.8     4.8     2.4    132  -40.0     0      1
logchirp_2-12k_50ms@L        0   100   100     0     18.6     0.76     2.8     3.1     2.3    105  -38.6     0      1
chirp_2-10k_20ms@L         -10   100   100     0     18.6     1.71     3.3     3.7     2.2     41  -45.1     0      1
chirp_2-10k_35ms@L           0   100   100     0     18.6     1.01     2.2     2.6     2.2    115  -37.6     0      1
logchirp_1-10k_50ms@L        0   100   100     0     18.7     0.86     1.8     2.3     2.1     56  -39.0     0      1
logchirp_1.5-8k_50ms@L       0   100   100     0     18.7     0.62     6.4     6.8     2.0    111  -37.2     0      1
chirp_3-12k_50ms@L           0   100   100     0     18.7     0.43     4.2     4.5     2.4    152  -39.0     0      1
chirp_1-5k_50ms@L          -10   100   100     0     18.8     1.13     1.7     3.0     2.0     50  -42.7     0      1
chirp_2-6k_50ms@L          -10   100   100     0     18.8     0.81     7.4     7.6     1.8     80  -42.7     0      1
chirp_3-8k_50ms@L          -20   100   100     0     18.9     2.35     5.9     8.4     2.0     25  -52.4     0      1
chirp_4-12k_20ms@L           0   100   100     0     19.0     1.19     2.6     3.5     2.3     78  -42.2     0      1
chirp_2-6k_50ms@L          -20   100   100     0     19.0     1.94     7.8    11.8     1.8     24  -51.6     0      1
noise_2-10k_50ms@L         -10   100   100     0     19.1     1.02     2.1     2.8     2.3     13  -44.9     0      1
chirp_2-10k_50ms@L         -10   100   100     0     19.1     1.13     1.8     2.1     2.2     46  -44.7     0      1
chirp_4-12k_50ms@L         -10   100   100     0     19.2     0.61     4.5     4.9     2.4     55  -47.3     0      1
chirp_2-10k_50ms@L           0   100   100     0     19.2     0.72     1.9     2.1     2.3    101  -37.6     0      1
chirp_1-8k_50ms@L            0   100   100     0     19.2     0.42     4.7     4.9     2.0     89  -37.3     0      1
noise_1-6k_50ms@L            0   100   100     0     19.2     1.06     7.5     8.7     1.8     14  -41.1     0      1
chirp_2-6k_50ms@L            0   100   100     0     19.2     0.71     8.9     9.1     1.9    170  -36.4     0      1
logchirp_1.5-8k_50ms@L     -10   100   100     0     19.3     0.92     6.2     7.0     2.0     52  -43.4     0      1
chirp_5-14k_50ms@L           0   100   100     0     19.3     0.64     5.1     5.8     2.5     99  -43.5     0      1
chirp_1-10k_50ms@L           0   100   100     0     19.4     0.87     1.8     1.9     2.2     86  -38.0     0      1
chirp_1-8k_50ms@L          -10   100   100     0     19.4     1.13     5.4     5.6     2.0     43  -43.3     0      1
chirp_3-10k_50ms@L           0   100   100     0     19.6     0.70     2.8     3.3     2.3    152  -38.3     0      1
chirp_5-14k_50ms@L         -10   100   100     0     19.6     1.12     5.7     6.0     2.5     40  -50.2     0      1
noise_2-10k_50ms@L         -20   100   100     0     19.6     2.43     3.2     3.3     2.1     27  -47.9     0      1
chirp_2-10k_20ms@L           0   100   100     0     19.7     1.54     2.1     2.6     2.2    102  -38.1     0      1
chirp_0.5-4k_50ms@L        -10   100   100     0     19.7     2.12     3.3     3.7     2.8     31  -43.3     0      1
chirp_1-5k_50ms@L            0   100   100     0     19.8     1.64     2.2     3.1     2.0     79  -39.2     0      1
chirp_6-16k_50ms@L           0   100   100     0     19.9     1.04     2.8     3.3     2.5     54  -46.0     0      1
chirp_0.5-4k_50ms@L          0   100   100     0     19.9     0.76     3.2     3.5     2.8     53  -39.5     0      1
noise_1.5-8k_50ms@L        -10   100   100     0     20.0     2.47     4.7     5.2     2.0     22  -48.3     0      1
logchirp_1-10k_50ms@L      -10   100   100     0     20.4     1.19     3.3     4.3     2.3     34  -43.4     0      1
chirp_2-10k_50ms@L         -20   100    33     0     15.0     0.00     1.5     1.5     1.8     15  -52.0     0      1
logchirp_1-10k_50ms@L      -20    33    33     0     17.7     0.00     4.6     4.6     1.9     13  -49.6     0      1
noise_2-10k_50ms@L           0    25    25     0     17.9     0.00     1.7     1.7     2.2     21  -42.9     0      1
chirp_1-8k_50ms@L          -20   100    33     0     18.0     0.00     5.8     5.8     1.8     14  -50.4     0      1
noise_4-12k_50ms@L         -10   100    33     0     18.6     0.00     2.8     2.8     2.2     30  -50.9     0      1
noise_1-6k_50ms@L          -10   100    67     0     19.2     0.38     7.7     8.0     1.8     18  -47.1     0      1
chirp_3-10k_50ms@L         -20   100    67     0     19.3     1.38     4.1     5.4     2.2     20  -53.0     0      1
logchirp_1.5-8k_50ms@L     -20   100    33     0     20.0     0.00     7.2     7.2     1.9     15  -51.2     0      1
chirp_1-5k_50ms@L          -20   100    67     0     20.8     1.57     2.8     3.6     1.8     16  -50.7     0      1
chirp_1.5-8k_50ms@L        -20   100    67     0     21.3     2.08     8.1     8.2     2.0     16  -51.0     0      1
noise_4-12k_50ms@L         -20    67     0     0                                               13  -54.6     0      1
noise_4-12k_50ms@L         -30     0     0     0                                                             0      1
chirp_2-10k_10ms@L         -20   100     0     0                                               14  -51.6     0      1
chirp_2-10k_10ms@L         -30     0     0     0                                                             0      1
chirp_1.5-8k_50ms@L        -30     0     0     0                                                             0      1
chirp_1-10k_50ms@L         -20   100     0     0                                               13  -51.7     0      1
chirp_1-10k_50ms@L         -30     0     0     0                                                             0      1
chirp_2-10k_50ms@L         -30     0     0     0                                                             0      1
noise_1.5-8k_50ms@L        -20     0     0     0                                                             0      1
noise_1.5-8k_50ms@L        -30     0     0     0                                                             0      1
chirp_8-18k_50ms@L           0   100     0     0                                               30  -51.6     0      1
chirp_8-18k_50ms@L         -10   100     0     0                                               14  -54.8     0      1
chirp_8-18k_50ms@L         -20     0     0     0                                                             0      1
chirp_8-18k_50ms@L         -30     0     0     0                                                             0      1
chirp_4-12k_20ms@L         -20    33     0     0                                               14  -54.7     0      1
chirp_4-12k_20ms@L         -30     0     0     0                                                             0      1
chirp_5-14k_50ms@L         -20    67     0     0                                               16  -55.4     0      1
chirp_5-14k_50ms@L         -30     0     0     0                                                             0      1
chirp_6-16k_50ms@L         -10   100     0     0                                               24  -52.9     0      1
chirp_6-16k_50ms@L         -20     0     0     0                                                             0      1
chirp_6-16k_50ms@L         -30     0     0     0                                                             0      1
chirp_2-10k_35ms@L         -20   100     0     0                                               17  -51.4     0      1
chirp_2-10k_35ms@L         -30     0     0     0                                                             0      1
chirp_1-8k_50ms@L          -30     0     0     0                                                             0      1
chirp_4-12k_50ms@L         -20   100     0     0                                               18  -54.3     0      1
chirp_4-12k_50ms@L         -30     0     0     0                                                             0      1
chirp_2-6k_50ms@L          -30     0     0     0                                                             0      1
noise_1-6k_50ms@L          -20     0     0     0                                                             0      1
noise_1-6k_50ms@L          -30     0     0     0                                                             0      1
chirp_0.5-4k_50ms@L        -20    33     0     0                                               13  -48.9     0      1
chirp_0.5-4k_50ms@L        -30     0     0     0                                                             0      1
chirp_3-12k_50ms@L         -20   100     0     0                                               21  -53.5     0      1
chirp_3-12k_50ms@L         -30     0     0     0                                                             0      1
chirp_1-5k_50ms@L          -30     0     0     0                                                             0      1
chirp_3-10k_50ms@L         -30     0     0     0                                                             0      1
chirp_2-10k_20ms@L         -20    33     0     0                                               14  -51.7     0      1
chirp_2-10k_20ms@L         -30     0     0     0                                                             0      1
noise_2-10k_50ms@L         -30     0     0     0                                                             0      1
logchirp_1-10k_50ms@L      -30     0     0     0                                                             0      1
logchirp_1.5-8k_50ms@L     -30     0     0     0                                                             0      1
chirp_3-8k_50ms@L          -30     0     0     0                                                             0      1
logchirp_2-12k_50ms@L      -20   100     0     0                                               17  -52.5     0      1
logchirp_2-12k_50ms@L      -30     0     0     0                                                             0      1
```

## 2026-11-16 20:41 — bench calibrate

- command (in `/home/nadasmartin/okos_lab_project/host`): `python bench.py calibrate --note 'first calibration check over P1-P4 (all signals/volumes), not applied'`
- duration: 18 s, finished
- code: `0ec10024c594` (copy: `docs/code_snapshots/2026-11-16_2018_0ec10024c594/`)
- notes: first calibration check over P1-P4 (all signals/volumes), not applied

```
mic square size(s) in these runs: 30 cm
267 trials, 4 positions, 3 of 4 sides of the array (+x, +y, -x, -y) covered

per-mic channel delay (relative to Mic1) [us]: Mic1 +0.0  Mic2 -10.9  Mic3 -4.1  Mic4 -1.8
timing error vs. truth: 19.1 us -> 17.9 us (in-sample)

same fit per signal (should agree if it is the electronics):
  chirp_0.5-4k_50ms@L           -11.1    +0.9    +1.2   (11 trials)
  chirp_1-10k_50ms@L             -9.9    -3.0    -0.6   (11 trials)
  chirp_1-5k_50ms@L             -11.5    -3.3    -4.9   (11 trials)
  chirp_1-8k_50ms@L             -16.0    -4.1    -1.0   (10 trials)
  chirp_1.5-8k_50ms@L           -11.9    -6.7    -5.7   (12 trials)
  chirp_2-10k_10ms@L            -12.4    -3.2    -1.2   (11 trials)
  chirp_2-10k_20ms@L            -11.6    -4.7    -1.8   (12 trials)
  chirp_2-10k_35ms@L             -9.1    -5.2    -4.9   (12 trials)
  chirp_2-10k_50ms@L            -11.9    -4.9    +0.5   (11 trials)
  chirp_2-6k_50ms@L             -10.0    -2.0    -4.6   (13 trials)
  chirp_3-10k_50ms@L            -10.5    -4.7    -1.2   (12 trials)
  chirp_3-12k_50ms@L             -8.0    -4.4    -1.4   (12 trials)
  chirp_3-8k_50ms@L             -10.4    -3.0    -3.3   (12 trials)
  chirp_4-12k_20ms@L             -7.4    -2.8    -0.5   (11 trials)
  chirp_4-12k_50ms@L             -7.3    -2.3    -0.2   (11 trials)
  chirp_5-14k_50ms@L             -7.0    -2.7    +0.3   (11 trials)
  chirp_6-16k_50ms@L            -11.1    -7.6    +0.4   (9 trials)
  chirp_8-18k_50ms@L             -5.7   -21.7   -15.8   (1 trials)
  logchirp_1-10k_50ms@L         -12.0    -3.3    -1.5   (11 trials)
  logchirp_1.5-8k_50ms@L        -13.4    -6.0    -4.9   (11 trials)
  logchirp_2-12k_50ms@L          -9.7    -4.7    -2.0   (12 trials)
  noise_1-6k_50ms@L             -16.9    -4.5    -0.5   (9 trials)
  noise_1.5-8k_50ms@L           -13.8    -4.7    -2.4   (11 trials)
  noise_2-10k_50ms@L            -10.0    -3.3    -0.1   (11 trials)
  noise_4-12k_50ms@L            -12.4    -6.7    -0.3   (9 trials)

leave one position out (fit on the others, test here) - the honest check:
  ( -32.0,  22.9,  46.5) cm: timing  24.2 ->  27.3 us, position error  13.8 ->   8.5 cm
  ( -28.3, -31.3,  42.0) cm: timing  18.9 ->  27.2 us, position error   3.3 ->   5.8 cm
  (  27.5, -32.3,  42.0) cm: timing  15.9 ->  24.1 us, position error   9.9 ->   4.1 cm
  (  33.8,  27.5,  47.0) cm: timing  13.8 ->  17.5 us, position error   2.5 ->   7.1 cm

saved: /home/nadasmartin/okos_lab_project/host/calibration.json
```

## 2026-11-16 20:41 — bench calibrate

- command (in `/home/nadasmartin/okos_lab_project/host`): `python bench.py calibrate --signal chirp --note 'same, chirps only, not applied'`
- duration: 16 s, finished
- code: `0ec10024c594` (copy: `docs/code_snapshots/2026-11-16_2018_0ec10024c594/`)
- notes: same, chirps only, not applied

```
mic square size(s) in these runs: 30 cm
227 trials, 4 positions, 3 of 4 sides of the array (+x, +y, -x, -y) covered

per-mic channel delay (relative to Mic1) [us]: Mic1 +0.0  Mic2 -10.5  Mic3 -3.9  Mic4 -2.0
timing error vs. truth: 19.0 us -> 17.9 us (in-sample)

same fit per signal (should agree if it is the electronics):
  chirp_0.5-4k_50ms@L           -11.1    +0.9    +1.2   (11 trials)
  chirp_1-10k_50ms@L             -9.9    -3.0    -0.6   (11 trials)
  chirp_1-5k_50ms@L             -11.5    -3.3    -4.9   (11 trials)
  chirp_1-8k_50ms@L             -16.0    -4.1    -1.0   (10 trials)
  chirp_1.5-8k_50ms@L           -11.9    -6.7    -5.7   (12 trials)
  chirp_2-10k_10ms@L            -12.4    -3.2    -1.2   (11 trials)
  chirp_2-10k_20ms@L            -11.6    -4.7    -1.8   (12 trials)
  chirp_2-10k_35ms@L             -9.1    -5.2    -4.9   (12 trials)
  chirp_2-10k_50ms@L            -11.9    -4.9    +0.5   (11 trials)
  chirp_2-6k_50ms@L             -10.0    -2.0    -4.6   (13 trials)
  chirp_3-10k_50ms@L            -10.5    -4.7    -1.2   (12 trials)
  chirp_3-12k_50ms@L             -8.0    -4.4    -1.4   (12 trials)
  chirp_3-8k_50ms@L             -10.4    -3.0    -3.3   (12 trials)
  chirp_4-12k_20ms@L             -7.4    -2.8    -0.5   (11 trials)
  chirp_4-12k_50ms@L             -7.3    -2.3    -0.2   (11 trials)
  chirp_5-14k_50ms@L             -7.0    -2.7    +0.3   (11 trials)
  chirp_6-16k_50ms@L            -11.1    -7.6    +0.4   (9 trials)
  chirp_8-18k_50ms@L             -5.7   -21.7   -15.8   (1 trials)
  logchirp_1-10k_50ms@L         -12.0    -3.3    -1.5   (11 trials)
  logchirp_1.5-8k_50ms@L        -13.4    -6.0    -4.9   (11 trials)
  logchirp_2-12k_50ms@L          -9.7    -4.7    -2.0   (12 trials)

leave one position out (fit on the others, test here) - the honest check:
  ( -32.0,  22.9,  46.5) cm: timing  24.2 ->  27.4 us, position error  13.8 ->   8.3 cm
  ( -28.3, -31.3,  42.0) cm: timing  18.9 ->  27.1 us, position error   3.1 ->   6.2 cm
  (  27.5, -32.3,  42.0) cm: timing  15.9 ->  23.8 us, position error   9.7 ->   4.4 cm
  (  33.8,  27.5,  47.0) cm: timing  13.8 ->  17.6 us, position error   2.5 ->   6.7 cm

saved: /home/nadasmartin/okos_lab_project/host/calibration.json
```

## 2026-11-16 20:41 — P4 sweep (by hand)

- Setup identical to P3 (array 30 cm, left channel, phone tilted towards the array, same lowered volume).
  Phone speaker at (−28.3, −31.3, 42.0) cm: distance 59.5 cm, azimuth 228°, elevation 45°. Firmware `cc8e9c945759` (= the sources).
- Data: `host/bench_results/run_20261116_204112_P4.jsonl`; full table in the automatic entry above.
- Detection: 0 dB and −10 dB 100 % (except noise 2–10k at 0 dB: 1/4).
  - −20 dB: most 50 ms chirps detected; noise, 6–16k and 8–18k not.
  - −30 dB: nothing (as at P3).
- Before any correction: tdoa rms 18–19 us, direction 2.0–2.3°, position error 2–5 cm for most chirps.

## 2026-11-16 ~20:50 — Analysis of P1–P4 (by hand): the array is rotated ~2.1°

Script: `host/analyze_sweeps.py` (saved so the numbers can be reproduced; the command is in its docstring and in `docs/reproduce.md`).
Fits use the median pair delays of the chirps with f_lo ≥ 2 kHz, 50 ms, all volumes, per position.

- Position fitted to the measured delays vs. measured position (nominal square):
  - P1 off 9.1 cm (range +14 %, direction 2.2°)
  - P2 off 2.5 cm (−3 %, 1.2°)
  - P3 off 6.2 cm (+10 %, 1.3°)
  - P4 off 3.4 cm (−5 %, 1.6°)
- **Per-mic delay calibration rejected:** `bench.py calibrate` over P1–P4 (automatic entries above; result in `host/calibration.json`, NOT applied).
  - Leave one position out, the timing gets WORSE at every position: P1 24.2→27.3, P2 13.8→17.5, P3 15.9→24.1, P4 18.9→27.2 us.
  - (Its "3 of 4 sides covered" warning is a classifier quirk: the positions lie near the diagonals, so P3 and P4 fell in one sector. They are really in 4 different quadrants.)
- **Error models fitted to all 4 positions together** (12 independent numbers; rms timing error after the fit; leave-one-out = fit on 3, test on the 4th):
      nothing fitted: rms 18.28 us
      model                          in-sample   leave-one-out per position (timing before -> after)
      speed of sound                  18.25 us   P1 23.3->23.7  P2 13.7->13.9  P3 16.1->16.3  P4 18.6->18.8   params [344.664]
      array size                      18.25 us   P1 23.3->23.7  P2 13.7->13.9  P3 16.1->16.3  P4 18.6->18.9   params [0.299]
      per-mic delays (3)              18.05 us   P1 23.3->29.2  P2 13.7->18.6  P3 16.1->22.5  P4 18.6->24.7   params [-4.153  0.154 -2.126]
      common phone offset (3)         18.16 us   P1 23.3->34.0  P2 13.7->23.0  P3 16.1->27.6  P4 18.6->28.0   params [-0.031  0.188  0.172]
      array rotation (1)               6.14 us   P1 23.3->11.2  P2 13.7-> 5.3  P3 16.1-> 4.7  P4 18.6-> 2.9   params [2.133]
      rotation + shift (3)             5.52 us   P1 23.3->11.6  P2 13.7->11.9  P3 16.1-> 4.4  P4 18.6-> 5.3   params [ 2.169 -0.243 -0.171]
      rotation + shift + size (4)      5.50 us   P1 23.3->13.3  P2 13.7->11.9  P3 16.1-> 4.9  P4 18.6-> 7.5   params [ 2.168 -0.242 -0.169  0.3  ]
      each mic x,y (8)                 5.07 us   P1 23.3->15.8  P2 13.7->23.0  P3 16.1->13.1  P4 18.6->16.6   params [-0.671 -0.672 -0.904  0.443  0.278  0.394  0.389 -0.798]
  - **Array rotation is the answer.** One parameter, +2.13° (the mics sit rotated counter-clockwise seen from above, relative to the axes the phone positions are measured in):
    - 18.3 → 6.1 us in-sample;
    - leave-one-out improves EVERY position (P1 23→11, P2 14→5, P3 16→5, P4 19→3 us);
    - every signal group, fitted on its own, gives the same angle:
        chirp f_lo < 2k    +2.02 deg    18.6 ->   8.9 us
        chirp f_lo 2-4k    +2.08 deg    18.3 ->   7.2 us
        chirp f_lo >= 4k   +2.18 deg    18.5 ->   5.7 us
        short chirps       +2.12 deg    18.5 ->   7.0 us
        logchirp           +2.09 deg    18.5 ->   7.7 us
        noise              +2.04 deg    18.2 ->   7.7 us
    - → geometry, not acoustics or electronics. It also explains the constant 1.2–2.2° direction error: with the rotation, the median direction error drops to 0.3°.
  - More parameters (shift, size, each mic) improve the in-sample fit only a little and do WORSE in leave-one-out (overfitting). Speed of sound, array size, delays and phone offset explain nothing.
- What is left after the rotation:
  - ~5.5 us timing error for the best signals;
  - P1 is the worst position (11 us) — the one played at max volume with a lot of room echo;
  - position errors are mostly in RANGE (distance), which is the weakly determined direction for a 30 cm array at 60 cm.
- **Signal ranking over all 4 positions with the rotation**, 0 and −10 dB (the levels detected everywhere), sorted by median position error:

```
=== square rotated 2.13 deg: gains (0, -10), all 4 positions, sorted by median position error ===
signal                   gain  ok% tdoa rms   std pos med pos max  dir   pos P1/P2/P3/P4 [cm]
chirp_6-16k_50ms            0   88      5.8  0.64     2.0     3.7  0.3     3.7   1.9   0.4   2.0
chirp_4-12k_20ms            0  100      5.4  0.71     2.0     7.9  0.3     7.9   2.3   0.8   1.7
noise_4-12k_50ms            0  100      5.3  0.83     2.8     8.7  0.3     8.7   1.7   0.2   3.9
chirp_4-12k_20ms          -10  100      5.6  0.68     2.9     7.2  0.3     7.2   3.4   1.7   2.4
chirp_3-12k_50ms            0  100      5.7  0.36     3.0     7.8  0.3     7.8   2.2   1.9   3.8
chirp_5-14k_50ms          -10  100      5.8  0.75     3.5     5.0  0.3     5.0   2.0   1.1   5.0
chirp_5-14k_50ms            0  100      5.7  0.54     3.5     5.2  0.3     5.2   2.0   1.2   5.0
chirp_4-12k_50ms            0  100      5.7  0.40     3.5     7.5  0.3     7.5   3.4   0.3   3.5
chirp_3-12k_50ms          -10  100      5.8  0.44     3.5     8.8  0.3     8.8   2.4   1.1   4.6
chirp_4-12k_50ms          -10  100      5.7  0.58     3.7     7.8  0.3     7.8   3.2   0.3   4.2
logchirp_2-12k_50ms         0  100      5.8  0.53     3.8     9.7  0.3     9.7   2.5   5.2   2.3
chirp_2-10k_10ms          -10  100      8.1  1.33     4.7    21.7  0.6    21.7   1.2   8.2   0.7
chirp_2-10k_20ms          -10  100      7.0  0.94     5.3    16.6  0.5    16.6   2.0   7.6   2.9
noise_2-10k_50ms          -10  100      7.1  1.06     5.4    10.7  0.4     8.5   1.7  10.7   2.3
chirp_3-8k_50ms           -10   92      9.6  0.44     5.4    36.1  0.8    36.1   1.1   7.6   3.2
logchirp_2-12k_50ms       -10  100      6.3  0.59     5.5    10.2  0.4    10.2   2.6   6.4   4.7
chirp_2-10k_10ms            0  100      8.1  1.35     5.6    22.3  0.5    22.3   0.7  10.3   0.8
chirp_1-10k_50ms          -10  100      6.7  0.81     6.1    11.2  0.5    11.2   2.7   9.5   0.9
chirp_2-10k_50ms            0   94      6.5  0.63     6.1    11.6  0.4    11.6   2.1  10.1   0.4
chirp_3-10k_50ms            0   94      6.6  0.54     6.2    12.5  0.5    12.5   2.7   9.8   2.1
chirp_1-8k_50ms             0   94      9.7  0.40     6.5    31.0  0.8    31.0   1.4   8.6   4.4
chirp_1.5-8k_50ms           0  100      9.6  0.73     6.5    28.3  0.8    28.3   1.1   8.9   4.1
chirp_1-10k_50ms            0  100      6.6  0.34     6.6    11.2  0.5    11.2   2.3  10.9   0.6
logchirp_1-10k_50ms         0  100      7.3  0.60     6.7    16.4  0.5    16.4   2.5  10.8   0.8
noise_1.5-8k_50ms           0  100      9.5  0.66     6.7    31.4  0.7    31.4   1.8   9.8   3.6
chirp_3-8k_50ms             0   94      9.6  0.51     6.8    34.4  0.8    34.4   1.2   9.2   4.3
logchirp_1-10k_50ms       -10  100      8.1  1.03     6.8    18.2  0.6    18.2   2.8  10.8   2.4
chirp_2-10k_50ms          -10   92      6.6  0.49     6.9    12.3  0.4    12.3   3.1  10.7   0.7
chirp_2-10k_35ms            0  100      7.0  0.87     6.9    18.6  0.5    18.6   2.2  11.6   0.7
chirp_2-10k_20ms            0  100      6.8  1.20     7.1    13.6  0.5    13.6   2.7  11.5   1.1
chirp_3-10k_50ms          -10  100      6.8  0.58     7.2    12.1  0.4    12.1   2.7  11.7   0.3
logchirp_1.5-8k_50ms      -10  100     10.2  0.76     7.4    30.7  1.0    30.7   2.3   8.6   6.1
chirp_1.5-8k_50ms         -10   92     10.0  0.68     7.6    30.5  0.9    30.5   1.2   9.8   5.4
noise_1.5-8k_50ms         -10  100      9.8  1.34     7.7    27.9  0.7    27.9   2.2  12.4   2.9
chirp_2-10k_35ms          -10   92      7.0  0.78     8.2    13.7  0.5    13.7   3.0  13.4   0.9
noise_1-6k_50ms             0  100     10.5  0.92     8.8    25.7  1.1    25.7   2.7  10.3   7.4
noise_1-6k_50ms           -10   83     10.8  1.40     9.3    28.5  1.0    28.5   1.0  11.0   7.6
chirp_2-6k_50ms           -10   92     11.2  0.68     9.9    31.5  1.1    31.5   1.6  12.2   7.5
chirp_0.5-4k_50ms         -10  100     10.0  1.54     9.9    24.2  1.0    17.2   1.4  24.2   2.6
chirp_2-6k_50ms             0   94     11.5  0.82    10.3    33.4  1.1    33.4   1.5  11.8   8.7
chirp_0.5-4k_50ms           0  100     10.4  0.91    13.1    27.0  1.0    23.7   1.1  27.0   2.6
chirp_1-5k_50ms           -10  100     10.9  0.95    13.4    33.4  0.7    33.4   2.1  24.8   0.9
chirp_1-5k_50ms             0  100     10.5  1.02    13.5    33.1  0.7    33.1   1.7  25.2   0.7
not usable at every position: chirp_6-16k_50ms@-10, noise_2-10k_50ms@0, chirp_8-18k_50ms@0, chirp_8-18k_50ms@-10, chirp_1-8k_50ms@-10, logchirp_1.5-8k_50ms@0, noise_4-12k_50ms@-10
```

- **Conclusions about the test signal:**
  - Best: **linear chirps 50 ms with a high band:**
    - 3–12k: std 0.36–0.44 us, position median 3.0–3.5 cm, max 7.8–8.8 cm (at P1);
    - 4–12k: std 0.40–0.58, median 3.5–3.7, max 7.5–7.8;
    - 5–14k: std 0.54–0.75, median 3.5, max 5.0–5.2 (most uniform over positions).
    - 4–12k 20 ms and 6–16k 50 ms are as accurate at 0 dB but less repeatable / less robust (6–16k fails at −10 dB at one position).
  - Bands starting below 2 kHz are clearly worse (median 6–13 cm, up to 25–34 cm): low frequencies suffer most from reflections, and P1 (echo) shows it most.
  - Noise bursts: low matched-filter snr, larger std, drop out at low volume → worse than chirps of the same band.
  - Volume: 0 vs −10 dB makes little difference as long as it is detected. The phone volume was changed between P1/P2/P3, so absolute volume conclusions are limited.
    Lower volume = less echo (P1 vs. the rest), but at P3/P4 −20 dB was already at the detection limit.
- **Proposed next steps** (not done yet; to discuss):
  1. Check the physical alignment: is the mic square turned ~2° against the measuring axes? (2.1° = 1.1 cm over 30 cm.)
     Either align it, or make the rotation a setting like `array` (firmware + localize.py) and measure it once.
  2. Make chirp 3–12k or 4–12k 50 ms the default test signal.
  3. Keep the phone volume fixed and recorded from now on; measure the room temperature.
  4. Repeat a couple of positions with the corrected geometry to confirm (expected: direction ~0.3°, position ~3 cm at 60 cm).

## 2026-11-18 08:55 — Decisions after P1–P4: rotation in the code, fixed test signal

**1. Array rotation is now part of the geometry (no physical re-alignment).**
- Measured value: **+2.13°** (counter-clockwise seen from above, about the array centre), from the P1–P4 fit (entry "Analysis of P1–P4"). Every signal group agreed: 2.0–2.2°.
- Firmware: `rot <deg>` command, saved in flash. Mic positions = the nominal square turned by it. Status line: `array_rot_deg`.
- Host: `localize.square(side, rot)`, `localize.MEASURED_ROT_DEG = 2.13`, `bench.py --rot`. Each run file records `array_rot_deg` and the rotated `mics_cm`.
- At 30 cm, the mics move by about 0.55 cm each, e.g. Mic1 (−15, 15) → (−15.55, 14.43) cm.
- Expected effect (from the leave-one-position-out check): timing error ~18 → ~6 µs, direction error ~1.5° → ~0.3°.
- The rotation belongs to the physical setup: if the array board is moved or turned, it must be measured again (a few sweep positions + `analyze_sweeps.py`).
- Assumption to check: changing the side to 20 / 10 cm keeps the same rotation (the mounts move along the diagonals of the same board).

**2. Fixed test signal: linear chirp 3–12 kHz, 50 ms.**
- Why: best timing stability over P1–P4 (std 0.36–0.44 µs between repetitions; position error median 3.0 cm with the rotated geometry, worst 7.8 cm at P1). Bands starting below 2 kHz were clearly worse (echoes); noise bursts were worse than chirps.
- Runner-ups: chirp 4–12k 50 ms (3.5 cm median, 7.5 cm max); chirp 5–14k 50 ms (most even, max 5.2 cm).
- From now on this is the ESP32 boot template (band bins 289–1187 = 3111–12780 Hz) and `signals_lib.DEFAULT`. It stays fixed for the main experiments, as the project plan requires (`docs/projektterv_10_13.pdf` §3, "Változatlan paraméterek").
- Volume: 0 and −10 dB were equivalent. For the main series: one fixed phone volume, written down, no change between positions.

Code: firmware `9587b9dbc09c`, code `6a7471c3aa5b`. Details in `docs/reproduce.md` §6. Firmware compiled but not flashed yet (board not connected).

## 2026-11-18 09:10 — Planning the distance series (decisions)

- Accuracy limit for "3D position usable" / "direction only": **not fixed in advance**. It will be decided after seeing the results (the project plan §5 recommends fixing it beforehand; this is a conscious deviation, to be stated in the report).
- Directions: a full distance series in every direction would take too long. Proposed instead (see the chat of 2026-11-18): one full series along the main line, a shorter one along a second line at 45° to it (along a side vs along a diagonal of the square), and spot checks in the other directions to test whether the room (furniture) breaks the symmetry.

## 2026-11-18 09:40 — Distance series: setup facts, geometry check, point plan, tools

**Setup facts (from the user):**
- The mic plane is only **4 cm above the floor** (the project plan suggested ~40 cm). The phone can go up to 165 cm above the mic plane.
- Free area of the room: between the +x=y line (az 45°) and the +y axis (az 90°), about 2 m.
- Accuracy limits are decided after the results (entry 09:10).

**Geometry check before planning (computed, no measurement).** How much does the geometry alone amplify timing noise?
- Model: 1 µs independent noise on each mic's arrival time, 30 cm array rotated 2.13°. Same model as `geom` in `host/analyze_series.py`.
- Planar array: **distance is well determined for low sources and poorly for steep ones.**
  - Horizontal 100 cm, z 20 cm: range std 1.7 cm/µs.
  - Horizontal 100 cm, z 140 cm: range std 13.8 cm/µs.
- **az 90° (the plane x = 0) is a blind plane for distance.** There the 6 pair delays carry only one independent number, so distance can't be found; direction still works.
  - At horizontal 100 cm, z 80 cm, range std per µs: 4.3 cm at az 45°, 6.1 cm at 70°, 10.4 cm at 80°, 58 cm at 90°.
- Array size: range std scales about 1/side² (10 cm is ~8–9× worse than 30 cm); direction scales about 1/side.
- Consequence: elevation and azimuth matter as much as distance. So the plan uses **rays of fixed elevation**: along a ray only the distance changes.
- A check against P1–P4 (horizontal ~45 cm, el ~45°): geom 1.3–1.8 cm/µs; the measured range errors (2–8 cm) imply ~2–4 µs effective timing error.

**Point plan:** `host/plans/distance_v1.json` (23 points, 29 placements; `python series.py --list` shows it).
- Line A, az 45° (diagonal of the square): elevations 10/30/50° × r = 50/100/150/200 cm (12 points). At el 30°, r 50/100/200 the phone is placed 3× (placement repeatability).
- Line B, az 75°: el 10/30/50 × r 100/200 (6 points).
- Line C, az 90° (blind plane): el 30 × r 100/200 (2 points). Direction should work there, distance should fail.
- S: spot checks at az 135/225/315, el 30, r 100 (3 points). By symmetry they equal A-e30-r100, so any difference comes from the room.
- r is the slant distance from the array centre. Targets are guides; the measured position counts. All targets satisfy z ≤ 153 cm and horizontal ≤ 197 cm.
- Order: all points with the 30 cm array (`--series a30`), then a20, then a10. Measured positions are kept in `host/plans/distance_v1_measured.json` and offered again (Enter) for the later series if the phone goes back on the same mark.

**Tools (new):**
- `host/series.py` goes through the plan point by point:
  - target shown, measured position typed in;
  - fixed signal chirp 3–12k 50 ms, 30 chirps every 0.5 s, fixed gain;
  - one result file per placement in `host/bench_results/series/<plan>/<series>/`, in the same format as `bench.py run`;
  - resumes where it stopped; logged here automatically.
- `host/analyze_series.py`: per point and array size: success rate, 3D error mean/p95, signed range error, direction error median/p95, `geom` (cm/µs), placement spread, Fraunhofer distances; figure `figures/line_A_vs_distance.png`.
  - Tested on the P1–P4 data converted to series files (scratch only): tables and figure OK.

## 2026-11-18 11:39 — distance series dryrun_test / dryrun (array 30.0 cm)

- command (in `/home/nadasmartin/okos_lab_project/host`): `python series.py --plan /tmp/claude-1000/-home-nadasmartin-okos-lab-project/3e5ecb96-595c-4ce1-af99-f8f9e2644202/scratchpad/dryrun_plan.json --series dryrun --array 30 --rot 2.13 --count 3 --note 'software dry run with a simulated phone, no sound'`
- duration: 14 s, finished
- code: `2b85f9ca36aa` (copy: `docs/code_snapshots/2026-11-18_1139_2b85f9ca36aa/`)
- notes: software dry run with a simulated phone, no sound

```
plan dryrun_test, series dryrun: 3 of 3 points to measure; signal chirp_3-12k_50ms, 3 x every 0.5 s, gain 0 dB, channel left
mic square 30 cm, rotated +2.13 deg: Mic1 (-15.5,+14.4)  Mic2 (+14.4,+15.5)  Mic3 (+15.5,-14.4)  Mic4 (-14.4,-15.5)
ESP32 firmware 9587b9dbc09c = the firmware sources on disk
ESP32: 44154 Hz/mic, mic delays [0.0, 0.0, 0.0, 0.0] us, 21 C -> c = 344.0 m/s

Open on the phone (same Wi-Fi):  http://192.168.1.76:8765/
waiting for the phone to tap 'Start audio' ...
phone ready (127.0.0.1)

next: [1/3] in-between 7, height 10 cm (x 41.8   y 206   z 10 cm) - waiting for the phone button

[1/3] z010-M7  in-between 7, height 10 cm
true position (41.8, 206.0, 10.0) cm: distance 210.4 cm, azimuth 78.5 deg, elevation 2.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 219.4  Mic3 858.8  Mic4 1050.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0     0     0     0                                                             0

next: [2/3] in-between 8, height 10 cm (x 125   y 214   z 10 cm) - waiting for the phone button
  skipped z010-M8

next: [3/3] y axis 50 cm, height 50 cm (x 0   y 50   z 50 cm) - waiting for the phone button

[3/3] z050-Y050  y axis 50 cm, height 50 cm
true position (0.0, 50.0, 50.0) cm: distance 70.7 cm, azimuth 90.0 deg, elevation 45.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 25.8  Mic3 599.2  Mic4 618.6
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0     0     0     0                                                             0

all points done

measured in this session:
z010-M7      in-between 7     z  10: ok  0/3  NO GOOD DETECTION
z010-M8      skipped
z050-Y050    y axis 50 cm     z  50: ok  0/3  NO GOOD DETECTION
```

## 2026-11-18 11:39 — distance series dryrun_test / dryrun (array 30.0 cm)

- command (in `/home/nadasmartin/okos_lab_project/host`): `python series.py --plan /tmp/claude-1000/-home-nadasmartin-okos-lab-project/3e5ecb96-595c-4ce1-af99-f8f9e2644202/scratchpad/dryrun_plan.json --series dryrun --array 30 --rot 2.13 --count 2 --note 'software dry run 2 (redo/finish), simulated phone, no sound'`
- duration: 17 s, finished
- code: `d219b4897885` (copy: `docs/code_snapshots/2026-11-18_1139_d219b4897885/`)
- notes: software dry run 2 (redo/finish), simulated phone, no sound

```
plan dryrun_test, series dryrun: 2 of 2 points to measure; signal chirp_3-12k_50ms, 2 x every 0.5 s, gain 0 dB, channel left
mic square 30 cm, rotated +2.13 deg: Mic1 (-15.5,+14.4)  Mic2 (+14.4,+15.5)  Mic3 (+15.5,-14.4)  Mic4 (-14.4,-15.5)
ESP32 firmware 9587b9dbc09c = the firmware sources on disk
ESP32: 44160 Hz/mic, mic delays [0.0, 0.0, 0.0, 0.0] us, 21 C -> c = 344.0 m/s

Open on the phone (same Wi-Fi):  http://192.168.1.76:8765/
waiting for the phone to tap 'Start audio' ...
phone ready (127.0.0.1)

next: [1/2] in-between 7, height 10 cm (x 41.8   y 206   z 10 cm) - waiting for the phone button

[1/2] z010-M7  in-between 7, height 10 cm
true position (41.8, 206.0, 10.0) cm: distance 210.4 cm, azimuth 78.5 deg, elevation 2.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 219.4  Mic3 858.8  Mic4 1050.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0     0     0     0                                                             0

next: [2/2] in-between 8, height 10 cm (x 125   y 214   z 10 cm) - waiting for the phone button

[2/2] z010-M8  in-between 8, height 10 cm
true position (125.0, 214.0, 10.0) cm: distance 248.0 cm, azimuth 59.7 deg, elevation 2.3 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 491.3  Mic3 758.7  Mic4 1202.4
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0     0     0     0                                                             0

all points done - waiting for Finish (or Redo previous) on the phone

[2/2] z010-M8  in-between 8, height 10 cm  (REDO)
true position (125.0, 214.0, 10.0) cm: distance 248.0 cm, azimuth 59.7 deg, elevation 2.3 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 491.3  Mic3 758.7  Mic4 1202.4
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0     0     0     0                                                             0

all points done - waiting for Finish (or Redo previous) on the phone

series finished

measured in this session:
z010-M7      in-between 7     z  10: ok  0/2  NO GOOD DETECTION
z010-M8      in-between 8     z  10: ok  0/2  NO GOOD DETECTION
z010-M8      in-between 8     z  10: ok  0/2  NO GOOD DETECTION  [redo]
```

## 2026-11-18 11:45 — Distance series: final grid (user's), phone-driven measuring

**The grid is the user's own; it replaces my distance_v1 proposal, which was never measured and is deleted.**
- `host/plans/distance_v2.json`: 16 horizontal positions × 5 heights = 80 points per array layout.
  - Y: on the +y axis at 50, 100, 150, 200 cm. Note: this is the blind plane x = 0, where distance is expected to be poorly determined (see 09:40).
  - D: on the +x=y diagonal at 50, 100, 150, 200 cm from the centre, i.e. x = y = 35.4 / 70.7 / 106.1 / 141.4 cm.
  - M1…M8 (in-between, user-given): (18, 46.5), (33.3, 78.5), (31.0, 126), (78.5, 117.8), (44.0, 162), (110, 158.5), (41.8, 206), (125, 214) cm.
  - Heights z = 10, 50, 90, 130, 170 cm **above the mic plane** (user's answer; the mic plane is 4 cm above the floor).
  - Order (the user's): the 16 positions in the order above at one height, then the next height. One array layout per session; then 20 cm, then 10 cm.
  - Positions are the planned coordinates (no typing): the user puts the speaker opening on them.
- **Signal:** only the best one, chirp 3–12 kHz 50 ms (user: "only measure with the best sample at every position"). 20 chirps per point, every 0.5 s, gain 0 dB at a fixed phone volume (user's choice: 20 chirps).
- **Phone-driven** (`host/series.py` rewritten, `host/phone_server.py` + `host/phone/index.html` extended):
  - The phone shows the next point (name, height, x y z) and "NEW HEIGHT" when z changes.
  - Buttons: **Ready – measure**, **Redo previous** (the new measurement replaces the old one), **Skip** (the point stays to do). Afterwards it shows the result of the last point (heard/good, errors, clipping).
  - After the last point: Finish, or Redo of the last point.
  - Server additions: `POST /action`, a panel (`ui`, `uiv`) in `/poll`, `set_ui()` / `wait_action()`.
- `host/analyze_series.py` adapted: uses the newest file per point (after a redo); figure `error_vs_distance.png` with one column per height, colour = array size, marker = Y / D / in-between.
- **Dry runs** with a simulated phone (a script pressing the buttons, no sound) against the real ESP32 (2 runs, logged above as "distance series dryrun_test / dryrun"): flow, skip, redo, finish and file writing OK. Their data was deleted.
- ESP32 flashed at ~11:00: firmware `9587b9dbc09c` (3–12 kHz default + rotation). Rotation +2.13° stored by the dry run (`--rot 2.13`).

## 2026-11-18 12:59 — distance series distance_v2 / a30 (array 30.0 cm)

- command (in `/home/nadasmartin/okos_lab_project/host`): `python series.py --series a30 --array 30 --rot 2.13 --channel left --temp 21 --note '30 cm layout; phone volume fixed by the user for the whole series (level not given); temperature not measured, 21 C assumed; speaker aimed at the array'`
- duration: 4726 s, finished
- code: `d219b4897885` (copy: `docs/code_snapshots/2026-11-18_1139_d219b4897885/`)
- notes: 30 cm layout; phone volume fixed by the user for the whole series (level not given); temperature not measured, 21 C assumed; speaker aimed at the array

```
plan distance_v2, series a30: 80 of 80 points to measure; signal chirp_3-12k_50ms, 20 x every 0.5 s, gain 0 dB, channel left
mic square 30 cm, rotated +2.13 deg: Mic1 (-15.5,+14.4)  Mic2 (+14.4,+15.5)  Mic3 (+15.5,-14.4)  Mic4 (-14.4,-15.5)
ESP32 firmware 9587b9dbc09c = the firmware sources on disk
ESP32: 43940 Hz/mic, mic delays [0.0, 0.0, 0.0, 0.0] us, 21 C -> c = 344.0 m/s

Open on the phone (same Wi-Fi):  http://192.168.1.76:8765/
waiting for the phone to tap 'Start audio' ...
phone ready (192.168.1.97)

next: [1/80] y axis 50 cm, height 10 cm (x 0   y 50   z 10 cm) - waiting for the phone button

[1/80] z010-Y050  y axis 50 cm, height 10 cm
true position (0.0, 50.0, 10.0) cm: distance 51.0 cm, azimuth 90.0 deg, elevation 11.3 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 41.2  Mic3 824.4  Mic4 848.5
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     32.7     0.64   597.4   597.9    11.0    620  -30.7     0

next: [2/80] y axis 100 cm, height 10 cm (x 0   y 100   z 10 cm) - waiting for the phone button

[1/80] z010-Y050  y axis 50 cm, height 10 cm  (REDO)
true position (0.0, 50.0, 10.0) cm: distance 51.0 cm, azimuth 90.0 deg, elevation 11.3 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 41.2  Mic3 824.4  Mic4 848.5
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     32.3     0.40   597.2   597.7    11.0    280  -37.5     0

next: [2/80] y axis 100 cm, height 10 cm (x 0   y 100   z 10 cm) - waiting for the phone button

[1/80] z010-Y050  y axis 50 cm, height 10 cm  (REDO)
true position (0.0, 50.0, 10.0) cm: distance 51.0 cm, azimuth 90.0 deg, elevation 11.3 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 41.2  Mic3 824.4  Mic4 848.5
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     33.3     0.39   597.5   598.1    11.0    429  -34.4     0

next: [2/80] y axis 100 cm, height 10 cm (x 0   y 100   z 10 cm) - waiting for the phone button

[1/80] z010-Y050  y axis 50 cm, height 10 cm  (REDO)
true position (0.0, 50.0, 10.0) cm: distance 51.0 cm, azimuth 90.0 deg, elevation 11.3 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 41.2  Mic3 824.4  Mic4 848.5
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     33.2     0.28   597.4   598.0    11.1    476  -34.2     0

next: [2/80] y axis 100 cm, height 10 cm (x 0   y 100   z 10 cm) - waiting for the phone button

[2/80] z010-Y100  y axis 100 cm, height 10 cm
true position (0.0, 100.0, 10.0) cm: distance 100.5 cm, azimuth 90.0 deg, elevation 5.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 37.3  Mic3 862.1  Mic4 889.9
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     31.2     0.60   523.3   523.9    10.0    234  -38.5     0

next: [3/80] y axis 150 cm, height 10 cm (x 0   y 150   z 10 cm) - waiting for the phone button

[3/80] z010-Y150  y axis 150 cm, height 10 cm
true position (0.0, 150.0, 10.0) cm: distance 150.3 cm, azimuth 90.0 deg, elevation 3.8 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 35.7  Mic3 868.3  Mic4 897.6
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     29.1     0.78   462.6   463.6     7.6    220  -39.0     0

next: [4/80] y axis 200 cm, height 10 cm (x 0   y 200   z 10 cm) - waiting for the phone button

[4/80] z010-Y200  y axis 200 cm, height 10 cm
true position (0.0, 200.0, 10.0) cm: distance 200.2 cm, azimuth 90.0 deg, elevation 2.9 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 34.9  Mic3 870.3  Mic4 900.4
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     28.7     0.73   409.5   410.6     6.9    155  -40.5     0

next: [5/80] diagonal 50 cm, height 10 cm (x 35.4   y 35.4   z 10 cm) - waiting for the phone button

[5/80] z010-D050  diagonal 50 cm, height 10 cm
true position (35.4, 35.4, 10.0) cm: distance 51.1 cm, azimuth 45.0 deg, elevation 11.3 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 697.8  Mic1 739.3  Mic4 1203.6
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     30.9     0.38     3.0     3.1     4.2    377  -33.0     0

next: [6/80] diagonal 100 cm, height 10 cm (x 70.7   y 70.7   z 10 cm) - waiting for the phone button

[6/80] z010-D100  diagonal 100 cm, height 10 cm
true position (70.7, 70.7, 10.0) cm: distance 100.5 cm, azimuth 45.0 deg, elevation 5.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 654.2  Mic1 698.8  Mic4 1225.9
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     32.0     0.84    19.4    20.3     6.0    179  -37.9     0

next: [7/80] diagonal 150 cm, height 10 cm (x 106.1   y 106.1   z 10 cm) - waiting for the phone button

[7/80] z010-D150  diagonal 150 cm, height 10 cm
true position (106.1, 106.1, 10.0) cm: distance 150.4 cm, azimuth 45.0 deg, elevation 3.8 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 635.1  Mic1 680.4  Mic4 1229.6
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     28.4     0.83    18.9    20.0     6.5    141  -39.3     0

next: [8/80] diagonal 200 cm, height 10 cm (x 141.4   y 141.4   z 10 cm) - waiting for the phone button

[8/80] z010-D200  diagonal 200 cm, height 10 cm
true position (141.4, 141.4, 10.0) cm: distance 200.2 cm, azimuth 45.0 deg, elevation 2.9 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 625.0  Mic1 670.6  Mic4 1230.8
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    95     0     26.7     0.99    21.7    23.3     6.1    103  -39.8     0

next: [9/80] in-between 1, height 10 cm (x 18   y 46.5   z 10 cm) - waiting for the phone button

[9/80] z010-M1  in-between 1, height 10 cm
true position (18.0, 46.5, 10.0) cm: distance 50.9 cm, azimuth 68.8 deg, elevation 11.3 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 428.8  Mic3 845.1  Mic4 1104.6
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     12.6     0.54     3.7     3.8     6.8    257  -35.0     0

next: [10/80] in-between 2, height 10 cm (x 33.3   y 78.5   z 10 cm) - waiting for the phone button

[10/80] z010-M2  in-between 2, height 10 cm
true position (33.3, 78.5, 10.0) cm: distance 85.9 cm, azimuth 67.0 deg, elevation 6.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 427.5  Mic3 833.2  Mic4 1147.1
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     25.4     0.67    11.4    12.2     5.4    130  -38.2     0

next: [11/80] in-between 3, height 10 cm (x 31   y 126   z 10 cm) - waiting for the phone button

[11/80] z010-M3  in-between 3, height 10 cm
true position (31.0, 126.0, 10.0) cm: distance 130.1 cm, azimuth 76.2 deg, elevation 4.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 266.4  Mic3 857.4  Mic4 1071.4
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    95     0     26.4     0.70    23.8    25.9     7.8    131  -39.4     0

next: [12/80] in-between 4, height 10 cm (x 78.5   y 117.8   z 10 cm) - waiting for the phone button

[12/80] z010-M4  in-between 4, height 10 cm
true position (78.5, 117.8, 10.0) cm: distance 141.9 cm, azimuth 56.3 deg, elevation 4.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 553.1  Mic3 747.4  Mic4 1214.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     25.6     0.77    17.6    18.2     6.1    110  -38.7     0

next: [13/80] in-between 5, height 10 cm (x 44   y 162   z 10 cm) - waiting for the phone button

[13/80] z010-M5  in-between 5, height 10 cm
true position (44.0, 162.0, 10.0) cm: distance 168.2 cm, azimuth 74.8 deg, elevation 3.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 282.0  Mic3 850.2  Mic4 1088.3
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     27.0     0.69    27.5    31.7     6.9    102  -39.8     0

next: [14/80] in-between 6, height 10 cm (x 110   y 158.5   z 10 cm) - waiting for the phone button

[14/80] z010-M6  in-between 6, height 10 cm
true position (110.0, 158.5, 10.0) cm: distance 193.2 cm, azimuth 55.2 deg, elevation 3.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 555.5  Mic3 728.2  Mic4 1219.1
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     27.7     0.85    19.7    21.2     5.9     88  -39.8     0

next: [15/80] in-between 7, height 10 cm (x 41.8   y 206   z 10 cm) - waiting for the phone button

[15/80] z010-M7  in-between 7, height 10 cm
true position (41.8, 206.0, 10.0) cm: distance 210.4 cm, azimuth 78.5 deg, elevation 2.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 219.4  Mic3 858.8  Mic4 1050.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     27.1     0.83    42.4    52.1     6.8    116  -40.3     0

next: [16/80] in-between 8, height 10 cm (x 125   y 214   z 10 cm) - waiting for the phone button

[16/80] z010-M8  in-between 8, height 10 cm
true position (125.0, 214.0, 10.0) cm: distance 248.0 cm, azimuth 59.7 deg, elevation 2.3 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 491.3  Mic3 758.7  Mic4 1202.4
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    55     0     26.7     1.61    22.1    30.6     4.9     72  -40.4     0

next: [17/80] y axis 50 cm, height 50 cm (x 0   y 50   z 50 cm) - waiting for the phone button

[17/80] z050-Y050  y axis 50 cm, height 50 cm
true position (0.0, 50.0, 50.0) cm: distance 70.7 cm, azimuth 90.0 deg, elevation 45.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 25.8  Mic3 599.2  Mic4 618.6
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     20.6     0.31   740.9   744.5     2.9    474  -33.7     0

next: [18/80] y axis 100 cm, height 50 cm (x 0   y 100   z 50 cm) - waiting for the phone button

[18/80] z050-Y100  y axis 100 cm, height 50 cm
true position (0.0, 100.0, 50.0) cm: distance 111.8 cm, azimuth 90.0 deg, elevation 26.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 32.5  Mic3 774.5  Mic4 800.1
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     24.1     0.41    85.2   568.4     2.4    271  -37.2     0

next: [19/80] y axis 150 cm, height 50 cm (x 0   y 150   z 50 cm) - waiting for the phone button

[19/80] z050-Y150  y axis 150 cm, height 50 cm
true position (0.0, 150.0, 50.0) cm: distance 158.1 cm, azimuth 90.0 deg, elevation 18.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 33.6  Mic3 825.4  Mic4 853.5
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     25.3     0.54   264.9   475.1     2.3    162  -40.2     0

next: [20/80] y axis 200 cm, height 50 cm (x 0   y 200   z 50 cm) - waiting for the phone button

[20/80] z050-Y200  y axis 200 cm, height 50 cm
true position (0.0, 200.0, 50.0) cm: distance 206.2 cm, azimuth 90.0 deg, elevation 14.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 33.7  Mic3 845.3  Mic4 874.6
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    80     1     26.5     0.71   414.0   415.1     2.2     83  -41.4     0

next: [21/80] diagonal 50 cm, height 50 cm (x 35.4   y 35.4   z 50 cm) - waiting for the phone button

[21/80] z050-D050  diagonal 50 cm, height 50 cm
true position (35.4, 35.4, 50.0) cm: distance 70.8 cm, azimuth 45.0 deg, elevation 45.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 453.2  Mic1 484.3  Mic4 852.2
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     24.9     0.39     4.6     5.1     2.7    394  -34.0     0

next: [22/80] diagonal 100 cm, height 50 cm (x 70.7   y 70.7   z 50 cm) - waiting for the phone button

[22/80] z050-D100  diagonal 100 cm, height 50 cm
true position (70.7, 70.7, 50.0) cm: distance 111.8 cm, azimuth 45.0 deg, elevation 26.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 574.8  Mic1 615.1  Mic4 1098.2
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     1     27.9     0.57     4.5     4.8     2.3    196  -37.7     0

next: [23/80] diagonal 150 cm, height 50 cm (x 106.1   y 106.1   z 50 cm) - waiting for the phone button

[23/80] z050-D150  diagonal 150 cm, height 50 cm
true position (106.1, 106.1, 50.0) cm: distance 158.2 cm, azimuth 45.0 deg, elevation 18.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 599.4  Mic1 642.5  Mic4 1168.1
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     24.6     0.60    24.7    27.5     2.1     92  -39.5     0

next: [24/80] diagonal 200 cm, height 50 cm (x 141.4   y 141.4   z 50 cm) - waiting for the phone button

[24/80] z050-D200  diagonal 200 cm, height 50 cm
true position (141.4, 141.4, 50.0) cm: distance 206.1 cm, azimuth 45.0 deg, elevation 14.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 605.2  Mic1 649.4  Mic4 1195.2
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     5     0     25.4     0.00    56.1    56.1     2.1     63  -40.2     0

next: [25/80] in-between 1, height 50 cm (x 18   y 46.5   z 50 cm) - waiting for the phone button

[25/80] z050-M1  in-between 1, height 50 cm
true position (18.0, 46.5, 50.0) cm: distance 70.6 cm, azimuth 68.8 deg, elevation 45.1 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 270.5  Mic3 579.8  Mic4 788.3
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      9.1     0.34     3.1     3.8     1.0    236  -33.5     0

next: [26/80] in-between 2, height 50 cm (x 33.3   y 78.5   z 50 cm) - waiting for the phone button

[26/80] z050-M2  in-between 2, height 50 cm
true position (33.3, 78.5, 50.0) cm: distance 98.8 cm, azimuth 67.0 deg, elevation 30.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 355.8  Mic3 710.2  Mic4 992.4
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     23.7     0.47     3.6     4.4     1.9    142  -36.3     0

next: [27/80] in-between 3, height 50 cm (x 31   y 126   z 50 cm) - waiting for the phone button

[27/80] z050-M3  in-between 3, height 50 cm
true position (31.0, 126.0, 50.0) cm: distance 139.1 cm, azimuth 76.2 deg, elevation 21.1 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 245.6  Mic3 799.3  Mic4 1002.1
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     20.6     0.52     7.0    10.0     1.8    129  -38.7     0

next: [28/80] in-between 4, height 50 cm (x 78.5   y 117.8   z 50 cm) - waiting for the phone button

[28/80] z050-M4  in-between 4, height 50 cm
true position (78.5, 117.8, 50.0) cm: distance 150.1 cm, azimuth 56.3 deg, elevation 19.5 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 517.7  Mic3 701.6  Mic4 1146.3
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     23.7     0.66    13.1    15.6     1.9    100  -39.5     0

next: [29/80] in-between 5, height 50 cm (x 44   y 162   z 50 cm) - waiting for the phone button

[29/80] z050-M5  in-between 5, height 50 cm
true position (44.0, 162.0, 50.0) cm: distance 175.2 cm, azimuth 74.8 deg, elevation 16.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 268.8  Mic3 814.5  Mic4 1044.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     22.5     0.66    30.7    39.0     1.7     83  -39.5     0

next: [30/80] in-between 6, height 50 cm (x 110   y 158.5   z 50 cm) - waiting for the phone button

[30/80] z050-M6  in-between 6, height 50 cm
true position (110.0, 158.5, 50.0) cm: distance 199.3 cm, azimuth 55.2 deg, elevation 14.5 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 536.3  Mic3 703.8  Mic4 1181.3
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                               77  -40.0     0

next: [31/80] in-between 7, height 50 cm (x 41.8   y 206   z 50 cm) - waiting for the phone button

[31/80] z050-M7  in-between 7, height 50 cm
true position (41.8, 206.0, 50.0) cm: distance 216.1 cm, azimuth 78.5 deg, elevation 13.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 212.9  Mic3 835.7  Mic4 1022.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                               46  -41.0     0

next: [32/80] in-between 8, height 50 cm (x 125   y 214   z 50 cm) - waiting for the phone button

[32/80] z050-M8  in-between 8, height 50 cm
true position (125.0, 214.0, 50.0) cm: distance 252.8 cm, azimuth 59.7 deg, elevation 11.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 481.0  Mic3 743.4  Mic4 1179.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                               40  -40.6     0

next: [33/80] y axis 50 cm, height 90 cm (x 0   y 50   z 90 cm) - waiting for the phone button

[33/80] z090-Y050  y axis 50 cm, height 90 cm
true position (0.0, 50.0, 90.0) cm: distance 103.0 cm, azimuth 90.0 deg, elevation 60.9 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 16.6  Mic3 416.5  Mic4 431.0
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     1     15.8     0.48   574.3   576.9     1.5    274  -36.6     0

next: [34/80] y axis 100 cm, height 90 cm (x 0   y 100   z 90 cm) - waiting for the phone button

[34/80] z090-Y100  y axis 100 cm, height 90 cm
true position (0.0, 100.0, 90.0) cm: distance 134.5 cm, azimuth 90.0 deg, elevation 42.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 26.0  Mic3 643.9  Mic4 666.0
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     1     20.3     0.43   642.5   678.0     1.7    229  -38.0     0

next: [35/80] y axis 150 cm, height 90 cm (x 0   y 150   z 90 cm) - waiting for the phone button

[35/80] z090-Y150  y axis 150 cm, height 90 cm
true position (0.0, 150.0, 90.0) cm: distance 174.9 cm, azimuth 90.0 deg, elevation 31.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 29.8  Mic3 745.8  Mic4 771.6
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     23.7     0.78   522.7   524.6     1.9    167  -39.5     0

next: [36/80] y axis 200 cm, height 90 cm (x 0   y 200   z 90 cm) - waiting for the phone button

[35/80] z090-Y150  y axis 150 cm, height 90 cm  (REDO)
true position (0.0, 150.0, 90.0) cm: distance 174.9 cm, azimuth 90.0 deg, elevation 31.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 29.8  Mic3 745.8  Mic4 771.6
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     23.4     0.62   522.2   525.5     1.9    163  -39.4     0

next: [36/80] y axis 200 cm, height 90 cm (x 0   y 200   z 90 cm) - waiting for the phone button

[35/80] z090-Y150  y axis 150 cm, height 90 cm  (REDO)
true position (0.0, 150.0, 90.0) cm: distance 174.9 cm, azimuth 90.0 deg, elevation 31.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 29.8  Mic3 745.8  Mic4 771.6
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     23.3     0.45   505.7   524.7     1.9    177  -39.3     0

next: [36/80] y axis 200 cm, height 90 cm (x 0   y 200   z 90 cm) - waiting for the phone button

[35/80] z090-Y150  y axis 150 cm, height 90 cm  (REDO)
true position (0.0, 150.0, 90.0) cm: distance 174.9 cm, azimuth 90.0 deg, elevation 31.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 29.8  Mic3 745.8  Mic4 771.6
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     23.4     0.57   522.4   525.3     1.9    178  -39.2     0

next: [36/80] y axis 200 cm, height 90 cm (x 0   y 200   z 90 cm) - waiting for the phone button

[35/80] z090-Y150  y axis 150 cm, height 90 cm  (REDO)
true position (0.0, 150.0, 90.0) cm: distance 174.9 cm, azimuth 90.0 deg, elevation 31.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 29.8  Mic3 745.8  Mic4 771.6
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     23.5     0.59   523.0   525.6     1.9    179  -39.2     0

next: [36/80] y axis 200 cm, height 90 cm (x 0   y 200   z 90 cm) - waiting for the phone button

[36/80] z090-Y200  y axis 200 cm, height 90 cm
true position (0.0, 200.0, 90.0) cm: distance 219.3 cm, azimuth 90.0 deg, elevation 24.2 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 31.4  Mic3 794.3  Mic4 822.1
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     1     24.5     0.78   377.4   441.0     2.0    113  -40.3     0

next: [37/80] diagonal 50 cm, height 90 cm (x 35.4   y 35.4   z 90 cm) - waiting for the phone button

[37/80] z090-D050  diagonal 50 cm, height 90 cm
true position (35.4, 35.4, 90.0) cm: distance 103.0 cm, azimuth 45.0 deg, elevation 60.9 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 298.1  Mic1 319.9  Mic4 589.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     2     20.5     0.46    18.0    19.5     1.8    240  -36.0     0

next: [38/80] diagonal 100 cm, height 90 cm (x 70.7   y 70.7   z 90 cm) - waiting for the phone button

[38/80] z090-D100  diagonal 100 cm, height 90 cm
true position (70.7, 70.7, 90.0) cm: distance 134.5 cm, azimuth 45.0 deg, elevation 42.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 464.8  Mic1 498.5  Mic4 910.8
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     25.0     0.43     8.1     8.8     2.1    254  -37.3     0

next: [39/80] diagonal 150 cm, height 90 cm (x 106.1   y 106.1   z 90 cm) - waiting for the phone button

[38/80] z090-D100  diagonal 100 cm, height 90 cm  (REDO)
true position (70.7, 70.7, 90.0) cm: distance 134.5 cm, azimuth 45.0 deg, elevation 42.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 464.8  Mic1 498.5  Mic4 910.8
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     24.8     0.39     7.1     9.1     2.1    236  -37.8     0

next: [39/80] diagonal 150 cm, height 90 cm (x 106.1   y 106.1   z 90 cm) - waiting for the phone button

[39/80] z090-D150  diagonal 150 cm, height 90 cm
true position (106.1, 106.1, 90.0) cm: distance 175.0 cm, azimuth 45.0 deg, elevation 31.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 535.1  Mic1 574.1  Mic4 1054.8
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     1     25.7     0.76     9.8    13.5     2.1    148  -39.5     0

next: [40/80] diagonal 200 cm, height 90 cm (x 141.4   y 141.4   z 90 cm) - waiting for the phone button

[40/80] z090-D200  diagonal 200 cm, height 90 cm
true position (141.4, 141.4, 90.0) cm: distance 219.3 cm, azimuth 45.0 deg, elevation 24.2 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 565.3  Mic1 606.9  Mic4 1122.9
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     25.4     0.90    17.2    24.4     2.3     77  -40.0     0

next: [41/80] in-between 1, height 90 cm (x 18   y 46.5   z 90 cm) - waiting for the phone button

[41/80] z090-M1  in-between 1, height 90 cm
true position (18.0, 46.5, 90.0) cm: distance 102.9 cm, azimuth 68.8 deg, elevation 61.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 175.0  Mic3 391.6  Mic4 546.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      9.1     0.44    12.3    15.3     0.6    213  -36.4     0

next: [42/80] in-between 2, height 90 cm (x 33.3   y 78.5   z 90 cm) - waiting for the phone button

[42/80] z090-M2  in-between 2, height 90 cm
true position (33.3, 78.5, 90.0) cm: distance 124.0 cm, azimuth 67.0 deg, elevation 46.5 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 271.8  Mic3 556.4  Mic4 790.8
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     1     20.6     0.49    12.9    15.1     1.6    174  -37.0     0

next: [43/80] in-between 3, height 90 cm (x 31   y 126   z 90 cm) - waiting for the phone button

[43/80] z090-M3  in-between 3, height 90 cm
true position (31.0, 126.0, 90.0) cm: distance 157.9 cm, azimuth 76.2 deg, elevation 34.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 211.4  Mic3 699.8  Mic4 882.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     20.3     0.48     7.5     9.7     1.6    170  -38.8     0

next: [44/80] in-between 4, height 90 cm (x 78.5   y 117.8   z 90 cm) - waiting for the phone button

[44/80] z090-M4  in-between 4, height 90 cm
true position (78.5, 117.8, 90.0) cm: distance 167.7 cm, azimuth 56.3 deg, elevation 32.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 456.0  Mic3 621.0  Mic4 1024.8
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0    220.6     0.86    60.8    64.4    18.2     99  -39.5     0

next: [45/80] in-between 5, height 90 cm (x 44   y 162   z 90 cm) - waiting for the phone button

[45/80] z090-M5  in-between 5, height 90 cm
true position (44.0, 162.0, 90.0) cm: distance 190.5 cm, azimuth 74.8 deg, elevation 28.2 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 244.1  Mic3 746.3  Mic4 960.2
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    95     0    191.4     1.01    57.0    60.7    15.7     65  -39.7     0

next: [46/80] in-between 6, height 90 cm (x 110   y 158.5   z 90 cm) - waiting for the phone button

[45/80] z090-M5  in-between 5, height 90 cm  (REDO)
true position (44.0, 162.0, 90.0) cm: distance 190.5 cm, azimuth 74.8 deg, elevation 28.2 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 244.1  Mic3 746.3  Mic4 960.2
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     21.4     0.97     7.9    13.7     1.7    101  -39.4     0

next: [46/80] in-between 6, height 90 cm (x 110   y 158.5   z 90 cm) - waiting for the phone button

[46/80] z090-M6  in-between 6, height 90 cm
true position (110.0, 158.5, 90.0) cm: distance 212.9 cm, azimuth 55.2 deg, elevation 25.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 498.3  Mic3 655.2  Mic4 1105.4
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     25.2     1.01    10.4    18.6     2.0     68  -40.0     0

next: [47/80] in-between 7, height 90 cm (x 41.8   y 206   z 90 cm) - waiting for the phone button

[47/80] z090-M7  in-between 7, height 90 cm
true position (41.8, 206.0, 90.0) cm: distance 228.7 cm, azimuth 78.5 deg, elevation 23.2 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 199.7  Mic3 788.4  Mic4 966.1
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    95     0     22.9     0.79    18.1    28.8     1.8     76  -40.7     0

next: [48/80] in-between 8, height 90 cm (x 125   y 214   z 90 cm) - waiting for the phone button

[48/80] z090-M8  in-between 8, height 90 cm
true position (125.0, 214.0, 90.0) cm: distance 263.7 cm, azimuth 59.7 deg, elevation 20.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 459.3  Mic3 711.0  Mic4 1130.8
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                               67  -40.8     0

next: [49/80] y axis 50 cm, height 130 cm (x 0   y 50   z 130 cm) - waiting for the phone button

[49/80] z130-Y050  y axis 50 cm, height 130 cm
true position (0.0, 50.0, 130.0) cm: distance 139.3 cm, azimuth 90.0 deg, elevation 69.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 12.0  Mic3 309.9  Mic4 321.0
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     1     12.9     0.67   500.8   502.0     1.1    181  -38.1     0

next: [50/80] y axis 100 cm, height 130 cm (x 0   y 100   z 130 cm) - waiting for the phone button

[50/80] z130-Y100  y axis 100 cm, height 130 cm
true position (0.0, 100.0, 130.0) cm: distance 164.0 cm, azimuth 90.0 deg, elevation 52.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 20.8  Mic3 528.8  Mic4 547.4
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     19.2     0.69   589.6   591.3     1.5    175  -38.5     0

next: [51/80] y axis 150 cm, height 130 cm (x 0   y 150   z 130 cm) - waiting for the phone button

[51/80] z130-Y150  y axis 150 cm, height 130 cm
true position (0.0, 150.0, 130.0) cm: distance 198.5 cm, azimuth 90.0 deg, elevation 40.9 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 25.9  Mic3 657.2  Mic4 680.3
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     20.1     1.05   183.4   595.4     1.6    142  -39.5     0

next: [52/80] y axis 200 cm, height 130 cm (x 0   y 200   z 130 cm) - waiting for the phone button

[52/80] z130-Y200  y axis 200 cm, height 130 cm
true position (0.0, 200.0, 130.0) cm: distance 238.5 cm, azimuth 90.0 deg, elevation 33.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 28.6  Mic3 730.2  Mic4 756.0
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    95     1     23.5     1.00   471.1   472.8     1.9    111  -40.4     0

next: [53/80] diagonal 50 cm, height 130 cm (x 35.4   y 35.4   z 130 cm) - waiting for the phone button

[53/80] z130-D050  diagonal 50 cm, height 130 cm
true position (35.4, 35.4, 130.0) cm: distance 139.3 cm, azimuth 45.0 deg, elevation 68.9 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 217.0  Mic1 233.2  Mic4 438.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     20.7     0.73    43.8    49.7     1.7    146  -37.8     0

next: [54/80] diagonal 100 cm, height 130 cm (x 70.7   y 70.7   z 130 cm) - waiting for the phone button

[54/80] z130-D100  diagonal 100 cm, height 130 cm
true position (70.7, 70.7, 130.0) cm: distance 164.0 cm, azimuth 45.0 deg, elevation 52.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 374.4  Mic1 402.1  Mic4 747.4
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     23.3     0.71    22.4    28.3     1.9    156  -38.5     0

next: [55/80] diagonal 150 cm, height 130 cm (x 106.1   y 106.1   z 130 cm) - waiting for the phone button

[55/80] z130-D150  diagonal 150 cm, height 130 cm
true position (106.1, 106.1, 130.0) cm: distance 198.5 cm, azimuth 45.0 deg, elevation 40.9 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 465.9  Mic1 500.4  Mic4 929.1
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     27.5     0.70    12.3    18.7     2.2    127  -39.7     0

next: [56/80] diagonal 200 cm, height 130 cm (x 141.4   y 141.4   z 130 cm) - waiting for the phone button

[56/80] z130-D200  diagonal 200 cm, height 130 cm
true position (141.4, 141.4, 130.0) cm: distance 238.5 cm, azimuth 45.0 deg, elevation 33.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 516.0  Mic1 554.3  Mic4 1032.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     25.9     1.02    16.8    29.0     2.1     97  -40.0     0

next: [57/80] in-between 1, height 130 cm (x 18   y 46.5   z 130 cm) - waiting for the phone button

[57/80] z130-M1  in-between 1, height 130 cm
true position (18.0, 46.5, 130.0) cm: distance 139.2 cm, azimuth 68.8 deg, elevation 69.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 126.5  Mic3 288.1  Mic4 406.1
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     1      9.1     0.76    49.0    56.6     0.6    115  -38.3     0

next: [58/80] in-between 2, height 130 cm (x 33.3   y 78.5   z 130 cm) - waiting for the phone button

[58/80] z130-M2  in-between 2, height 130 cm
true position (33.3, 78.5, 130.0) cm: distance 155.5 cm, azimuth 67.0 deg, elevation 56.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 211.4  Mic3 439.4  Mic4 631.7
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     20.2     0.60    20.1    26.6     1.6    150  -38.5     0

next: [59/80] in-between 3, height 130 cm (x 31   y 126   z 130 cm) - waiting for the phone button

[59/80] z130-M3  in-between 3, height 130 cm
true position (31.0, 126.0, 130.0) cm: distance 183.7 cm, azimuth 76.2 deg, elevation 45.1 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 178.3  Mic3 598.8  Mic4 758.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     19.8     0.81    42.7    48.4     1.6     89  -39.5     0

next: [60/80] in-between 4, height 130 cm (x 78.5   y 117.8   z 130 cm) - waiting for the phone button

[60/80] z130-M4  in-between 4, height 130 cm
true position (78.5, 117.8, 130.0) cm: distance 192.2 cm, azimuth 56.3 deg, elevation 42.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 392.3  Mic3 536.5  Mic4 894.1
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     25.8     0.89    11.9    22.2     2.0     69  -39.8     0

next: [61/80] in-between 5, height 130 cm (x 44   y 162   z 130 cm) - waiting for the phone button

[61/80] z130-M5  in-between 5, height 130 cm
true position (44.0, 162.0, 130.0) cm: distance 212.3 cm, azimuth 74.8 deg, elevation 37.8 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 216.1  Mic3 667.0  Mic4 861.3
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     21.7     0.76    12.5    17.0     1.7    104  -39.8     0

next: [62/80] in-between 6, height 130 cm (x 110   y 158.5   z 130 cm) - waiting for the phone button

[62/80] z130-M6  in-between 6, height 130 cm
true position (110.0, 158.5, 130.0) cm: distance 232.6 cm, azimuth 55.2 deg, elevation 34.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 452.2  Mic3 595.9  Mic4 1011.1
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     25.8     1.02    12.6    19.3     2.1     67  -40.1     0

next: [63/80] in-between 7, height 130 cm (x 41.8   y 206   z 130 cm) - waiting for the phone button

[63/80] z130-M7  in-between 7, height 130 cm
true position (41.8, 206.0, 130.0) cm: distance 247.2 cm, azimuth 78.5 deg, elevation 31.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 183.1  Mic3 728.0  Mic4 893.7
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    55     0     24.0     1.28    51.2    65.7     1.9     80  -40.4     0

next: [64/80] in-between 8, height 130 cm (x 125   y 214   z 130 cm) - waiting for the phone button

[64/80] z130-M8  in-between 8, height 130 cm
true position (125.0, 214.0, 130.0) cm: distance 279.9 cm, azimuth 59.7 deg, elevation 27.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 430.5  Mic3 667.7  Mic4 1065.1
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    15     0     26.2     1.13    39.3    43.9     2.1     55  -40.8     0

next: [65/80] y axis 50 cm, height 170 cm (x 0   y 50   z 170 cm) - waiting for the phone button

[65/80] z170-Y050  y axis 50 cm, height 170 cm
true position (0.0, 50.0, 170.0) cm: distance 177.2 cm, azimuth 90.0 deg, elevation 73.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 9.3  Mic3 244.4  Mic4 253.3
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    90     0      9.9     1.49   441.7   447.4     0.8    123  -40.4     0

next: [66/80] y axis 100 cm, height 170 cm (x 0   y 100   z 170 cm) - waiting for the phone button

[66/80] z170-Y100  y axis 100 cm, height 170 cm
true position (0.0, 100.0, 170.0) cm: distance 197.2 cm, azimuth 90.0 deg, elevation 59.5 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 17.0  Mic3 440.2  Mic4 456.0
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     18.1     1.17   501.3   503.1     1.4    122  -40.1     0

next: [67/80] y axis 150 cm, height 170 cm (x 0   y 150   z 170 cm) - waiting for the phone button

[67/80] z170-Y150  y axis 150 cm, height 170 cm
true position (0.0, 150.0, 170.0) cm: distance 226.7 cm, azimuth 90.0 deg, elevation 48.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 22.3  Mic3 575.5  Mic4 596.0
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     20.0     1.12   571.7   575.3     1.6    109  -40.2     0

next: [68/80] y axis 200 cm, height 170 cm (x 0   y 200   z 170 cm) - waiting for the phone button

[68/80] z170-Y200  y axis 200 cm, height 170 cm
true position (0.0, 200.0, 170.0) cm: distance 262.5 cm, azimuth 90.0 deg, elevation 40.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 25.8  Mic3 663.5  Mic4 687.1
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    95     0     22.1     1.22   515.6   518.5     1.8     91  -39.8     0

next: [69/80] diagonal 50 cm, height 170 cm (x 35.4   y 35.4   z 170 cm) - waiting for the phone button

[69/80] z170-D050  diagonal 50 cm, height 170 cm
true position (35.4, 35.4, 170.0) cm: distance 177.2 cm, azimuth 45.0 deg, elevation 73.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 169.4  Mic1 182.2  Mic4 345.9
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    15     0     17.7     1.09    49.9    66.0     1.4    130  -39.9     0

next: [70/80] diagonal 100 cm, height 170 cm (x 70.7   y 70.7   z 170 cm) - waiting for the phone button

[70/80] z170-D100  diagonal 100 cm, height 170 cm
true position (70.7, 70.7, 170.0) cm: distance 197.2 cm, azimuth 45.0 deg, elevation 59.5 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 307.9  Mic1 331.0  Mic4 622.1
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                              106  -39.5     0

next: [71/80] diagonal 150 cm, height 170 cm (x 106.1   y 106.1   z 170 cm) - waiting for the phone button

[71/80] z170-D150  diagonal 150 cm, height 170 cm
true position (106.1, 106.1, 170.0) cm: distance 226.7 cm, azimuth 45.0 deg, elevation 48.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 404.1  Mic1 434.3  Mic4 813.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    30     0     25.4     1.22    42.9    56.5     2.1     81  -39.9     0

next: [72/80] diagonal 200 cm, height 170 cm (x 141.4   y 141.4   z 170 cm) - waiting for the phone button

[72/80] z170-D200  diagonal 200 cm, height 170 cm
true position (141.4, 141.4, 170.0) cm: distance 262.5 cm, azimuth 45.0 deg, elevation 40.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 465.8  Mic1 500.6  Mic4 937.6
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                               82  -40.0     0

next: [73/80] in-between 1, height 170 cm (x 18   y 46.5   z 170 cm) - waiting for the phone button

[73/80] z170-M1  in-between 1, height 170 cm
true position (18.0, 46.5, 170.0) cm: distance 177.2 cm, azimuth 68.8 deg, elevation 73.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 98.5  Mic3 226.0  Mic4 320.3
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    95     0     10.6     1.32   111.4   122.0     0.7     40  -40.2     0

next: [74/80] in-between 2, height 170 cm (x 33.3   y 78.5   z 170 cm) - waiting for the phone button

[74/80] z170-M2  in-between 2, height 170 cm
true position (33.3, 78.5, 170.0) cm: distance 190.2 cm, azimuth 67.0 deg, elevation 63.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 170.4  Mic3 357.4  Mic4 517.3
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    80     2     16.5     1.49    33.9    57.2     1.3     76  -40.2     0

next: [75/80] in-between 3, height 170 cm (x 31   y 126   z 170 cm) - waiting for the phone button

[75/80] z170-M3  in-between 3, height 170 cm
true position (31.0, 126.0, 170.0) cm: distance 213.9 cm, azimuth 76.2 deg, elevation 52.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 151.0  Mic3 512.6  Mic4 651.8
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    95     0     19.6     1.06    64.4    79.8     1.5     76  -40.0     0

next: [76/80] in-between 4, height 170 cm (x 78.5   y 117.8   z 170 cm) - waiting for the phone button

[76/80] z170-M4  in-between 4, height 170 cm
true position (78.5, 117.8, 170.0) cm: distance 221.2 cm, azimuth 56.3 deg, elevation 50.2 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 337.1  Mic3 462.6  Mic4 776.9
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    70     0     22.1     1.13    35.3    46.5     1.8     79  -39.7     0

next: [77/80] in-between 5, height 170 cm (x 44   y 162   z 170 cm) - waiting for the phone button

[77/80] z170-M5  in-between 5, height 170 cm
true position (44.0, 162.0, 170.0) cm: distance 238.9 cm, azimuth 74.8 deg, elevation 45.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 189.9  Mic3 590.9  Mic4 765.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    15     0     22.0     0.77    69.4    74.8     1.8     68  -40.7     0

next: [78/80] in-between 6, height 170 cm (x 110   y 158.5   z 170 cm) - waiting for the phone button

[78/80] z170-M6  in-between 6, height 170 cm
true position (110.0, 158.5, 170.0) cm: distance 257.1 cm, azimuth 55.2 deg, elevation 41.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 405.9  Mic3 536.0  Mic4 914.6
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                               71  -40.2     0

next: [79/80] in-between 7, height 170 cm (x 41.8   y 206   z 170 cm) - waiting for the phone button

[79/80] z170-M7  in-between 7, height 170 cm
true position (41.8, 206.0, 170.0) cm: distance 270.3 cm, azimuth 78.5 deg, elevation 39.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 166.0  Mic3 664.3  Mic4 817.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     5     0     21.3     0.00    79.1    79.1     1.7     57  -40.1     0

next: [80/80] in-between 8, height 170 cm (x 125   y 214   z 170 cm) - waiting for the phone button

[80/80] z170-M8  in-between 8, height 170 cm
true position (125.0, 214.0, 170.0) cm: distance 300.5 cm, azimuth 59.7 deg, elevation 34.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 398.7  Mic3 619.7  Mic4 991.7
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                               58  -40.7     0

all points done - waiting for Finish (or Redo previous) on the phone

series finished

measured in this session:
z010-Y050    y axis 50 cm     z  10: ok 20/20  pos err 597.4 cm (p90 597.9)  dir err 10.95 deg
z010-Y050    y axis 50 cm     z  10: ok 20/20  pos err 597.2 cm (p90 597.7)  dir err 10.95 deg  [redo]
z010-Y050    y axis 50 cm     z  10: ok 20/20  pos err 597.5 cm (p90 598.1)  dir err 11.04 deg  [redo]
z010-Y050    y axis 50 cm     z  10: ok 20/20  pos err 597.4 cm (p90 598.0)  dir err 11.07 deg  [redo]
z010-Y100    y axis 100 cm    z  10: ok 20/20  pos err 523.3 cm (p90 523.9)  dir err 10.02 deg
z010-Y150    y axis 150 cm    z  10: ok 20/20  pos err 462.6 cm (p90 463.6)  dir err  7.62 deg
z010-Y200    y axis 200 cm    z  10: ok 20/20  pos err 409.5 cm (p90 410.6)  dir err  6.93 deg
z010-D050    diagonal 50 cm   z  10: ok 20/20  pos err   3.0 cm (p90   3.1)  dir err  4.22 deg
z010-D100    diagonal 100 cm  z  10: ok 20/20  pos err  19.4 cm (p90  20.3)  dir err  5.98 deg
z010-D150    diagonal 150 cm  z  10: ok 20/20  pos err  18.9 cm (p90  20.0)  dir err  6.54 deg
z010-D200    diagonal 200 cm  z  10: ok 19/20  pos err  21.7 cm (p90  23.3)  dir err  6.07 deg
z010-M1      in-between 1     z  10: ok 20/20  pos err   3.7 cm (p90   3.8)  dir err  6.81 deg
z010-M2      in-between 2     z  10: ok 20/20  pos err  11.4 cm (p90  12.2)  dir err  5.44 deg
z010-M3      in-between 3     z  10: ok 19/20  pos err  23.8 cm (p90  25.9)  dir err  7.80 deg
z010-M4      in-between 4     z  10: ok 20/20  pos err  17.6 cm (p90  18.2)  dir err  6.13 deg
z010-M5      in-between 5     z  10: ok 20/20  pos err  27.5 cm (p90  31.7)  dir err  6.93 deg
z010-M6      in-between 6     z  10: ok 20/20  pos err  19.7 cm (p90  21.2)  dir err  5.92 deg
z010-M7      in-between 7     z  10: ok 20/20  pos err  42.4 cm (p90  52.1)  dir err  6.83 deg
z010-M8      in-between 8     z  10: ok 11/20  pos err  22.1 cm (p90  30.6)  dir err  4.90 deg
z050-Y050    y axis 50 cm     z  50: ok 20/20  pos err 740.9 cm (p90 744.5)  dir err  2.88 deg
z050-Y100    y axis 100 cm    z  50: ok 20/20  pos err  85.2 cm (p90 568.4)  dir err  2.43 deg
z050-Y150    y axis 150 cm    z  50: ok 20/20  pos err 264.9 cm (p90 475.1)  dir err  2.30 deg
z050-Y200    y axis 200 cm    z  50: ok 16/20  pos err 414.0 cm (p90 415.1)  dir err  2.22 deg
z050-D050    diagonal 50 cm   z  50: ok 20/20  pos err   4.6 cm (p90   5.1)  dir err  2.66 deg
z050-D100    diagonal 100 cm  z  50: ok 20/20  pos err   4.5 cm (p90   4.8)  dir err  2.29 deg
z050-D150    diagonal 150 cm  z  50: ok 20/20  pos err  24.7 cm (p90  27.5)  dir err  2.10 deg
z050-D200    diagonal 200 cm  z  50: ok  1/20  pos err  56.1 cm (p90  56.1)  dir err  2.05 deg
z050-M1      in-between 1     z  50: ok 20/20  pos err   3.1 cm (p90   3.8)  dir err  1.00 deg
z050-M2      in-between 2     z  50: ok 20/20  pos err   3.6 cm (p90   4.4)  dir err  1.85 deg
z050-M3      in-between 3     z  50: ok 20/20  pos err   7.0 cm (p90  10.0)  dir err  1.77 deg
z050-M4      in-between 4     z  50: ok 20/20  pos err  13.1 cm (p90  15.6)  dir err  1.94 deg
z050-M5      in-between 5     z  50: ok 20/20  pos err  30.7 cm (p90  39.0)  dir err  1.72 deg
z050-M6      in-between 6     z  50: ok  0/20  NO GOOD DETECTION
z050-M7      in-between 7     z  50: ok  0/20  NO GOOD DETECTION
z050-M8      in-between 8     z  50: ok  0/20  NO GOOD DETECTION
z090-Y050    y axis 50 cm     z  90: ok 20/20  pos err 574.3 cm (p90 576.9)  dir err  1.51 deg
z090-Y100    y axis 100 cm    z  90: ok 20/20  pos err 642.5 cm (p90 678.0)  dir err  1.71 deg
z090-Y150    y axis 150 cm    z  90: ok 20/20  pos err 522.7 cm (p90 524.6)  dir err  1.89 deg
z090-Y150    y axis 150 cm    z  90: ok 20/20  pos err 522.2 cm (p90 525.5)  dir err  1.89 deg  [redo]
z090-Y150    y axis 150 cm    z  90: ok 20/20  pos err 505.7 cm (p90 524.7)  dir err  1.89 deg  [redo]
z090-Y150    y axis 150 cm    z  90: ok 20/20  pos err 522.4 cm (p90 525.3)  dir err  1.89 deg  [redo]
z090-Y150    y axis 150 cm    z  90: ok 20/20  pos err 523.0 cm (p90 525.6)  dir err  1.89 deg  [redo]
z090-Y200    y axis 200 cm    z  90: ok 20/20  pos err 377.4 cm (p90 441.0)  dir err  2.05 deg
z090-D050    diagonal 50 cm   z  90: ok 20/20  pos err  18.0 cm (p90  19.5)  dir err  1.77 deg
z090-D100    diagonal 100 cm  z  90: ok 20/20  pos err   8.1 cm (p90   8.8)  dir err  2.09 deg
z090-D100    diagonal 100 cm  z  90: ok 20/20  pos err   7.1 cm (p90   9.1)  dir err  2.06 deg  [redo]
z090-D150    diagonal 150 cm  z  90: ok 20/20  pos err   9.8 cm (p90  13.5)  dir err  2.07 deg
z090-D200    diagonal 200 cm  z  90: ok 20/20  pos err  17.2 cm (p90  24.4)  dir err  2.27 deg
z090-M1      in-between 1     z  90: ok 20/20  pos err  12.3 cm (p90  15.3)  dir err  0.58 deg
z090-M2      in-between 2     z  90: ok 20/20  pos err  12.9 cm (p90  15.1)  dir err  1.59 deg
z090-M3      in-between 3     z  90: ok 20/20  pos err   7.5 cm (p90   9.7)  dir err  1.59 deg
z090-M4      in-between 4     z  90: ok 20/20  pos err  60.8 cm (p90  64.4)  dir err 18.16 deg
z090-M5      in-between 5     z  90: ok 19/20  pos err  57.0 cm (p90  60.7)  dir err 15.73 deg
z090-M5      in-between 5     z  90: ok 20/20  pos err   7.9 cm (p90  13.7)  dir err  1.67 deg  [redo]
z090-M6      in-between 6     z  90: ok 20/20  pos err  10.4 cm (p90  18.6)  dir err  1.99 deg
z090-M7      in-between 7     z  90: ok 19/20  pos err  18.1 cm (p90  28.8)  dir err  1.84 deg
z090-M8      in-between 8     z  90: ok  0/20  NO GOOD DETECTION
z130-Y050    y axis 50 cm     z 130: ok 20/20  pos err 500.8 cm (p90 502.0)  dir err  1.09 deg
z130-Y100    y axis 100 cm    z 130: ok 20/20  pos err 589.6 cm (p90 591.3)  dir err  1.54 deg
z130-Y150    y axis 150 cm    z 130: ok 20/20  pos err 183.4 cm (p90 595.4)  dir err  1.60 deg
z130-Y200    y axis 200 cm    z 130: ok 19/20  pos err 471.1 cm (p90 472.8)  dir err  1.92 deg
z130-D050    diagonal 50 cm   z 130: ok 20/20  pos err  43.8 cm (p90  49.7)  dir err  1.70 deg
z130-D100    diagonal 100 cm  z 130: ok 20/20  pos err  22.4 cm (p90  28.3)  dir err  1.89 deg
z130-D150    diagonal 150 cm  z 130: ok 20/20  pos err  12.3 cm (p90  18.7)  dir err  2.20 deg
z130-D200    diagonal 200 cm  z 130: ok 20/20  pos err  16.8 cm (p90  29.0)  dir err  2.10 deg
z130-M1      in-between 1     z 130: ok 20/20  pos err  49.0 cm (p90  56.6)  dir err  0.64 deg
z130-M2      in-between 2     z 130: ok 20/20  pos err  20.1 cm (p90  26.6)  dir err  1.58 deg
z130-M3      in-between 3     z 130: ok 20/20  pos err  42.7 cm (p90  48.4)  dir err  1.57 deg
z130-M4      in-between 4     z 130: ok 20/20  pos err  11.9 cm (p90  22.2)  dir err  2.05 deg
z130-M5      in-between 5     z 130: ok 20/20  pos err  12.5 cm (p90  17.0)  dir err  1.70 deg
z130-M6      in-between 6     z 130: ok 20/20  pos err  12.6 cm (p90  19.3)  dir err  2.05 deg
z130-M7      in-between 7     z 130: ok 11/20  pos err  51.2 cm (p90  65.7)  dir err  1.93 deg
z130-M8      in-between 8     z 130: ok  3/20  pos err  39.3 cm (p90  43.9)  dir err  2.12 deg
z170-Y050    y axis 50 cm     z 170: ok 18/20  pos err 441.7 cm (p90 447.4)  dir err  0.76 deg
z170-Y100    y axis 100 cm    z 170: ok 20/20  pos err 501.3 cm (p90 503.1)  dir err  1.43 deg
z170-Y150    y axis 150 cm    z 170: ok 20/20  pos err 571.7 cm (p90 575.3)  dir err  1.60 deg
z170-Y200    y axis 200 cm    z 170: ok 19/20  pos err 515.6 cm (p90 518.5)  dir err  1.82 deg
z170-D050    diagonal 50 cm   z 170: ok  3/20  pos err  49.9 cm (p90  66.0)  dir err  1.44 deg
z170-D100    diagonal 100 cm  z 170: ok  0/20  NO GOOD DETECTION
z170-D150    diagonal 150 cm  z 170: ok  6/20  pos err  42.9 cm (p90  56.5)  dir err  2.05 deg
z170-D200    diagonal 200 cm  z 170: ok  0/20  NO GOOD DETECTION
z170-M1      in-between 1     z 170: ok 19/20  pos err 111.4 cm (p90 122.0)  dir err  0.75 deg
z170-M2      in-between 2     z 170: ok 16/20  pos err  33.9 cm (p90  57.2)  dir err  1.30 deg
z170-M3      in-between 3     z 170: ok 19/20  pos err  64.4 cm (p90  79.8)  dir err  1.52 deg
z170-M4      in-between 4     z 170: ok 14/20  pos err  35.3 cm (p90  46.5)  dir err  1.75 deg
z170-M5      in-between 5     z 170: ok  3/20  pos err  69.4 cm (p90  74.8)  dir err  1.80 deg
z170-M6      in-between 6     z 170: ok  0/20  NO GOOD DETECTION
z170-M7      in-between 7     z 170: ok  1/20  pos err  79.1 cm (p90  79.1)  dir err  1.73 deg
z170-M8      in-between 8     z 170: ok  0/20  NO GOOD DETECTION
```

## 2026-11-18 13:00 — distance series distance_v2 / a30 (array as stored cm)

- command (in `/home/nadasmartin/okos_lab_project/host`): `python series.py --series a30 --points zz`
- duration: 0 s, exited (unknown point id(s): zz)
- code: `279d0f0fa7bb` (copy: `docs/code_snapshots/2026-11-18_1300_279d0f0fa7bb/`)

## 2026-11-18 13:10 — Distance series a30 (30 cm array): results and first reading

**What ran.**
- Run time: 11:49–12:59, all 80 points of plan `distance_v2` (the user's grid).
- Settings: 20 × chirp 3–12 kHz / 50 ms per point, left channel, gain 0 dB, rotation +2.13°.
- Firmware `9587b9dbc09c`, code `d219b4897885`.
- Raw data: `host/bench_results/series/distance_v2/a30/` (89 files; 9 are redos).
- Redone points: z010-Y050 (3×), z090-Y150 (4×), z090-D100, z090-M5. The analysis uses the newest file of each point.
- Phone volume: fixed by the user, level not recorded. Temperature: not measured, 21 °C assumed.

**Analysis.**
- Command: `python analyze_series.py --series a30` (in `host/`). The full table is reproducible with that command.
- Figure: `host/bench_results/series/distance_v2/figures/error_vs_distance.png`.
- Rejection breakdown: one-off script over the event fields `misfit_us`, `q`, `dir_az`, `dir_el`. The numbers below come from it.

**Findings.**
1. **Diagonal and in-between points give a usable 3D position up to about 2–2.5 m.** This holds at z = 50 and 90 cm.
   - Mean position error 3–5 cm within about 1.1 m (z = 50).
   - About 7–20 cm out to 2.3 m (z = 90).
   - z = 130: 13–45 cm.
   - z = 170: 35–110 cm.
   - Error rises with elevation, as the geometry predicts: steep sources hide the distance from a planar array. The `geom` column rises from about 2 to over 30 cm/µs.
   - The distance error is mostly negative (measured closer than true) at z ≥ 90.
2. **Y axis (x = 0, the blind plane): distance fails completely, direction does not.**
   - All 20 Y points have a range error of +300…+740 cm; the solver runs out to its bound.
   - Direction error is 1–3° at z ≥ 50.
   - This confirms the prediction logged at 09:40. With one independent TDOA across x, distance is not observable there.
   - Consequence: about half the directions around a square array are near a blind plane (x = 0 or y = 0, up to a rotation of the setup). Position near them should be reported as direction only.
3. **Direction is the robust quantity.**
   - At z ≥ 50 the median direction error is 0.6–2.3° at every accepted point, including all Y points and the farthest points (2.8–3 m).
   - It does not grow noticeably with distance. The ~2° floor looks like a systematic bias (placement, speaker offset, residual geometry), not noise; the p95 is only about 0.1° above the median.
4. **z = 10 cm is special: direction error 4–11°.**
   - The source is almost in the mic plane (elevation 2–11°).
   - The mic plane is only 4 cm above the floor, so the floor reflection arrives almost together with the direct sound.
   - Position on D/M at z = 10 is still 3–40 cm.
5. **Success rate.**
   - 100 % at almost every point up to about 2 m and z ≤ 130.
   - Drops at the far corners (M6–M8 at z = 50: 0 %; M8 at z = 90: 0 %) and at most points at z = 170 (0–30 % on D, M5–M8).
   - Cause:
     - the matched-filter quality `q` sits at the 0.2 threshold (median 0.14–0.21 at the failing points);
     - and/or the six delays disagree (misfit 15–350 µs vs the 10 µs limit), i.e. reflections, furniture.
   - The received level was about −40 dB at every point (phone volume fixed), so it is not plain loudness.
   - **The rejected chirps still give the direction.** Median direction error of rejected chirps at the failing points is 1.5–8° (one exception: z050-M8 30°, misfit 346 µs). So far away, or with reflections, the array still knows the direction but not a consistent position. This is the user's "only direction" regime.
6. **One suspected placement error:** z090-M4 has an 18° direction error and 60 cm position error, while every neighbour is about 2°.
   - z090-M5 showed the same symptom (16°) and its redo gave 1.7°.
   - Proposed: re-measure z090-M4 before the layout change. `series.py` gained `--points` for this (13:05).
7. **Fraunhofer distance** (30 cm, 7.5 kHz) is 394 cm (side) / 787 cm (diagonal). Every point lies inside it (near field), so the range cue exists in principle. The position failures here come from elevation and the blind plane, not from the far-field limit.

**Code change (13:05):** `host/series.py` gained `--points id,id,...` to measure selected points again. A new file supersedes the old one, as with a redo.

## 2026-11-18 13:25 — a30: z090-M4 excluded (user's placement mistake); layout changed to 20 cm; series a20 started

**Exclusion of z090-M4.**
- The user confirmed that the phone was at the wrong position for a30 z090-M4. The 18° direction error noted in the 13:10 entry (finding 6) is explained by that.
- Decision (user): leave it out of all evaluations; do not re-measure.
- How:
  - new file `host/bench_results/series/distance_v2/excluded.json` lists it with the reason, who decided and the date;
  - `host/analyze_series.py` now reads that file (`load_excluded`), prints every excluded point and skips it;
  - the raw file stays on disk.
- a30 is now evaluated on 79 points. The findings of the 13:10 entry are unchanged; finding 6 is settled.

**Layout change: 30 → 20 cm.**
- The user rebuilt the mic square at 20 cm side, putting it back in place (same origin, same orientation, same mic numbering) as precisely as possible.
- **Not calibrated separately (user's choice):** the rotation +2.13° fitted on the 30 cm layout is assumed to hold. Any placement or rotation difference is therefore part of the a20 errors. A rotation fit on a20 (as `analyze_sweeps.py` did for the 30 cm array) can check this afterwards.
- Unchanged: phone volume (same as a30), left channel, chirp 3–12 kHz / 50 ms, 20 chirps per point, plan `distance_v2`, temperature 21 °C assumed.

**Run started (13:20),** in `host/`:
`python series.py --series a20 --array 20 --rot 2.13 --channel left --temp 21 --note "..."`
- Startup:
  - firmware `9587b9dbc09c` = the sources on disk;
  - 44239 Hz/mic;
  - mics Mic1 (−10.4, +9.6), Mic2 (+9.6, +10.4), Mic3 (+10.4, −9.6), Mic4 (−9.6, −10.4) cm.
- Fraunhofer distance (20 cm, 7.5 kHz): 175 cm (side) / 350 cm (diagonal). The far points (≥ 175 cm) are now beyond the side-based value.

## 2026-11-18 16:34 — distance series distance_v2 / a20 (array 20.0 cm)

- command (in `/home/nadasmartin/okos_lab_project/host`): `python series.py --series a20 --array 20 --rot 2.13 --channel left --temp 21 --note '20 cm layout; array put back in place as precisely as possible by the user, not calibrated separately: rotation +2.13 deg from the 30 cm fit assumed; same phone volume as a30 (level not given); temperature not measured, 21 C assumed; speaker aimed at the array'`
- duration: 2973 s, finished
- code: `704e78049795` (copy: `docs/code_snapshots/2026-11-18_1548_704e78049795/`)
- notes: 20 cm layout; array put back in place as precisely as possible by the user, not calibrated separately: rotation +2.13 deg from the 30 cm fit assumed; same phone volume as a30 (level not given); temperature not measured, 21 C assumed; speaker aimed at the array

```
plan distance_v2, series a20: 80 of 80 points to measure; signal chirp_3-12k_50ms, 20 x every 0.5 s, gain 0 dB, channel left
mic square 20 cm, rotated +2.13 deg: Mic1 (-10.4,+9.6)  Mic2 (+9.6,+10.4)  Mic3 (+10.4,-9.6)  Mic4 (-9.6,-10.4)
ESP32 firmware 9587b9dbc09c = the firmware sources on disk
ESP32: 44239 Hz/mic, mic delays [0.0, 0.0, 0.0, 0.0] us, 21 C -> c = 344.0 m/s

Open on the phone (same Wi-Fi):  http://192.168.1.76:8765/
waiting for the phone to tap 'Start audio' ...
phone ready (192.168.1.97)

next: [1/80] y axis 50 cm, height 10 cm (x 0   y 50   z 10 cm) - waiting for the phone button

[1/80] z010-Y050  y axis 50 cm, height 10 cm
true position (0.0, 50.0, 10.0) cm: distance 51.0 cm, azimuth 90.0 deg, elevation 11.3 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 25.5  Mic3 562.2  Mic4 579.8
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     20.7     0.29   583.9   584.7     8.0    661  -30.5     0

next: [2/80] y axis 100 cm, height 10 cm (x 0   y 100   z 10 cm) - waiting for the phone button

[2/80] z010-Y100  y axis 100 cm, height 10 cm
true position (0.0, 100.0, 10.0) cm: distance 100.5 cm, azimuth 90.0 deg, elevation 5.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 23.7  Mic3 577.3  Mic4 596.8
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     21.0     0.75   519.2   521.0     9.0    222  -36.0     0

next: [3/80] y axis 150 cm, height 10 cm (x 0   y 150   z 10 cm) - waiting for the phone button

[3/80] z010-Y150  y axis 150 cm, height 10 cm
true position (0.0, 150.0, 10.0) cm: distance 150.3 cm, azimuth 90.0 deg, elevation 3.8 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 23.0  Mic3 579.8  Mic4 600.0
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     1     21.4     0.63   466.3   467.2     8.8    192  -37.5     0

next: [4/80] y axis 200 cm, height 10 cm (x 0   y 200   z 10 cm) - waiting for the phone button

[4/80] z010-Y200  y axis 200 cm, height 10 cm
true position (0.0, 200.0, 10.0) cm: distance 200.2 cm, azimuth 90.0 deg, elevation 2.9 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 22.7  Mic3 580.6  Mic4 601.1
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     20.9     0.75   414.7   415.7     8.6    162  -38.1     0

next: [5/80] diagonal 50 cm, height 10 cm (x 35.4   y 35.4   z 10 cm) - waiting for the phone button

[5/80] z010-D050  diagonal 50 cm, height 10 cm
true position (35.4, 35.4, 10.0) cm: distance 51.1 cm, azimuth 45.0 deg, elevation 11.3 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 441.1  Mic1 470.0  Mic4 804.4
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     21.9     0.33     4.7     4.8     4.5    474  -30.1     0

next: [6/80] diagonal 100 cm, height 10 cm (x 70.7   y 70.7   z 10 cm) - waiting for the phone button

[6/80] z010-D100  diagonal 100 cm, height 10 cm
true position (70.7, 70.7, 10.0) cm: distance 100.5 cm, azimuth 45.0 deg, elevation 5.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 422.1  Mic1 452.2  Mic4 817.4
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     20.8     0.69    21.0    22.7     6.5    207  -36.2     0

next: [7/80] diagonal 150 cm, height 10 cm (x 106.1   y 106.1   z 10 cm) - waiting for the phone button

[7/80] z010-D150  diagonal 150 cm, height 10 cm
true position (106.1, 106.1, 10.0) cm: distance 150.4 cm, azimuth 45.0 deg, elevation 3.8 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 413.8  Mic1 444.2  Mic4 819.7
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     19.1     0.71    28.5    30.6     8.0    162  -37.0     0

next: [8/80] diagonal 200 cm, height 10 cm (x 141.4   y 141.4   z 10 cm) - waiting for the phone button

[8/80] z010-D200  diagonal 200 cm, height 10 cm
true position (141.4, 141.4, 10.0) cm: distance 200.2 cm, azimuth 45.0 deg, elevation 2.9 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 409.5  Mic1 439.9  Mic4 820.6
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     15.9     3.18    36.5    46.0     8.5    131  -37.5     0

next: [9/80] in-between 1, height 10 cm (x 18   y 46.5   z 10 cm) - waiting for the phone button

[8/80] z010-D200  diagonal 200 cm, height 10 cm  (REDO)
true position (141.4, 141.4, 10.0) cm: distance 200.2 cm, azimuth 45.0 deg, elevation 2.9 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 409.5  Mic1 439.9  Mic4 820.6
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    95     0     17.4     0.92    31.6    35.0     8.4    127  -37.5     0

next: [9/80] in-between 1, height 10 cm (x 18   y 46.5   z 10 cm) - waiting for the phone button

[9/80] z010-M1  in-between 1, height 10 cm
true position (18.0, 46.5, 10.0) cm: distance 50.9 cm, azimuth 68.8 deg, elevation 11.3 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 266.5  Mic3 555.1  Mic4 743.7
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      9.7     0.43     4.3     4.6     5.7    386  -30.8     0

next: [10/80] in-between 2, height 10 cm (x 33.3   y 78.5   z 10 cm) - waiting for the phone button

[10/80] z010-M2  in-between 2, height 10 cm
true position (33.3, 78.5, 10.0) cm: distance 85.9 cm, azimuth 67.0 deg, elevation 6.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 271.5  Mic3 546.0  Mic4 766.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     18.3     0.54    15.9    16.9     6.8    166  -35.8     0

next: [11/80] in-between 3, height 10 cm (x 31   y 126   z 10 cm) - waiting for the phone button

[11/80] z010-M3  in-between 3, height 10 cm
true position (31.0, 126.0, 10.0) cm: distance 130.1 cm, azimuth 76.2 deg, elevation 4.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 171.4  Mic3 567.6  Mic4 715.6
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     18.5     0.72    26.0    29.7     8.4    148  -36.9     0

next: [12/80] in-between 4, height 10 cm (x 78.5   y 117.8   z 10 cm) - waiting for the phone button

[11/80] z010-M3  in-between 3, height 10 cm  (REDO)
true position (31.0, 126.0, 10.0) cm: distance 130.1 cm, azimuth 76.2 deg, elevation 4.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 171.4  Mic3 567.6  Mic4 715.6
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     19.0     0.73    27.5    30.6     8.5    160  -36.7     0

next: [12/80] in-between 4, height 10 cm (x 78.5   y 117.8   z 10 cm) - waiting for the phone button

[12/80] z010-M4  in-between 4, height 10 cm
true position (78.5, 117.8, 10.0) cm: distance 141.9 cm, azimuth 56.3 deg, elevation 4.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 358.8  Mic3 489.2  Mic4 809.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     20.0     0.76    28.1    32.1     8.2    128  -36.9     0

next: [13/80] in-between 5, height 10 cm (x 44   y 162   z 10 cm) - waiting for the phone button

[13/80] z010-M5  in-between 5, height 10 cm
true position (44.0, 162.0, 10.0) cm: distance 168.2 cm, azimuth 74.8 deg, elevation 3.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 182.8  Mic3 563.0  Mic4 726.2
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     17.9     0.74    40.2    43.8     8.1    139  -37.4     0

next: [14/80] in-between 6, height 10 cm (x 110   y 158.5   z 10 cm) - waiting for the phone button

[14/80] z010-M6  in-between 6, height 10 cm
true position (110.0, 158.5, 10.0) cm: distance 193.2 cm, azimuth 55.2 deg, elevation 3.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 363.0  Mic3 478.5  Mic4 812.8
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     18.9     0.86    38.6    45.3     8.4     90  -37.9     0

next: [15/80] in-between 7, height 10 cm (x 41.8   y 206   z 10 cm) - waiting for the phone button

[15/80] z010-M7  in-between 7, height 10 cm
true position (41.8, 206.0, 10.0) cm: distance 210.4 cm, azimuth 78.5 deg, elevation 2.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 143.0  Mic3 570.1  Mic4 700.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     5     0     19.2     0.00   105.9   105.9     8.3     87  -37.9     0

next: [16/80] in-between 8, height 10 cm (x 125   y 214   z 10 cm) - waiting for the phone button

[16/80] z010-M8  in-between 8, height 10 cm
true position (125.0, 214.0, 10.0) cm: distance 248.0 cm, azimuth 59.7 deg, elevation 2.3 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 322.1  Mic3 500.8  Mic4 801.7
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    10     2     21.8     0.50    72.2    75.4     8.9     70  -38.2     0

next: [17/80] y axis 50 cm, height 50 cm (x 0   y 50   z 50 cm) - waiting for the phone button

[17/80] z050-Y050  y axis 50 cm, height 50 cm
true position (0.0, 50.0, 50.0) cm: distance 70.7 cm, azimuth 90.0 deg, elevation 45.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 16.7  Mic3 406.2  Mic4 419.9
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     12.9     0.34    63.0    63.1     2.4    525  -31.2     0

next: [18/80] y axis 100 cm, height 50 cm (x 0   y 100   z 50 cm) - waiting for the phone button

[17/80] z050-Y050  y axis 50 cm, height 50 cm  (REDO)
true position (0.0, 50.0, 50.0) cm: distance 70.7 cm, azimuth 90.0 deg, elevation 45.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 16.7  Mic3 406.2  Mic4 419.9
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     1     12.8     0.33    63.0    63.1     2.4    507  -31.5     0

next: [18/80] y axis 100 cm, height 50 cm (x 0   y 100   z 50 cm) - waiting for the phone button

[18/80] z050-Y100  y axis 100 cm, height 50 cm
true position (0.0, 100.0, 50.0) cm: distance 111.8 cm, azimuth 90.0 deg, elevation 26.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 20.9  Mic3 518.7  Mic4 536.5
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     1     16.2     0.40    93.5   564.8     2.2    388  -34.0     0

next: [19/80] y axis 150 cm, height 50 cm (x 0   y 150   z 50 cm) - waiting for the phone button

[19/80] z050-Y150  y axis 150 cm, height 50 cm
true position (0.0, 150.0, 50.0) cm: distance 158.1 cm, azimuth 90.0 deg, elevation 18.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 21.8  Mic3 551.2  Mic4 570.5
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     18.0     0.47   478.5   479.9     2.4    199  -37.4     0

next: [20/80] y axis 200 cm, height 50 cm (x 0   y 200   z 50 cm) - waiting for the phone button

[20/80] z050-Y200  y axis 200 cm, height 50 cm
true position (0.0, 200.0, 50.0) cm: distance 206.2 cm, azimuth 90.0 deg, elevation 14.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 22.0  Mic3 563.9  Mic4 583.9
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     17.7     0.67   411.3   415.9     2.3    122  -39.0     0

next: [21/80] diagonal 50 cm, height 50 cm (x 35.4   y 35.4   z 50 cm) - waiting for the phone button

[21/80] z050-D050  diagonal 50 cm, height 50 cm
true position (35.4, 35.4, 50.0) cm: distance 70.8 cm, azimuth 45.0 deg, elevation 45.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 296.9  Mic1 318.1  Mic4 575.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     13.5     0.40    12.7    13.7     2.0    341  -31.1     0

next: [22/80] diagonal 100 cm, height 50 cm (x 70.7   y 70.7   z 50 cm) - waiting for the phone button

[22/80] z050-D100  diagonal 100 cm, height 50 cm
true position (70.7, 70.7, 50.0) cm: distance 111.8 cm, azimuth 45.0 deg, elevation 26.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 373.8  Mic1 401.0  Mic4 733.6
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     2     15.3     0.44    17.1    18.4     2.3    302  -33.7     0

next: [23/80] diagonal 150 cm, height 50 cm (x 106.1   y 106.1   z 50 cm) - waiting for the phone button

[23/80] z050-D150  diagonal 150 cm, height 50 cm
true position (106.1, 106.1, 50.0) cm: distance 158.2 cm, azimuth 45.0 deg, elevation 18.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 391.6  Mic1 420.5  Mic4 779.1
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     16.3     0.53    13.2    20.8     2.3    176  -36.7     0

next: [24/80] diagonal 200 cm, height 50 cm (x 141.4   y 141.4   z 50 cm) - waiting for the phone button

[24/80] z050-D200  diagonal 200 cm, height 50 cm
true position (141.4, 141.4, 50.0) cm: distance 206.1 cm, azimuth 45.0 deg, elevation 14.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 396.9  Mic1 426.5  Mic4 796.9
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     15.2     0.57    55.7    69.7     2.2     91  -38.3     0

next: [25/80] in-between 1, height 50 cm (x 18   y 46.5   z 50 cm) - waiting for the phone button

[25/80] z050-M1  in-between 1, height 50 cm
true position (18.0, 46.5, 50.0) cm: distance 70.6 cm, azimuth 68.8 deg, elevation 45.1 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 175.6  Mic3 386.4  Mic4 533.2
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      3.2     0.34    14.2    15.1     0.7    434  -31.4     0

next: [26/80] in-between 2, height 50 cm (x 33.3   y 78.5   z 50 cm) - waiting for the phone button

[26/80] z050-M2  in-between 2, height 50 cm
true position (33.3, 78.5, 50.0) cm: distance 98.8 cm, azimuth 67.0 deg, elevation 30.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 229.4  Mic3 468.4  Mic4 664.6
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     16.4     0.42    21.6    22.4     2.1    319  -33.3     0

next: [27/80] in-between 3, height 50 cm (x 31   y 126   z 50 cm) - waiting for the phone button

[27/80] z050-M3  in-between 3, height 50 cm
true position (31.0, 126.0, 50.0) cm: distance 139.1 cm, azimuth 76.2 deg, elevation 21.1 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 158.8  Mic3 529.8  Mic4 669.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     14.4     0.42    41.4    44.4     1.9    198  -36.1     0

next: [28/80] in-between 4, height 50 cm (x 78.5   y 117.8   z 50 cm) - waiting for the phone button

[28/80] z050-M4  in-between 4, height 50 cm
true position (78.5, 117.8, 50.0) cm: distance 150.1 cm, azimuth 56.3 deg, elevation 19.5 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 337.0  Mic3 460.3  Mic4 764.8
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     14.8     0.45    14.6    18.1     2.1    147  -36.3     0

next: [29/80] in-between 5, height 50 cm (x 44   y 162   z 50 cm) - waiting for the phone button

[29/80] z050-M5  in-between 5, height 50 cm
true position (44.0, 162.0, 50.0) cm: distance 175.2 cm, azimuth 74.8 deg, elevation 16.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 174.7  Mic3 539.7  Mic4 697.2
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     16.8     0.53    50.2    56.0     2.1    126  -38.0     0

next: [30/80] in-between 6, height 50 cm (x 110   y 158.5   z 50 cm) - waiting for the phone button

[30/80] z050-M6  in-between 6, height 50 cm
true position (110.0, 158.5, 50.0) cm: distance 199.3 cm, azimuth 55.2 deg, elevation 14.5 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 351.0  Mic3 463.0  Mic4 787.7
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     17.2     0.66     8.8    15.8     2.1     78  -38.0     0

next: [31/80] in-between 7, height 50 cm (x 41.8   y 206   z 50 cm) - waiting for the phone button

[31/80] z050-M7  in-between 7, height 50 cm
true position (41.8, 206.0, 50.0) cm: distance 216.1 cm, azimuth 78.5 deg, elevation 13.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 138.9  Mic3 555.0  Mic4 682.2
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     15.1     0.54    93.9    97.0     4.2    121  -38.0     0

next: [32/80] in-between 8, height 50 cm (x 125   y 214   z 50 cm) - waiting for the phone button

[31/80] z050-M7  in-between 7, height 50 cm  (REDO)
true position (41.8, 206.0, 50.0) cm: distance 216.1 cm, azimuth 78.5 deg, elevation 13.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 138.9  Mic3 555.0  Mic4 682.2
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                               57  -38.3     0

next: [32/80] in-between 8, height 50 cm (x 125   y 214   z 50 cm) - waiting for the phone button

[32/80] z050-M8  in-between 8, height 50 cm
true position (125.0, 214.0, 50.0) cm: distance 252.8 cm, azimuth 59.7 deg, elevation 11.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 315.6  Mic3 490.9  Mic4 786.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                               63  -38.6     0

next: [33/80] y axis 50 cm, height 90 cm (x 0   y 50   z 90 cm) - waiting for the phone button

[33/80] z090-Y050  y axis 50 cm, height 90 cm
true position (0.0, 50.0, 90.0) cm: distance 103.0 cm, azimuth 90.0 deg, elevation 60.9 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 10.9  Mic3 280.3  Mic4 290.2
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     12.4     0.45   573.4   576.1     1.7    287  -35.1     0

next: [34/80] y axis 100 cm, height 90 cm (x 0   y 100   z 90 cm) - waiting for the phone button

[34/80] z090-Y100  y axis 100 cm, height 90 cm
true position (0.0, 100.0, 90.0) cm: distance 134.5 cm, azimuth 90.0 deg, elevation 42.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 16.9  Mic3 431.0  Mic4 446.1
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     14.0     0.46   461.9   683.6     1.9    288  -36.0     0

next: [35/80] y axis 150 cm, height 90 cm (x 0   y 150   z 90 cm) - waiting for the phone button

[35/80] z090-Y150  y axis 150 cm, height 90 cm
true position (0.0, 150.0, 90.0) cm: distance 174.9 cm, azimuth 90.0 deg, elevation 31.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 19.4  Mic3 498.0  Mic4 515.7
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     16.1     0.49   528.8   532.8     2.1    247  -36.7     0

next: [36/80] y axis 200 cm, height 90 cm (x 0   y 200   z 90 cm) - waiting for the phone button

[36/80] z090-Y200  y axis 200 cm, height 90 cm
true position (0.0, 200.0, 90.0) cm: distance 219.3 cm, azimuth 90.0 deg, elevation 24.2 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 20.5  Mic3 530.0  Mic4 548.9
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     17.1     0.81   436.0   439.3     2.0    161  -37.7     0

next: [37/80] diagonal 50 cm, height 90 cm (x 35.4   y 35.4   z 90 cm) - waiting for the phone button

[37/80] z090-D050  diagonal 50 cm, height 90 cm
true position (35.4, 35.4, 90.0) cm: distance 103.0 cm, azimuth 45.0 deg, elevation 60.9 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 197.4  Mic1 212.1  Mic4 396.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     12.0     0.43    33.1    35.9     1.5    385  -34.3     0

next: [38/80] diagonal 100 cm, height 90 cm (x 70.7   y 70.7   z 90 cm) - waiting for the phone button

[38/80] z090-D100  diagonal 100 cm, height 90 cm
true position (70.7, 70.7, 90.0) cm: distance 134.5 cm, azimuth 45.0 deg, elevation 42.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 305.1  Mic1 327.7  Mic4 609.1
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    95     0     15.7     0.51    27.7    29.9     2.0    247  -35.2     0

next: [39/80] diagonal 150 cm, height 90 cm (x 106.1   y 106.1   z 90 cm) - waiting for the phone button

[39/80] z090-D150  diagonal 150 cm, height 90 cm
true position (106.1, 106.1, 90.0) cm: distance 175.0 cm, azimuth 45.0 deg, elevation 31.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 351.1  Mic1 377.2  Mic4 704.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     15.5     0.55    19.1    26.5     2.0    189  -36.2     0

next: [40/80] diagonal 200 cm, height 90 cm (x 141.4   y 141.4   z 90 cm) - waiting for the phone button

[39/80] z090-D150  diagonal 150 cm, height 90 cm  (REDO)
true position (106.1, 106.1, 90.0) cm: distance 175.0 cm, azimuth 45.0 deg, elevation 31.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 351.1  Mic1 377.2  Mic4 704.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     15.3     0.46    17.0    23.1     1.9    207  -36.4     0

next: [40/80] diagonal 200 cm, height 90 cm (x 141.4   y 141.4   z 90 cm) - waiting for the phone button

[40/80] z090-D200  diagonal 200 cm, height 90 cm
true position (141.4, 141.4, 90.0) cm: distance 219.3 cm, azimuth 45.0 deg, elevation 24.2 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 371.5  Mic1 399.3  Mic4 748.9
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     15.7     0.88    12.4    22.3     1.9    155  -37.2     0

next: [41/80] in-between 1, height 90 cm (x 18   y 46.5   z 90 cm) - waiting for the phone button

[41/80] z090-M1  in-between 1, height 90 cm
true position (18.0, 46.5, 90.0) cm: distance 102.9 cm, azimuth 68.8 deg, elevation 61.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 115.4  Mic3 261.4  Mic4 367.4
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      5.0     0.48    44.2    47.1     0.4    147  -34.9     0

next: [42/80] in-between 2, height 90 cm (x 33.3   y 78.5   z 90 cm) - waiting for the phone button

[42/80] z090-M2  in-between 2, height 90 cm
true position (33.3, 78.5, 90.0) cm: distance 124.0 cm, azimuth 67.0 deg, elevation 46.5 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 177.7  Mic3 368.9  Mic4 529.7
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     11.4     0.52    34.2    37.9     1.4    197  -34.8     0

next: [43/80] in-between 3, height 90 cm (x 31   y 126   z 90 cm) - waiting for the phone button

[43/80] z090-M3  in-between 3, height 90 cm
true position (31.0, 126.0, 90.0) cm: distance 157.9 cm, azimuth 76.2 deg, elevation 34.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 137.8  Mic3 464.7  Mic4 589.4
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    95     0     14.9     0.53    57.9    62.7     1.9    150  -36.7     0

next: [44/80] in-between 4, height 90 cm (x 78.5   y 117.8   z 90 cm) - waiting for the phone button

[44/80] z090-M4  in-between 4, height 90 cm
true position (78.5, 117.8, 90.0) cm: distance 167.7 cm, azimuth 56.3 deg, elevation 32.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 298.5  Mic3 409.0  Mic4 684.2
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     16.1     0.45    41.3    43.4     2.1    169  -36.3     0

next: [45/80] in-between 5, height 90 cm (x 44   y 162   z 90 cm) - waiting for the phone button

[45/80] z090-M5  in-between 5, height 90 cm
true position (44.0, 162.0, 90.0) cm: distance 190.5 cm, azimuth 74.8 deg, elevation 28.2 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 159.3  Mic3 495.1  Mic4 641.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     18.1     0.64    93.0    97.0     2.1    150  -37.0     0

next: [46/80] in-between 6, height 90 cm (x 110   y 158.5   z 90 cm) - waiting for the phone button

[46/80] z090-M6  in-between 6, height 90 cm
true position (110.0, 158.5, 90.0) cm: distance 212.9 cm, azimuth 55.2 deg, elevation 25.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 327.0  Mic3 431.8  Mic4 737.3
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     17.3     0.79    47.5    53.5     2.1    117  -37.1     0

next: [47/80] in-between 7, height 90 cm (x 41.8   y 206   z 90 cm) - waiting for the phone button

[47/80] z090-M7  in-between 7, height 90 cm
true position (41.8, 206.0, 90.0) cm: distance 228.7 cm, azimuth 78.5 deg, elevation 23.2 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 130.6  Mic3 523.8  Mic4 644.6
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     1     19.1     0.70   115.0   125.1     2.3     94  -37.8     0

next: [48/80] in-between 8, height 90 cm (x 125   y 214   z 90 cm) - waiting for the phone button

[48/80] z090-M8  in-between 8, height 90 cm
true position (125.0, 214.0, 90.0) cm: distance 263.7 cm, azimuth 59.7 deg, elevation 20.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 301.8  Mic3 469.9  Mic4 754.1
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                               80  -38.1     0

next: [49/80] y axis 50 cm, height 130 cm (x 0   y 50   z 130 cm) - waiting for the phone button

[49/80] z130-Y050  y axis 50 cm, height 130 cm
true position (0.0, 50.0, 130.0) cm: distance 139.3 cm, azimuth 90.0 deg, elevation 69.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 7.9  Mic3 207.7  Mic4 215.3
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      7.3     0.78   483.8   500.7     0.9    294  -37.2     0

next: [50/80] y axis 100 cm, height 130 cm (x 0   y 100   z 130 cm) - waiting for the phone button

[50/80] z130-Y100  y axis 100 cm, height 130 cm
true position (0.0, 100.0, 130.0) cm: distance 164.0 cm, azimuth 90.0 deg, elevation 52.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 13.6  Mic3 353.6  Mic4 366.3
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     1     12.1     0.73   573.8   585.9     1.5    186  -37.2     0

next: [51/80] y axis 150 cm, height 130 cm (x 0   y 150   z 130 cm) - waiting for the phone button

[51/80] z130-Y150  y axis 150 cm, height 130 cm
true position (0.0, 150.0, 130.0) cm: distance 198.5 cm, azimuth 90.0 deg, elevation 40.9 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 16.9  Mic3 438.8  Mic4 454.5
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     14.8     0.57   600.0   604.1     1.9    206  -37.5     0

next: [52/80] y axis 200 cm, height 130 cm (x 0   y 200   z 130 cm) - waiting for the phone button

[52/80] z130-Y200  y axis 200 cm, height 130 cm
true position (0.0, 200.0, 130.0) cm: distance 238.5 cm, azimuth 90.0 deg, elevation 33.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 18.8  Mic3 487.2  Mic4 504.7
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     1     16.1     0.73   480.5   483.5     2.0    167  -37.6     0

next: [53/80] diagonal 50 cm, height 130 cm (x 35.4   y 35.4   z 130 cm) - waiting for the phone button

[53/80] z130-D050  diagonal 50 cm, height 130 cm
true position (35.4, 35.4, 130.0) cm: distance 139.3 cm, azimuth 45.0 deg, elevation 68.9 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 144.2  Mic1 155.1  Mic4 293.9
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      9.5     0.84    84.0    88.9     1.1    195  -36.6     0

next: [54/80] diagonal 100 cm, height 130 cm (x 70.7   y 70.7   z 130 cm) - waiting for the phone button

[54/80] z130-D100  diagonal 100 cm, height 130 cm
true position (70.7, 70.7, 130.0) cm: distance 164.0 cm, azimuth 45.0 deg, elevation 52.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 247.1  Mic1 265.7  Mic4 499.7
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     14.7     0.66    58.8    65.5     1.8    216  -36.6     0

next: [55/80] diagonal 150 cm, height 130 cm (x 106.1   y 106.1   z 130 cm) - waiting for the phone button

[55/80] z130-D150  diagonal 150 cm, height 130 cm
true position (106.1, 106.1, 130.0) cm: distance 198.5 cm, azimuth 45.0 deg, elevation 40.9 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 306.9  Mic1 330.0  Mic4 620.3
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     16.2     0.73    46.1    53.7     2.0    154  -37.2     0

next: [56/80] diagonal 200 cm, height 130 cm (x 141.4   y 141.4   z 130 cm) - waiting for the phone button

[56/80] z130-D200  diagonal 200 cm, height 130 cm
true position (141.4, 141.4, 130.0) cm: distance 238.5 cm, azimuth 45.0 deg, elevation 33.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 340.0  Mic1 365.5  Mic4 688.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     1     16.9     0.79    61.9    70.0     2.2    134  -37.4     0

next: [57/80] in-between 1, height 130 cm (x 18   y 46.5   z 130 cm) - waiting for the phone button

[57/80] z130-M1  in-between 1, height 130 cm
true position (18.0, 46.5, 130.0) cm: distance 139.2 cm, azimuth 68.8 deg, elevation 69.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 83.9  Mic3 192.2  Mic4 272.3
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      4.9     0.78    91.4    95.5     0.4     97  -37.2     0

next: [58/80] in-between 2, height 130 cm (x 33.3   y 78.5   z 130 cm) - waiting for the phone button

[58/80] z130-M2  in-between 2, height 130 cm
true position (33.3, 78.5, 130.0) cm: distance 155.5 cm, azimuth 67.0 deg, elevation 56.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 139.3  Mic3 292.0  Mic4 422.8
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     12.4     0.59    65.5    73.1     1.5    122  -36.5     0

next: [59/80] in-between 3, height 130 cm (x 31   y 126   z 130 cm) - waiting for the phone button

[59/80] z130-M3  in-between 3, height 130 cm
true position (31.0, 126.0, 130.0) cm: distance 183.7 cm, azimuth 76.2 deg, elevation 45.1 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 116.9  Mic3 398.2  Mic4 506.8
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     13.3     0.63    83.2    91.6     1.7     81  -37.5     0

next: [60/80] in-between 4, height 130 cm (x 78.5   y 117.8   z 130 cm) - waiting for the phone button

[60/80] z130-M4  in-between 4, height 130 cm
true position (78.5, 117.8, 130.0) cm: distance 192.2 cm, azimuth 56.3 deg, elevation 42.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 258.0  Mic3 354.5  Mic4 597.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     13.8     0.74    53.7    63.0     1.8    116  -37.2     0

next: [61/80] in-between 5, height 130 cm (x 44   y 162   z 130 cm) - waiting for the phone button

[61/80] z130-M5  in-between 5, height 130 cm
true position (44.0, 162.0, 130.0) cm: distance 212.3 cm, azimuth 74.8 deg, elevation 37.8 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 141.7  Mic3 443.0  Mic4 575.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     16.9     0.68   100.0   106.0     2.1    114  -37.8     0

next: [62/80] in-between 6, height 130 cm (x 110   y 158.5   z 130 cm) - waiting for the phone button

[62/80] z130-M6  in-between 6, height 130 cm
true position (110.0, 158.5, 130.0) cm: distance 232.6 cm, azimuth 55.2 deg, elevation 34.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 297.5  Mic3 393.5  Mic4 674.6
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     18.0     0.77    75.9    83.3     2.2    104  -37.6     0

next: [63/80] in-between 7, height 130 cm (x 41.8   y 206   z 130 cm) - waiting for the phone button

[63/80] z130-M7  in-between 7, height 130 cm
true position (41.8, 206.0, 130.0) cm: distance 247.2 cm, azimuth 78.5 deg, elevation 31.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 120.2  Mic3 484.0  Mic4 596.4
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     16.6     0.84   117.0   130.6     2.0     62  -38.0     0

next: [64/80] in-between 8, height 130 cm (x 125   y 214   z 130 cm) - waiting for the phone button

[64/80] z130-M8  in-between 8, height 130 cm
true position (125.0, 214.0, 130.0) cm: distance 279.9 cm, azimuth 59.7 deg, elevation 27.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 283.4  Mic3 441.7  Mic4 710.4
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    90     1     18.7     1.07   100.8   111.0     2.3    102  -38.3     0

next: [65/80] y axis 50 cm, height 170 cm (x 0   y 50   z 170 cm) - waiting for the phone button

[65/80] z170-Y050  y axis 50 cm, height 170 cm
true position (0.0, 50.0, 170.0) cm: distance 177.2 cm, azimuth 90.0 deg, elevation 73.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 6.2  Mic3 163.5  Mic4 169.5
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    95     0      6.6     1.14   438.4   447.9     0.7    155  -39.0     0

next: [66/80] y axis 100 cm, height 170 cm (x 0   y 100   z 170 cm) - waiting for the phone button

[66/80] z170-Y100  y axis 100 cm, height 170 cm
true position (0.0, 100.0, 170.0) cm: distance 197.2 cm, azimuth 90.0 deg, elevation 59.5 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 11.2  Mic3 294.2  Mic4 304.8
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     10.1     1.11   496.1   500.6     1.2    132  -38.0     0

next: [67/80] y axis 150 cm, height 170 cm (x 0   y 150   z 170 cm) - waiting for the phone button

[67/80] z170-Y150  y axis 150 cm, height 170 cm
true position (0.0, 150.0, 170.0) cm: distance 226.7 cm, azimuth 90.0 deg, elevation 48.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 14.7  Mic3 384.2  Mic4 398.1
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    95     0     13.9     1.23   569.2   572.6     1.6    146  -37.8     0

next: [68/80] y axis 200 cm, height 170 cm (x 0   y 200   z 170 cm) - waiting for the phone button

[68/80] z170-Y200  y axis 200 cm, height 170 cm
true position (0.0, 200.0, 170.0) cm: distance 262.5 cm, azimuth 90.0 deg, elevation 40.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 16.9  Mic3 442.7  Mic4 458.7
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     5     0     14.1     0.00   252.1   252.1     1.8    140  -38.0     0

next: [69/80] diagonal 50 cm, height 170 cm (x 35.4   y 35.4   z 170 cm) - waiting for the phone button

[69/80] z170-D050  diagonal 50 cm, height 170 cm
true position (35.4, 35.4, 170.0) cm: distance 177.2 cm, azimuth 45.0 deg, elevation 73.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 112.7  Mic1 121.3  Mic4 231.4
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                               93  -38.0     0

next: [70/80] diagonal 100 cm, height 170 cm (x 70.7   y 70.7   z 170 cm) - waiting for the phone button

[70/80] z170-D100  diagonal 100 cm, height 170 cm
true position (70.7, 70.7, 170.0) cm: distance 197.2 cm, azimuth 45.0 deg, elevation 59.5 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 203.9  Mic1 219.3  Mic4 415.7
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    85     0     14.8     0.92    93.8   106.8     1.7    159  -37.5     0

next: [71/80] diagonal 150 cm, height 170 cm (x 106.1   y 106.1   z 170 cm) - waiting for the phone button

[71/80] z170-D150  diagonal 150 cm, height 170 cm
true position (106.1, 106.1, 170.0) cm: distance 226.7 cm, azimuth 45.0 deg, elevation 48.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 267.0  Mic1 287.2  Mic4 543.1
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    45     0     16.8     1.52    59.0    84.1     2.0    113  -37.3     0

next: [72/80] diagonal 200 cm, height 170 cm (x 141.4   y 141.4   z 170 cm) - waiting for the phone button

[72/80] z170-D200  diagonal 200 cm, height 170 cm
true position (141.4, 141.4, 170.0) cm: distance 262.5 cm, azimuth 45.0 deg, elevation 40.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic3 307.6  Mic1 330.8  Mic4 625.6
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                               96  -37.8     0

next: [73/80] in-between 1, height 170 cm (x 18   y 46.5   z 170 cm) - waiting for the phone button

[73/80] z170-M1  in-between 1, height 170 cm
true position (18.0, 46.5, 170.0) cm: distance 177.2 cm, azimuth 68.8 deg, elevation 73.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 65.4  Mic3 150.8  Mic4 214.3
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    70     1      7.4     1.43   116.0   135.2     0.9     44  -38.4     0

next: [74/80] in-between 2, height 170 cm (x 33.3   y 78.5   z 170 cm) - waiting for the phone button

[74/80] z170-M2  in-between 2, height 170 cm
true position (33.3, 78.5, 170.0) cm: distance 190.2 cm, azimuth 67.0 deg, elevation 63.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 112.8  Mic3 237.8  Mic4 345.9
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    40     0     12.1     1.93   123.2   133.6     1.3     47  -38.0     0

next: [75/80] in-between 3, height 170 cm (x 31   y 126   z 170 cm) - waiting for the phone button

[75/80] z170-M3  in-between 3, height 170 cm
true position (31.0, 126.0, 170.0) cm: distance 213.9 cm, azimuth 76.2 deg, elevation 52.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 99.5  Mic3 341.2  Mic4 435.4
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    90     0     14.1     1.11   136.4   150.0     1.7     57  -38.1     0

next: [76/80] in-between 4, height 170 cm (x 78.5   y 117.8   z 170 cm) - waiting for the phone button

[76/80] z170-M4  in-between 4, height 170 cm
true position (78.5, 117.8, 170.0) cm: distance 221.2 cm, azimuth 56.3 deg, elevation 50.2 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 222.5  Mic3 306.4  Mic4 518.7
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    80     0     13.3     1.24    87.1   106.4     1.5     88  -38.0     0

next: [77/80] in-between 5, height 170 cm (x 44   y 162   z 170 cm) - waiting for the phone button

[77/80] z170-M5  in-between 5, height 170 cm
true position (44.0, 162.0, 170.0) cm: distance 238.9 cm, azimuth 74.8 deg, elevation 45.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 125.0  Mic3 392.9  Mic4 511.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                               65  -37.6     0

next: [78/80] in-between 6, height 170 cm (x 110   y 158.5   z 170 cm) - waiting for the phone button

[78/80] z170-M6  in-between 6, height 170 cm
true position (110.0, 158.5, 170.0) cm: distance 257.1 cm, azimuth 55.2 deg, elevation 41.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 267.8  Mic3 354.7  Mic4 610.3
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    75     0     15.9     1.30    55.1    81.7     2.0     81  -37.8     0

next: [79/80] in-between 7, height 170 cm (x 41.8   y 206   z 170 cm) - waiting for the phone button

[79/80] z170-M7  in-between 7, height 170 cm
true position (41.8, 206.0, 170.0) cm: distance 270.3 cm, azimuth 78.5 deg, elevation 39.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 109.2  Mic3 441.9  Mic4 545.2
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                               55  -37.8     0

next: [80/80] in-between 8, height 170 cm (x 125   y 214   z 170 cm) - waiting for the phone button

[80/80] z170-M8  in-between 8, height 170 cm
true position (125.0, 214.0, 170.0) cm: distance 300.5 cm, azimuth 59.7 deg, elevation 34.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 262.9  Mic3 410.4  Mic4 661.4
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                              103  -38.3     0

all points done - waiting for Finish (or Redo previous) on the phone

series finished

measured in this session:
z010-Y050    y axis 50 cm     z  10: ok 20/20  pos err 583.9 cm (p90 584.7)  dir err  8.02 deg
z010-Y100    y axis 100 cm    z  10: ok 20/20  pos err 519.2 cm (p90 521.0)  dir err  8.98 deg
z010-Y150    y axis 150 cm    z  10: ok 20/20  pos err 466.3 cm (p90 467.2)  dir err  8.80 deg
z010-Y200    y axis 200 cm    z  10: ok 20/20  pos err 414.7 cm (p90 415.7)  dir err  8.61 deg
z010-D050    diagonal 50 cm   z  10: ok 20/20  pos err   4.7 cm (p90   4.8)  dir err  4.54 deg
z010-D100    diagonal 100 cm  z  10: ok 20/20  pos err  21.0 cm (p90  22.7)  dir err  6.50 deg
z010-D150    diagonal 150 cm  z  10: ok 20/20  pos err  28.5 cm (p90  30.6)  dir err  7.98 deg
z010-D200    diagonal 200 cm  z  10: ok 20/20  pos err  36.5 cm (p90  46.0)  dir err  8.48 deg
z010-D200    diagonal 200 cm  z  10: ok 19/20  pos err  31.6 cm (p90  35.0)  dir err  8.35 deg  [redo]
z010-M1      in-between 1     z  10: ok 20/20  pos err   4.3 cm (p90   4.6)  dir err  5.67 deg
z010-M2      in-between 2     z  10: ok 20/20  pos err  15.9 cm (p90  16.9)  dir err  6.76 deg
z010-M3      in-between 3     z  10: ok 20/20  pos err  26.0 cm (p90  29.7)  dir err  8.41 deg
z010-M3      in-between 3     z  10: ok 20/20  pos err  27.5 cm (p90  30.6)  dir err  8.51 deg  [redo]
z010-M4      in-between 4     z  10: ok 20/20  pos err  28.1 cm (p90  32.1)  dir err  8.17 deg
z010-M5      in-between 5     z  10: ok 20/20  pos err  40.2 cm (p90  43.8)  dir err  8.05 deg
z010-M6      in-between 6     z  10: ok 20/20  pos err  38.6 cm (p90  45.3)  dir err  8.45 deg
z010-M7      in-between 7     z  10: ok  1/20  pos err 105.9 cm (p90 105.9)  dir err  8.33 deg
z010-M8      in-between 8     z  10: ok  2/20  pos err  72.2 cm (p90  75.4)  dir err  8.88 deg
z050-Y050    y axis 50 cm     z  50: ok 20/20  pos err  63.0 cm (p90  63.1)  dir err  2.38 deg
z050-Y050    y axis 50 cm     z  50: ok 20/20  pos err  63.0 cm (p90  63.1)  dir err  2.36 deg  [redo]
z050-Y100    y axis 100 cm    z  50: ok 20/20  pos err  93.5 cm (p90 564.8)  dir err  2.17 deg
z050-Y150    y axis 150 cm    z  50: ok 20/20  pos err 478.5 cm (p90 479.9)  dir err  2.42 deg
z050-Y200    y axis 200 cm    z  50: ok 20/20  pos err 411.3 cm (p90 415.9)  dir err  2.34 deg
z050-D050    diagonal 50 cm   z  50: ok 20/20  pos err  12.7 cm (p90  13.7)  dir err  1.97 deg
z050-D100    diagonal 100 cm  z  50: ok 20/20  pos err  17.1 cm (p90  18.4)  dir err  2.28 deg
z050-D150    diagonal 150 cm  z  50: ok 20/20  pos err  13.2 cm (p90  20.8)  dir err  2.28 deg
z050-D200    diagonal 200 cm  z  50: ok 20/20  pos err  55.7 cm (p90  69.7)  dir err  2.15 deg
z050-M1      in-between 1     z  50: ok 20/20  pos err  14.2 cm (p90  15.1)  dir err  0.73 deg
z050-M2      in-between 2     z  50: ok 20/20  pos err  21.6 cm (p90  22.4)  dir err  2.13 deg
z050-M3      in-between 3     z  50: ok 20/20  pos err  41.4 cm (p90  44.4)  dir err  1.93 deg
z050-M4      in-between 4     z  50: ok 20/20  pos err  14.6 cm (p90  18.1)  dir err  2.07 deg
z050-M5      in-between 5     z  50: ok 20/20  pos err  50.2 cm (p90  56.0)  dir err  2.14 deg
z050-M6      in-between 6     z  50: ok 20/20  pos err   8.8 cm (p90  15.8)  dir err  2.14 deg
z050-M7      in-between 7     z  50: ok 20/20  pos err  93.9 cm (p90  97.0)  dir err  4.17 deg
z050-M7      in-between 7     z  50: ok  0/20  NO GOOD DETECTION  [redo]
z050-M8      in-between 8     z  50: ok  0/20  NO GOOD DETECTION
z090-Y050    y axis 50 cm     z  90: ok 20/20  pos err 573.4 cm (p90 576.1)  dir err  1.67 deg
z090-Y100    y axis 100 cm    z  90: ok 20/20  pos err 461.9 cm (p90 683.6)  dir err  1.86 deg
z090-Y150    y axis 150 cm    z  90: ok 20/20  pos err 528.8 cm (p90 532.8)  dir err  2.14 deg
z090-Y200    y axis 200 cm    z  90: ok 20/20  pos err 436.0 cm (p90 439.3)  dir err  2.01 deg
z090-D050    diagonal 50 cm   z  90: ok 20/20  pos err  33.1 cm (p90  35.9)  dir err  1.51 deg
z090-D100    diagonal 100 cm  z  90: ok 19/20  pos err  27.7 cm (p90  29.9)  dir err  2.04 deg
z090-D150    diagonal 150 cm  z  90: ok 20/20  pos err  19.1 cm (p90  26.5)  dir err  1.98 deg
z090-D150    diagonal 150 cm  z  90: ok 20/20  pos err  17.0 cm (p90  23.1)  dir err  1.92 deg  [redo]
z090-D200    diagonal 200 cm  z  90: ok 20/20  pos err  12.4 cm (p90  22.3)  dir err  1.94 deg
z090-M1      in-between 1     z  90: ok 20/20  pos err  44.2 cm (p90  47.1)  dir err  0.39 deg
z090-M2      in-between 2     z  90: ok 20/20  pos err  34.2 cm (p90  37.9)  dir err  1.37 deg
z090-M3      in-between 3     z  90: ok 19/20  pos err  57.9 cm (p90  62.7)  dir err  1.89 deg
z090-M4      in-between 4     z  90: ok 20/20  pos err  41.3 cm (p90  43.4)  dir err  2.06 deg
z090-M5      in-between 5     z  90: ok 20/20  pos err  93.0 cm (p90  97.0)  dir err  2.12 deg
z090-M6      in-between 6     z  90: ok 20/20  pos err  47.5 cm (p90  53.5)  dir err  2.14 deg
z090-M7      in-between 7     z  90: ok 20/20  pos err 115.0 cm (p90 125.1)  dir err  2.31 deg
z090-M8      in-between 8     z  90: ok  0/20  NO GOOD DETECTION
z130-Y050    y axis 50 cm     z 130: ok 20/20  pos err 483.8 cm (p90 500.7)  dir err  0.89 deg
z130-Y100    y axis 100 cm    z 130: ok 20/20  pos err 573.8 cm (p90 585.9)  dir err  1.50 deg
z130-Y150    y axis 150 cm    z 130: ok 20/20  pos err 600.0 cm (p90 604.1)  dir err  1.90 deg
z130-Y200    y axis 200 cm    z 130: ok 20/20  pos err 480.5 cm (p90 483.5)  dir err  2.04 deg
z130-D050    diagonal 50 cm   z 130: ok 20/20  pos err  84.0 cm (p90  88.9)  dir err  1.08 deg
z130-D100    diagonal 100 cm  z 130: ok 20/20  pos err  58.8 cm (p90  65.5)  dir err  1.77 deg
z130-D150    diagonal 150 cm  z 130: ok 20/20  pos err  46.1 cm (p90  53.7)  dir err  2.00 deg
z130-D200    diagonal 200 cm  z 130: ok 20/20  pos err  61.9 cm (p90  70.0)  dir err  2.17 deg
z130-M1      in-between 1     z 130: ok 20/20  pos err  91.4 cm (p90  95.5)  dir err  0.42 deg
z130-M2      in-between 2     z 130: ok 20/20  pos err  65.5 cm (p90  73.1)  dir err  1.47 deg
z130-M3      in-between 3     z 130: ok 20/20  pos err  83.2 cm (p90  91.6)  dir err  1.66 deg
z130-M4      in-between 4     z 130: ok 20/20  pos err  53.7 cm (p90  63.0)  dir err  1.77 deg
z130-M5      in-between 5     z 130: ok 20/20  pos err 100.0 cm (p90 106.0)  dir err  2.14 deg
z130-M6      in-between 6     z 130: ok 20/20  pos err  75.9 cm (p90  83.3)  dir err  2.19 deg
z130-M7      in-between 7     z 130: ok 20/20  pos err 117.0 cm (p90 130.6)  dir err  2.04 deg
z130-M8      in-between 8     z 130: ok 18/20  pos err 100.8 cm (p90 111.0)  dir err  2.28 deg
z170-Y050    y axis 50 cm     z 170: ok 19/20  pos err 438.4 cm (p90 447.9)  dir err  0.74 deg
z170-Y100    y axis 100 cm    z 170: ok 20/20  pos err 496.1 cm (p90 500.6)  dir err  1.19 deg
z170-Y150    y axis 150 cm    z 170: ok 19/20  pos err 569.2 cm (p90 572.6)  dir err  1.60 deg
z170-Y200    y axis 200 cm    z 170: ok  1/20  pos err 252.1 cm (p90 252.1)  dir err  1.75 deg
z170-D050    diagonal 50 cm   z 170: ok  0/20  NO GOOD DETECTION
z170-D100    diagonal 100 cm  z 170: ok 17/20  pos err  93.8 cm (p90 106.8)  dir err  1.72 deg
z170-D150    diagonal 150 cm  z 170: ok  9/20  pos err  59.0 cm (p90  84.1)  dir err  2.04 deg
z170-D200    diagonal 200 cm  z 170: ok  0/20  NO GOOD DETECTION
z170-M1      in-between 1     z 170: ok 14/20  pos err 116.0 cm (p90 135.2)  dir err  0.87 deg
z170-M2      in-between 2     z 170: ok  8/20  pos err 123.2 cm (p90 133.6)  dir err  1.35 deg
z170-M3      in-between 3     z 170: ok 18/20  pos err 136.4 cm (p90 150.0)  dir err  1.67 deg
z170-M4      in-between 4     z 170: ok 16/20  pos err  87.1 cm (p90 106.4)  dir err  1.54 deg
z170-M5      in-between 5     z 170: ok  0/20  NO GOOD DETECTION
z170-M6      in-between 6     z 170: ok 15/20  pos err  55.1 cm (p90  81.7)  dir err  1.97 deg
z170-M7      in-between 7     z 170: ok  0/20  NO GOOD DETECTION
z170-M8      in-between 8     z 170: ok  0/20  NO GOOD DETECTION
```

## 2026-11-18 16:45 — Series a20 (20 cm array): results; the +2.13° rotation is wrong for the series — 0° fits

**What ran.**
- Run time: 15:49–16:27, all 80 points of `distance_v2`, settings as for a30 (13:25 entry). The ESP32 localized with rotation +2.13°.
- Raw data: `host/bench_results/series/distance_v2/a20/` (85 files).
- Redos (newest file used): z010-D200, z010-M3, z050-Y050, z050-M7, z090-D150.
- Firmware `9587b9dbc09c`; code as the automatic entry above records.

**Rotation check (new in `host/analyze_series.py`, `fit_rotation`).**
- What it fits: the rotation of the mic square that best explains the measured pair delays at the true positions (accepted chirps, z ≥ 50; z = 10 is left out because of the floor echo).
- Result:

  | series | best rotation | rms at best | rms at +2.13° (used) | chirps |
  |---|---|---|---|---|
  | a30 | −0.15° | 5.5 µs | 21.7 µs | 967 |
  | a20 | −0.05° | 4.7 µs | 14.6 µs | 1052 |

- Both layouts agree on ≈ 0°. The +2.13° from P1–P4 (2026-11-16) triples the residual here. The 2026-11-18 morning decision is therefore revised.
- Likely reason: P1–P4 were 4 hand-measured positions whose axes differ by about 2° from the floor grid the user laid out for the series. Or the array was turned slightly between then and now. Either way, the series grid is the reference that matters, and it says 0°.
- The ~2° direction "floor" noted for a30 (13:10 entry, finding 3) was this rotation error, not placement noise.

**Re-scoring with rotation 0 (host).**
- New `analyze_series.py --rot <deg>` (`relocalize`) localizes every accepted chirp again on the host from its `arr_us`, with the given rotation.
- Check: `--rot 2.13` reproduces the ESP32's own numbers (e.g. a30 z050-D050 4.6 cm / 2.65° vs 4.6 / 2.66).
- The accept flags (misfit, quality) do not depend on the geometry and are kept.
- Commands (in `host/`): `python analyze_series.py --rot 0`.
- Figure: `host/bench_results/series/distance_v2/figures/error_vs_distance_rot0.png`.
- The plain `error_vs_distance.png` stays the ESP32 result as run.

Medians over points (D+M = diagonal and in-between, Y = y axis); each cell is the ESP32 result at +2.13° → the host re-score at 0°:

| series | heights | 3D position (D+M) | direction (D+M) | direction (Y) |
|---|---|---|---|---|
| a30 | z 10 | 19.6 → 18.8 cm | 6.1 → 5.8° | 8.8 → 8.5° |
| a30 | z 50–90 | 11.7 → 8.2 cm | 1.83 → **0.62°** | 2.13 → 0.77° |
| a30 | z 130 | 21.8 → 21.4 cm | 1.90 → **0.34°** | 1.58 → 0.39° |
| a30 | z 170 | 59.8 → 59.6 cm | 1.62 → **0.57°** | 1.50 → 0.43° |
| a20 | z 10 | 28.4 → 28.1 cm | 8.1 → 7.9° | 8.7 → 8.4° |
| a20 | z 50–90 | 33.1 → 33.1 cm | 2.05 → **0.79°** | 2.16 → 1.01° |
| a20 | z 130 | 79.1 → 78.9 cm | 1.88 → **0.68°** | 1.69 → 0.65° |
| a20 | z 170 | 93.4 → 93.3 cm | 1.68 → **0.64°** | 1.40 → 0.24° |

**First reading of a20 vs a30 (details and figures later, together with a10).**
1. **Direction barely suffers from the smaller array.** 0.3–0.6° (30 cm) vs 0.6–0.8° (20 cm) at z ≥ 50, every distance, including the y axis.
2. **3D position gets much worse.** Medians (D+M, at 0°):
   - z 50–90: 8 → 33 cm;
   - z 130: 21 → 79 cm;
   - z 170: 60 → 93 cm.
   The distance error is mostly negative (measured too close), growing with height and distance. This fits range error ∝ 1/side² (×2.25 expected from 30 → 20 cm). The 20 cm Fraunhofer distance (175 cm side) is inside the measured range.
3. **The y axis (blind plane) fails in distance for both arrays**; direction is fine.
4. **z = 10 cm keeps a 6–8° direction error** with either rotation, so it is not geometry calibration. It is the near-grazing case with the floor echo (mic plane 4 cm above the floor).
5. **Success rate:** a20 has 0 % at a few far or high points (z050-M7/M8, z090-M8, z170-D050/D200/M5/M7/M8) and is otherwise mostly 100 %. Same pattern as a30: quality at the 0.2 limit and misfit from reflections.

**Code changes (16:45).**
- `host/analyze_series.py`:
  - `fit_rotation` (printed for every series at each run);
  - `relocalize` and `--rot` (figure gets the suffix `_rot<deg>`).
- `host/localize.py`: `MEASURED_ROT_DEG` changed from 2.13 to **0.0**, with a history comment. `host/analyze_sweeps.py`: docstring updated.
- The a10 series will run with `--rot 0`, which also stores 0 on the ESP32.
- The a30 and a20 raw data stay as recorded (ESP32 at +2.13°). The evaluations for the conclusions should use `--rot 0` (or the fitted value), applied the same way to every series.

## 2026-11-18 — Layout changed to 10 cm; series a10 started

- The user rebuilt the mic square at 10 cm side, placed like a30/a20. It was not calibrated separately.
- Rotation **0°**, per the re-fit on a30/a20 (16:45 entry); `--rot 0` also stored 0 on the ESP32.
- Everything else is unchanged: phone volume (same as a30/a20), left channel, chirp 3–12 kHz / 50 ms, 20 chirps per point, plan `distance_v2`, 21 °C assumed.
- Command (in `host/`): `python series.py --series a10 --array 10 --rot 0 --channel left --temp 21 --note "..."`
- Startup:
  - firmware `9587b9dbc09c` = the sources on disk;
  - 44160 Hz/mic;
  - mics Mic1 (−5, +5), Mic2 (+5, +5), Mic3 (+5, −5), Mic4 (−5, −5) cm.
- Fraunhofer distance (10 cm, 7.5 kHz): 44 cm (side) / 87 cm (diagonal). Almost every point lies beyond it, so the 10 cm array is expected to give direction but little usable distance.

## 2026-11-18 17:48 — distance series distance_v2 / a10 (array 10.0 cm)

- command (in `/home/nadasmartin/okos_lab_project/host`): `python series.py --series a10 --array 10 --rot 0 --channel left --temp 21 --note '10 cm layout; array placed by the user like a30/a20, not calibrated separately; rotation 0 deg (re-fitted on a30/a20); same phone volume as a30/a20 (level not given); temperature not measured, 21 C assumed; speaker aimed at the array'`
- duration: 3718 s, finished
- code: `9940b13f7689` (copy: `docs/code_snapshots/2026-11-18_1648_9940b13f7689/`)
- notes: 10 cm layout; array placed by the user like a30/a20, not calibrated separately; rotation 0 deg (re-fitted on a30/a20); same phone volume as a30/a20 (level not given); temperature not measured, 21 C assumed; speaker aimed at the array

```
plan distance_v2, series a10: 80 of 80 points to measure; signal chirp_3-12k_50ms, 20 x every 0.5 s, gain 0 dB, channel left
mic square 10 cm, rotated +0.00 deg: Mic1 (-5.0,+5.0)  Mic2 (+5.0,+5.0)  Mic3 (+5.0,-5.0)  Mic4 (-5.0,-5.0)
ESP32 firmware 9587b9dbc09c = the firmware sources on disk
ESP32: 44160 Hz/mic, mic delays [0.0, 0.0, 0.0, 0.0] us, 21 C -> c = 344.0 m/s

Open on the phone (same Wi-Fi):  http://192.168.1.76:8765/
waiting for the phone to tap 'Start audio' ...
phone ready (192.168.1.97)

next: [1/80] y axis 50 cm, height 10 cm (x 0   y 50   z 10 cm) - waiting for the phone button

[1/80] z010-Y050  y axis 50 cm, height 10 cm
true position (0.0, 50.0, 10.0) cm: distance 51.0 cm, azimuth 90.0 deg, elevation 11.3 deg
expected arrival after first mic [us]: Mic1 0.0  Mic2 0.0  Mic3 283.6  Mic4 283.6
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      7.4     0.32   580.7   582.9     7.2    722  -30.9     0

next: [2/80] y axis 100 cm, height 10 cm (x 0   y 100   z 10 cm) - waiting for the phone button

[2/80] z010-Y100  y axis 100 cm, height 10 cm
true position (0.0, 100.0, 10.0) cm: distance 100.5 cm, azimuth 90.0 deg, elevation 5.7 deg
expected arrival after first mic [us]: Mic1 0.0  Mic2 0.0  Mic3 288.9  Mic4 288.9
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      8.7     0.90   520.6   526.3    10.7    238  -36.6     0

next: [3/80] y axis 150 cm, height 10 cm (x 0   y 150   z 10 cm) - waiting for the phone button

[3/80] z010-Y150  y axis 150 cm, height 10 cm
true position (0.0, 150.0, 10.0) cm: distance 150.3 cm, azimuth 90.0 deg, elevation 3.8 deg
expected arrival after first mic [us]: Mic1 0.0  Mic2 0.0  Mic3 289.9  Mic4 289.9
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      7.7     0.66   469.7   474.7    10.9    218  -37.5     0

next: [4/80] y axis 200 cm, height 10 cm (x 0   y 200   z 10 cm) - waiting for the phone button

[4/80] z010-Y200  y axis 200 cm, height 10 cm
true position (0.0, 200.0, 10.0) cm: distance 200.2 cm, azimuth 90.0 deg, elevation 2.9 deg
expected arrival after first mic [us]: Mic1 0.0  Mic2 0.0  Mic3 290.2  Mic4 290.2
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      8.2     0.71   423.8   427.0    11.8    185  -38.6     0

next: [5/80] diagonal 50 cm, height 10 cm (x 35.4   y 35.4   z 10 cm) - waiting for the phone button

[5/80] z010-D050  diagonal 50 cm, height 10 cm
true position (35.4, 35.4, 10.0) cm: distance 51.1 cm, azimuth 45.0 deg, elevation 11.3 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 215.1  Mic3 215.1  Mic4 403.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      6.4     0.32    10.1    10.6     5.9    814  -29.8     0

next: [6/80] diagonal 100 cm, height 10 cm (x 70.7   y 70.7   z 10 cm) - waiting for the phone button

[6/80] z010-D100  diagonal 100 cm, height 10 cm
true position (70.7, 70.7, 10.0) cm: distance 100.5 cm, azimuth 45.0 deg, elevation 5.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 211.7  Mic3 211.7  Mic4 409.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      7.3     0.62    32.3    36.3     9.0    253  -36.8     0

next: [7/80] diagonal 150 cm, height 10 cm (x 106.1   y 106.1   z 10 cm) - waiting for the phone button

[7/80] z010-D150  diagonal 150 cm, height 10 cm
true position (106.1, 106.1, 10.0) cm: distance 150.4 cm, azimuth 45.0 deg, elevation 3.8 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 209.9  Mic3 209.9  Mic4 410.2
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      7.6     0.65    48.2    55.8    10.9    233  -37.5     0

next: [8/80] diagonal 200 cm, height 10 cm (x 141.4   y 141.4   z 10 cm) - waiting for the phone button

[8/80] z010-D200  diagonal 200 cm, height 10 cm
true position (141.4, 141.4, 10.0) cm: distance 200.2 cm, azimuth 45.0 deg, elevation 2.9 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 208.9  Mic3 208.9  Mic4 410.6
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      8.1     0.67    46.9    63.9    12.0    187  -37.6     0

next: [9/80] in-between 1, height 10 cm (x 18   y 46.5   z 10 cm) - waiting for the phone button

[9/80] z010-M1  in-between 1, height 10 cm
true position (18.0, 46.5, 10.0) cm: distance 50.9 cm, azimuth 68.8 deg, elevation 11.3 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 112.4  Mic3 274.0  Mic4 368.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0     11.0     0.26    14.7    15.2     7.3    452  -31.0     0

next: [10/80] in-between 2, height 10 cm (x 33.3   y 78.5   z 10 cm) - waiting for the phone button

[10/80] z010-M2  in-between 2, height 10 cm
true position (33.3, 78.5, 10.0) cm: distance 85.9 cm, azimuth 67.0 deg, elevation 6.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 118.9  Mic3 271.4  Mic4 378.3
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      7.2     0.45    33.6    35.6     8.5    126  -36.1     0

next: [11/80] in-between 3, height 10 cm (x 31   y 126   z 10 cm) - waiting for the phone button

[11/80] z010-M3  in-between 3, height 10 cm
true position (31.0, 126.0, 10.0) cm: distance 130.1 cm, azimuth 76.2 deg, elevation 4.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 71.9  Mic3 283.8  Mic4 350.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      9.0     0.62    78.1    80.9    11.8    113  -37.2     0

next: [12/80] in-between 4, height 10 cm (x 78.5   y 117.8   z 10 cm) - waiting for the phone button

[12/80] z010-M4  in-between 4, height 10 cm
true position (78.5, 117.8, 10.0) cm: distance 141.9 cm, azimuth 56.3 deg, elevation 4.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 165.5  Mic3 245.9  Mic4 402.1
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      8.2     0.74    61.3    65.8    11.2    145  -37.3     0

next: [13/80] in-between 5, height 10 cm (x 44   y 162   z 10 cm) - waiting for the phone button

[13/80] z010-M5  in-between 5, height 10 cm
true position (44.0, 162.0, 10.0) cm: distance 168.2 cm, azimuth 74.8 deg, elevation 3.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 78.3  Mic3 282.1  Mic4 356.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      8.8     0.92   117.5   121.1    11.7     97  -37.6     0

next: [14/80] in-between 6, height 10 cm (x 110   y 158.5   z 10 cm) - waiting for the phone button

[14/80] z010-M6  in-between 6, height 10 cm
true position (110.0, 158.5, 10.0) cm: distance 193.2 cm, azimuth 55.2 deg, elevation 3.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 169.0  Mic3 242.0  Mic4 404.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      8.4     0.84    73.2    95.2    12.3    130  -38.2     0

next: [15/80] in-between 7, height 10 cm (x 41.8   y 206   z 10 cm) - waiting for the phone button

[15/80] z010-M7  in-between 7, height 10 cm
true position (41.8, 206.0, 10.0) cm: distance 210.4 cm, azimuth 78.5 deg, elevation 2.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 59.1  Mic3 285.8  Mic4 342.2
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      8.7     1.11   151.5   161.2    12.3     88  -38.2     0

next: [16/80] in-between 8, height 10 cm (x 125   y 214   z 10 cm) - waiting for the phone button

[16/80] z010-M8  in-between 8, height 10 cm
true position (125.0, 214.0, 10.0) cm: distance 248.0 cm, azimuth 59.7 deg, elevation 2.3 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 149.1  Mic3 253.3  Mic4 397.3
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     5     0      7.6     0.00   133.4   133.4    12.2     89  -38.4     0

next: [17/80] y axis 50 cm, height 50 cm (x 0   y 50   z 50 cm) - waiting for the phone button

[17/80] z050-Y050  y axis 50 cm, height 50 cm
true position (0.0, 50.0, 50.0) cm: distance 70.7 cm, azimuth 90.0 deg, elevation 45.0 deg
expected arrival after first mic [us]: Mic1 0.0  Mic2 0.0  Mic3 204.8  Mic4 204.8
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     1     13.1     9.90   734.8   740.1     2.7    752  -31.7     0

next: [18/80] y axis 100 cm, height 50 cm (x 0   y 100   z 50 cm) - waiting for the phone button

[18/80] z050-Y100  y axis 100 cm, height 50 cm
true position (0.0, 100.0, 50.0) cm: distance 111.8 cm, azimuth 90.0 deg, elevation 26.6 deg
expected arrival after first mic [us]: Mic1 0.0  Mic2 0.0  Mic3 259.7  Mic4 259.7
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      5.9     0.40   103.0   103.0     2.6    455  -33.9     0

next: [19/80] y axis 150 cm, height 50 cm (x 0   y 150   z 50 cm) - waiting for the phone button

[19/80] z050-Y150  y axis 150 cm, height 50 cm
true position (0.0, 150.0, 50.0) cm: distance 158.1 cm, azimuth 90.0 deg, elevation 18.4 deg
expected arrival after first mic [us]: Mic1 0.0  Mic2 0.0  Mic3 275.6  Mic4 275.6
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      5.6     0.40   145.6   179.3     3.4    240  -37.1     0

next: [20/80] y axis 200 cm, height 50 cm (x 0   y 200   z 50 cm) - waiting for the phone button

[20/80] z050-Y200  y axis 200 cm, height 50 cm
true position (0.0, 200.0, 50.0) cm: distance 206.2 cm, azimuth 90.0 deg, elevation 14.0 deg
expected arrival after first mic [us]: Mic1 0.0  Mic2 0.0  Mic3 281.9  Mic4 281.9
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      6.0     0.52   424.7   426.7     4.1    144  -38.8     0

next: [21/80] diagonal 50 cm, height 50 cm (x 35.4   y 35.4   z 50 cm) - waiting for the phone button

[21/80] z050-D050  diagonal 50 cm, height 50 cm
true position (35.4, 35.4, 50.0) cm: distance 70.8 cm, azimuth 45.0 deg, elevation 45.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 150.2  Mic3 150.2  Mic4 290.1
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      6.8     0.33    28.3    29.2     2.2    491  -31.8     0

next: [22/80] diagonal 100 cm, height 50 cm (x 70.7   y 70.7   z 50 cm) - waiting for the phone button

[22/80] z050-D100  diagonal 100 cm, height 50 cm
true position (70.7, 70.7, 50.0) cm: distance 111.8 cm, azimuth 45.0 deg, elevation 26.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 188.9  Mic3 188.9  Mic4 367.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      8.6     0.45    55.2    56.9     4.0    531  -33.5     0

next: [23/80] diagonal 150 cm, height 50 cm (x 106.1   y 106.1   z 50 cm) - waiting for the phone button

[23/80] z050-D150  diagonal 150 cm, height 50 cm
true position (106.1, 106.1, 50.0) cm: distance 158.2 cm, azimuth 45.0 deg, elevation 18.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 199.1  Mic3 199.1  Mic4 390.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      4.6     0.51    37.4    44.0     3.2    322  -35.8     0

next: [24/80] diagonal 200 cm, height 50 cm (x 141.4   y 141.4   z 50 cm) - waiting for the phone button

[24/80] z050-D200  diagonal 200 cm, height 50 cm
true position (141.4, 141.4, 50.0) cm: distance 206.1 cm, azimuth 45.0 deg, elevation 14.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 202.7  Mic3 202.7  Mic4 398.8
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      4.6     0.61    22.1    37.7     3.4    168  -37.6     0

next: [25/80] in-between 1, height 50 cm (x 18   y 46.5   z 50 cm) - waiting for the phone button

[25/80] z050-M1  in-between 1, height 50 cm
true position (18.0, 46.5, 50.0) cm: distance 70.6 cm, azimuth 68.8 deg, elevation 45.1 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 77.4  Mic3 194.2  Mic4 264.7
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     1     21.5    18.88    33.8    36.4     2.1    278  -31.7     0

next: [26/80] in-between 2, height 50 cm (x 33.3   y 78.5   z 50 cm) - waiting for the phone button

[26/80] z050-M2  in-between 2, height 50 cm
true position (33.3, 78.5, 50.0) cm: distance 98.8 cm, azimuth 67.0 deg, elevation 30.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 101.8  Mic3 234.5  Mic4 328.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      7.0     0.42    46.5    48.9     3.1    223  -33.2     0

next: [27/80] in-between 3, height 50 cm (x 31   y 126   z 50 cm) - waiting for the phone button

[27/80] z050-M3  in-between 3, height 50 cm
true position (31.0, 126.0, 50.0) cm: distance 139.1 cm, azimuth 76.2 deg, elevation 21.1 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 66.9  Mic3 265.3  Mic4 328.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      5.1     0.43    90.5    92.7     2.7    171  -35.3     0

next: [28/80] in-between 4, height 50 cm (x 78.5   y 117.8   z 50 cm) - waiting for the phone button

[28/80] z050-M4  in-between 4, height 50 cm
true position (78.5, 117.8, 50.0) cm: distance 150.1 cm, azimuth 56.3 deg, elevation 19.5 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 156.0  Mic3 232.0  Mic4 380.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      5.4     0.35    54.2    60.3     3.5    195  -35.9     0

next: [29/80] in-between 5, height 50 cm (x 44   y 162   z 50 cm) - waiting for the phone button

[29/80] z050-M5  in-between 5, height 50 cm
true position (44.0, 162.0, 50.0) cm: distance 175.2 cm, azimuth 74.8 deg, elevation 16.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 75.0  Mic3 270.7  Mic4 341.8
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      5.8     0.49   121.4   124.3     3.5    101  -37.3     0

next: [30/80] in-between 6, height 50 cm (x 110   y 158.5   z 50 cm) - waiting for the phone button

[30/80] z050-M6  in-between 6, height 50 cm
true position (110.0, 158.5, 50.0) cm: distance 199.3 cm, azimuth 55.2 deg, elevation 14.5 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 163.6  Mic3 234.3  Mic4 391.6
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    70     0      4.7     0.56    88.5    96.8     3.6    104  -38.0     0

next: [31/80] in-between 7, height 50 cm (x 41.8   y 206   z 50 cm) - waiting for the phone button

[31/80] z050-M7  in-between 7, height 50 cm
true position (41.8, 206.0, 50.0) cm: distance 216.1 cm, azimuth 78.5 deg, elevation 13.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 57.5  Mic3 278.3  Mic4 333.3
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      5.7     0.65   152.6   157.6     4.2     69  -38.8     0

next: [32/80] in-between 8, height 50 cm (x 125   y 214   z 50 cm) - waiting for the phone button

[32/80] z050-M8  in-between 8, height 50 cm
true position (125.0, 214.0, 50.0) cm: distance 252.8 cm, azimuth 59.7 deg, elevation 11.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 146.1  Mic3 248.4  Mic4 389.7
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                               58  -39.0     0

next: [33/80] y axis 50 cm, height 90 cm (x 0   y 50   z 90 cm) - waiting for the phone button

[33/80] z090-Y050  y axis 50 cm, height 90 cm
true position (0.0, 50.0, 90.0) cm: distance 103.0 cm, azimuth 90.0 deg, elevation 60.9 deg
expected arrival after first mic [us]: Mic1 0.0  Mic2 0.0  Mic3 140.9  Mic4 140.9
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      5.5     0.41   567.2   574.7     1.4    386  -34.5     0

next: [34/80] y axis 100 cm, height 90 cm (x 0   y 100   z 90 cm) - waiting for the phone button

[34/80] z090-Y100  y axis 100 cm, height 90 cm
true position (0.0, 100.0, 90.0) cm: distance 134.5 cm, azimuth 90.0 deg, elevation 42.0 deg
expected arrival after first mic [us]: Mic1 0.0  Mic2 0.0  Mic3 215.8  Mic4 215.8
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     1      6.6     0.43   693.3   700.7     2.1    350  -35.8     0

next: [35/80] y axis 150 cm, height 90 cm (x 0   y 150   z 90 cm) - waiting for the phone button

[35/80] z090-Y150  y axis 150 cm, height 90 cm
true position (0.0, 150.0, 90.0) cm: distance 174.9 cm, azimuth 90.0 deg, elevation 31.0 deg
expected arrival after first mic [us]: Mic1 0.0  Mic2 0.0  Mic3 249.1  Mic4 249.1
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      7.6     0.58   545.2   550.3     3.2    309  -36.5     0

next: [36/80] y axis 200 cm, height 90 cm (x 0   y 200   z 90 cm) - waiting for the phone button

[36/80] z090-Y200  y axis 200 cm, height 90 cm
true position (0.0, 200.0, 90.0) cm: distance 219.3 cm, azimuth 90.0 deg, elevation 24.2 deg
expected arrival after first mic [us]: Mic1 0.0  Mic2 0.0  Mic3 265.0  Mic4 265.0
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      4.4     0.58   439.0   448.1     1.8    211  -37.8     0

next: [37/80] diagonal 50 cm, height 90 cm (x 35.4   y 35.4   z 90 cm) - waiting for the phone button

[37/80] z090-D050  diagonal 50 cm, height 90 cm
true position (35.4, 35.4, 90.0) cm: distance 103.0 cm, azimuth 45.0 deg, elevation 60.9 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 101.4  Mic3 101.4  Mic4 199.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    95     0      3.8     0.44    66.9    69.7     0.9    173  -34.1     0

next: [38/80] diagonal 100 cm, height 90 cm (x 70.7   y 70.7   z 90 cm) - waiting for the phone button

[38/80] z090-D100  diagonal 100 cm, height 90 cm
true position (70.7, 70.7, 90.0) cm: distance 134.5 cm, azimuth 45.0 deg, elevation 42.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 155.6  Mic3 155.6  Mic4 305.3
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      5.7     0.52    66.7    70.5     1.9    272  -35.9     0

next: [39/80] diagonal 150 cm, height 90 cm (x 106.1   y 106.1   z 90 cm) - waiting for the phone button

[39/80] z090-D150  diagonal 150 cm, height 90 cm
true position (106.1, 106.1, 90.0) cm: distance 175.0 cm, azimuth 45.0 deg, elevation 31.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 179.3  Mic3 179.3  Mic4 352.4
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      5.7     0.62    82.9    90.3     2.4    328  -36.2     0

next: [40/80] diagonal 200 cm, height 90 cm (x 141.4   y 141.4   z 90 cm) - waiting for the phone button

[40/80] z090-D200  diagonal 200 cm, height 90 cm
true position (141.4, 141.4, 90.0) cm: distance 219.3 cm, azimuth 45.0 deg, elevation 24.2 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 190.2  Mic3 190.2  Mic4 374.8
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      3.4     0.51    47.5    56.7     1.7    293  -37.0     0

next: [41/80] in-between 1, height 90 cm (x 18   y 46.5   z 90 cm) - waiting for the phone button

[41/80] z090-M1  in-between 1, height 90 cm
true position (18.0, 46.5, 90.0) cm: distance 102.9 cm, azimuth 68.8 deg, elevation 61.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 51.9  Mic3 132.2  Mic4 181.9
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     1     11.7     9.93    72.5    75.3     0.8    182  -34.4     0

next: [42/80] in-between 2, height 90 cm (x 33.3   y 78.5   z 90 cm) - waiting for the phone button

[42/80] z090-M2  in-between 2, height 90 cm
true position (33.3, 78.5, 90.0) cm: distance 124.0 cm, azimuth 67.0 deg, elevation 46.5 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 80.0  Mic3 185.8  Mic4 261.9
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     2     14.0    12.42    73.5    79.2     1.6    154  -35.7     0

next: [43/80] in-between 3, height 90 cm (x 31   y 126   z 90 cm) - waiting for the phone button

[43/80] z090-M3  in-between 3, height 90 cm
true position (31.0, 126.0, 90.0) cm: distance 157.9 cm, azimuth 76.2 deg, elevation 34.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 58.5  Mic3 233.2  Mic4 288.8
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      6.2     0.57   112.0   115.2     2.4    192  -36.3     0

next: [44/80] in-between 4, height 90 cm (x 78.5   y 117.8   z 90 cm) - waiting for the phone button

[44/80] z090-M4  in-between 4, height 90 cm
true position (78.5, 117.8, 90.0) cm: distance 167.7 cm, azimuth 56.3 deg, elevation 32.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 138.9  Mic3 206.9  Mic4 340.1
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      5.9     0.49    69.4    81.1     2.4    181  -36.1     0

next: [45/80] in-between 5, height 90 cm (x 44   y 162   z 90 cm) - waiting for the phone button

[45/80] z090-M5  in-between 5, height 90 cm
true position (44.0, 162.0, 90.0) cm: distance 190.5 cm, azimuth 74.8 deg, elevation 28.2 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 68.7  Mic3 248.6  Mic4 314.3
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      5.8     0.53   140.9   144.6     2.3    146  -36.5     0

next: [46/80] in-between 6, height 90 cm (x 110   y 158.5   z 90 cm) - waiting for the phone button

[46/80] z090-M6  in-between 6, height 90 cm
true position (110.0, 158.5, 90.0) cm: distance 212.9 cm, azimuth 55.2 deg, elevation 25.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 152.8  Mic3 219.0  Mic4 366.6
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      4.6     0.58   113.4   125.5     2.1    164  -37.2     0

next: [47/80] in-between 7, height 90 cm (x 41.8   y 206   z 90 cm) - waiting for the phone button

[47/80] z090-M7  in-between 7, height 90 cm
true position (41.8, 206.0, 90.0) cm: distance 228.7 cm, azimuth 78.5 deg, elevation 23.2 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 54.2  Mic3 262.9  Mic4 315.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      5.1     0.50   184.9   188.1     2.2    127  -37.7     0

next: [48/80] in-between 8, height 90 cm (x 125   y 214   z 90 cm) - waiting for the phone button

[48/80] z090-M8  in-between 8, height 90 cm
true position (125.0, 214.0, 90.0) cm: distance 263.7 cm, azimuth 59.7 deg, elevation 20.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 139.9  Mic3 238.0  Mic4 373.7
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    10     1      4.7     0.87   148.0   157.3     2.8     96  -38.3     0

next: [49/80] y axis 50 cm, height 130 cm (x 0   y 50   z 130 cm) - waiting for the phone button

[49/80] z130-Y050  y axis 50 cm, height 130 cm
true position (0.0, 50.0, 130.0) cm: distance 139.3 cm, azimuth 90.0 deg, elevation 69.0 deg
expected arrival after first mic [us]: Mic1 0.0  Mic2 0.0  Mic3 104.2  Mic4 104.2
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      4.0     0.58   289.3   494.9     0.8    141  -36.8     0

next: [50/80] y axis 100 cm, height 130 cm (x 0   y 100   z 130 cm) - waiting for the phone button

[50/80] z130-Y100  y axis 100 cm, height 130 cm
true position (0.0, 100.0, 130.0) cm: distance 164.0 cm, azimuth 90.0 deg, elevation 52.4 deg
expected arrival after first mic [us]: Mic1 0.0  Mic2 0.0  Mic3 177.1  Mic4 177.1
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      4.8     0.54   161.2   578.2     1.2    278  -36.6     0

next: [51/80] y axis 150 cm, height 130 cm (x 0   y 150   z 130 cm) - waiting for the phone button

[51/80] z130-Y150  y axis 150 cm, height 130 cm
true position (0.0, 150.0, 130.0) cm: distance 198.5 cm, azimuth 90.0 deg, elevation 40.9 deg
expected arrival after first mic [us]: Mic1 0.0  Mic2 0.0  Mic3 219.6  Mic4 219.6
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      5.7     0.72   604.8   614.2     1.8    254  -37.2     0

next: [52/80] y axis 200 cm, height 130 cm (x 0   y 200   z 130 cm) - waiting for the phone button

[52/80] z130-Y200  y axis 200 cm, height 130 cm
true position (0.0, 200.0, 130.0) cm: distance 238.5 cm, azimuth 90.0 deg, elevation 33.0 deg
expected arrival after first mic [us]: Mic1 0.0  Mic2 0.0  Mic3 243.6  Mic4 243.6
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      7.1     0.84   478.5   500.0     2.9    190  -37.5     0

next: [53/80] diagonal 50 cm, height 130 cm (x 35.4   y 35.4   z 130 cm) - waiting for the phone button

[53/80] z130-D050  diagonal 50 cm, height 130 cm
true position (35.4, 35.4, 130.0) cm: distance 139.3 cm, azimuth 45.0 deg, elevation 68.9 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 74.5  Mic3 74.5  Mic4 147.6
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      4.5     0.71   114.4   117.1     1.1     84  -36.3     0

next: [54/80] diagonal 100 cm, height 130 cm (x 70.7   y 70.7   z 130 cm) - waiting for the phone button

[54/80] z130-D100  diagonal 100 cm, height 130 cm
true position (70.7, 70.7, 130.0) cm: distance 164.0 cm, azimuth 45.0 deg, elevation 52.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 126.9  Mic3 126.9  Mic4 250.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      3.4     0.52    89.6    99.3     1.0    174  -36.7     0

next: [55/80] diagonal 150 cm, height 130 cm (x 106.1   y 106.1   z 130 cm) - waiting for the phone button

[55/80] z130-D150  diagonal 150 cm, height 130 cm
true position (106.1, 106.1, 130.0) cm: distance 198.5 cm, azimuth 45.0 deg, elevation 40.9 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 157.4  Mic3 157.4  Mic4 310.6
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      4.4     0.65   110.7   119.3     1.4    193  -37.4     0

next: [56/80] diagonal 200 cm, height 130 cm (x 141.4   y 141.4   z 130 cm) - waiting for the phone button

[56/80] z130-D200  diagonal 200 cm, height 130 cm
true position (141.4, 141.4, 130.0) cm: distance 238.5 cm, azimuth 45.0 deg, elevation 33.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 174.4  Mic3 174.4  Mic4 344.6
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      2.5     0.79    97.6   120.0     1.0    222  -37.7     0

next: [57/80] in-between 1, height 130 cm (x 18   y 46.5   z 130 cm) - waiting for the phone button

[57/80] z130-M1  in-between 1, height 130 cm
true position (18.0, 46.5, 130.0) cm: distance 139.2 cm, azimuth 68.8 deg, elevation 69.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 38.0  Mic3 97.4  Mic4 134.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      4.2     0.55   126.3   128.2     0.7     68  -36.3     0

next: [58/80] in-between 2, height 130 cm (x 33.3   y 78.5   z 130 cm) - waiting for the phone button

[58/80] z130-M2  in-between 2, height 130 cm
true position (33.3, 78.5, 130.0) cm: distance 155.5 cm, azimuth 67.0 deg, elevation 56.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 63.2  Mic3 147.7  Mic4 208.9
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      3.4     0.58   117.6   120.3     0.7    134  -36.3     0

next: [59/80] in-between 3, height 130 cm (x 31   y 126   z 130 cm) - waiting for the phone button

[59/80] z130-M3  in-between 3, height 130 cm
true position (31.0, 126.0, 130.0) cm: distance 183.7 cm, azimuth 76.2 deg, elevation 45.1 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 50.0  Mic3 200.2  Mic4 248.3
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      5.0     0.60   144.6   149.4     1.4    184  -37.3     0

next: [60/80] in-between 4, height 130 cm (x 78.5   y 117.8   z 130 cm) - waiting for the phone button

[60/80] z130-M4  in-between 4, height 130 cm
true position (78.5, 117.8, 130.0) cm: distance 192.2 cm, azimuth 56.3 deg, elevation 42.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 120.6  Mic3 180.0  Mic4 296.8
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      4.9     0.51   107.9   116.4     1.6    114  -37.2     0

next: [61/80] in-between 5, height 130 cm (x 44   y 162   z 130 cm) - waiting for the phone button

[61/80] z130-M5  in-between 5, height 130 cm
true position (44.0, 162.0, 130.0) cm: distance 212.3 cm, azimuth 74.8 deg, elevation 37.8 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 61.3  Mic3 222.8  Mic4 281.9
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      5.0     0.67   146.3   157.6     1.7    137  -37.7     0

next: [62/80] in-between 6, height 130 cm (x 110   y 158.5   z 130 cm) - waiting for the phone button

[62/80] z130-M6  in-between 6, height 130 cm
true position (110.0, 158.5, 130.0) cm: distance 232.6 cm, azimuth 55.2 deg, elevation 34.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 139.4  Mic3 200.0  Mic4 335.4
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      4.1     0.92   136.5   149.0     1.5    124  -37.6     0

next: [63/80] in-between 7, height 130 cm (x 41.8   y 206   z 130 cm) - waiting for the phone button

[63/80] z130-M7  in-between 7, height 130 cm
true position (41.8, 206.0, 130.0) cm: distance 247.2 cm, azimuth 78.5 deg, elevation 31.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 50.0  Mic3 243.0  Mic4 291.4
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      8.5     0.68   207.9   212.2     3.2    142  -37.5     0

next: [64/80] in-between 8, height 130 cm (x 125   y 214   z 130 cm) - waiting for the phone button

[64/80] z130-M8  in-between 8, height 130 cm
true position (125.0, 214.0, 130.0) cm: distance 279.9 cm, azimuth 59.7 deg, elevation 27.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 131.6  Mic3 224.0  Mic4 352.1
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    85     0      5.1     1.34   183.8   199.9     1.9     94  -38.2     0

next: [65/80] y axis 50 cm, height 170 cm (x 0   y 50   z 170 cm) - waiting for the phone button

[65/80] z170-Y050  y axis 50 cm, height 170 cm
true position (0.0, 50.0, 170.0) cm: distance 177.2 cm, azimuth 90.0 deg, elevation 73.6 deg
expected arrival after first mic [us]: Mic1 0.0  Mic2 0.0  Mic3 82.0  Mic4 82.0
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      4.4     0.89   176.7   428.0     1.0     89  -38.3     0

next: [66/80] y axis 100 cm, height 170 cm (x 0   y 100   z 170 cm) - waiting for the phone button

[66/80] z170-Y100  y axis 100 cm, height 170 cm
true position (0.0, 100.0, 170.0) cm: distance 197.2 cm, azimuth 90.0 deg, elevation 59.5 deg
expected arrival after first mic [us]: Mic1 0.0  Mic2 0.0  Mic3 147.3  Mic4 147.3
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    25     0      2.5     0.91   492.8   494.7     0.3    210  -38.2     0

next: [67/80] y axis 150 cm, height 170 cm (x 0   y 150   z 170 cm) - waiting for the phone button

[67/80] z170-Y150  y axis 150 cm, height 170 cm
true position (0.0, 150.0, 170.0) cm: distance 226.7 cm, azimuth 90.0 deg, elevation 48.6 deg
expected arrival after first mic [us]: Mic1 0.0  Mic2 0.0  Mic3 192.2  Mic4 192.2
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100   100     0      4.6     0.99   555.4   562.9     1.0    234  -38.0     0

next: [68/80] y axis 200 cm, height 170 cm (x 0   y 200   z 170 cm) - waiting for the phone button

[68/80] z170-Y200  y axis 200 cm, height 170 cm
true position (0.0, 200.0, 170.0) cm: distance 262.5 cm, azimuth 90.0 deg, elevation 40.4 deg
expected arrival after first mic [us]: Mic1 0.0  Mic2 0.0  Mic3 221.4  Mic4 221.4
note: 0 deg from a blind plane (x=0 or y=0): distance is poorly determined there, direction is fine
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                              192  -37.5     0

next: [69/80] diagonal 50 cm, height 170 cm (x 35.4   y 35.4   z 170 cm) - waiting for the phone button

[69/80] z170-D050  diagonal 50 cm, height 170 cm
true position (35.4, 35.4, 170.0) cm: distance 177.2 cm, azimuth 45.0 deg, elevation 73.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 58.3  Mic3 58.3  Mic4 116.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    50     1      6.1     0.87   124.1   149.3     1.5     80  -38.0     0

next: [70/80] diagonal 100 cm, height 170 cm (x 70.7   y 70.7   z 170 cm) - waiting for the phone button

[70/80] z170-D100  diagonal 100 cm, height 170 cm
true position (70.7, 70.7, 170.0) cm: distance 197.2 cm, azimuth 45.0 deg, elevation 59.5 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 105.1  Mic3 105.1  Mic4 208.3
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                               80  -37.9     0

next: [71/80] diagonal 150 cm, height 170 cm (x 106.1   y 106.1   z 170 cm) - waiting for the phone button

[71/80] z170-D150  diagonal 150 cm, height 170 cm
true position (106.1, 106.1, 170.0) cm: distance 226.7 cm, azimuth 45.0 deg, elevation 48.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 137.4  Mic3 137.4  Mic4 272.0
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                              124  -37.8     0

next: [72/80] diagonal 200 cm, height 170 cm (x 141.4   y 141.4   z 170 cm) - waiting for the phone button

[72/80] z170-D200  diagonal 200 cm, height 170 cm
true position (141.4, 141.4, 170.0) cm: distance 262.5 cm, azimuth 45.0 deg, elevation 40.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 158.2  Mic3 158.2  Mic4 313.1
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                              156  -38.2     0

next: [73/80] in-between 1, height 170 cm (x 18   y 46.5   z 170 cm) - waiting for the phone button

[73/80] z170-M1  in-between 1, height 170 cm
true position (18.0, 46.5, 170.0) cm: distance 177.2 cm, azimuth 68.8 deg, elevation 73.7 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 29.7  Mic3 76.5  Mic4 105.7
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    80     0      2.7     1.17   152.3   446.0     0.6     78  -38.0     0

next: [74/80] in-between 2, height 170 cm (x 33.3   y 78.5   z 170 cm) - waiting for the phone button

[74/80] z170-M2  in-between 2, height 170 cm
true position (33.3, 78.5, 170.0) cm: distance 190.2 cm, azimuth 67.0 deg, elevation 63.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 51.4  Mic3 120.5  Mic4 170.8
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                               69  -38.0     0

next: [75/80] in-between 3, height 170 cm (x 31   y 126   z 170 cm) - waiting for the phone button

[75/80] z170-M3  in-between 3, height 170 cm
true position (31.0, 126.0, 170.0) cm: distance 213.9 cm, azimuth 76.2 deg, elevation 52.6 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 42.7  Mic3 171.8  Mic4 213.3
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    85     0      4.1     1.18   179.1   185.1     1.0    144  -37.7     0

next: [76/80] in-between 4, height 170 cm (x 78.5   y 117.8   z 170 cm) - waiting for the phone button

[76/80] z170-M4  in-between 4, height 170 cm
true position (78.5, 117.8, 170.0) cm: distance 221.2 cm, azimuth 56.3 deg, elevation 50.2 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 104.4  Mic3 156.0  Mic4 257.8
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                               80  -37.8     0

next: [77/80] in-between 5, height 170 cm (x 44   y 162   z 170 cm) - waiting for the phone button

[77/80] z170-M5  in-between 5, height 170 cm
true position (44.0, 162.0, 170.0) cm: distance 238.9 cm, azimuth 74.8 deg, elevation 45.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 54.3  Mic3 197.8  Mic4 250.6
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100    15     0      4.6     0.75   182.0   190.7     1.2    116  -38.0     0

next: [78/80] in-between 6, height 170 cm (x 110   y 158.5   z 170 cm) - waiting for the phone button

[78/80] z170-M6  in-between 6, height 170 cm
true position (110.0, 158.5, 170.0) cm: distance 257.1 cm, azimuth 55.2 deg, elevation 41.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 125.8  Mic3 180.6  Mic4 303.5
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                              106  -38.0     0

next: [79/80] in-between 7, height 170 cm (x 41.8   y 206   z 170 cm) - waiting for the phone button

[79/80] z170-M7  in-between 7, height 170 cm
true position (41.8, 206.0, 170.0) cm: distance 270.3 cm, azimuth 78.5 deg, elevation 39.0 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 45.6  Mic3 222.1  Mic4 266.4
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                              134  -37.8     0

next: [80/80] in-between 8, height 170 cm (x 125   y 214   z 170 cm) - waiting for the phone button

[80/80] z170-M8  in-between 8, height 170 cm
true position (125.0, 214.0, 170.0) cm: distance 300.5 cm, azimuth 59.7 deg, elevation 34.4 deg
expected arrival after first mic [us]: Mic2 0.0  Mic1 122.3  Mic3 208.4  Mic4 327.8
signal                    gain  det%   ok% extra tdoa rms tdoa std pos err     p90 dir err    snr    lvl  clip
                          [dB]                       [us]     [us]    [cm]    [cm]   [deg]          [dB]      
chirp_3-12k_50ms             0   100     0     0                                               76  -38.0     0

all points done - waiting for Finish (or Redo previous) on the phone

series finished

measured in this session:
z010-Y050    y axis 50 cm     z  10: ok 20/20  pos err 580.7 cm (p90 582.9)  dir err  7.20 deg
z010-Y100    y axis 100 cm    z  10: ok 20/20  pos err 520.6 cm (p90 526.3)  dir err 10.74 deg
z010-Y150    y axis 150 cm    z  10: ok 20/20  pos err 469.7 cm (p90 474.7)  dir err 10.89 deg
z010-Y200    y axis 200 cm    z  10: ok 20/20  pos err 423.8 cm (p90 427.0)  dir err 11.79 deg
z010-D050    diagonal 50 cm   z  10: ok 20/20  pos err  10.1 cm (p90  10.6)  dir err  5.91 deg
z010-D100    diagonal 100 cm  z  10: ok 20/20  pos err  32.3 cm (p90  36.3)  dir err  8.95 deg
z010-D150    diagonal 150 cm  z  10: ok 20/20  pos err  48.2 cm (p90  55.8)  dir err 10.94 deg
z010-D200    diagonal 200 cm  z  10: ok 20/20  pos err  46.9 cm (p90  63.9)  dir err 11.95 deg
z010-M1      in-between 1     z  10: ok 20/20  pos err  14.7 cm (p90  15.2)  dir err  7.32 deg
z010-M2      in-between 2     z  10: ok 20/20  pos err  33.6 cm (p90  35.6)  dir err  8.52 deg
z010-M3      in-between 3     z  10: ok 20/20  pos err  78.1 cm (p90  80.9)  dir err 11.84 deg
z010-M4      in-between 4     z  10: ok 20/20  pos err  61.3 cm (p90  65.8)  dir err 11.17 deg
z010-M5      in-between 5     z  10: ok 20/20  pos err 117.5 cm (p90 121.1)  dir err 11.74 deg
z010-M6      in-between 6     z  10: ok 20/20  pos err  73.2 cm (p90  95.2)  dir err 12.34 deg
z010-M7      in-between 7     z  10: ok 20/20  pos err 151.5 cm (p90 161.2)  dir err 12.30 deg
z010-M8      in-between 8     z  10: ok  1/20  pos err 133.4 cm (p90 133.4)  dir err 12.19 deg
z050-Y050    y axis 50 cm     z  50: ok 21/20  pos err 734.8 cm (p90 740.1)  dir err  2.71 deg
z050-Y100    y axis 100 cm    z  50: ok 20/20  pos err 103.0 cm (p90 103.0)  dir err  2.64 deg
z050-Y150    y axis 150 cm    z  50: ok 20/20  pos err 145.6 cm (p90 179.3)  dir err  3.37 deg
z050-Y200    y axis 200 cm    z  50: ok 20/20  pos err 424.7 cm (p90 426.7)  dir err  4.09 deg
z050-D050    diagonal 50 cm   z  50: ok 20/20  pos err  28.3 cm (p90  29.2)  dir err  2.24 deg
z050-D100    diagonal 100 cm  z  50: ok 20/20  pos err  55.2 cm (p90  56.9)  dir err  4.03 deg
z050-D150    diagonal 150 cm  z  50: ok 20/20  pos err  37.4 cm (p90  44.0)  dir err  3.18 deg
z050-D200    diagonal 200 cm  z  50: ok 20/20  pos err  22.1 cm (p90  37.7)  dir err  3.43 deg
z050-M1      in-between 1     z  50: ok 21/20  pos err  33.8 cm (p90  36.4)  dir err  2.07 deg
z050-M2      in-between 2     z  50: ok 20/20  pos err  46.5 cm (p90  48.9)  dir err  3.12 deg
z050-M3      in-between 3     z  50: ok 20/20  pos err  90.5 cm (p90  92.7)  dir err  2.73 deg
z050-M4      in-between 4     z  50: ok 20/20  pos err  54.2 cm (p90  60.3)  dir err  3.45 deg
z050-M5      in-between 5     z  50: ok 20/20  pos err 121.4 cm (p90 124.3)  dir err  3.51 deg
z050-M6      in-between 6     z  50: ok 14/20  pos err  88.5 cm (p90  96.8)  dir err  3.58 deg
z050-M7      in-between 7     z  50: ok 20/20  pos err 152.6 cm (p90 157.6)  dir err  4.18 deg
z050-M8      in-between 8     z  50: ok  0/20  NO GOOD DETECTION
z090-Y050    y axis 50 cm     z  90: ok 20/20  pos err 567.2 cm (p90 574.7)  dir err  1.39 deg
z090-Y100    y axis 100 cm    z  90: ok 20/20  pos err 693.3 cm (p90 700.7)  dir err  2.12 deg
z090-Y150    y axis 150 cm    z  90: ok 20/20  pos err 545.2 cm (p90 550.3)  dir err  3.25 deg
z090-Y200    y axis 200 cm    z  90: ok 20/20  pos err 439.0 cm (p90 448.1)  dir err  1.78 deg
z090-D050    diagonal 50 cm   z  90: ok 19/20  pos err  66.9 cm (p90  69.7)  dir err  0.89 deg
z090-D100    diagonal 100 cm  z  90: ok 20/20  pos err  66.7 cm (p90  70.5)  dir err  1.92 deg
z090-D150    diagonal 150 cm  z  90: ok 20/20  pos err  82.9 cm (p90  90.3)  dir err  2.45 deg
z090-D200    diagonal 200 cm  z  90: ok 20/20  pos err  47.5 cm (p90  56.7)  dir err  1.71 deg
z090-M1      in-between 1     z  90: ok 21/20  pos err  72.5 cm (p90  75.3)  dir err  0.81 deg
z090-M2      in-between 2     z  90: ok 22/20  pos err  73.5 cm (p90  79.2)  dir err  1.56 deg
z090-M3      in-between 3     z  90: ok 20/20  pos err 112.0 cm (p90 115.2)  dir err  2.35 deg
z090-M4      in-between 4     z  90: ok 20/20  pos err  69.4 cm (p90  81.1)  dir err  2.45 deg
z090-M5      in-between 5     z  90: ok 20/20  pos err 140.9 cm (p90 144.6)  dir err  2.31 deg
z090-M6      in-between 6     z  90: ok 20/20  pos err 113.4 cm (p90 125.5)  dir err  2.14 deg
z090-M7      in-between 7     z  90: ok 20/20  pos err 184.9 cm (p90 188.1)  dir err  2.25 deg
z090-M8      in-between 8     z  90: ok  2/20  pos err 148.0 cm (p90 157.3)  dir err  2.75 deg
z130-Y050    y axis 50 cm     z 130: ok 20/20  pos err 289.3 cm (p90 494.9)  dir err  0.77 deg
z130-Y100    y axis 100 cm    z 130: ok 20/20  pos err 161.2 cm (p90 578.2)  dir err  1.19 deg
z130-Y150    y axis 150 cm    z 130: ok 20/20  pos err 604.8 cm (p90 614.2)  dir err  1.79 deg
z130-Y200    y axis 200 cm    z 130: ok 20/20  pos err 478.5 cm (p90 500.0)  dir err  2.88 deg
z130-D050    diagonal 50 cm   z 130: ok 20/20  pos err 114.4 cm (p90 117.1)  dir err  1.06 deg
z130-D100    diagonal 100 cm  z 130: ok 20/20  pos err  89.6 cm (p90  99.3)  dir err  0.96 deg
z130-D150    diagonal 150 cm  z 130: ok 20/20  pos err 110.7 cm (p90 119.3)  dir err  1.45 deg
z130-D200    diagonal 200 cm  z 130: ok 20/20  pos err  97.6 cm (p90 120.0)  dir err  0.97 deg
z130-M1      in-between 1     z 130: ok 20/20  pos err 126.3 cm (p90 128.2)  dir err  0.67 deg
z130-M2      in-between 2     z 130: ok 20/20  pos err 117.6 cm (p90 120.3)  dir err  0.69 deg
z130-M3      in-between 3     z 130: ok 20/20  pos err 144.6 cm (p90 149.4)  dir err  1.43 deg
z130-M4      in-between 4     z 130: ok 20/20  pos err 107.9 cm (p90 116.4)  dir err  1.64 deg
z130-M5      in-between 5     z 130: ok 20/20  pos err 146.3 cm (p90 157.6)  dir err  1.72 deg
z130-M6      in-between 6     z 130: ok 20/20  pos err 136.5 cm (p90 149.0)  dir err  1.53 deg
z130-M7      in-between 7     z 130: ok 20/20  pos err 207.9 cm (p90 212.2)  dir err  3.19 deg
z130-M8      in-between 8     z 130: ok 17/20  pos err 183.8 cm (p90 199.9)  dir err  1.95 deg
z170-Y050    y axis 50 cm     z 170: ok 20/20  pos err 176.7 cm (p90 428.0)  dir err  1.02 deg
z170-Y100    y axis 100 cm    z 170: ok  5/20  pos err 492.8 cm (p90 494.7)  dir err  0.26 deg
z170-Y150    y axis 150 cm    z 170: ok 20/20  pos err 555.4 cm (p90 562.9)  dir err  0.95 deg
z170-Y200    y axis 200 cm    z 170: ok  0/20  NO GOOD DETECTION
z170-D050    diagonal 50 cm   z 170: ok 10/20  pos err 124.1 cm (p90 149.3)  dir err  1.53 deg
z170-D100    diagonal 100 cm  z 170: ok  0/20  NO GOOD DETECTION
z170-D150    diagonal 150 cm  z 170: ok  0/20  NO GOOD DETECTION
z170-D200    diagonal 200 cm  z 170: ok  0/20  NO GOOD DETECTION
z170-M1      in-between 1     z 170: ok 16/20  pos err 152.3 cm (p90 446.0)  dir err  0.61 deg
z170-M2      in-between 2     z 170: ok  0/20  NO GOOD DETECTION
z170-M3      in-between 3     z 170: ok 17/20  pos err 179.1 cm (p90 185.1)  dir err  0.98 deg
z170-M4      in-between 4     z 170: ok  0/20  NO GOOD DETECTION
z170-M5      in-between 5     z 170: ok  3/20  pos err 182.0 cm (p90 190.7)  dir err  1.18 deg
z170-M6      in-between 6     z 170: ok  0/20  NO GOOD DETECTION
z170-M7      in-between 7     z 170: ok  0/20  NO GOOD DETECTION
z170-M8      in-between 8     z 170: ok  0/20  NO GOOD DETECTION
```

## 2026-11-18 17:50 — Series a10 (10 cm array): results; all three layouts measured

**What ran.**
- Run time: 16:48–17:48, all 80 points of `distance_v2`, no redos. ESP32 with rotation 0°; other settings as for a30/a20.
- Raw data: `host/bench_results/series/distance_v2/a10/` (80 files).
- Rotation fit on a10: −0.15° (rms 6.8 µs at both −0.15° and 0°). This confirms the 0° decision of the 16:45 entry; all three layouts now agree on −0.15…−0.05°.

**Evaluation of all three series, same way:**
- Command (in `host/`): `python analyze_series.py --rot 0`. All chirps are re-localized on the host with 0°; for a10 that equals the ESP32's own result.
- Figure: `host/bench_results/series/distance_v2/figures/error_vs_distance_rot0.png`.
- Medians over the diagonal and in-between points (D+M) per height band:

  | heights | 3D position a30 / a20 / a10 [cm] | direction a30 / a20 / a10 [deg] | success a30 / a20 / a10 [%] |
  |---|---|---|---|
  | z 10 | 18.8 / 28.1 / 55.1 | 5.8 / 7.9 / 11.5 | 95 / 84 / 92 |
  | z 50–90 | 8.2 / 33.1 / 72.1 | 0.62 / 0.79 / 2.41 | 78 / 87 / 91 |
  | z 130 | 21.4 / 78.9 / 120.4 | 0.34 / 0.68 / 1.44 | 89 / 99 / 99 |
  | z 170 | 59.6 / 93.3 / 177.4 | 0.57 / 0.64 / 1.07 | 34 / 40 / 19 |

- y axis (blind plane), direction median at z ≥ 50: 0.56° / 0.72° / 1.79°. Distance fails for all three (hundreds of cm).

**First reading (the conclusions are to be drawn together with the user later):**
1. **10 cm gives direction only.** 3D position error is 55–180 cm, the same order as the distance itself. The distance is almost always measured far too short (range median −30…−180 cm). This fits the Fraunhofer distance of 44 cm: every point but the nearest z = 10 ones is in the far field, where the wavefront curvature that carries the distance is below the timing noise.
2. **Direction scales roughly with 1/side** (≈0.6° → 0.8° → 2.4° at z 50–90), and distance much faster. As expected: direction ∝ 1/side, range ∝ 1/side².
3. **Success rate does not depend much on the array size.** It is set by the place: z = 170 and the far corners (M7/M8) fail with every array. The cause seen for a30 applies (quality at the 0.2 limit, misfit from reflections).
4. **z = 10 cm is the worst direction case for every array** (6–12°): grazing incidence plus the floor echo.
5. **Range is biased short with every array** (negative median at almost every D/M point, more with height and smaller array). This is worth a closer look in the analysis phase. Candidates: solver bias when the curvature is weak; the floor or ceiling echo; the phone's speaker not exactly at the planned point.

**Code change:** `host/analyze_series.py` `geom_range_per_us` now returns ∞ when the point lies exactly in a blind plane. With rotation 0 the y-axis points are exactly at x = 0, and the pseudo-inverse had reported 0.0 cm/µs there (wrong: the distance is not observable at all).

## 2026-11-18 — Data inventory after the three series

All series data is on this laptop, in the project folder:
- **Raw data:** `host/bench_results/series/distance_v2/a30/` (89 files, redos included), `a20/` (85), `a10/` (80). One JSONL per point placement: meta (true position, geometry, settings, firmware/code version) plus every chirp the ESP32 reported (arrival times, quality, misfit, ESP32 position and direction, level).
- **Exclusion list:** `host/bench_results/series/distance_v2/excluded.json` (a30 z090-M4).
- **Full console printouts of the three runs:** copied from the temporary session folder to `host/bench_results/series/distance_v2/console/a30.log`, `a20.log`, `a10.log`.
- **Figures:**
  - `error_vs_distance.png`: ESP32 results as run;
  - `error_vs_distance_rot0.png`: host re-localization at 0°;
  - `error_vs_distance_rot2.13.png`: the check that the host reproduces the ESP32;
  - all in `host/bench_results/series/distance_v2/figures/`.
- **Code:** snapshots in `docs/code_snapshots/`.

The project is not under git and there is no copy elsewhere.
