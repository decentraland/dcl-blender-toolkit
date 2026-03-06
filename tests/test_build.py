"""Tests for the build script and project structure."""

import os
import re
import sys
import zipfile

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")
ASSETS_DIR = os.path.join(ROOT_DIR, "assets")
MANIFEST_FILE = os.path.join(ROOT_DIR, "blender_manifest.toml")

sys.path.insert(0, os.path.join(ROOT_DIR, "scripts"))
import build


class TestProjectStructure:
    def test_src_directory_exists(self):
        assert os.path.isdir(SRC_DIR)

    def test_init_py_exists(self):
        assert os.path.isfile(os.path.join(SRC_DIR, "__init__.py"))

    def test_assets_directory_exists(self):
        assert os.path.isdir(ASSETS_DIR)

    def test_manifest_exists(self):
        assert os.path.isfile(MANIFEST_FILE)

    def test_license_exists(self):
        assert os.path.isfile(os.path.join(ROOT_DIR, "LICENSE"))

    def test_blend_files_in_assets(self):
        expected = {"AvatarShape_A.blend", "AvatarShape_B.blend", "Avatar_File.blend"}
        actual = {f for f in os.listdir(ASSETS_DIR) if f.endswith(".blend")}
        assert expected == actual


class TestVersionParsing:
    def test_read_bl_info_version(self):
        version = build.read_bl_info_version()
        assert re.match(r"^\d+\.\d+\.\d+$", version)

    def test_version_matches_manifest(self):
        bl_version = build.read_bl_info_version()
        with open(MANIFEST_FILE) as f:
            manifest = f.read()
        match = re.search(r'^version\s*=\s*"(.*?)"', manifest, re.MULTILINE)
        assert match is not None
        assert match.group(1) == bl_version


class TestBuild:
    def test_build_produces_zip(self):
        version = build.read_bl_info_version()
        zip_path = build.build_zip(version)
        assert os.path.isfile(zip_path)
        assert zip_path.endswith(".zip")

    def test_zip_contains_init(self):
        version = build.read_bl_info_version()
        zip_path = build.build_zip(version)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert any(n.endswith("__init__.py") for n in names)

    def test_zip_contains_manifest(self):
        version = build.read_bl_info_version()
        zip_path = build.build_zip(version)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert any(n.endswith("blender_manifest.toml") for n in names)

    def test_zip_contains_assets(self):
        version = build.read_bl_info_version()
        zip_path = build.build_zip(version)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert any("assets/" in n for n in names)

    def test_zip_package_name(self):
        version = build.read_bl_info_version()
        zip_path = build.build_zip(version)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert all(n.startswith("decentraland_tools/") for n in names)

    def test_zip_no_pycache(self):
        version = build.read_bl_info_version()
        zip_path = build.build_zip(version)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert not any("__pycache__" in n for n in names)

    def test_zip_no_pyc(self):
        version = build.read_bl_info_version()
        zip_path = build.build_zip(version)
        with zipfile.ZipFile(zip_path, "r") as zf:
            names = zf.namelist()
            assert not any(n.endswith((".pyc", ".pyo")) for n in names)


class TestPatchVersion:
    def _read_bl_info_raw(self):
        with open(os.path.join(SRC_DIR, "__init__.py")) as f:
            return f.read()

    def _read_manifest_raw(self):
        with open(MANIFEST_FILE) as f:
            return f.read()

    def test_patch_version_updates_bl_info(self):
        original = build.read_bl_info_version()
        try:
            build.patch_version("9.8.7")
            assert build.read_bl_info_version() == "9.8.7"
            assert '"version": (9, 8, 7)' in self._read_bl_info_raw()
        finally:
            build.patch_version(original)

    def test_patch_version_updates_manifest(self):
        original = build.read_bl_info_version()
        try:
            build.patch_version("9.8.7")
            assert 'version = "9.8.7"' in self._read_manifest_raw()
        finally:
            build.patch_version(original)

    def test_patch_version_roundtrip(self):
        original = build.read_bl_info_version()
        build.patch_version("3.2.1")
        assert build.read_bl_info_version() == "3.2.1"
        build.patch_version(original)
        assert build.read_bl_info_version() == original

    def test_patch_version_keeps_files_in_sync(self):
        original = build.read_bl_info_version()
        try:
            build.patch_version("5.6.7")
            bl_version = build.read_bl_info_version()
            manifest_match = re.search(r'^version\s*=\s*"(.*?)"', self._read_manifest_raw(), re.MULTILINE)
            assert manifest_match is not None
            assert bl_version == manifest_match.group(1) == "5.6.7"
        finally:
            build.patch_version(original)


class TestSyntax:
    def test_all_python_files_compile(self):
        import py_compile

        for dirpath, dirnames, filenames in os.walk(SRC_DIR):
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for filename in filenames:
                if not filename.endswith(".py"):
                    continue
                filepath = os.path.join(dirpath, filename)
                # This will raise PyCompileError if syntax is invalid
                py_compile.compile(filepath, doraise=True)
