"""The vendored rule book: its provenance, its loader and the validators that must read from it."""

import hashlib
import importlib.util
import io
import json
import os
import re
import sys
import tarfile

import pytest

from tests._helpers import SRC_DIR, read_source

ROOT_DIR = os.path.dirname(SRC_DIR)
RULES_DIR = os.path.join(SRC_DIR, "rules")

sys.path.insert(0, os.path.join(ROOT_DIR, "scripts"))
import sync_rules  # noqa: E402


def load_rules():
    spec = importlib.util.spec_from_file_location("rules", os.path.join(RULES_DIR, "__init__.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def rules():
    return load_rules()


class TestProvenance:
    def test_lock_matches_the_vendored_manifest(self):
        with open(os.path.join(RULES_DIR, "manifest.lock"), encoding="utf-8") as f:
            lock = json.load(f)
        with open(os.path.join(RULES_DIR, "manifest.json"), "rb") as f:
            raw = f.read()
        assert lock["package"] == sync_rules.PACKAGE
        assert lock["rulesVersion"] == json.loads(raw)["version"]
        assert lock["sha256"] == hashlib.sha256(raw).hexdigest(), (
            "manifest.json was edited by hand; run make sync-rules"
        )

    def test_manifest_has_the_blocks_the_validators_read(self, rules):
        manifest = rules.manifest()
        assert {"default", "perCategory", "hiddenHandsBudget", "headSlots", "hiddenHeadLimit"} <= set(
            manifest["triangles"]
        )
        assert {"default", "skin", "maxSize"} <= set(manifest["textures"])
        assert {"default", "skin", "avatarSkinMat"} <= set(manifest["materials"])
        assert {"expectedFps", "fpsTolerance", "maxFrames", "rootMotion"} <= set(manifest["emote"])
        assert {"horizontalErrorMeters", "verticalWarnMeters", "verticalErrorMeters"} <= set(
            manifest["emote"]["rootMotion"]
        )
        assert "emoteBytes" in manifest["fileSize"]
        assert re.fullmatch(r"\d+\.\d+\.\d+", rules.rules_version())


class TestTriangleLimit:
    def test_plain_category(self, rules):
        tris = rules.manifest()["triangles"]
        assert rules.triangle_limit("hat") == tris["perCategory"]["hat"]
        assert rules.triangle_limit("unknown") == tris["default"]

    def test_hiding_the_hands_adds_their_budget(self, rules):
        tris = rules.manifest()["triangles"]
        assert (
            rules.triangle_limit("hands_wear", ("hands",))
            == tris["perCategory"]["hands_wear"] + tris["hiddenHandsBudget"]
        )

    def test_hiding_the_head_caps_at_the_helmet_limit(self, rules):
        tris = rules.manifest()["triangles"]
        assert rules.triangle_limit("hat", ("head",)) == tris["hiddenHeadLimit"]
        assert rules.triangle_limit("helmet") <= tris["hiddenHeadLimit"]


class TestValidatorsReadTheManifest:
    """A limit typed into a validator drifts from the Builder; every number must come from src/rules."""

    CONSUMERS = ["validate_emote.py", "avatar_limitations.py", "validate_textures.py", "export_emote_glb.py"]
    # Unit conversions (1000, 1024 * 1024) are allowed; the limits themselves are not.
    KNOWN_LIMITS = re.compile(r"(?<![\w.])(500|1500|3000|4000|5000|300|25|35)(?![\w.])")

    @pytest.mark.parametrize("filename", CONSUMERS)
    def test_imports_the_rules(self, filename):
        source = read_source(os.path.join(SRC_DIR, "ops", filename))
        assert "from ..rules import" in source

    @pytest.mark.parametrize("filename", CONSUMERS)
    def test_no_rule_book_literals(self, filename):
        source = read_source(os.path.join(SRC_DIR, "ops", filename))
        code = "\n".join(line for line in source.splitlines() if not line.lstrip().startswith("#"))
        hits = [m.group(0) for m in self.KNOWN_LIMITS.finditer(code)]
        assert not hits, f"{filename} hard-codes {hits}; read them from the manifest instead"

    def test_export_size_limit_comes_from_the_manifest(self):
        source = read_source(os.path.join(SRC_DIR, "ops", "export_emote_glb.py"))
        assert 'manifest()["fileSize"]["emoteBytes"]' in source
        assert "file_size > 1024 * 1024" not in source

    def test_fps_is_compared_with_the_tolerance(self):
        source = read_source(os.path.join(SRC_DIR, "ops", "validate_emote.py"))
        assert "fps_tolerance" in source and "fps != 30" not in source


class TestSyncScript:
    def _tarball(self, entries):
        buffer = io.BytesIO()
        with tarfile.open(fileobj=buffer, mode="w:gz") as tar:
            for name, data in entries.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                tar.addfile(info, io.BytesIO(data))
        return buffer.getvalue()

    def test_reads_the_manifest_out_of_the_npm_tarball(self):
        manifest = json.dumps({"version": "9.9.9"}).encode()
        tarball = self._tarball({"package/package.json": b"{}", sync_rules.MANIFEST_IN_TARBALL: manifest})
        assert sync_rules.manifest_from_tarball(tarball) == manifest

    def test_rejects_a_tarball_without_the_manifest(self):
        with pytest.raises(RuntimeError, match="not in the package tarball"):
            sync_rules.manifest_from_tarball(self._tarball({"package/package.json": b"{}"}))

    def test_writes_the_manifest_and_its_lock(self, tmp_path):
        lock = sync_rules.write_vendored(b'{"version": "1.2.3", "x": 1}', "0.0.1", rules_dir=str(tmp_path))
        written = (tmp_path / "manifest.json").read_bytes()
        assert json.loads(written) == {"version": "1.2.3", "x": 1}
        assert lock["rulesVersion"] == "1.2.3"
        assert lock["packageVersion"] == "0.0.1"
        assert lock["sha256"] == hashlib.sha256(written).hexdigest()
        assert json.loads((tmp_path / "manifest.lock").read_text()) == lock

    def test_check_reports_a_stale_copy(self, monkeypatch, capsys):
        monkeypatch.setattr(sync_rules, "read_lock", lambda: {"packageVersion": "0.1.0", "rulesVersion": "0.1.0"})
        monkeypatch.setattr(sync_rules, "package_metadata", lambda version: {"version": "0.2.0"})
        assert sync_rules.check() == 1
        assert "make sync-rules" in capsys.readouterr().out

    def test_check_passes_on_the_latest(self, monkeypatch):
        monkeypatch.setattr(sync_rules, "read_lock", lambda: {"packageVersion": "0.2.0", "rulesVersion": "0.5.0"})
        monkeypatch.setattr(sync_rules, "package_metadata", lambda version: {"version": "0.2.0"})
        assert sync_rules.check() == 0

    def test_check_tolerates_being_offline(self, monkeypatch, capsys):
        def offline(version):
            raise OSError("no network")

        monkeypatch.setattr(sync_rules, "read_lock", lambda: {"packageVersion": "0.2.0", "rulesVersion": "0.5.0"})
        monkeypatch.setattr(sync_rules, "package_metadata", offline)
        assert sync_rules.check() == 0
        assert "WARNING" in capsys.readouterr().out
