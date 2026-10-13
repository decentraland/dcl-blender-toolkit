"""Regression tests for exporting emotes that carry a prop."""

import os

from tests._helpers import SRC_DIR, load_emote_utils, read_source

emote_utils = load_emote_utils()


class FakeBone:
    def __init__(self, name):
        self.name = name


class FakeBoneCollection:
    def __init__(self, names):
        self._bones = [FakeBone(name) for name in names]

    def __iter__(self):
        return iter(self._bones)

    def __contains__(self, name):
        return any(bone.name == name for bone in self._bones)


class FakeArmatureData:
    def __init__(self, bone_names):
        self.bones = FakeBoneCollection(bone_names)


class FakeModifier:
    def __init__(self, type_, obj):
        self.type = type_
        self.object = obj


class FakeObject:
    def __init__(self, name, type_="MESH", bone_names=None, parent=None):
        self.name = name
        self.type = type_
        self.parent = parent
        self.modifiers = []
        self.data = FakeArmatureData(bone_names or []) if type_ == "ARMATURE" else object()


class FakeContext:
    def __init__(self, objects, active=None, selected=None):
        self.scene = type("FakeScene", (), {"objects": objects})()
        self.active_object = active
        self.selected_objects = selected if selected is not None else []


AVATAR_BONES = ["Avatar_Hips", "Avatar_Spine", "CTRL_Avatar_Root"]
PROP_BONES = ["Prop_Root"]


def _prop_emote_scene():
    avatar = FakeObject("Armature", "ARMATURE", AVATAR_BONES)
    avatar_mesh = FakeObject("ShapeA_uBody_BaseMesh", "MESH", parent=avatar)
    prop = FakeObject("Armature_Prop", "ARMATURE", PROP_BONES)
    prop_mesh = FakeObject("Space_Gun", "MESH", parent=prop)
    prop_skinned = FakeObject("Laser", "MESH")
    prop_skinned.modifiers.append(FakeModifier("ARMATURE", prop))
    unrelated = FakeObject("Reference_Ground", "MESH")
    objects = [avatar, avatar_mesh, prop, prop_mesh, prop_skinned, unrelated]
    return objects, avatar, prop


class TestArmatureIdentification:
    def test_avatar_rig_is_recognised(self):
        avatar = FakeObject("Armature", "ARMATURE", AVATAR_BONES)
        assert emote_utils.is_avatar_armature(avatar)
        assert not emote_utils.is_prop_armature(avatar)

    def test_prop_rig_is_not_mistaken_for_avatar(self):
        prop = FakeObject("Armature_Prop", "ARMATURE", PROP_BONES)
        assert not emote_utils.is_avatar_armature(prop)
        assert emote_utils.is_prop_armature(prop)

    def test_meshes_are_neither(self):
        mesh = FakeObject("Space_Gun", "MESH")
        assert not emote_utils.is_avatar_armature(mesh)
        assert not emote_utils.is_prop_armature(mesh)

    def test_active_prop_rig_does_not_shadow_the_avatar_rig(self):
        objects, avatar, prop = _prop_emote_scene()
        context = FakeContext(objects, active=prop, selected=[prop])
        assert emote_utils.find_avatar_armature(context) is avatar

    def test_prop_rigs_are_listed(self):
        objects, avatar, prop = _prop_emote_scene()
        context = FakeContext(objects, active=avatar)
        assert emote_utils.find_prop_armatures(context, avatar) == [prop]

    def test_a_mocap_or_retarget_rig_is_not_a_prop(self):
        source = FakeObject("mixamorig", "ARMATURE", ["mixamorig:Hips", "mixamorig:Spine"])
        assert not emote_utils.is_prop_armature(source)
        avatar = FakeObject("Armature", "ARMATURE", AVATAR_BONES)
        assert emote_utils.find_prop_armatures(FakeContext([avatar, source], active=avatar), avatar) == []

    def test_a_rig_animated_by_a_prop_action_is_a_prop(self):
        rig = FakeObject("Gun_Rig", "ARMATURE", ["root", "trigger"])
        rig.animation_data = type("AnimData", (), {"action": type("Action", (), {"name": "Invaders_Prop"})()})()
        assert emote_utils.is_prop_armature(rig)

    def test_the_imported_prop_rig_name_counts(self):
        assert emote_utils.is_prop_armature(FakeObject("Armature_Prop.001", "ARMATURE", ["root"]))

    def test_custom_rigs_that_miss_the_convention_are_listed_for_the_user(self):
        avatar = FakeObject("Armature", "ARMATURE", AVATAR_BONES)
        prop = FakeObject("Armature_Prop", "ARMATURE", PROP_BONES)
        sword = FakeObject("Sword_Rig", "ARMATURE", ["root", "blade"])
        context = FakeContext([avatar, prop, sword], active=avatar)
        assert emote_utils.find_unrecognised_armatures(context, avatar) == [sword]


