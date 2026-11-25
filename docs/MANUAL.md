# Manual: flash the firmware, start the host

Short how-to for the 4-mic TDOA system (ESP32 + laptop + phone).
Paths are relative to the project folder `/home/nadasmartin/okos_lab_project/`.
Details of every parameter: `docs/reproduce.md`.

## 1. One-time setup (laptop)

```
cd /home/nadasmartin/okos_lab_project
python3 -m venv .venv
source .venv/bin/activate
pip install -r host/requirements.txt
```

**Serial port access.** The ESP32 appears as `/dev/ttyUSB0`, and your user must be in the `dialout` group:

```
sudo usermod -aG dialout $USER
```

Log out and back in afterwards.

**Phone access.** Let the phone reach the laptop on the local Wi-Fi:

```
sudo ufw allow from 192.168.1.0/24 to any port 8765 proto tcp
```

## 2. Flash the firmware

Connect the ESP32 with USB, then run:

```
cd /home/nadasmartin/okos_lab_project/firmware
../.venv/bin/pio run -e esp32 -t upload
```

- `esp32` (the default) is the **on-board localization firmware**. Every host program below needs it.
- The upload takes about 30 s. If it hangs at "Connecting...", hold the board's **BOOT** button until writing starts.
- Settings survive a re-flash because they are kept in flash: array size, rotation and mic delays.

**Check the board.** Within about 1 s the board should print one JSON status line per second:

```
cd /home/nadasmartin/okos_lab_project/host
../.venv/bin/python -c "from esp_link import EspLink; e=EspLink(); e.send('status'); print(e.wait_status(8)); e.close()"
```

Expected output: a line with `"fs": ~44100`, `"array_cm": 30`, `"array_rot_deg": 0` and an `"fw"` fingerprint. The host programs print whether that fingerprint equals the sources on disk.

## 3. Start the host

Activate the environment first, in every new terminal:

```
cd /home/nadasmartin/okos_lab_project/host
source ../.venv/bin/activate
```

### Live demo

```
python live_app.py                # 30 cm array, phone held 100 cm above the mics
python live_app.py --height 80    # different phone height
python live_app.py --min-q 0.15   # stricter accept rule (default 0.12; firmware uses 0.2)
python live_app.py --demo         # no hardware: replays recorded data
```

1. On the **laptop**, open http://localhost:8766/
2. On the **phone** (same Wi-Fi), open the URL the program prints, e.g. `http://192.168.1.76:8765/`. Tap **"Tap to start audio"**, then **"Start sound"** (on the phone or on the laptop page).
3. Hold the phone flat at the given height, with the bottom speaker towards the mics. Keep the screen on.

Stop with Ctrl+C. Every chirp is logged to `host/live_logs/`.

### Measurements

| Task | Command |
|---|---|
| Distance series (phone-driven) | `python series.py --series a30 --array 30 --rot 0 --channel left --temp 21` |
| Signal comparison at one position | `python bench.py sweep --label P1 --channel left --array 30 --rot 0 --pos X Y Z` |
| Evaluate all series | `python analyze_series.py` |
| Interactive analysis page | `python build_dashboard.py`, then open `docs/dashboard/index.html` |

## 4. Troubleshooting

**"no status line from the ESP32" or "no connection to ESP32"**

1. **Another program is using the port.** Check with `fuser -v /dev/ttyUSB0`, then close that program. Only one program can use the port at a time; this includes a running `live_app.py`, a `pio device monitor`, or Arduino IDE.
2. **Wrong firmware on the board.** For example, a sketch from another project. You will see binary garbage instead of `{"type":"status",...}` lines. Flash `-e esp32` again (section 2).
3. **The board is still booting.** Wait 2 s and start again.

**Port not found.** Check with `ls /dev/ttyUSB*`. Use another USB cable (some cables carry power only) or another USB port. If the port has a different name, pass it with `--port /dev/ttyUSB1`.

**The phone plays nothing.** Reload the page and tap "Tap to start audio" again. Check that the media volume is up and that no Bluetooth speaker is connected.

**The phone cannot open the page.** It must be on the same Wi-Fi as the laptop, and the firewall rule from section 1 must be in place.
