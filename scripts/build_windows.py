"""Clean, pinned Windows x64 folder build. Does not sign, publish or install."""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import shutil
import struct
import subprocess
import sys
import venv

if __package__:
    from .package_distribution import ROOT, source_epoch, source_version
else:
    from package_distribution import ROOT, source_epoch, source_version


def run(*args: str, env: dict | None = None, timeout: int | None = None) -> None:
    print("+ " + " ".join(str(a) for a in args), flush=True)
    subprocess.run(args, cwd=ROOT, check=True, env=env, timeout=timeout)


def windows_version_info(version: str) -> str:
    numbers = tuple(int(n) for n in version.split(".")) + (0,)
    return f'''VSVersionInfo(
  ffi=FixedFileInfo(filevers={numbers!r}, prodvers={numbers!r}, mask=0x3f,
    flags=0, OS=0x40004, fileType=0x1, subtype=0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'ICCPrint contributors'),
    StringStruct('FileDescription', 'ICC-managed printing utility'),
    StringStruct('FileVersion', '{version}'),
    StringStruct('InternalName', 'ICCPrint'),
    StringStruct('OriginalFilename', 'ICCPrint.exe'),
    StringStruct('ProductName', 'ICCPrint'),
    StringStruct('ProductVersion', '{version}'),
    StringStruct('LegalCopyright', 'ICCPrint contributors; MIT License')
  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])
'''


def main() -> int:
    if sys.platform != "win32" or struct.calcsize("P") != 8 or platform.machine().lower() not in ("amd64", "x86_64"):
        raise SystemExit("Build requires native 64-bit x86 Windows and x64 Python (not ARM64).")
    if sys.version_info[:2] not in ((3, 12), (3, 13)):
        raise SystemExit("Build requires Python 3.12 or 3.13.")
    work = ROOT / "build/windows"
    work.mkdir(parents=True, exist_ok=True)
    environment = work / "venv"
    print("Creating isolated, clean build environment (development .venv is unchanged).", flush=True)
    venv.EnvBuilder(with_pip=True, clear=True).create(environment)
    python = str(environment / "Scripts/python.exe")
    run(python, "-m", "pip", "install", "pip==26.2.1", "setuptools==84.0.0", "wheel==0.48.0")
    run(python, "-m", "pip", "install", "--no-build-isolation", "-r", "requirements-build.txt")
    run(python, "-m", "pip", "check")
    env = dict(os.environ, QT_QPA_PLATFORM="offscreen", PYTHONHASHSEED="0",
               SOURCE_DATE_EPOCH=str(source_epoch()))
    run(python, "-m", "compileall", "-q", "iccprint", "scripts", "tests", env=env)
    run(python, "-m", "unittest", "discover", "-s", "tests", "-v", env=env)
    dist = ROOT / "dist/ICCPrint"
    if dist.exists():
        shutil.rmtree(dist)
    version_file = work / "version_info.txt"
    version_file.write_text(windows_version_info(source_version()), encoding="utf-8")
    run(python, "-m", "PyInstaller", "--noconfirm", "--clean", "--windowed", "--onedir", "--noupx",
        "--name", "ICCPrint", "--paths", str(ROOT), "--distpath", str(ROOT / "dist"),
        "--workpath", str(work / "pyinstaller"), "--specpath", str(work),
        "--version-file", str(version_file), "--collect-all", "pypdfium2",
        "--hidden-import", "PySide6.QtPrintSupport", "scripts/frozen_entry.py", env=env)
    for name in ("START_HERE.txt", "README.md", "README_zh-TW.md", "LICENSE", "CHANGELOG.md", "THIRD_PARTY_NOTICES.md", "CONTRIBUTING.md", "SECURITY.md"):
        shutil.copy2(ROOT / name, dist / name)
    shutil.copytree(ROOT / "docs", dist / "docs", dirs_exist_ok=True)
    run(python, "scripts/collect_licenses.py", str(dist / "third_party_licenses"), "--include-build")
    report = work / "frozen-smoke-test.json"
    report.unlink(missing_ok=True)
    run(str(dist / "ICCPrint.exe"), "--smoke-test", str(report), env=env, timeout=90)
    result = json.loads(report.read_text(encoding="utf-8"))
    if not result.get("ok") or not result.get("frozen") or result.get("version") != source_version():
        raise RuntimeError("Frozen executable smoke test did not pass")
    run(python, "scripts/package_distribution.py", str(dist))
    print("Verified bundle, ZIP and SHA-256 checksum are in dist/. See docs/RELEASE_CHECKLIST.md before distribution.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
