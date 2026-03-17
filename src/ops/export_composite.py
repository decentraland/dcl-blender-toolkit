"""Export Decentraland Composite – exports individual GLBs + main.composite."""

import json
import os

import bpy

from .composite_utils import (
    FIRST_ENTITY_ID,
    blender_pos_to_dcl,
    blender_quat_to_dcl,
    blender_scale_to_dcl,
    build_composite,
    sanitize_filename,
)


class OBJECT_OT_export_composite(bpy.types.Operator):
    bl_idname = "object.export_composite"
    bl_label = "Export Composite"
    bl_description = "Export scene objects as individual GLBs with a Decentraland main.composite"
    bl_options = {"REGISTER", "UNDO"}

    scene_dir: bpy.props.StringProperty(
        name="Scene Directory",
        description="Root directory of the Decentraland scene project",
        default="",
        subtype="DIR_PATH",
    )

    scene_title: bpy.props.StringProperty(
        name="Scene Title",
        description="Display title for scene.json",
        default="My Scene",
    )

    export_hidden: bpy.props.BoolProperty(
        name="Include Hidden",
        description="Export hidden objects as well",
        default=False,
    )

    overwrite_scene_json: bpy.props.BoolProperty(
        name="Overwrite scene.json",
        description="Overwrite scene.json even if it already exists",
        default=False,
    )

    # ------------------------------------------------------------------

    def _resolve_scene_dir(self):
        raw = self.scene_dir.strip()
        if raw:
            return os.path.normpath(bpy.path.abspath(raw))
        if bpy.data.filepath:
            return os.path.dirname(bpy.data.filepath)
        return os.path.join(os.path.expanduser("~"), "Desktop", "dcl_scene")

    def _collect_objects(self, context):
        """Return mesh objects sorted by name."""
        objs = []
        for obj in context.scene.objects:
            if obj.type != "MESH":
                continue
            if not self.export_hidden and not obj.visible_get():
                continue
            objs.append(obj)
        objs.sort(key=lambda o: o.name)
        return objs

    def _export_glb(self, context, obj, filepath):
        """Export a single object as GLB, preserving selection state."""
        prev_selected = list(context.selected_objects)
        prev_active = context.view_layer.objects.active

        try:
            for o in prev_selected:
                o.select_set(False)
            obj.select_set(True)
            context.view_layer.objects.active = obj

            bpy.ops.export_scene.gltf(
                filepath=filepath,
                export_format="GLB",
                use_selection=True,
                export_apply=True,
                export_yup=True,
            )
        finally:
            obj.select_set(False)
            for o in prev_selected:
                if o.name in context.scene.objects:
                    o.select_set(True)
            if prev_active and prev_active.name in context.scene.objects:
                context.view_layer.objects.active = prev_active

    def _unique_filename(self, models_dir, base_name, used):
        """Return a unique GLB filename inside *models_dir*."""
        candidate = base_name
        counter = 1
        while candidate in used:
            candidate = f"{base_name}_{counter:03d}"
            counter += 1
        used.add(candidate)
        return candidate + ".glb"

    def execute(self, context):
        scene_dir = self._resolve_scene_dir()
        models_dir = os.path.join(scene_dir, "assets", "models")
        composite_dir = os.path.join(scene_dir, "assets", "scene")
        os.makedirs(models_dir, exist_ok=True)
        os.makedirs(composite_dir, exist_ok=True)

        objects = self._collect_objects(context)
        if not objects:
            self.report({"WARNING"}, "No mesh objects to export.")
            return {"CANCELLED"}

        # Build entity ID map (sorted order → deterministic IDs)
        entity_map = {}
        for idx, obj in enumerate(objects):
            entity_map[obj.name] = FIRST_ENTITY_ID + idx

        used_filenames = set()
        entities_data = []

        for obj in objects:
            eid = entity_map[obj.name]
            safe_name = sanitize_filename(obj.name)
            glb_name = self._unique_filename(models_dir, safe_name, used_filenames)
            glb_path = os.path.join(models_dir, glb_name)

            self._export_glb(context, obj, glb_path)

            # Determine transform: local if parent is also exported, else world
            parent_eid = 0
            if obj.parent and obj.parent.name in entity_map:
                parent_eid = entity_map[obj.parent.name]
                mat = obj.matrix_local
            else:
                mat = obj.matrix_world

            pos = mat.to_translation()
            rot = mat.to_quaternion()
            scl = mat.to_scale()

            transform = {
                "position": blender_pos_to_dcl(pos),
                "rotation": blender_quat_to_dcl(rot),
                "scale": blender_scale_to_dcl(scl),
                "parent": parent_eid,
            }

            entities_data.append(
                {
                    "entity_id": eid,
                    "transform": transform,
                    "gltf_src": f"assets/models/{glb_name}",
                    "name": obj.name,
                }
            )

        # Write main.composite
        composite = build_composite(entities_data)
        composite_path = os.path.join(composite_dir, "main.composite")
        with open(composite_path, "w") as f:
            json.dump(composite, f, indent=2)

        # Write scene.json
        scene_json_path = os.path.join(scene_dir, "scene.json")
        if not os.path.exists(scene_json_path) or self.overwrite_scene_json:
            scene_json = {
                "ecs7": True,
                "runtimeVersion": "7",
                "display": {"title": self.scene_title},
                "main": "bin/index.js",
                "scene": {"parcels": ["0,0"], "base": "0,0"},
            }
            with open(scene_json_path, "w") as f:
                json.dump(scene_json, f, indent=2)

        self.report({"INFO"}, f"Exported {len(entities_data)} entities to {composite_path}")
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "scene_dir")
        layout.prop(self, "scene_title")
        layout.separator()
        layout.prop(self, "export_hidden")
        layout.prop(self, "overwrite_scene_json")
        layout.separator()
        out = self._resolve_scene_dir()
        layout.label(text=f"Output: {out}/assets/scene/main.composite", icon="FILE")

    def invoke(self, context, event):
        if not self.scene_dir and bpy.data.filepath:
            self.scene_dir = os.path.dirname(bpy.data.filepath) + os.sep
        return context.window_manager.invoke_props_dialog(self, width=500)
