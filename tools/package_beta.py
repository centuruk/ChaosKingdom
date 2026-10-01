"""Package source, manuscript, and an already-built native app without private saves."""
from pathlib import Path
import platform
import subprocess
import zipfile
import hashlib

ROOT = Path(__file__).resolve().parents[1]
VERSION = "0.3.0-beta.2"


def add_tree(bundle, path, prefix):
    for file in sorted(path.rglob("*")):
        if file.is_file() and not any(p in {"__pycache__", ".pytest_cache", ".DS_Store"} for p in file.parts):
            bundle.write(file, str(Path(prefix) / file.relative_to(path)))


def main():
    output = ROOT / "releases"
    output.mkdir(exist_ok=True)
    source = output / f"ChaosKingdom-{VERSION}-source.zip"
    with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name in ("chaos_kingdom", "tools", "tests", "docs", ".github"):
            add_tree(bundle, ROOT / name, f"ChaosKingdom/{name}")
        for name in ("README.md", "AGENTS.md", "pyproject.toml", "requirements.txt", "launch.py", "launch.command", "launch.bat", ".gitignore"):
            bundle.write(ROOT / name, f"ChaosKingdom/{name}")
    print(source.name)
    app = ROOT / "dist/ChaosKingdom.app"
    if platform.system() == "Darwin" and app.is_dir():
        native = output / f"ChaosKingdom-{VERSION}-macOS-{platform.machine()}.zip"
        # Preserve framework symlinks, executable permissions, and macOS metadata.
        # Traversing the bundle with ZipFile.write would dereference symlink files.
        native.unlink(missing_ok=True)
        subprocess.run(["ditto", "-c", "-k", "--sequesterRsrc", "--keepParent", str(app), str(native)], check=True)
        with zipfile.ZipFile(native, "a", zipfile.ZIP_DEFLATED) as bundle:
            bundle.write(ROOT / "docs/BETA_GUIDE.md", "테스터안내.md")
            bundle.write(ROOT / "docs/book.html", "개발원고.html")
        print(native.name)
    packages = sorted(output.glob(f"ChaosKingdom-{VERSION}-*.zip"))
    (output / "SHA256SUMS.txt").write_text("".join(f"{hashlib.sha256(path.read_bytes()).hexdigest()}  {path.name}\n" for path in packages), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
