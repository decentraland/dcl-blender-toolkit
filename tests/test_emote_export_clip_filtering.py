"""Regression tests: an emote GLB must only carry the active emote's clips.

The glTF exporter emits, per rig, the active action plus every non-muted NLA
strip - and when the export holds a single armature, every armature action in
the file (export_anim_single_armature). A file with two emotes authored in it
exported four clips, which the Builder rejects and both previews choke on.
"""

import importlib.util
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _load_emote_utils():
    """Load emote_utils standalone; importing src/ would pull in bpy."""
    path = os.path.join(SRC_DIR, "ops", "emote_utils.py")
    spec = importlib.util.spec_from_file_location("emote_utils", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


emote_utils = _load_emote_utils()


class FakeStrip:
    def __init__(self, mute=False):
        self.mute = mute


class FakeTrack:
    def __init__(self, strips):
        self.strips = strips


class FakeAnimationData:
    def __init__(self, nla_tracks):
        self.nla_tracks = nla_tracks


class FakeRig:
    def __init__(self, name, nla_tracks=None, library=None):
        self.name = name
        self.library = library
        self.animation_data = FakeAnimationData(nla_tracks) if nla_tracks is not None else None


class TestNlaMuting:
    def test_all_strips_are_muted_and_restored(self):
        stashed = FakeStrip(mute=False)
        already_muted = FakeStrip(mute=True)
        other_take = FakeStrip(mute=False)
        avatar = FakeRig("Armature", nla_tracks=[FakeTrack([stashed, already_muted])])
        prop = FakeRig("Armature_Prop", nla_tracks=[FakeTrack([other_take])])

        cache = emote_utils.mute_armature_nla_strips([avatar, prop])

        assert stashed.mute and already_muted.mute and other_take.mute

        emote_utils.restore_nla_mutes(cache)

        assert not stashed.mute
        assert already_muted.mute, "a strip muted by the author must stay muted"
        assert not other_take.mute

    def test_rig_without_animation_data_is_skipped(self):
        rig = FakeRig("Armature")
        assert emote_utils.mute_armature_nla_strips([rig]) == []


class TestExportNames:
    def _find_object(self, objects):
        return lambda name: next((obj for obj in objects if obj.name == name), None)

    def test_avatar_rig_is_renamed_to_armature(self):
        avatar = FakeRig("Armature.001")
        cache = emote_utils.claim_export_names(avatar, [], self._find_object([avatar]))
        assert avatar.name == "Armature"

        emote_utils.restore_names(cache)
        assert avatar.name == "Armature.001"

    def test_name_holder_is_parked_and_restored(self):
        reference = FakeRig("Armature")
        avatar = FakeRig("Armature.001")
        objects = [reference, avatar]

        cache = emote_utils.claim_export_names(avatar, [], self._find_object(objects))

        assert avatar.name == "Armature"
        assert reference.name == "Armature.dclexport"

        emote_utils.restore_names(cache)

        assert avatar.name == "Armature.001"
        assert reference.name == "Armature"

    def test_single_prop_rig_is_renamed(self):
        avatar = FakeRig("Armature")
        prop = FakeRig("Gun_Rig")
        cache = emote_utils.claim_export_names(avatar, [prop], self._find_object([avatar, prop]))
        assert prop.name == "Armature_Prop"

        emote_utils.restore_names(cache)
        assert prop.name == "Gun_Rig"

    def test_multiple_prop_rigs_are_left_alone(self):
        avatar = FakeRig("Armature")
        props = [FakeRig("Gun_Rig"), FakeRig("Holster_Rig")]
        cache = emote_utils.claim_export_names(avatar, props, self._find_object([avatar, *props]))
        assert [prop.name for prop in props] == ["Gun_Rig", "Holster_Rig"]
        assert cache == []

    def test_correct_names_leave_nothing_to_restore(self):
        avatar = FakeRig("Armature")
        prop = FakeRig("Armature_Prop")
        assert emote_utils.claim_export_names(avatar, [prop], self._find_object([avatar, prop])) == []

    def test_linked_holder_blocks_the_rename(self):
        linked_reference = FakeRig("Armature", library=object())
        avatar = FakeRig("Armature.001")
        cache = emote_utils.claim_export_names(avatar, [], self._find_object([linked_reference, avatar]))
        assert avatar.name == "Armature.001", "renaming anyway would only get auto-suffixed"
        assert linked_reference.name == "Armature"
        assert cache == []

    def test_linked_rig_is_never_renamed(self):
        avatar = FakeRig("Armature.001", library=object())
        assert emote_utils.claim_export_names(avatar, [], self._find_object([avatar])) == []
        assert avatar.name == "Armature.001"


class FakeFCurve:
    def __init__(self, data_path):
        self.data_path = data_path


class FakeAction:
    def __init__(self, name, bone_names=()):
        self.name = name
        self.fcurves = [FakeFCurve(f'pose.bones["{bone}"].location') for bone in bone_names]


class FakePoseBone:
    def __init__(self, name):
        self.name = name


class FakePose:
    def __init__(self, bone_names):
        self.bones = [FakePoseBone(name) for name in bone_names]


class FakeAnimatedRig:
    def __init__(self, name, bone_names, active_action=None):
        self.name = name
        self.pose = FakePose(bone_names)
        self.animation_data = type("FakeAnimData", (), {"action": active_action})() if active_action else None


def _two_emote_scene():
    """A file holding two emotes, each with its own prop rig."""
    avatar = FakeAnimatedRig("Armature", ["Avatar_Hips"], FakeAction("Invaders_Avatar"))
    tv_rig = FakeAnimatedRig("Armature_Prop", ["GameSet_Root"], FakeAction("Gamer_Prop", ["GameSet_Root"]))
    gun_rig = FakeAnimatedRig("Armature_Prop.001", ["Prop_Root"])
    actions = [
        FakeAction("Gamer_Avatar", ["Avatar_Hips"]),
        FakeAction("Gamer_Prop", ["GameSet_Root"]),
        FakeAction("Invaders_Avatar", ["Avatar_Hips"]),
        FakeAction("Invaders_Prop", ["Prop_Root"]),
    ]
    return avatar, tv_rig, gun_rig, actions


class TestPropActionPairing:
    def test_parked_prop_action_is_paired_by_name_and_bones(self):
        avatar, tv_rig, gun_rig, actions = _two_emote_scene()
        selected, assignments = emote_utils.pair_prop_actions(avatar, [tv_rig, gun_rig], actions)
        assert selected == [gun_rig], "only the rig whose action pairs with Invaders_Avatar"
        assert len(assignments) == 1
        rig, action, previous = assignments[0]
        assert rig is gun_rig
        assert action.name == "Invaders_Prop"
        assert previous is None

    def test_other_emotes_prop_rig_is_excluded(self):
        avatar, tv_rig, gun_rig, actions = _two_emote_scene()
        selected, _ = emote_utils.pair_prop_actions(avatar, [tv_rig, gun_rig], actions)
        assert tv_rig not in selected, "Gamer's prop must not export with the Invaders emote"

    def test_already_active_paired_action_needs_no_assignment(self):
        avatar, _, gun_rig, actions = _two_emote_scene()
        gun_rig.animation_data = type("FakeAnimData", (), {"action": actions[3]})()
        selected, assignments = emote_utils.pair_prop_actions(avatar, [gun_rig], actions)
        assert selected == [gun_rig]
        assert assignments == []

    def test_pairing_is_case_insensitive(self):
        avatar = FakeAnimatedRig("Armature", ["Avatar_Hips"], FakeAction("Invaders_avatar"))
        gun_rig = FakeAnimatedRig("Gun", ["Prop_Root"])
        actions = [FakeAction("INVADERS_PROP", ["Prop_Root"])]
        selected, assignments = emote_utils.pair_prop_actions(avatar, [gun_rig], actions)
        assert selected == [gun_rig]
        assert len(assignments) == 1

    def test_without_naming_convention_animated_rigs_export(self):
        avatar = FakeAnimatedRig("Armature", ["Avatar_Hips"], FakeAction("MyDance"))
        animated = FakeAnimatedRig("Gun", ["Prop_Root"], FakeAction("GunAction", ["Prop_Root"]))
        static = FakeAnimatedRig("Crate", ["Crate_Root"])
        selected, assignments = emote_utils.pair_prop_actions(avatar, [animated, static], [])
        assert selected == [animated]
        assert assignments == []

    def test_prop_action_bound_to_wrong_bones_is_not_paired(self):
        avatar = FakeAnimatedRig("Armature", ["Avatar_Hips"], FakeAction("Invaders_Avatar"))
        tv_rig = FakeAnimatedRig("TV", ["GameSet_Root"])
        actions = [FakeAction("Invaders_Prop", ["Prop_Root"])]
        selected, assignments = emote_utils.pair_prop_actions(avatar, [tv_rig], actions)
        assert selected == []
        assert assignments == []


class TestExporterWiring:
    def test_exporter_disables_the_all_actions_fallback(self):
        src = _read(os.path.join(SRC_DIR, "ops", "export_emote_glb.py"))
        assert '"export_anim_single_armature": False' in src

    def test_exporter_mutes_nla_and_claims_names(self):
        src = _read(os.path.join(SRC_DIR, "ops", "export_emote_glb.py"))
        assert "mute_armature_nla_strips" in src
        assert "claim_export_names" in src
        assert "restore_nla_mutes" in src
        assert "restore_names" in src

    def test_exporter_pairs_prop_rigs_to_the_active_emote(self):
        src = _read(os.path.join(SRC_DIR, "ops", "export_emote_glb.py"))
        assert "pair_prop_actions" in src
        assert "apply_action_assignments" in src
        assert "restore_action_assignments" in src
