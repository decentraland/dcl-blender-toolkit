"""
Integration test for Export Emote GLB — runs inside Blender.

Usage:
    blender --background --python tests/test_emote_export_blender.py

Installs the addon from the built zip and exports a scene modeled after a real
authoring session: the avatar rig auto-suffixed to 'Armature.001' because a
reference object holds the name, a prop rig with geometry, and TWO emotes'
worth of actions (active + parked on NLA). The GLB must come out with only the
active emote's clips and the armature names Decentraland expects.
"""

import json
import os
import struct
import sys
import tempfile

# ---------------------------------------------------------------------------
# Bootstrap: build zip, install addon
# ---------------------------------------------------------------------------

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "scripts"))

import build  # noqa: E402

version = build.read_bl_info_version()
zip_path = build.build_zip(version)

import bpy  # noqa: E402

# Factory settings before enabling: read_factory_settings reloads addons and
# would tear our registration down again. Also disable any installed copy of
# the addon so the test exercises the freshly built one.
bpy.ops.wm.read_factory_settings(use_empty=True)
for module in ("bl_ext.blender_org.decentraland_tools", "bl_ext.user_default.decentraland_tools"):
    try:
        bpy.ops.preferences.addon_disable(module=module)
    except Exception:
        pass

bpy.ops.preferences.addon_install(filepath=zip_path, overwrite=True)
bpy.ops.preferences.addon_enable(module="decentraland_tools")

import decentraland_tools  # noqa: E402

assert decentraland_tools.bl_info["name"] == "Decentraland Tools", "Addon did not load"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        msg = f"  FAIL: {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)


def read_glb(path):
    with open(path, "rb") as f:
        data = f.read()
    chunk_len = struct.unpack_from("<I", data, 12)[0]
    return json.loads(data[20 : 20 + chunk_len])


def animation_names(gltf):
    return sorted(anim.get("name") for anim in gltf.get("animations", []))


def scene_root_names(gltf):
    nodes = gltf.get("nodes", [])
    return sorted(nodes[i].get("name") for scene in gltf.get("scenes", []) for i in scene.get("nodes", []))


def make_armature(name, bone_names):
    arm_data = bpy.data.armatures.new(name)
    obj = bpy.data.objects.new(name, arm_data)
    bpy.context.scene.collection.objects.link(obj)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.mode_set(mode="EDIT")
    for index, bone_name in enumerate(bone_names):
        bone = arm_data.edit_bones.new(bone_name)
        bone.head = (0.0, 0.0, index * 0.1)
        bone.tail = (0.0, 0.1, index * 0.1)
    bpy.ops.object.mode_set(mode="OBJECT")
    return obj


def key_bone(rig, bone_name, frames=(1, 30)):
    pose_bone = rig.pose.bones[bone_name]
    for frame in frames:
        pose_bone.keyframe_insert(data_path="location", frame=frame)
        pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame)
        pose_bone.keyframe_insert(data_path="scale", frame=frame)


def assign_action(rig, action_name, bone_name):
    action = bpy.data.actions.new(action_name)
    action.use_fake_user = True
    if not rig.animation_data:
        rig.animation_data_create()
    rig.animation_data.action = action
    key_bone(rig, bone_name)
    return action


def park_on_nla(rig, action):
    track = rig.animation_data.nla_tracks.new()
    track.name = action.name
    strip = track.strips.new(action.name, 1, action)
    strip.mute = False
    if getattr(strip, "action_slot", True) is None and getattr(action, "slots", None):
        strip.action_slot = action.slots[0]
    return strip


# ---------------------------------------------------------------------------
# Scene: reference object owns 'Armature', two emotes authored in the file
# ---------------------------------------------------------------------------

scene = bpy.context.scene
scene.render.fps = 30
scene.dcl_tools.emote_start_frame = 1
scene.dcl_tools.emote_end_frame = 30

reference = bpy.data.objects.new("Armature", None)
scene.collection.objects.link(reference)

