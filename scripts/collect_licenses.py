"""Collect runtime dependency license/notice files for a binary distribution."""

from __future__ import annotations

import argparse
import importlib.metadata as metadata
import shutil
from pathlib import Path


RUNTIME_DISTRIBUTIONS = (
    "PySide6",
    "PySide6_Essentials",
    "PySide6_Addons",
    "shiboken6",
    "Pillow",
    "pypdfium2",
    "pypdfium2_raw",
)

KEYWORDS = ("license", "licence", "copying", "notice", "copyright")


def safe_name(value: str) -> str:
    return "".join(c if c.isalnum() or c in "-_." else "_" for c in value)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    dest = args.destination
    dest.mkdir(parents=True, exist_ok=True)

    summary: list[str] = []
    for dist_name in RUNTIME_DISTRIBUTIONS:
        try:
            dist = metadata.distribution(dist_name)
        except metadata.PackageNotFoundError:
            summary.append(f"{dist_name}: not installed")
            continue

        version = dist.version
        copied = 0
        target_dir = dest / safe_name(f"{dist.metadata.get('Name', dist_name)}-{version}")
        for file in dist.files or ():
            base = Path(str(file)).name.lower()
            if not any(k in base for k in KEYWORDS):
                continue
            src = Path(dist.locate_file(file))
            if not src.is_file():
                continue
            target_dir.mkdir(parents=True, exist_ok=True)
            target = target_dir / Path(str(file)).name
            if target.exists():
                stem, suffix = target.stem, target.suffix
                target = target_dir / f"{stem}_{copied + 1}{suffix}"
            shutil.copy2(src, target)
            copied += 1

        summary.append(f"{dist.metadata.get('Name', dist_name)} {version}: {copied} license/notice file(s)")

    (dest / "COLLECTED_LICENSES.txt").write_text("\n".join(summary) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
