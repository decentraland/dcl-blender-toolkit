import bpy

from .emote_utils import (
    find_avatar_armature,
    find_prop_armatures,
    get_deform_pose_bones,
    sanitize_emote_name,
)


def _find_starting_pose_action():
    for action in bpy.data.actions:
        if "startingpose" in action.name.lower() or "starting_pose" in action.name.lower():
            return action
    return None


def _assign_action(armature, name, source_action):
    """Assign a new action called ``name`` to ``armature``, copied from ``source_action``."""
    if not armature.animation_data:
        armature.animation_data_create()

    if source_action:
        action = source_action.copy()
        action.name = name
    else:
        action = bpy.data.actions.new(name=name)
    action.use_fake_user = True
    armature.animation_data.action = action
    return action


class OBJECT_OT_create_emote_action(bpy.types.Operator):
    bl_idname = "object.create_emote_action"
    bl_label = "Create Emote Action"
    bl_description = "Create a new emote action by duplicating the active action or starting pose"
    bl_options = {"REGISTER", "UNDO"}

    emote_name: bpy.props.StringProperty(
        name="Emote Name",
        description="Final action name (auto-formatted as Capitalized_Words)",
        default="My_Emote",
    )

    create_prop_action: bpy.props.BoolProperty(
        name="Create Prop Action",
        description="Also create a matching action on each prop armature in the scene",
        default=True,
    )

    def execute(self, context):
        arm = find_avatar_armature(context)
        if not arm:
            self.report({"ERROR"}, "No armature found. Import or select a DCL rig first.")
            return {"CANCELLED"}

        if not arm.animation_data:
            arm.animation_data_create()

        source_action = arm.animation_data.action or _find_starting_pose_action()

        prop_armatures = find_prop_armatures(context, arm) if self.create_prop_action else []
        base_name = sanitize_emote_name(self.emote_name)

        # Decentraland tells the two clips apart by the _Avatar / _Prop suffixes, so
        # only add them once a prop rig is actually part of the emote.
        avatar_name = f"{base_name}_Avatar" if prop_armatures else base_name
        avatar_action = _assign_action(arm, avatar_name, source_action)

        created = [avatar_action.name]
        for index, prop_armature in enumerate(prop_armatures):
            prop_source = prop_armature.animation_data.action if prop_armature.animation_data else None
            suffix = "_Prop" if index == 0 else f"_Prop_{index + 1}"
            created.append(_assign_action(prop_armature, f"{base_name}{suffix}", prop_source).name)

        self.report({"INFO"}, f"Created action(s): {', '.join(created)}")
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "emote_name")
        prop_armatures = find_prop_armatures(context)
        if prop_armatures:
            layout.prop(self, "create_prop_action")
            layout.label(text=f"{len(prop_armatures)} prop rig(s) detected", icon="OBJECT_DATA")
        layout.label(text="Allowed format: Capitalized_Words", icon="INFO")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class OBJECT_OT_set_emote_boundary_keyframes(bpy.types.Operator):
    bl_idname = "object.set_emote_boundary_keyframes"
    bl_label = "Set Boundary Keys"
    bl_description = "Insert keyframes for deform bones on first/last emote frames to avoid overrides"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm = find_avatar_armature(context)
        if not arm:
            self.report({"ERROR"}, "No armature found. Import or select a DCL rig first.")
            return {"CANCELLED"}

        start_frame = int(context.scene.dcl_tools.emote_start_frame)
        end_frame = int(context.scene.dcl_tools.emote_end_frame)
        if end_frame <= start_frame:
            self.report({"ERROR"}, "End frame must be greater than start frame.")
            return {"CANCELLED"}

        # A prop rig animates on its own action, so it needs boundary keys too.
        targets = [arm] + find_prop_armatures(context, arm)
        animated = [obj for obj in targets if obj.animation_data and obj.animation_data.action]
        if not animated:
            self.report({"ERROR"}, "No active action found on the target armature.")
            return {"CANCELLED"}

        skipped = [obj.name for obj in targets if obj not in animated]

        original_frame = context.scene.frame_current
        total_bones = 0
        inserted = 0
        try:
            for armature in animated:
                bones = get_deform_pose_bones(armature)
                if not bones:
                    continue
                total_bones += len(bones)
                for frame in (start_frame, end_frame):
                    context.scene.frame_set(frame)
                    for pose_bone in bones:
                        pose_bone.keyframe_insert(data_path="location", frame=frame, group=pose_bone.name)
                        if pose_bone.rotation_mode == "QUATERNION":
                            pose_bone.keyframe_insert(
                                data_path="rotation_quaternion", frame=frame, group=pose_bone.name
                            )
                        elif pose_bone.rotation_mode == "AXIS_ANGLE":
                            pose_bone.keyframe_insert(
                                data_path="rotation_axis_angle", frame=frame, group=pose_bone.name
                            )
                        else:
                            pose_bone.keyframe_insert(data_path="rotation_euler", frame=frame, group=pose_bone.name)
                        pose_bone.keyframe_insert(data_path="scale", frame=frame, group=pose_bone.name)
                        inserted += 1
        finally:
            context.scene.frame_set(original_frame)

        if not total_bones:
            self.report({"ERROR"}, "No pose bones available on target armature.")
            return {"CANCELLED"}

        message = (
            f"Inserted boundary keys for {total_bones} deform bones across "
            f"{len(animated)} rig(s) ({inserted} channel sets)."
        )
        if skipped:
            self.report({"WARNING"}, f"{message} Skipped (no action): {', '.join(skipped)}.")
        else:
            self.report({"INFO"}, message)
        return {"FINISHED"}
