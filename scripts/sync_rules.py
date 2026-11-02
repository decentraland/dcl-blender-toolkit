#!/usr/bin/env python3
"""
Vendor the Decentraland rule book's limits from @dcl-regenesislabs/wearable-validator.

The validators under src/ read every threshold from src/rules/manifest.json, so the Blender
checks and the Builder's checks agree on the numbers. The lock file records which package
version the copy came from.

Usage:
    python scripts/sync_rules.py                 # vendor the latest published manifest
    python scripts/sync_rules.py --version 0.6.3 # vendor a specific package version
    python scripts/sync_rules.py --check         # exit 1 when the vendored copy is behind npm
"""

import argparse
import hashlib
import io
import json
import os
import sys
import tarfile
from datetime import datetime, timezone
from urllib.error import URLError
from urllib.request import urlopen

PACKAGE = "@dcl-regenesislabs/wearable-validator"
REGISTRY = "https://registry.npmjs.org"
MANIFEST_IN_TARBALL = "package/dist/manifest/manifest.json"

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RULES_DIR = os.path.join(ROOT_DIR, "src", "rules")
MANIFEST_PATH = os.path.join(RULES_DIR, "manifest.json")
LOCK_PATH = os.path.join(RULES_DIR, "manifest.lock")


def fetch(url):
    with urlopen(url, timeout=30) as response:
        return response.read()


def package_metadata(version):
    data = json.loads(fetch(f"{REGISTRY}/{PACKAGE}/{version}"))
    return {"version": data["version"], "tarball": data["dist"]["tarball"], "shasum": data["dist"]["shasum"]}


def manifest_from_tarball(tarball_bytes):
    """Return the manifest's raw bytes from an npm tarball without extracting it to disk."""
    with tarfile.open(fileobj=io.BytesIO(tarball_bytes), mode="r:gz") as tar:
        try:
            member = tar.getmember(MANIFEST_IN_TARBALL)
        except KeyError:
            raise RuntimeError(f"{MANIFEST_IN_TARBALL} is not in the package tarball")
        if not member.isfile():
            raise RuntimeError(f"{MANIFEST_IN_TARBALL} is not a regular file")
        return tar.extractfile(member).read()


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def read_lock(path=LOCK_PATH):
    if not os.path.isfile(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_vendored(manifest_bytes, package_version, rules_dir=RULES_DIR):
    manifest = json.loads(manifest_bytes)
    os.makedirs(rules_dir, exist_ok=True)
    manifest_path = os.path.join(rules_dir, "manifest.json")
    lock_path = os.path.join(rules_dir, "manifest.lock")

    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)
        f.write("\n")
    with open(manifest_path, "rb") as f:
        written = f.read()

    lock = {
        "package": PACKAGE,
        "packageVersion": package_version,
        "rulesVersion": manifest["version"],
        "sha256": sha256(written),
        "syncedAt": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "source": f"{REGISTRY}/{PACKAGE}/{package_version}",
    }
    with open(lock_path, "w", encoding="utf-8") as f:
        json.dump(lock, f, indent=2)
        f.write("\n")
    return lock


def sync(version):
    meta = package_metadata(version)
    tarball = fetch(meta["tarball"])
    if hashlib.sha1(tarball).hexdigest() != meta["shasum"]:
        raise RuntimeError("npm tarball checksum mismatch")
    lock = write_vendored(manifest_from_tarball(tarball), meta["version"])
    print(f"Vendored {PACKAGE}@{lock['packageVersion']} (rules {lock['rulesVersion']}) into src/rules/")
    return lock


def check():
    lock = read_lock()
    if lock is None:
        print("No src/rules/manifest.lock. Run: make sync-rules")
        return 1
    try:
        latest = package_metadata("latest")
    except (URLError, OSError, ValueError) as error:
        print(f"WARNING: could not reach npm to compare rules ({error}); skipping the freshness check")
        return 0
    if latest["version"] != lock["packageVersion"]:
        print(
            f"Rules manifest is behind: vendored {PACKAGE}@{lock['packageVersion']}, "
            f"npm latest is {latest['version']}. Run: make sync-rules"
        )
        return 1
    print(f"Rules manifest is up to date ({PACKAGE}@{lock['packageVersion']}, rules {lock['rulesVersion']})")
    return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--version", default="latest", help="package version to vendor (default: latest)")
    parser.add_argument("--check", action="store_true", help="only report whether the vendored copy is behind npm")
    args = parser.parse_args()

    if args.check:
        sys.exit(check())
    try:
        sync(args.version)
    except (URLError, OSError, RuntimeError, ValueError) as error:
        print(f"ERROR: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