def _with_action(rig, name):
    rig.animation_data = type("AnimData", (), {"action": type("Action", (), {"name": name})()})()
    return rig


class TestPropRigChoice:
    def test_no_prop_rigs_means_no_choice(self):
        assert emote_utils.choose_prop_armature(FakeContext([]), []) is None

    def test_the_active_or_selected_prop_rig_wins(self):
        first = _with_action(FakeObject("Armature_Prop", "ARMATURE", PROP_BONES), "A_Prop")
        second = FakeObject("Armature_Prop.001", "ARMATURE", PROP_BONES)
        rigs = [first, second]
        assert emote_utils.choose_prop_armature(FakeContext(rigs, active=second), rigs) is second
        assert emote_utils.choose_prop_armature(FakeContext(rigs, selected=[second]), rigs) is second

    def test_otherwise_a_rig_without_a_prop_action_is_preferred(self):
        # Emote A already owns the first rig; a new emote's action must not replace A_Prop.
        first = _with_action(FakeObject("Armature_Prop", "ARMATURE", PROP_BONES), "A_Prop")
        second = FakeObject("Armature_Prop.001", "ARMATURE", PROP_BONES)
        rigs = [first, second]
        assert emote_utils.choose_prop_armature(FakeContext(rigs), rigs) is second

    def test_the_first_rig_is_the_fallback(self):
        first = _with_action(FakeObject("Armature_Prop", "ARMATURE", PROP_BONES), "A_Prop")
        second = _with_action(FakeObject("Armature_Prop.001", "ARMATURE", PROP_BONES), "B_Prop")
        rigs = [first, second]
        assert emote_utils.choose_prop_armature(FakeContext(rigs), rigs) is first


