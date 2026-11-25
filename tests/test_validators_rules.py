"""The validators apply the vendored limits the way the rule book does: same severity, same unit."""

from types import SimpleNamespace

import pytest

from tests._helpers import load_toolkit_module

rules = load_toolkit_module("rules")
validate_emote = load_toolkit_module("ops.validate_emote")
avatar_limitations = load_toolkit_module("ops.avatar_limitations")


def emote_context(fps, start, end, strict=False, fps_base=1.0, sampling_rate=1):
    """A scene with no rig: validation stops right after the fps and duration checks."""
    scene = SimpleNamespace(
        dcl_tools=SimpleNamespace(
            emote_strict_validation=strict,
            emote_start_frame=start,
            emote_end_frame=end,
            emote_sampling_rate=sampling_rate,
        ),
        render=SimpleNamespace(fps=fps, fps_base=fps_base),
        objects=[],
    )
    return SimpleNamespace(scene=scene, active_object=None, selected_objects=[])


class TestEmoteTiming:
    @pytest.mark.parametrize(
        "fps, start, end, expect_fps_warning, expect_duration_error",
        [
            (30, 1, 300, False, False),  # last key at exactly 10 s
            (30, 1, 301, False, True),  # one frame over: the exporter keeps absolute times
            (30, 61, 360, False, True),  # 300 frames long, but the last key sits at 12 s
            (25, 1, 300, False, True),  # within the fps tolerance, but 12 s long
            (24, 1, 240, True, False),  # outside the tolerance: advisory only, 10 s is fine
            (60, 1, 600, True, False),  # far from 30 fps, still 10 s: the Builder accepts it
        ],
    )
    def test_fps_is_advisory_and_duration_is_the_last_key_time(
        self, fps, start, end, expect_fps_warning, expect_duration_error
    ):
        result = validate_emote.run_emote_validation(emote_context(fps, start, end))
        fps_warnings = [m for m in result["warnings"] if "framerate" in m]
        duration_errors = [m for m in result["errors"] if "Last key sits" in m]
        assert bool(fps_warnings) == expect_fps_warning
        assert bool(duration_errors) == expect_duration_error
        assert not [m for m in result["errors"] if "framerate" in m], "fps never blocks"
        assert result["metrics"]["duration_s"] == round(end / fps, 2)

    def test_sampling_rate_lowers_the_frame_rate_the_builder_infers(self):
        # Exported every 2 frames, a 30 fps scene has keys 1/15 s apart, which the rule book reads as ~15 fps.
        result = validate_emote.run_emote_validation(emote_context(30, 1, 300, sampling_rate=2))
        assert result["metrics"]["exported_fps"] == 15
        assert any("sampled every 2 frames" in m for m in result["warnings"])
        assert not [m for m in result["errors"] if "Last key sits" in m], "sampling never changes the last key time"

    def test_fps_base_is_part_of_the_frame_rate_like_the_exporter(self):
        # 30 fps with an NTSC base is 30.03 fps in the exporter's formula, so frame 300 sits just under 10 s.
        result = validate_emote.run_emote_validation(emote_context(30, 1, 300, fps_base=1.001))
        assert result["metrics"]["fps"] == 30.03
        assert result["metrics"]["duration_s"] == round(300 / 30.03, 2)
        assert not [m for m in result["errors"] if "Last key sits" in m]

    def test_limits_come_from_the_manifest(self):
        emote = rules.manifest()["emote"]
        fps = emote["expectedFps"] + emote["fpsTolerance"] + 1
        result = validate_emote.run_emote_validation(emote_context(fps, 1, 2))
        assert any(f"{emote['expectedFps']}fps" in m for m in result["warnings"])
        over = emote["maxDurationSeconds"] * emote["expectedFps"] + 1
        result = validate_emote.run_emote_validation(emote_context(emote["expectedFps"], 1, over))
        assert any(f"max is {emote['maxDurationSeconds']}s" in m for m in result["errors"])


