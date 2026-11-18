# PlatformIO pre-build script: puts a fingerprint of the firmware sources into
# the binary (FW_SRC_HASH, shown as "fw" in the status line). host/lablog.py
# computes the same fingerprint from the files on disk, so every run can show
# whether the ESP32 runs exactly the code in the repository / a snapshot.
# Files: platformio.ini, src/main.cpp, lib/tdoa/*.h|*.cpp (keep in sync with lablog.py).
import hashlib
from pathlib import Path

Import("env")  # noqa: F821  (provided by PlatformIO)

root = Path(env.subst("$PROJECT_DIR"))  # noqa: F821
files = [root / "platformio.ini", root / "src" / "main.cpp"] + \
    sorted(p for p in (root / "lib" / "tdoa").iterdir() if p.suffix in (".h", ".cpp"))
h = hashlib.sha256()
for p in sorted(files, key=lambda p: p.relative_to(root).as_posix()):
    h.update(p.relative_to(root).as_posix().encode() + b"\0" + p.read_bytes() + b"\0")
fw = h.hexdigest()[:12]
print(f"firmware source fingerprint: {fw}")
env.Append(CPPDEFINES=[("FW_SRC_HASH", '\\"%s\\"' % fw)])  # noqa: F821