class TestEmoteExportObjectSet:
    def test_prop_rig_and_its_geometry_are_included(self):
        objects, avatar, prop = _prop_emote_scene()
        context = FakeContext(objects, active=avatar)
        names = [obj.name for obj in emote_utils.collect_emote_export_objects(context, avatar)]
        assert "Armature" in names
        assert "Armature_Prop" in names
        assert "Space_Gun" in names, "prop geometry parented to the prop rig must be exported"
        assert "Laser" in names, "prop geometry skinned via Armature modifier must be exported"

    def test_avatar_body_meshes_and_scene_props_are_excluded(self):
        objects, avatar, prop = _prop_emote_scene()
        context = FakeContext(objects, active=avatar)
        names = [obj.name for obj in emote_utils.collect_emote_export_objects(context, avatar)]
        assert "ShapeA_uBody_BaseMesh" not in names
        assert "Reference_Ground" not in names

    def test_nested_prop_geometry_is_included(self):
        avatar = FakeObject("Armature", "ARMATURE", AVATAR_BONES)
        prop = FakeObject("Armature_Prop", "ARMATURE", PROP_BONES)
        holder = FakeObject("Gun_Group", "EMPTY", parent=prop)
        nested = FakeObject("Gun_Barrel", "MESH", parent=holder)
        context = FakeContext([avatar, prop, holder, nested], active=avatar)
        names = [obj.name for obj in emote_utils.collect_emote_export_objects(context, avatar)]
        assert "Gun_Barrel" in names

    def test_no_duplicates_when_geometry_is_both_parented_and_skinned(self):
        avatar = FakeObject("Armature", "ARMATURE", AVATAR_BONES)
        prop = FakeObject("Armature_Prop", "ARMATURE", PROP_BONES)
        mesh = FakeObject("Space_Gun", "MESH", parent=prop)
        mesh.modifiers.append(FakeModifier("ARMATURE", prop))
        context = FakeContext([avatar, prop, mesh], active=avatar)
        names = [obj.name for obj in emote_utils.collect_emote_export_objects(context, avatar)]
        assert names.count("Space_Gun") == 1

    def test_emote_without_prop_exports_the_armature_alone(self):
        avatar = FakeObject("Armature", "ARMATURE", AVATAR_BONES)
        avatar_mesh = FakeObject("ShapeA_uBody_BaseMesh", "MESH", parent=avatar)
        context = FakeContext([avatar, avatar_mesh], active=avatar)
        objects = emote_utils.collect_emote_export_objects(context, avatar)
        assert [obj.name for obj in objects] == ["Armature"]


class TestExporterWiring:
    def test_exporter_uses_the_prop_aware_object_set(self):
        src = read_source(os.path.join(SRC_DIR, "ops", "export_emote_glb.py"))
        assert "collect_emote_export_objects" in src
        assert "find_avatar_armature" in src

    def test_exporter_no_longer_hides_everything_but_one_armature(self):
        src = read_source(os.path.join(SRC_DIR, "ops", "export_emote_glb.py"))
        assert "obj.hide_viewport = obj != armature" not in src


class TestValidatorWiring:
    def test_validator_reads_registered_properties(self):
        """Guards the regression where a merge restored lookups of unregistered properties."""
        src = read_source(os.path.join(SRC_DIR, "ops", "validate_emote.py"))
        assert "context.scene.dcl_tools" in src
        assert "dcl_emote_start_frame" not in src
        assert "dcl_emote_end_frame" not in src
        assert "dcl_emote_strict_validation" not in src

    def test_validator_checks_prop_rigs(self):
        src = read_source(os.path.join(SRC_DIR, "ops", "validate_emote.py"))
        assert "find_prop_armatures" in src
        assert "prop_armature_count" in src


class TestActionNaming:
    def test_action_creation_is_prop_aware(self):
        src = read_source(os.path.join(SRC_DIR, "ops", "emote_actions.py"))
        assert "find_prop_armatures" in src
        assert "_Avatar" in src
        assert "_Prop" in src

    def test_only_one_prop_action_is_created(self):
        # A second rig would get '_Prop_2', which pair_prop_actions never matches.
        src = read_source(os.path.join(SRC_DIR, "ops", "emote_actions.py"))
        assert "_Prop_" not in src
        assert "prop_armature = choose_prop_armature(context, prop_armatures)" in src

    def test_skipped_armatures_are_explained(self):
        src = read_source(os.path.join(SRC_DIR, "ops", "emote_actions.py"))
        assert src.count("find_unrecognised_armatures(context") == 2
        assert "PROP_CONVENTION_HINT" in src


class TestRotationDataPath:
    def test_follows_the_bone_rotation_mode(self):
        class Bone:
            def __init__(self, mode):
                self.rotation_mode = mode

        assert emote_utils.rotation_data_path(Bone("QUATERNION")) == "rotation_quaternion"
        assert emote_utils.rotation_data_path(Bone("AXIS_ANGLE")) == "rotation_axis_angle"
        assert emote_utils.rotation_data_path(Bone("XYZ")) == "rotation_euler"
