"""Import a template wearable (glTF) bundled under assets/Templates."""

import os

import bpy

from .. import dcl_rig_metadata

TEMPLATES_DIR_NAME = "Templates"

# Blender's EnumProperty items callback requires the returned strings to remain
# alive on the Python side, or it will crash on garbage collection. Cache at
# module scope so references survive across UI redraws.
_TEMPLATE_ENUM_CACHE = []


def _scan_template_folders(templates_root):
    """Return a sorted list of (rel_dir, glb_filename) for each template folder."""
    if not os.path.isdir(templates_root):
        return []

    entries = []
    seen_dirs = set()
    for dirpath, _, filenames in os.walk(templates_root):
        glbs = sorted(f for f in filenames if f.lower().endswith(".glb"))
        if not glbs or dirpath in seen_dirs:
            continue
        seen_dirs.add(dirpath)
        rel_dir = os.path.relpath(dirpath, templates_root)
        entries.append((rel_dir, glbs[0]))

    entries.sort(key=lambda e: e[0].lower())
    return entries


def _templates_enum_items(self, context):
    assets_dir = dcl_rig_metadata.get_assets_dir()
    templates_root = os.path.join(assets_dir, TEMPLATES_DIR_NAME)
    entries = _scan_template_folders(templates_root)

    _TEMPLATE_ENUM_CACHE.clear()
    if not entries:
        _TEMPLATE_ENUM_CACHE.append(("NONE", "(no templates found)", ""))
        return _TEMPLATE_ENUM_CACHE

    for rel_dir, glb_name in entries:
        identifier = rel_dir.replace(os.sep, "/")
        display = identifier.replace("/", " / ")
        tooltip = f"Import {glb_name}"
        _TEMPLATE_ENUM_CACHE.append((identifier, display, tooltip))
    return _TEMPLATE_ENUM_CACHE


class OBJECT_OT_import_template_wearable(bpy.types.Operator):
    bl_idname = "object.import_template_wearable"
    bl_label = "Create from Template"
    bl_description = "Import a bundled wearable template (glTF) to start a new wearable from"
    bl_options = {"REGISTER", "UNDO"}

    template: bpy.props.EnumProperty(
        name="Template",
        description="Choose a wearable template to import",
        items=_templates_enum_items,
    )

    def execute(self, context):
        if self.template == "NONE" or not self.template:
            self.report({"WARNING"}, "No templates available in assets/Templates")
            return {"CANCELLED"}

        assets_dir = dcl_rig_metadata.get_assets_dir()
        templates_root = os.path.join(assets_dir, TEMPLATES_DIR_NAME)
        folder = os.path.join(templates_root, self.template.replace("/", os.sep))

        if not os.path.isdir(folder):
            self.report({"ERROR"}, f"Template folder not found: {folder}")
            return {"CANCELLED"}

        glb_path = None
        for fn in sorted(os.listdir(folder)):
            if fn.lower().endswith(".glb"):
                glb_path = os.path.join(folder, fn)
                break

        if not glb_path:
            self.report({"ERROR"}, f"No .glb file in template folder: {folder}")
            return {"CANCELLED"}

        objects_before = set(bpy.data.objects)

        try:
            bpy.ops.import_scene.gltf(filepath=glb_path)
        except Exception as exc:
            self.report({"ERROR"}, f"Failed to import template: {exc}")
            return {"CANCELLED"}

        new_objects = [o for o in bpy.data.objects if o not in objects_before]

        # Each wearable .glb ships the full DCL avatar armature (64 bones) for skinning.
        # Hide the imported armature so the bone cluster does not obscure the wearable mesh
        # itself — otherwise the imported armature renders as a sphere-like blob of bones.
        mesh_objects = []
        for obj in new_objects:
            if obj.type == "ARMATURE":
                obj.hide_set(True)
            elif obj.type == "MESH":
                mesh_objects.append(obj)

        for obj in bpy.data.objects:
            try:
                obj.select_set(False)
            except RuntimeError:
                pass

        for obj in mesh_objects:
            obj.select_set(True)
        if mesh_objects:
            context.view_layer.objects.active = mesh_objects[0]
            try:
                bpy.ops.view3d.view_selected()
            except RuntimeError:
                pass

        self.report({"INFO"}, f"Imported template: {self.template}")
        return {"FINISHED"}

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=360)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "template")
        layout.separator()
        layout.label(text="Imports a bundled wearable template as a starting point.")
        layout.label(text="Templates live in the add-on's assets/Templates folder.")
