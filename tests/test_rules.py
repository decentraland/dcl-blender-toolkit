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
        assert {"expectedFps", "fpsTolerance", "maxDurationSeconds", "rootMotion"} <= set(manifest["emote"])
        assert {"horizontalErrorMeters", "verticalWarnMeters", "verticalErrorMeters"} <= set(
            manifest["emote"]["rootMotion"]
        )
        assert {"emoteBytes", "modelHeadroomBytes"} <= set(manifest["fileSize"])
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
        assert 'manifest()["fileSize"]' in source and 'sizes["emoteBytes"] - sizes["modelHeadroomBytes"]' in source
        assert "file_size > 1024 * 1024" not in source

    def test_fps_is_compared_with_the_tolerance(self):
        source = read_source(os.path.join(SRC_DIR, "ops", "validate_emote.py"))
        assert "fps_tolerance" in source and "fps != 30" not in source

    def test_frame_range_properties_are_not_clamped_to_a_limit(self):
        source = read_source(os.path.join(SRC_DIR, "__init__.py"))
        for prop in ("emote_start_frame", "emote_end_frame"):
            block = source[source.index(prop) : source.index(")", source.index(prop))]
            assert "max=" not in block, f"{prop} is clamped; the duration check decides the frame budget"


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

    def test_rejects_a_manifest_without_a_version_before_writing(self, tmp_path):
        with pytest.raises(RuntimeError, match="string version"):
            sync_rules.write_vendored(b'{"x": 1}', "0.0.1", rules_dir=str(tmp_path))
        assert not (tmp_path / "manifest.json").exists() and not (tmp_path / "manifest.lock").exists()

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

    def _published(self, monkeypatch, manifest):
        monkeypatch.setattr(sync_rules, "read_lock", lambda: {"packageVersion": "0.1.0", "rulesVersion": "0.1.0"})
        monkeypatch.setattr(sync_rules, "package_metadata", lambda version: {"version": "0.2.0", "tarball": "t"})
        monkeypatch.setattr(sync_rules, "fetch", lambda url: b"")
        monkeypatch.setattr(sync_rules, "verify_integrity", lambda data, integrity: None)
        monkeypatch.setattr(sync_rules, "manifest_from_tarball", lambda data: json.dumps(manifest).encode())

    def test_check_warns_when_the_numbers_changed_but_never_fails(self, monkeypatch, capsys):
        with open(os.path.join(RULES_DIR, "manifest.json"), encoding="utf-8") as f:
            changed = json.load(f)
        changed["textures"] = dict(changed["textures"], maxSize=changed["textures"]["maxSize"] + 1)
        changed["version"] = "9.9.9"
        self._published(monkeypatch, changed)
        assert sync_rules.check() == 0
        out = capsys.readouterr().out
        assert "::warning::" in out and "textures, version" in out and "make sync-rules" in out

    def test_check_is_quiet_when_only_the_package_moved(self, monkeypatch, capsys):
        with open(os.path.join(RULES_DIR, "manifest.json"), encoding="utf-8") as f:
            self._published(monkeypatch, json.load(f))
        assert sync_rules.check() == 0
        assert "::warning::" not in capsys.readouterr().out

    def test_check_tolerates_a_truncated_download(self, monkeypatch, capsys):
        def truncated(url):
            raise EOFError("Compressed file ended before the end-of-stream marker was reached")

        with open(os.path.join(RULES_DIR, "manifest.json"), encoding="utf-8") as f:
            self._published(monkeypatch, json.load(f))
        monkeypatch.setattr(sync_rules, "fetch", truncated)
        assert sync_rules.check() == 0
        assert "skipping" in capsys.readouterr().out

    def test_check_tolerates_being_offline(self, monkeypatch, capsys):
        def offline(version):
            raise OSError("no network")

        monkeypatch.setattr(sync_rules, "read_lock", lambda: {"packageVersion": "0.2.0", "rulesVersion": "0.5.0"})
        monkeypatch.setattr(sync_rules, "package_metadata", offline)
        assert sync_rules.check() == 0
        assert "WARNING" in capsys.readouterr().out


class TestSyncScriptHardening:
    def test_integrity_accepts_matching_sha512(self):
        import base64

        data = b"tarball"
        sri = "sha512-" + base64.b64encode(hashlib.sha512(data).digest()).decode()
        sync_rules.verify_integrity(data, sri)

    def test_integrity_fails_closed_when_missing_or_weak(self):
        with pytest.raises(RuntimeError, match="no dist.integrity"):
            sync_rules.verify_integrity(b"tarball", None)
        with pytest.raises(RuntimeError, match="weak"):
            sync_rules.verify_integrity(b"tarball", "sha1-AAAA")

    def test_integrity_rejects_a_tampered_tarball(self):
        with pytest.raises(RuntimeError, match="integrity"):
            sync_rules.verify_integrity(b"tarball", "sha512-AAAA")

    def test_metadata_rejects_a_tarball_off_the_registry(self, monkeypatch):
        body = json.dumps({"version": "1.0.0", "dist": {"tarball": "https://evil.example/x.tgz"}}).encode()
        monkeypatch.setattr(sync_rules, "fetch", lambda url: body)
        with pytest.raises(RuntimeError, match="not hosted"):
            sync_rules.package_metadata("latest")

    def test_check_surfaces_http_errors_as_warnings(self, monkeypatch, capsys):
        from urllib.error import HTTPError

        def missing(version):
            raise HTTPError("https://registry.npmjs.org/x", 404, "Not Found", {}, None)

        monkeypatch.setattr(sync_rules, "read_lock", lambda: {"packageVersion": "0.2.0", "rulesVersion": "0.5.0"})
        monkeypatch.setattr(sync_rules, "package_metadata", missing)
        assert sync_rules.check() == 0
        assert "::warning::" in capsys.readouterr().out
