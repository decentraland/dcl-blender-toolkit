"""The validators apply the vendored limits the way the rule book does: same severity, same unit."""

from types import SimpleNamespace

import pytest

from tests._helpers import load_toolkit_module

rules = load_toolkit_module("rules")
validate_emote = load_toolkit_module("ops.validate_emote")
avatar_limitations = load_toolkit_module("ops.avatar_limitations")


def emote_context(fps, start, end, strict=False):
    """A scene with no rig: validation stops right after the fps and duration checks."""
    scene = SimpleNamespace(
        dcl_tools=SimpleNamespace(emote_strict_validation=strict, emote_start_frame=start, emote_end_frame=end),
        render=SimpleNamespace(fps=fps),
        objects=[],
    )
    return SimpleNamespace(scene=scene, active_object=None, selected_objects=[])


def timing_messages(result):
    return [m for m in result["errors"] + result["warnings"] if "framerate" in m or "Animation runs" in m]


class TestEmoteTiming:
    @pytest.mark.parametrize(
        "fps, start, end, expect_fps_warning, expect_duration_error",
        [
            (30, 1, 301, False, False),  # exactly 10 s at 30 fps
            (30, 1, 302, False, True),  # one frame over 10 s
            (25, 1, 300, False, True),  # within the fps tolerance, but 12 s long
            (24, 1, 241, True, False),  # outside the tolerance: advisory only, 10 s is fine
            (60, 1, 601, True, False),  # far from 30 fps, still 10 s: the Builder accepts it
        ],
    )
    def test_fps_is_advisory_and_duration_is_measured_in_seconds(
        self, fps, start, end, expect_fps_warning, expect_duration_error
    ):
        result = validate_emote.run_emote_validation(emote_context(fps, start, end))
        fps_warnings = [m for m in result["warnings"] if "framerate" in m]
        duration_errors = [m for m in result["errors"] if "Animation runs" in m]
        assert bool(fps_warnings) == expect_fps_warning
        assert bool(duration_errors) == expect_duration_error
        assert not [m for m in result["errors"] if "framerate" in m], "fps never blocks"
        assert result["metrics"]["duration_s"] == round((end - start) / fps, 2)

    def test_limits_come_from_the_manifest(self):
        emote = rules.manifest()["emote"]
        fps = emote["expectedFps"] + emote["fpsTolerance"] + 1
        result = validate_emote.run_emote_validation(emote_context(fps, 1, 2))
        assert any(f"{emote['expectedFps']}fps" in m for m in result["warnings"])
        over = emote["maxDurationSeconds"] * emote["expectedFps"] + 2
        result = validate_emote.run_emote_validation(emote_context(emote["expectedFps"], 1, over))
        assert any(f"max is {emote['maxDurationSeconds']}s" in m for m in result["errors"])


class TestWearableLimits:
    def test_every_type_resolves_to_the_rule_book(self):
        tris = rules.manifest()["triangles"]
        for identifier, (_label, category, hides) in avatar_limitations.WEARABLE_TYPES.items():
            limits = avatar_limitations.wearable_limits(identifier)
            assert limits["triangles"] == rules.triangle_limit(category, hides)

    def test_hand_accessory_hiding_the_hand_gets_the_hidden_budget(self):
        tris = rules.manifest()["triangles"]
        plain = avatar_limitations.wearable_limits("HAND_ACCESSORY")["triangles"]
        hiding = avatar_limitations.wearable_limits("HAND_ACCESSORY_HIDE")["triangles"]
        assert hiding == plain + tris["hiddenHandsBudget"]

    def test_skin_gets_its_own_material_and_texture_budget(self):
        manifest = rules.manifest()
        skin = avatar_limitations.wearable_limits("SKIN")
        hat = avatar_limitations.wearable_limits("HAT")
        assert (skin["materials"], skin["textures"]) == (manifest["materials"]["skin"], manifest["textures"]["skin"])
        assert (hat["materials"], hat["textures"]) == (
            manifest["materials"]["default"],
            manifest["textures"]["default"],
        )

    def test_unknown_type_is_an_error(self):
        with pytest.raises(KeyError):
            avatar_limitations.wearable_limits("CAPE")
