import math

import bpy

from .emote_utils import (
    find_target_armature,
    get_deform_pose_bones,
    iter_action_fcurves,
    keyframe_exists,
    pose_bone_world_location,
)


def _action_matches_armature(action, bone_names):
    if not action:
        return False
    for fcurve in iter_action_fcurves(action):
        if not fcurve.data_path.startswith('pose.bones["'):
            continue
        for bone_name in bone_names:
            if f'pose.bones["{bone_name}"]' in fcurve.data_path:
                return True
    return False


def run_emote_validation(context):
    """
    Validate current emote configuration.
    Returns: dict(errors=[], warnings=[], info=[], metrics={...}, armature=obj_or_none)
    """
    strict_mode = bool(getattr(context.scene, "dcl_emote_strict_validation", False))
    start_frame = int(getattr(context.scene, "dcl_emote_start_frame", 1))
    end_frame = int(getattr(context.scene, "dcl_emote_end_frame", 300))

    result = {
        "errors": [],
        "warnings": [],
        "info": [],
        "metrics": {},
        "armature": None,
    }

    def push(message, is_error=False):
        if is_error:
            result["errors"].append(message)
        else:
            result["warnings"].append(message)

    # FPS and timeline constraints.
    fps = int(context.scene.render.fps)
    result["metrics"]["fps"] = fps
    if fps != 30:
        push(f"Scene framerate is {fps}fps; Decentraland emotes must be 30fps.", is_error=True)

    if end_frame <= start_frame:
        push("End frame must be greater than start frame.", is_error=True)
        return result

    length_frames = end_frame - start_frame + 1
    result["metrics"]["frame_length"] = length_frames
    if length_frames > 300:
        push(f"Animation length is {length_frames} frames; max is 300 frames.", is_error=True)

    # Armature/action constraints.
    armature = find_target_armature(context)
    result["armature"] = armature
    if not armature:
        push("No armature found. Import/select DCL rig before validating.", is_error=True)
        return result

    if not armature.animation_data or not armature.animation_data.action:
        push("Target armature has no active action.", is_error=True)
        return result

    action = armature.animation_data.action
    result["metrics"]["active_action"] = action.name

    arm_bone_names = {pb.name for pb in armature.pose.bones}
    armature_actions = [a for a in bpy.data.actions if _action_matches_armature(a, arm_bone_names)]
    result["metrics"]["armature_action_count"] = len(armature_actions)

    if len(armature_actions) != 1:
        message = f"Detected {len(armature_actions)} armature actions. Keep only one final emote action before export."
        push(message, is_error=strict_mode)

    # Boundary keyframes for deform bones.
    deform_bones = get_deform_pose_bones(armature)
    missing_boundary = []
    for pose_bone in deform_bones:
        base = f'pose.bones["{pose_bone.name}"]'
        channels = [f"{base}.location", f"{base}.scale"]
        if pose_bone.rotation_mode == "QUATERNION":
            channels.append(f"{base}.rotation_quaternion")
        elif pose_bone.rotation_mode == "AXIS_ANGLE":
            channels.append(f"{base}.rotation_axis_angle")
        else:
            channels.append(f"{base}.rotation_euler")

        for channel in channels:
            if not keyframe_exists(action, channel, start_frame) or not keyframe_exists(action, channel, end_frame):
                missing_boundary.append(f"{pose_bone.name}:{channel.split('.')[-1]}")

    result["metrics"]["deform_bone_count"] = len(deform_bones)
    if missing_boundary:
        push(
            f"Missing first/last-frame keys on {len(missing_boundary)} bone channels. "
            "Set first and last frame keys on deform channels to prevent emote overrides.",
            is_error=strict_mode,
        )

    # Approximate displacement/height guidance (<= 1m).
    marker = None
    for marker_name in ("CTRL_Avatar_UpperBody", "Avatar_Hips", "Hips"):
        marker = armature.pose.bones.get(marker_name)
        if marker:
            break

    original_frame = context.scene.frame_current
    max_horizontal = 0.0
    max_vertical = 0.0

    reference = None
    try:
        for frame in range(start_frame, end_frame + 1):
            context.scene.frame_set(frame)
            if marker:
                position = pose_bone_world_location(armature, marker)
            else:
                position = armature.matrix_world.translation.copy()
            if reference is None:
                reference = position.copy()
            dx = position.x - reference.x
            dy = position.y - reference.y
            dz = position.z - reference.z
            max_horizontal = max(max_horizontal, math.sqrt(dx * dx + dy * dy))
            max_vertical = max(max_vertical, abs(dz))
    finally:
        context.scene.frame_set(original_frame)

    result["metrics"]["max_horizontal_m"] = round(max_horizontal, 4)
    result["metrics"]["max_vertical_m"] = round(max_vertical, 4)
    if max_horizontal > 1.0:
        push(
            f"Horizontal displacement reaches {max_horizontal:.2f}m (recommended <= 1.0m).",
            is_error=False,
        )
    if max_vertical > 1.0:
        push(
            f"Vertical displacement reaches {max_vertical:.2f}m (recommended <= 1.0m).",
            is_error=False,
        )

    if not result["errors"] and not result["warnings"]:
        result["info"].append("Validation passed. Emote is ready for export.")
    return result


class OBJECT_OT_validate_emote(bpy.types.Operator):
    bl_idname = "object.validate_emote"
    bl_label = "Validate Emote"
    bl_description = "Validate rig/action settings against Decentraland emote requirements"
    bl_options = {"REGISTER", "UNDO"}

    _last_result = None

    def execute(self, context):
        result = self._last_result or run_emote_validation(context)
        self._last_result = result

        if result["errors"]:
            self.report({"ERROR"}, f"Emote validation failed with {len(result['errors'])} error(s).")
            return {"CANCELLED"}
        if result["warnings"]:
            self.report({"WARNING"}, f"Emote validation has {len(result['warnings'])} warning(s).")
            return {"FINISHED"}

        self.report({"INFO"}, "Emote validation passed.")
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        result = self._last_result or {}
        metrics = result.get("metrics", {})

        box = layout.box()
        box.label(text="Metrics", icon="INFO")
        box.label(text=f"FPS: {metrics.get('fps', '-')}")
        box.label(text=f"Frame Length: {metrics.get('frame_length', '-')}")
        box.label(text=f"Active Action: {metrics.get('active_action', '-')}")
        box.label(text=f"Max Horizontal Offset: {metrics.get('max_horizontal_m', '-')} m")
        box.label(text=f"Max Vertical Offset: {metrics.get('max_vertical_m', '-')} m")

        if result.get("errors"):
            box = layout.box()
            box.label(text="Errors", icon="ERROR")
            for message in result["errors"][:8]:
                box.label(text=message)
            if len(result["errors"]) > 8:
                box.label(text=f"... and {len(result['errors']) - 8} more")

        if result.get("warnings"):
            box = layout.box()
            box.label(text="Warnings", icon="WARNING")
            for message in result["warnings"][:8]:
                box.label(text=message)
            if len(result["warnings"]) > 8:
                box.label(text=f"... and {len(result['warnings']) - 8} more")

        if result.get("info"):
            box = layout.box()
            box.label(text="Status", icon="CHECKMARK")
            for message in result["info"]:
                box.label(text=message)

    def invoke(self, context, event):
        self._last_result = run_emote_validation(context)
        return context.window_manager.invoke_props_dialog(self, width=560)
