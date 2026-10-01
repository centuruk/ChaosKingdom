"""Build on the target OS; PyInstaller is intentionally never used to cross-compile."""
from pathlib import Path
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    command = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed",
               "--name", "ChaosKingdom", "--collect-data", "chaos_kingdom", str(ROOT / "launch.py")]
    environment = os.environ.copy()
    environment.setdefault("PYINSTALLER_CONFIG_DIR", str(ROOT / "build" / "pyinstaller-cache"))
    return subprocess.call(command, cwd=ROOT, env=environment)


if __name__ == "__main__":
    raise SystemExit(main())
