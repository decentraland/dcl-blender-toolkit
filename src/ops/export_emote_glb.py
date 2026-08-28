import os

import bpy

from .emote_utils import (
    apply_action_assignments,
    claim_export_names,
    collect_emote_export_objects,
    find_avatar_armature,
    find_prop_armatures,
    mute_armature_nla_strips,
    pair_prop_actions,
    prepare_view_layer_for_export,
    restore_action_assignments,
    restore_names,
    restore_nla_mutes,
    restore_view_layer_state,
)
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

        armature = find_avatar_armature(context)
        if not armature:
            self.report({"ERROR"}, "No armature found for export.")
            return {"CANCELLED"}

        # Only the prop rigs whose action pairs with the emote being exported:
        # other emotes' props authored in the same file must stay out.
        all_prop_armatures = find_prop_armatures(context, armature)
        prop_armatures, action_assignments = pair_prop_actions(armature, all_prop_armatures, bpy.data.actions)
        export_objects = collect_emote_export_objects(context, armature, prop_armatures)
        export_names = {obj.name for obj in export_objects}

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
        nla_mute_cache = []
        rename_cache = []
        view_layer_undo = []
        hide_cache = []
        selectable_names = set()

        try:
            # Excluded or hidden collections would crash select_set below or
            # silently drop their objects from the export.
            view_layer_undo = prepare_view_layer_for_export(context.view_layer, export_objects)
            context.view_layer.update()
            selectable_names = {obj.name for obj in context.view_layer.objects}

            missing = sorted(export_names - selectable_names)
            if missing:
                self.report(
                    {"ERROR"},
                    "Cannot export, not in the current view layer: " + ", ".join(missing),
                )
                return {"CANCELLED"}

            # Keep only the emote content visible/selected: the avatar armature plus
            # any prop armatures and their geometry.
            for obj in context.scene.objects:
                visibility_cache[obj.name] = obj.hide_viewport
                in_export = obj.name in export_names
                obj.hide_viewport = not in_export
                if obj.name not in selectable_names:
                    continue
                if in_export and obj.hide_get():
                    hide_cache.append(obj)
                    obj.hide_set(False)
                obj.select_set(in_export)

            context.view_layer.objects.active = armature

            # Only the active action of each rig may become a clip; anything
            # parked on NLA tracks (stashes, other emotes) must not leak in.
            apply_action_assignments(action_assignments)
            nla_mute_cache = mute_armature_nla_strips([armature, *prop_armatures])
            rename_cache = claim_export_names(armature, prop_armatures, bpy.data.objects.get)

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
                    # With a single armature the exporter would otherwise emit
                    # every action in the file, not just the active one.
                    "export_anim_single_armature": False,
                    "export_apply": False,
                },
                {
                    "filepath": out_path,
                    "export_format": "GLB",
                    "use_selection": True,
                    "export_animations": True,
                    "export_anim_single_armature": False,
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
            # Names first: the caches below are keyed by pre-export names.
            restore_names(rename_cache)
            restore_nla_mutes(nla_mute_cache)
            restore_action_assignments(action_assignments)
            for obj in hide_cache:
                obj.hide_set(True)

            # Restore viewport visibility and selection while the view layer
            # still holds everything we selected.
            for obj in context.scene.objects:
                if obj.name in visibility_cache:
                    obj.hide_viewport = visibility_cache[obj.name]
                if obj.name in selectable_names:
                    obj.select_set(False)

            for obj in selection_cache:
                if obj and obj.name in bpy.data.objects and obj.name in selectable_names:
                    bpy.data.objects[obj.name].select_set(True)
            if active_cache and active_cache.name in bpy.data.objects:
                context.view_layer.objects.active = bpy.data.objects[active_cache.name]
            context.scene.frame_set(original_frame)
            restore_view_layer_state(view_layer_undo)

        file_size = os.path.getsize(out_path) if os.path.exists(out_path) else 0
        size_mb = file_size / (1024 * 1024) if file_size else 0.0
        prop_note = ""
        if prop_armatures:
            prop_objects = len(export_objects) - 1 - len(prop_armatures)
            prop_note = f" Included {len(prop_armatures)} prop rig(s) with {prop_objects} object(s)."
        skipped = len(all_prop_armatures) - len(prop_armatures)
        if skipped:
            prop_note += f" Skipped {skipped} prop rig(s) not paired with this emote."
        if file_size > 1024 * 1024:
            self.report(
                {"WARNING"},
                f"Exported {out_path} ({size_mb:.2f} MB). DCL recommends <= 1 MB.{prop_note}",
            )
        else:
            self.report({"INFO"}, f"Exported {out_path} ({size_mb:.2f} MB).{prop_note}")
        return {"FINISHED"}

    def invoke(self, context, event):
        if not self.filepath:
            base_dir = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.path.expanduser("~/Desktop")
            self.filepath = os.path.join(base_dir, "Emote.glb")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}
