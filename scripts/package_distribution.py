"""Versioned portable archive and SHA-256 inventory. Uses only the stdlib."""
from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
MANIFEST_NAME = "BUILD_MANIFEST.json"
REQUIRED_FILES = (
    "ICCPrint.exe", "START_HERE.txt", "README.md", "README_zh-TW.md", "LICENSE",
    "THIRD_PARTY_NOTICES.md", "CHANGELOG.md", "CONTRIBUTING.md", "SECURITY.md", "docs/INSTALL_WINDOWS.md",
    "docs/USER_GUIDE.md", "docs/COLOR_MANAGEMENT.md", "docs/TROUBLESHOOTING.md",
    "third_party_licenses/COLLECTED_LICENSES.json", "third_party_licenses/Python/LICENSE.txt",
)


def source_version(root: Path = ROOT) -> str:
    tree = ast.parse((root / "iccprint/__init__.py").read_text(encoding="utf-8"))
    for statement in tree.body:
        if isinstance(statement, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "__version__" for t in statement.targets):
            value = ast.literal_eval(statement.value)
            if isinstance(value, str) and len(value.split(".")) == 3 and all(p.isdigit() for p in value.split(".")):
                return value
    raise ValueError("Expected numeric major.minor.patch in iccprint.__version__")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def distribution_files(folder: Path) -> list[Path]:
    paths = sorted(folder.rglob("*"))
    if any(path.is_symlink() for path in paths):
        raise ValueError("Distribution must not contain symlinks")
    return [path for path in paths if path.is_file()]


def validate_distribution(folder: Path) -> None:
    missing = [name for name in REQUIRED_FILES if not (folder / name).is_file()]
    if not (folder / "_internal").is_dir():
        missing.append("_internal/")
    if missing:
        raise ValueError("Incomplete distribution: " + ", ".join(missing))
    for path in distribution_files(folder):
        if path.suffix.lower() in (".icc", ".icm"):
            raise ValueError(f"Private ICC profile must not be bundled: {path.name}")


def build_manifest(folder: Path, version: str, build_info: dict | None = None) -> dict:
    entries = [{"path": p.relative_to(folder).as_posix(), "size": p.stat().st_size,
                "sha256": sha256(p)} for p in distribution_files(folder) if p.relative_to(folder).as_posix() != MANIFEST_NAME]
    return {"schema_version": 1, "application": "ICCPrint", "version": version,
            "target": "windows-x64", "build": build_info or {}, "files": entries}


def verify_manifest(folder: Path) -> None:
    manifest = json.loads((folder / MANIFEST_NAME).read_text(encoding="utf-8"))
    expected = manifest["files"]
    actual = build_manifest(folder, manifest["version"])["files"]
    if expected != actual:
        raise ValueError("Distribution manifest does not match its contents")


def source_epoch(root: Path = ROOT) -> int:
    if os.environ.get("SOURCE_DATE_EPOCH"):
        return int(os.environ["SOURCE_DATE_EPOCH"])
    try:
        return int(subprocess.check_output(["git", "log", "-1", "--format=%ct"], cwd=root, text=True).strip())
    except (OSError, ValueError, subprocess.CalledProcessError):
        return 315532800  # ZIP epoch: 1980-01-01


def create_archive(folder: Path, output: Path, epoch: int) -> None:
    """Stable order/timestamps/permissions for identical bundle contents."""
    date_time = time.gmtime(max(315532800, min(epoch, 4354819198)))[:6]
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in distribution_files(folder):
            info = zipfile.ZipInfo(f"ICCPrint/{path.relative_to(folder).as_posix()}", date_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.create_system = 3
            info.external_attr = 0o100644 << 16
            with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as destination:
                shutil.copyfileobj(source, destination)


def environment_info() -> dict:
    try:
        revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip())
    except (OSError, subprocess.CalledProcessError):
        revision, dirty = "unknown", None
    return {"commit": revision, "working_tree_dirty": dirty, "python": platform.python_version(),
            "platform": platform.platform(), "architecture": platform.machine(),
            "packages": dict(sorted((d.metadata["Name"], d.version) for d in metadata.distributions() if d.metadata["Name"]))}


def package(folder: Path, output_dir: Path) -> Path:
    folder = folder.resolve()
    output_dir = output_dir.resolve()
    if output_dir == folder or folder in output_dir.parents:
        raise ValueError("Archive output must be outside the distribution folder")
    validate_distribution(folder)
    version = source_version()
    manifest = build_manifest(folder, version, environment_info())
    (folder / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    verify_manifest(folder)
    output_dir.mkdir(parents=True, exist_ok=True)
    archive = output_dir / f"ICCPrint-{version}-Windows-x64.zip"
    create_archive(folder, archive, source_epoch())
    (output_dir / (archive.name + ".sha256")).write_text(f"{sha256(archive)}  {archive.name}\n", encoding="ascii")
    return archive


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("folder", type=Path)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    print(package(args.folder, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
