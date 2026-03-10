import os

import bpy

from .emote_utils import find_target_armature
from .validate_emote import run_emote_validation


class OBJECT_OT_export_emote_glb(bpy.types.Operator):
    bl_idname = "object.export_emote_glb"
    bl_label = "Export Emote GLB"
    bl_description = "Export emote animation to GLB with Decentraland-focused settings"
    bl_options = {"REGISTER", "UNDO"}

    filepath: bpy.props.StringProperty(
        name="File Path",
        description="Destination GLB file path",
        default="",
        subtype="FILE_PATH",
    )

    def execute(self, context):
        validation = run_emote_validation(context)
        if validation["errors"]:
            self.report({"ERROR"}, "Cannot export: emote validation has blocking errors.")
            return {"CANCELLED"}
        if validation["warnings"] and context.scene.dcl_tools.emote_strict_validation:
            self.report({"ERROR"}, "Strict mode enabled: resolve validation warnings before export.")
            return {"CANCELLED"}

        armature = find_target_armature(context)
        if not armature:
            self.report({"ERROR"}, "No armature found for export.")
            return {"CANCELLED"}

        out_path = self.filepath.strip()
        if not out_path:
            self.report({"ERROR"}, "Choose an export path.")
            return {"CANCELLED"}
        if not out_path.lower().endswith(".glb"):
            out_path += ".glb"
        out_dir = os.path.dirname(out_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        start_frame = int(context.scene.dcl_tools.emote_start_frame)
        end_frame = int(context.scene.dcl_tools.emote_end_frame)
        frame_step = int(context.scene.dcl_tools.emote_sampling_rate)

        visibility_cache = {}
        selection_cache = list(context.selected_objects)
        active_cache = context.view_layer.objects.active
        original_frame = context.scene.frame_current

        try:
            # Keep only armature visible/selected for safer export content.
            for obj in context.scene.objects:
                visibility_cache[obj.name] = obj.hide_viewport
                obj.hide_viewport = obj != armature
                obj.select_set(False)

            armature.hide_viewport = False
            armature.select_set(True)
            context.view_layer.objects.active = armature

            context.scene.frame_start = start_frame
            context.scene.frame_end = end_frame
            context.scene.frame_set(start_frame)

            export_kwargs_sets = [
                {
                    "filepath": out_path,
                    "export_format": "GLB",
                    "use_selection": True,
                    "use_visible": True,
                    "export_def_bones": True,
                    "export_force_sampling": True,
                    "export_frame_step": frame_step,
                    "export_frame_range": True,
                    "export_animations": True,
                    "export_apply": False,
                },
                {
                    "filepath": out_path,
                    "export_format": "GLB",
                    "use_selection": True,
                    "export_animations": True,
                    "export_apply": False,
                },
                {
                    "filepath": out_path,
                    "export_format": "GLB",
                },
            ]

            last_error = None
            for kwargs in export_kwargs_sets:
                try:
                    bpy.ops.export_scene.gltf(**kwargs)
                    last_error = None
                    break
                except Exception as exc:
                    last_error = exc

            if last_error:
                self.report({"ERROR"}, f"Export failed: {last_error}")
                return {"CANCELLED"}
        finally:
            # Restore viewport visibility and selection.
            for obj in context.scene.objects:
                if obj.name in visibility_cache:
                    obj.hide_viewport = visibility_cache[obj.name]
                obj.select_set(False)

            for obj in selection_cache:
                if obj and obj.name in bpy.data.objects:
                    bpy.data.objects[obj.name].select_set(True)
            if active_cache and active_cache.name in bpy.data.objects:
                context.view_layer.objects.active = bpy.data.objects[active_cache.name]
            context.scene.frame_set(original_frame)

        file_size = os.path.getsize(out_path) if os.path.exists(out_path) else 0
        size_mb = file_size / (1024 * 1024) if file_size else 0.0
        if file_size > 1024 * 1024:
            self.report({"WARNING"}, f"Exported {out_path} ({size_mb:.2f} MB). DCL recommends <= 1 MB.")
        else:
            self.report({"INFO"}, f"Exported {out_path} ({size_mb:.2f} MB).")
        return {"FINISHED"}

    def invoke(self, context, event):
        if not self.filepath:
            base_dir = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.path.expanduser("~/Desktop")
            self.filepath = os.path.join(base_dir, "Emote.glb")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}
