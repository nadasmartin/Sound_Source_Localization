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
import io
import re
import shlex
import sys
from datetime import datetime
from pathlib import Path

LOG = Path(__file__).resolve().parent.parent / "docs" / "experiment_log.md"
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
        body = (f"- command (in `{Path.cwd()}`): `{cmd}`\n"
                f"- duration: {secs:.0f} s, {ending}\n" + (f"- notes: {notes}\n" if notes else "") +
                ("\n```\n" + out + "\n```" if out else ""))
        try:
            append(title, body)
        except OSError as e:
            print(f"(could not write the experiment log {LOG}: {e})", file=sys.stderr)