avatar = make_armature("Armature", ["Avatar_Hips", "Avatar_Spine"])
check("avatar rig got auto-suffixed by the name holder", avatar.name == "Armature.001", avatar.name)

prop = make_armature("Gun_Rig", ["Prop_Root"])

mesh_data = bpy.data.meshes.new("Space_Gun")
mesh_data.from_pydata([(0, 0, 0), (1, 0, 0), (0, 1, 0)], [], [(0, 1, 2)])
prop_mesh = bpy.data.objects.new("Space_Gun", mesh_data)
prop_mesh.parent = prop
scene.collection.objects.link(prop_mesh)

invaders_avatar = assign_action(avatar, "Invaders_Avatar", "Avatar_Hips")
park_on_nla(avatar, invaders_avatar)
assign_action(avatar, "Gamer_Avatar", "Avatar_Hips")

invaders_prop = assign_action(prop, "Invaders_Prop", "Prop_Root")
park_on_nla(prop, invaders_prop)
assign_action(prop, "Gamer_Prop", "Prop_Root")

bpy.context.view_layer.objects.active = avatar

# The prop lives in a collection that is excluded from the view layer - the
# exact setup that crashed select_set in the field - and the avatar rig is
# hidden, which a use_visible export would silently drop.
props_collection = bpy.data.collections.new("Props")
scene.collection.children.link(props_collection)
for obj in (prop, prop_mesh):
    scene.collection.objects.unlink(obj)
    props_collection.objects.link(obj)
props_layer = bpy.context.view_layer.layer_collection.children["Props"]
props_layer.exclude = True
avatar.hide_set(True)

# ---------------------------------------------------------------------------
# Export 1: prop emote
# ---------------------------------------------------------------------------

out_dir = tempfile.mkdtemp(prefix="dcl_emote_export_")
prop_glb = os.path.join(out_dir, "prop_emote.glb")

print("\nExporting prop emote...")
result = bpy.ops.object.export_emote_glb(filepath=prop_glb)
check("export finished", result == {"FINISHED"}, str(result))

gltf = read_glb(prop_glb)
check(
    "only the active emote's clips are exported",
    animation_names(gltf) == ["Gamer_Avatar", "Gamer_Prop"],
    str(animation_names(gltf)),
)
check(
    "roots are named Armature and Armature_Prop",
    scene_root_names(gltf) == ["Armature", "Armature_Prop"],
    str(scene_root_names(gltf)),
)
check("prop geometry is in the GLB", any(m.get("name") == "Space_Gun" for m in gltf.get("meshes", [])))

check("avatar rig name restored", avatar.name == "Armature.001", avatar.name)
check("prop rig name restored", prop.name == "Gun_Rig", prop.name)
check("reference object name restored", reference.name == "Armature", reference.name)
check("prop collection exclusion restored", props_layer.exclude)
check("avatar hide state restored", avatar.hide_get())
avatar.hide_set(False)
check(
    "NLA strips unmuted after export",
    not any(s.mute for rig in (avatar, prop) for t in rig.animation_data.nla_tracks for s in t.strips),
)

# ---------------------------------------------------------------------------
# Export 2: basic emote (single armature, parked actions in the file)
# ---------------------------------------------------------------------------

bpy.data.objects.remove(prop_mesh)
bpy.data.objects.remove(prop)
bpy.context.view_layer.objects.active = avatar

basic_glb = os.path.join(out_dir, "basic_emote.glb")

print("\nExporting basic emote...")
result = bpy.ops.object.export_emote_glb(filepath=basic_glb)
check("export finished", result == {"FINISHED"}, str(result))

gltf = read_glb(basic_glb)
check(
    "single armature exports a single clip despite parked actions",
    animation_names(gltf) == ["Gamer_Avatar"],
    str(animation_names(gltf)),
)
check("root is named Armature", scene_root_names(gltf) == ["Armature"], str(scene_root_names(gltf)))

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print(f"\n{passed} passed, {failed} failed")
sys.exit(1 if failed else 0)
