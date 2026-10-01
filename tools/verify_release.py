"""Check the archive a tester receives, including an unpacked macOS executable."""
import json
import os
from pathlib import Path
import platform
import subprocess
import tempfile
import zipfile
import hashlib

from package_beta import ROOT, VERSION


def main():
    source = ROOT / "releases" / f"ChaosKingdom-{VERSION}-source.zip"
    with zipfile.ZipFile(source) as bundle:
        assert bundle.testzip() is None
        assert not any(any(p in {"saves", ".venv", "__pycache__", "reports"} for p in Path(name).parts) for name in bundle.namelist())
        assert sum(n.startswith("ChaosKingdom/chaos_kingdom/data/battlefields/") and n.endswith(".json") for n in bundle.namelist()) == 50
    evidence = {"game": VERSION, "source_archive_crc_valid": True, "source_excludes_user_saves": True}
    if platform.system() == "Darwin":
        native = ROOT / "releases" / f"ChaosKingdom-{VERSION}-macOS-{platform.machine()}.zip"
        with zipfile.ZipFile(native) as bundle:
            assert bundle.testzip() is None
            symlinks = sum((info.external_attr >> 16) & 0o170000 == 0o120000 for info in bundle.infolist())
            assert symlinks > 0
        with tempfile.TemporaryDirectory(prefix="chaos-beta-unpacked-") as folder:
            subprocess.run(["ditto", "-x", "-k", str(native), folder], check=True)
            app = Path(folder) / "ChaosKingdom.app"
            executable = app / "Contents/MacOS/ChaosKingdom"
            assert os.access(executable, os.X_OK)
            environment = os.environ.copy()
            environment["CHAOS_KINGDOM_HOME"] = str(Path(folder) / "test-save")
            environment["SDL_AUDIODRIVER"] = "dummy"
            checks = []
            for command in (["doctor"], ["validate-maps"], *[
                ["play", "--headless", "--frames", "2", "--view", view] for view in ("editor", "battle")
            ]):
                result = subprocess.run([str(executable), *command], cwd=folder, env=environment,
                                        capture_output=True, text=True, timeout=30)
                assert result.returncode == 0, result.stderr + result.stdout
                checks.append({"command": command, "exit_code": result.returncode})
            data = app / "Contents/Resources/chaos_kingdom"
            assert len(list((data / "data/battlefields").glob("*.json"))) == 50
            manifest = json.loads((data / "assets/manifest.json").read_text(encoding="utf-8"))
            assert all(hashlib.sha256((data / "assets" / a["file"]).read_bytes()).hexdigest() == a["sha256"] for a in manifest["assets"])
            evidence.update(target=f"macOS {platform.machine()}", native_archive_crc_valid=True,
                            framework_symlinks=symlinks, executable_permission_preserved=True,
                            unpacked_app_checks=checks, regional_maps=50, generated_assets=len(manifest["assets"]))
    else:
        evidence["native_execution"] = "not checked on this host"
    (ROOT / "docs/evidence/beta-package.json").write_text(json.dumps(evidence, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
