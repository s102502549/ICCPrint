"""Packaging checks run without Windows, PyInstaller or a physical printer."""
import json
from pathlib import Path
import tempfile
import tomllib
import unittest
from unittest import mock
import zipfile

from iccprint import __version__
from scripts import collect_licenses as licenses
from scripts import package_distribution as bundle
from scripts.build_windows import windows_version_info


class PackagingTests(unittest.TestCase):
    def test_single_version_source_and_gui_entry(self):
        project = tomllib.loads((bundle.ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(bundle.source_version(), __version__)
        self.assertIn("version", project["project"]["dynamic"])
        self.assertEqual(project["project"]["gui-scripts"]["iccprint"], "iccprint.__main__:main")
        self.assertIn(f"'{__version__}'", windows_version_info(__version__))

    def test_manifest_detects_modified_missing_and_extra_files(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "payload.txt").write_text("hello", encoding="utf-8")
            manifest = bundle.build_manifest(root, "0.3.0")
            (root / bundle.MANIFEST_NAME).write_text(json.dumps(manifest), encoding="utf-8")
            bundle.verify_manifest(root)
            (root / "payload.txt").write_text("tampered", encoding="utf-8")
            with self.assertRaises(ValueError):
                bundle.verify_manifest(root)
            (root / "payload.txt").unlink()
            with self.assertRaises(ValueError):
                bundle.verify_manifest(root)
            (root / "payload.txt").write_text("hello", encoding="utf-8")
            (root / "extra.txt").write_text("unexpected", encoding="utf-8")
            with self.assertRaises(ValueError):
                bundle.verify_manifest(root)

    def test_archive_has_stable_bytes_and_one_top_level_folder(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "payload"
            folder.mkdir()
            (folder / "a.txt").write_text("ICCPrint", encoding="utf-8")
            paths = [root / "a.zip", root / "b.zip"]
            for path in paths:
                bundle.create_archive(folder, path, 1700000000)
            self.assertEqual(bundle.sha256(paths[0]), bundle.sha256(paths[1]))
            with zipfile.ZipFile(paths[0]) as archive:
                self.assertEqual(archive.namelist(), ["ICCPrint/a.txt"])
                self.assertEqual(archive.read("ICCPrint/a.txt"), b"ICCPrint")

    def test_incomplete_distribution_is_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaisesRegex(ValueError, "Incomplete distribution"):
                bundle.validate_distribution(Path(temporary))

    def test_private_profiles_are_rejected(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in bundle.REQUIRED_FILES:
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.touch()
            (root / "_internal").mkdir()
            (root / "private.ICC").touch()
            with self.assertRaisesRegex(ValueError, "Private ICC"):
                bundle.validate_distribution(root)

    def test_end_to_end_package_and_checksum(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            folder = root / "bundle"
            for name in bundle.REQUIRED_FILES:
                path = folder / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(b"fixture")
            (folder / "_internal").mkdir()
            (folder / "_internal/runtime.dll").write_bytes(b"runtime")
            with mock.patch.object(bundle, "environment_info", return_value={"commit": "fixture"}):
                archive = bundle.package(folder, root / "out")
            self.assertEqual(archive.name, f"ICCPrint-{__version__}-Windows-x64.zip")
            checksum = Path(str(archive) + ".sha256").read_text(encoding="ascii").split()[0]
            self.assertEqual(checksum, bundle.sha256(archive))
            with zipfile.ZipFile(archive) as zipped:
                zipped.extractall(root / "extracted")
            bundle.validate_distribution(root / "extracted/ICCPrint")
            bundle.verify_manifest(root / "extracted/ICCPrint")
            with self.assertRaisesRegex(ValueError, "outside"):
                bundle.package(folder, folder / "archives")

    def test_license_collection_includes_directory_contents(self):
        self.assertTrue(licenses.is_notice("package.dist-info/licenses/BUILD_LICENSES/icu.txt"))
        self.assertTrue(licenses.is_notice("package/LICENSE"))
        self.assertFalse(licenses.is_notice("package/source.py"))

    def test_license_collection_preserves_colliding_basenames(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for name in ("one/licenses/LICENSE", "two/licenses/LICENSE"):
                p = root / name
                p.parent.mkdir(parents=True)
                p.write_text(name, encoding="utf-8")
            fake = mock.Mock()
            fake.files = ["one/licenses/LICENSE", "two/licenses/LICENSE"]
            fake.version = "1.0"
            fake.metadata = {"Name": "example", "License": "MIT"}
            fake.read_text.return_value = "Name: example\nVersion: 1.0\n\nUpstream description\n"
            fake.locate_file.side_effect = lambda name: root / name
            with mock.patch.object(licenses.metadata, "distribution", return_value=fake):
                record = licenses.collect_distribution("example", root / "collected")
            self.assertEqual(len(record["files"]), 2)
            self.assertNotEqual(record["files"][0], record["files"][1])
            self.assertEqual((root / "collected/example-1.0/PACKAGE_METADATA.txt").read_text(encoding="utf-8"),
                             fake.read_text.return_value)

    def test_license_paths_cannot_escape_destination(self):
        for name in ("../LICENSE", "/LICENSE", "C:/LICENSE", "x/../../LICENSE"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                licenses.safe_relative_path(name)

    def test_missing_runtime_is_a_build_error(self):
        with mock.patch.object(licenses.metadata, "distribution", side_effect=licenses.metadata.PackageNotFoundError):
            with self.assertRaisesRegex(RuntimeError, "Missing runtime"):
                licenses.collect_distribution("missing", Path("unused"))


if __name__ == "__main__":
    unittest.main()