class TestWearableLimits:
    @pytest.mark.parametrize(
        "identifier, triangles",
        [
            ("MASK", 500),
            ("HAND_ACCESSORY", 1000),
            ("HAT", 1500),
            ("HAND_ACCESSORY_HIDE", 1500),
            ("HELMET_HIDE_HEAD", 4000),
        ],
    )
    def test_known_budgets(self, identifier, triangles):
        # Values as of rules 0.8.x: a sync that changes them must update this table on purpose.
        assert avatar_limitations.wearable_limits(identifier)["triangles"] == triangles

    def test_tolerated_triangles_follow_the_rule_book_margin(self):
        for identifier in avatar_limitations.WEARABLE_TYPES:
            limits = avatar_limitations.wearable_limits(identifier)
            assert limits["triangles_tolerated"] == rules.triangle_tolerated_limit(limits["triangles"])
            assert limits["triangles_tolerated"] > limits["triangles"]

    @pytest.mark.parametrize(
        "count, icon",
        [
            (1000, "CHECKMARK"),
            (1200, "WARNING_LARGE"),  # 80% of the budget
            (1500, "WARNING_LARGE"),  # exactly the budget: accepted, not a rejection
            (1501, "WARNING_LARGE"),  # inside the tolerated margin
            (1650, "WARNING_LARGE"),  # the last tolerated count
            (1651, "ERROR"),
        ],
    )
    def test_triangle_icon_follows_the_rule_book_severity(self, count, icon):
        assert avatar_limitations.triangles_icon(count, 1500) == icon

    def test_material_limit_grows_by_one_with_emission_or_transparency(self):
        hat = avatar_limitations.wearable_limits("HAT")
        skin = avatar_limitations.wearable_limits("SKIN")
        assert avatar_limitations.effective_material_limit(hat, {"emission_or_alpha": False}) == 2
        assert avatar_limitations.effective_material_limit(hat, {"emission_or_alpha": True}) == 3
        assert avatar_limitations.effective_material_limit(hat, {}) == 2
        assert avatar_limitations.effective_material_limit(skin, {"emission_or_alpha": True}) == 5

    def test_every_type_has_a_category_the_rule_book_knows(self):
        per_category = rules.manifest()["triangles"]["perCategory"]
        for _label, category, _hides in avatar_limitations.WEARABLE_TYPES.values():
            assert category in per_category

    def test_helmet_hiding_the_head_shows_the_capped_budget(self):
        tris = rules.manifest()["triangles"]
        assert avatar_limitations.wearable_limits("HELMET_HIDE_HEAD")["triangles"] == tris["hiddenHeadLimit"]

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


def _socket(value, linked=False):
    return SimpleNamespace(default_value=value, is_linked=linked)


def _material(inputs=None, blend_method="OPAQUE", use_nodes=True):
    """A stand-in for a Blender material with one Principled BSDF whose inputs are given by name."""
    node = SimpleNamespace(type="BSDF_PRINCIPLED", inputs=inputs or {})
    return SimpleNamespace(use_nodes=use_nodes, node_tree=SimpleNamespace(nodes=[node]), blend_method=blend_method)


class TestMaterialTraits:
    """What earns the third material, read from the Principled BSDF the way the glTF exporter does."""

    def test_emissive_needs_a_strength_and_a_colour_that_is_not_black(self):
        glowing = _material({"Emission Color": _socket((1.0, 0.4, 0.0, 1.0)), "Emission Strength": _socket(1.0)})
        black = _material({"Emission Color": _socket((0.0, 0.0, 0.0, 1.0)), "Emission Strength": _socket(1.0)})
        off = _material({"Emission Color": _socket((1.0, 1.0, 1.0, 1.0)), "Emission Strength": _socket(0.0)})
        textured = _material(
            {"Emission Color": _socket((0.0, 0.0, 0.0, 1.0), linked=True), "Emission Strength": _socket(1.0)}
        )
        assert avatar_limitations.material_is_emissive(glowing)
        assert not avatar_limitations.material_is_emissive(black)
        assert not avatar_limitations.material_is_emissive(off)
        assert avatar_limitations.material_is_emissive(textured)

    def test_emissive_reads_the_older_input_name_too(self):
        older = _material({"Emission": _socket((0.2, 0.2, 0.2, 1.0)), "Emission Strength": _socket(2.0)})
        assert avatar_limitations.material_is_emissive(older)

    def test_transparent_is_an_alpha_input_that_is_linked_or_below_one(self):
        assert avatar_limitations.material_is_transparent(_material({"Alpha": _socket(0.5)}))
        assert avatar_limitations.material_is_transparent(_material({"Alpha": _socket(1.0, linked=True)}))
        assert not avatar_limitations.material_is_transparent(_material({"Alpha": _socket(1.0)}))

    def test_the_blend_mode_alone_says_nothing_from_blender_4_2_on(self):
        # there the property mirrors the render method (a new material reads HASHED) and the exporter ignores it
        assert not avatar_limitations.material_is_transparent(_material({"Alpha": _socket(1.0)}, blend_method="HASHED"))

    def test_a_material_without_nodes_has_neither(self):
        plain = _material(use_nodes=False)
        assert not avatar_limitations.material_is_emissive(plain)
        assert not avatar_limitations.material_is_transparent(plain)
