import bpy

from .emote_utils import (
    find_target_armature,
    get_deform_pose_bones,
    sanitize_emote_name,
)


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

    def execute(self, context):
        arm = find_target_armature(context)
        if not arm:
            self.report({"ERROR"}, "No armature found. Import or select a DCL rig first.")
            return {"CANCELLED"}

        if not arm.animation_data:
            arm.animation_data_create()

        source_action = arm.animation_data.action
        if source_action is None:
            for action in bpy.data.actions:
                if "startingpose" in action.name.lower() or "starting_pose" in action.name.lower():
                    source_action = action
                    break

        final_name = sanitize_emote_name(self.emote_name)
        if source_action:
            new_action = source_action.copy()
            new_action.name = final_name
            new_action.use_fake_user = True
            arm.animation_data.action = new_action
            self.report({"INFO"}, f"Created action '{new_action.name}' from '{source_action.name}'")
        else:
            new_action = bpy.data.actions.new(name=final_name)
            new_action.use_fake_user = True
            arm.animation_data.action = new_action
            self.report({"INFO"}, f"Created new action '{new_action.name}'")
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "emote_name")
        layout.label(text="Allowed format: Capitalized_Words", icon="INFO")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class OBJECT_OT_set_emote_boundary_keyframes(bpy.types.Operator):
    bl_idname = "object.set_emote_boundary_keyframes"
    bl_label = "Set Boundary Keys"
    bl_description = "Insert keyframes for deform bones on first/last emote frames to avoid overrides"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        arm = find_target_armature(context)
        if not arm:
            self.report({"ERROR"}, "No armature found. Import or select a DCL rig first.")
            return {"CANCELLED"}

        if not arm.animation_data or not arm.animation_data.action:
            self.report({"ERROR"}, "No active action found on the target armature.")
            return {"CANCELLED"}

        start_frame = int(context.scene.dcl_tools.emote_start_frame)
        end_frame = int(context.scene.dcl_tools.emote_end_frame)
        if end_frame <= start_frame:
            self.report({"ERROR"}, "End frame must be greater than start frame.")
            return {"CANCELLED"}

        original_frame = context.scene.frame_current
        bones = get_deform_pose_bones(arm)
        if not bones:
            self.report({"ERROR"}, "No pose bones available on target armature.")
            return {"CANCELLED"}

        inserted = 0
        for frame in (start_frame, end_frame):
            context.scene.frame_set(frame)
            for pose_bone in bones:
                pose_bone.keyframe_insert(data_path="location", frame=frame, group=pose_bone.name)
                if pose_bone.rotation_mode == "QUATERNION":
                    pose_bone.keyframe_insert(data_path="rotation_quaternion", frame=frame, group=pose_bone.name)
                elif pose_bone.rotation_mode == "AXIS_ANGLE":
                    pose_bone.keyframe_insert(data_path="rotation_axis_angle", frame=frame, group=pose_bone.name)
                else:
                    pose_bone.keyframe_insert(data_path="rotation_euler", frame=frame, group=pose_bone.name)
                pose_bone.keyframe_insert(data_path="scale", frame=frame, group=pose_bone.name)
                inserted += 1

        context.scene.frame_set(original_frame)
        self.report({"INFO"}, f"Inserted boundary keys for {len(bones)} deform bones ({inserted} channel sets).")
        return {"FINISHED"}
