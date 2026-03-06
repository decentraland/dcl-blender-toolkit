#!/usr/bin/env python3
"""
Build script for Decentraland Tools Blender extension.

Assembles a distributable zip from src/, assets/, and blender_manifest.toml.
The zip contains a top-level package directory that Blender can install
as both a legacy add-on (2.80+) and an extension (4.2+).

Usage:
    python scripts/build.py                    # uses version from bl_info
    python scripts/build.py --version 1.3.0    # override version (used by CI)
"""

import argparse
import os
import re
import sys
import zipfile

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")
ASSETS_DIR = os.path.join(ROOT_DIR, "assets")
MANIFEST_FILE = os.path.join(ROOT_DIR, "blender_manifest.toml")
DIST_DIR = os.path.join(ROOT_DIR, "dist")

# Package name inside the zip — this is what Blender sees as the addon folder
PACKAGE_NAME = "decentraland_tools"


def read_bl_info_version():
    """Read version tuple from bl_info in __init__.py."""
    init_path = os.path.join(SRC_DIR, "__init__.py")
    with open(init_path) as f:
        content = f.read()
    # Match version tuple, allowing optional whitespace/newlines between elements
    match = re.search(
        r'"version"\s*:\s*\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)',
        content,
        re.DOTALL,
    )
    if not match:
        print("ERROR: Could not parse version from bl_info in __init__.py")
        sys.exit(1)
    return f"{match.group(1)}.{match.group(2)}.{match.group(3)}"


def patch_version(version_str):
    """Patch version in both __init__.py bl_info and blender_manifest.toml."""
    major, minor, patch = version_str.split(".")

    # Patch bl_info in __init__.py
    init_path = os.path.join(SRC_DIR, "__init__.py")
    with open(init_path) as f:
        content = f.read()
    new_content, count = re.subn(
        r'("version"\s*:\s*\()\s*\d+\s*,\s*\d+\s*,\s*\d+\s*(\))',
        rf"\g<1>{major}, {minor}, {patch}\2",
        content,
        flags=re.DOTALL,
    )
    if count == 0:
        print("ERROR: Could not find version tuple in bl_info to patch")
        sys.exit(1)
    with open(init_path, "w") as f:
        f.write(new_content)

    # Patch blender_manifest.toml
    with open(MANIFEST_FILE) as f:
        manifest = f.read()
    new_manifest, count = re.subn(
        r'^version\s*=\s*".*?"',
        f'version = "{version_str}"',
        manifest,
        flags=re.MULTILINE,
    )
    if count == 0:
        print("ERROR: Could not find version field in blender_manifest.toml to patch")
        sys.exit(1)
    with open(MANIFEST_FILE, "w") as f:
        f.write(new_manifest)

    # Verify patching worked by re-reading
    verified = read_bl_info_version()
    if verified != version_str:
        print(f"ERROR: Version verification failed. Expected {version_str}, got {verified}")
        sys.exit(1)

    print(f"Patched version to {version_str}")


def build_zip(version_str):
    """Build the distributable zip."""
    os.makedirs(DIST_DIR, exist_ok=True)

    zip_name = f"{PACKAGE_NAME}-{version_str}.zip"
    zip_path = os.path.join(DIST_DIR, zip_name)

    if os.path.exists(zip_path):
        os.remove(zip_path)

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        # Add all source files
        for dirpath, dirnames, filenames in os.walk(SRC_DIR):
            # Skip __pycache__
            dirnames[:] = [d for d in dirnames if d != "__pycache__"]
            for filename in filenames:
                if filename.endswith((".pyc", ".pyo")):
                    continue
                filepath = os.path.join(dirpath, filename)
                arcname = os.path.join(
                    PACKAGE_NAME,
                    os.path.relpath(filepath, SRC_DIR),
                )
                zf.write(filepath, arcname)

        # Add assets
        if os.path.isdir(ASSETS_DIR):
            for filename in os.listdir(ASSETS_DIR):
                filepath = os.path.join(ASSETS_DIR, filename)
                if os.path.isfile(filepath):
                    arcname = os.path.join(PACKAGE_NAME, "assets", filename)
                    zf.write(filepath, arcname)

        # Add blender_manifest.toml at package root
        zf.write(MANIFEST_FILE, os.path.join(PACKAGE_NAME, "blender_manifest.toml"))

    file_size = os.path.getsize(zip_path)
    size_mb = file_size / (1024 * 1024)
    print(f"Built {zip_path} ({size_mb:.2f} MB)")
    return zip_path


def main():
    parser = argparse.ArgumentParser(description="Build Decentraland Tools extension")
    parser.add_argument(
        "--version",
        help="Override version (e.g. 1.3.0). If not set, reads from bl_info.",
    )
    args = parser.parse_args()

    version = args.version or read_bl_info_version()

    # Validate version format
    if not re.match(r"^\d+\.\d+\.\d+$", version):
        print(f"ERROR: Invalid version format '{version}'. Expected X.Y.Z")
        sys.exit(1)

    if args.version:
        patch_version(version)

    zip_path = build_zip(version)

    # Verify the zip is valid
    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        init_found = any(n.endswith("__init__.py") for n in names)
        manifest_found = any(n.endswith("blender_manifest.toml") for n in names)
        assets_found = any("assets/" in n for n in names)

        if not init_found:
            print("WARNING: __init__.py not found in zip")
        if not manifest_found:
            print("WARNING: blender_manifest.toml not found in zip")
        if not assets_found:
            print("WARNING: assets/ not found in zip")

        print(f"Zip contains {len(names)} files")

    print(f"Version: {version}")
    print("Build complete.")


if __name__ == "__main__":
    main()
