"""Experiment notebook: docs/experiment_log.md (plain Markdown, append-only).

Every bench.py run / calibrate and every mic_levels.py session appends an entry
by itself: the exact command, the setup it saw (ESP32 state, phone, ...) and
the results it printed. Raw data stays in bench_results/ etc.; the entry names
the file. Notes written by hand (or by Claude) go in the same file.

    from lablog import record
    with record("bench run P1"):     # everything printed inside is also logged
        ...
"""

import contextlib
import hashlib
import io
import re
import shutil
import shlex
import sys
from datetime import datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
LOG = PROJECT / "docs" / "experiment_log.md"
SNAPSHOTS = PROJECT / "docs" / "code_snapshots"


# ------------------------------------------------------------ code version
# Which code produced a result: a fingerprint of the sources, and a copy of
# them in docs/code_snapshots/<date>_<fingerprint>/ (made once per version).

def firmware_files():
    fw = PROJECT / "firmware"
    return [fw / "platformio.ini", fw / "src" / "main.cpp"] + \
        sorted(p for p in (fw / "lib" / "tdoa").iterdir() if p.suffix in (".h", ".cpp"))


def host_files():
    h = PROJECT / "host"
    return sorted(h.glob("*.py")) + [h / "phone" / "index.html"]


def _fingerprint(files, root):
    """Same scheme as firmware/fw_version.py: sha256 over (relative path, content)."""
    h = hashlib.sha256()
    for p in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
        h.update(p.relative_to(root).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
    return h.hexdigest()[:12]


def firmware_fingerprint():
    """What the ESP32 reports as "fw" if it was built from these files."""
    return _fingerprint(firmware_files(), PROJECT / "firmware")


def code_version():
    """{"code": fingerprint of host + firmware sources, "fw": firmware part,
    "snapshot": path of the saved copy}. Saves the copy if it is new."""
    files = host_files() + firmware_files() + [PROJECT / "firmware" / "fw_version.py"]
    files = [p for p in files if p.exists()]
    code = _fingerprint(files, PROJECT)
    existing = sorted(SNAPSHOTS.glob(f"*_{code}")) if SNAPSHOTS.exists() else []
    if existing:
        snap = existing[0]
    else:
        snap = SNAPSHOTS / f"{datetime.now():%Y-%m-%d_%H%M}_{code}"
        for p in files:
            dst = snap / p.relative_to(PROJECT)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(p, dst)
    return {"code": code, "fw": firmware_fingerprint(), "snapshot": str(snap.relative_to(PROJECT))}


def firmware_check(status):
    """One line: does the ESP32 run the firmware in the repository?"""
    on_board = (status or {}).get("fw")
    here = firmware_fingerprint()
    if not on_board:
        return "ESP32 firmware: no build fingerprint (flashed before 2026-11-16 21:00)"
    if on_board == here:
        return f"ESP32 firmware {on_board} = the firmware sources on disk"
    return (f"WARNING: ESP32 firmware {on_board} differs from the sources on disk ({here}): "
            "flash it, or note which version ran")


_ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")


def append(title, body):
    LOG.parent.mkdir(exist_ok=True)
    with open(LOG, "a") as f:
        f.write(f"\n## {datetime.now():%Y-%m-%d %H:%M} — {title}\n\n{body.rstrip()}\n")


class _Tee(io.TextIOBase):
    def __init__(self, out):
        self.out, self.buf = out, io.StringIO()

    def write(self, s):
        self.buf.write(s)
        return self.out.write(s)

    def flush(self):
        self.out.flush()

    def isatty(self):
        return self.out.isatty()


@contextlib.contextmanager
def record(title, notes=""):
    """Log the command line and everything printed inside the block (also on
    Ctrl+C or an error, with how it ended)."""
    tee = _Tee(sys.stdout)
    started = datetime.now()
    ending = "finished"
    try:
        with contextlib.redirect_stdout(tee):
            yield tee
    except KeyboardInterrupt:
        ending = "stopped with Ctrl+C"
        raise
    except SystemExit as e:
        ending = f"exited ({e.code})" if e.code not in (None, 0) else "finished"
        raise
    except BaseException as e:
        ending = f"FAILED: {type(e).__name__}: {e}"
        raise
    finally:
        out = _ANSI.sub("", tee.buf.getvalue()).strip()
        cmd = "python " + " ".join(shlex.quote(a) for a in sys.argv)
        secs = (datetime.now() - started).total_seconds()
        try:
            v = code_version()
            ver = f"- code: `{v['code']}` (copy: `{v['snapshot']}/`)\n"
        except OSError as e:
            ver = f"- code: unknown ({e})\n"
        body = (f"- command (in `{Path.cwd()}`): `{cmd}`\n"
                f"- duration: {secs:.0f} s, {ending}\n" + ver + (f"- notes: {notes}\n" if notes else "") +
                ("\n```\n" + out + "\n```" if out else ""))
        try:
            append(title, body)
        except OSError as e:
            print(f"(could not write the experiment log {LOG}: {e})", file=sys.stderr)
