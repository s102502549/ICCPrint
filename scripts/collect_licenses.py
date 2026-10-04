"""Collect installed dependency notices without dropping nested license files."""
from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
from pathlib import Path, PurePosixPath
import shutil
import sys
import sysconfig

RUNTIME_DISTRIBUTIONS = ("PySide6", "PySide6_Essentials", "PySide6_Addons", "shiboken6", "Pillow", "pypdfium2")
BUILD_DISTRIBUTIONS = ("pyinstaller",)  # Its bootloader is redistributed.
KEYWORDS = ("license", "licence", "copying", "notice", "copyright")
ROOT = Path(__file__).resolve().parents[1]


def safe_name(value: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in value)


def is_notice(path: str) -> bool:
    # Match directories too: PDFium uses licenses/BUILD_LICENSES/icu.txt, etc.
    return any(keyword in part.lower() for part in PurePosixPath(path).parts for keyword in KEYWORDS)


def safe_relative_path(value: str) -> Path:
    path = PurePosixPath(value.replace("\\", "/"))
    if path.is_absolute() or any(p in ("", ".", "..") or ":" in p for p in path.parts):
        raise ValueError(f"Unsafe distribution license path: {value}")
    return Path(*path.parts)


def collect_distribution(name: str, destination: Path, required: bool = True) -> dict:
    try:
        dist = metadata.distribution(name)
    except metadata.PackageNotFoundError:
        if required:
            raise RuntimeError(f"Missing runtime dependency: {name}") from None
        return {"name": name, "installed": False, "files": []}
    target_dir = destination / safe_name(f"{dist.metadata.get('Name', name)}-{dist.version}")
    target_dir.mkdir(parents=True, exist_ok=True)
    copied = []
    for file in sorted(dist.files or (), key=str):
        if not is_notice(str(file)):
            continue
        relative = safe_relative_path(str(file))
        source = Path(dist.locate_file(file))
        if not source.is_file():
            raise RuntimeError(f"License listed in package metadata is missing: {name}: {file}")
        target = target_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(target.relative_to(destination).as_posix())
    # Preserve upstream metadata even for wheels that omit separate license files.
    raw_metadata = dist.read_text("METADATA") or dist.read_text("PKG-INFO")
    if not raw_metadata:
        raise RuntimeError(f"Missing upstream package metadata: {name}")
    (target_dir / "PACKAGE_METADATA.txt").write_text(raw_metadata, encoding="utf-8")
    return {"name": dist.metadata.get("Name", name), "version": dist.version, "installed": True,
            "license": dist.metadata.get("License-Expression") or dist.metadata.get("License"),
            "files": copied,
            "review_required": not copied}


def collect(destination: Path, include_build: bool = False) -> list[dict]:
    destination.mkdir(parents=True, exist_ok=True)
    records = [collect_distribution(name, destination) for name in RUNTIME_DISTRIBUTIONS]
    if include_build:
        records += [collect_distribution(name, destination) for name in BUILD_DISTRIBUTIONS]
    # Standard Qt LGPL/GPL texts accompany exact package metadata/source references.
    shutil.copytree(ROOT / "docs/licenses", destination / "Qt-license-texts", dirs_exist_ok=True)
    python_license_candidates = (Path(sys.base_prefix) / "LICENSE.txt",
                                 Path(sysconfig.get_path("stdlib")) / "LICENSE.txt")
    python_license = next((p for p in python_license_candidates if p.is_file()), None)
    if python_license is None:
        raise RuntimeError("Python LICENSE.txt not found; cannot produce a redistributable bundle")
    (destination / "Python").mkdir(exist_ok=True)
    shutil.copy2(python_license, destination / "Python/LICENSE.txt")
    (destination / "COLLECTED_LICENSES.json").write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")
    summary = [f"{r['name']} {r.get('version', '')}: {len(r['files'])} upstream notice files"
               + ("; package omits license files, REVIEW required (see THIRD_PARTY_NOTICES.md)" if r.get("review_required") else "")
               for r in records]
    (destination / "COLLECTED_LICENSES.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
    return records


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    parser.add_argument("--include-build", action="store_true")
    args = parser.parse_args()
    collect(args.destination, args.include_build)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
