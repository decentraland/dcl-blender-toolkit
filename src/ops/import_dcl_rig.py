import os

import bpy

from .. import dcl_rig_metadata
from .emote_utils import find_target_armature

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _has_child_collection(parent_collection, child_name):
    return any(coll.name == child_name for coll in parent_collection.children)


def _find_armature_in_collection(collection):
    for obj in collection.objects:
        if obj.type == "ARMATURE":
            return obj
    for child in collection.children:
        arm = _find_armature_in_collection(child)
        if arm:
            return arm
    return None


def _set_collection_visibility(context, collection_name, exclude=False):
    """
    Set the checkbox (exclude) state and hide_viewport for a collection
    in the current view layer.  ``exclude=True`` unchecks the collection
    (hides it completely); ``exclude=False`` checks it (makes it visible).
    """

    def _walk_layer_collections(layer_coll):
        if layer_coll.collection.name == collection_name:
            return layer_coll
        for child in layer_coll.children:
            found = _walk_layer_collections(child)
            if found:
                return found
        return None

    lc = _walk_layer_collections(context.view_layer.layer_collection)
    if lc:
        lc.exclude = exclude
        lc.collection.hide_viewport = exclude


def _import_collection_from_rig(context, collection_name, operator):
    """
    Import a single named collection from the bundled DCL rig file.
    Returns the imported (or existing) collection, or None on failure.
    """
    rig_path = dcl_rig_metadata.get_rig_blend_path()
    if not os.path.exists(rig_path):
        operator.report({"ERROR"}, f"Rig file missing: {rig_path}")
        return None

    # Reuse if already present.
    existing = bpy.data.collections.get(collection_name)
    if existing:
        if not _has_child_collection(context.scene.collection, existing.name):
            context.scene.collection.children.link(existing)
        operator.report({"INFO"}, f"'{collection_name}' already exists in scene.")
        return existing

    try:
        with bpy.data.libraries.load(rig_path, link=False) as (data_from, data_to):
            if collection_name in data_from.collections:
                data_to.collections = [collection_name]
            else:
                operator.report({"ERROR"}, f"Collection '{collection_name}' not found in Avatar_File.blend")
                return None
    except Exception as exc:
        operator.report({"ERROR"}, f"Failed importing '{collection_name}': {exc}")
        return None

    imported = bpy.data.collections.get(collection_name)
    if imported and not _has_child_collection(context.scene.collection, imported.name):
        context.scene.collection.children.link(imported)
    return imported


# ---------------------------------------------------------------------------
# Import DCL Rig (Avatar collection)
# ---------------------------------------------------------------------------


class OBJECT_OT_import_dcl_rig(bpy.types.Operator):
    bl_idname = "object.import_dcl_rig"
    bl_label = "Import DCL Rig"
    bl_description = "Append the official Decentraland avatar rig into the current scene"
    bl_options = {"REGISTER", "UNDO"}

    make_active: bpy.props.BoolProperty(
        name="Make Imported Rig Active",
        description="Select the imported armature and make it active after import",
        default=True,
    )

    def execute(self, context):
        coll = _import_collection_from_rig(context, "Avatar", self)
        if coll is None:
            return {"CANCELLED"}

        active_armature = _find_armature_in_collection(coll) or find_target_armature(context)

        # DCL animation defaults.
        context.scene.render.fps = 30
        context.scene.frame_start = 1
        context.scene.frame_end = 300
        context.scene.frame_set(context.scene.frame_start)

        # --- Clean outliner presentation ---
        # Hide Avatar_ShapeB by default; keep only Avatar_ShapeA visible.
        _set_collection_visibility(context, "Avatar_ShapeB", exclude=True)
        _set_collection_visibility(context, "Avatar_ShapeA", exclude=False)

        if self.make_active and active_armature:
            for obj in context.selected_objects:
                obj.select_set(False)
            active_armature.select_set(True)
            context.view_layer.objects.active = active_armature

        self.report({"INFO"}, "DCL rig imported. Scene set to 30 fps / 1-300 frames.")
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "make_active")
        layout.separator()
        layout.label(text=f"Rig version: {dcl_rig_metadata.DCL_RIG_VERSION}")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)


# ---------------------------------------------------------------------------
# Add Prop (Prop collection with Armature_Prop)
# ---------------------------------------------------------------------------


class OBJECT_OT_import_dcl_prop(bpy.types.Operator):
    bl_idname = "object.import_dcl_prop"
    bl_label = "Add Prop"
    bl_description = "Import the DCL Prop armature from Avatar_File.blend for emote props"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        coll = _import_collection_from_rig(context, "Prop", self)
        if coll is None:
            return {"CANCELLED"}

        # Select the prop armature for convenience.
        prop_arm = _find_armature_in_collection(coll)
        if prop_arm:
            for obj in context.selected_objects:
                obj.select_set(False)
            prop_arm.select_set(True)
            context.view_layer.objects.active = prop_arm

        self.report({"INFO"}, "Prop collection imported (Armature_Prop).")
        return {"FINISHED"}


# ---------------------------------------------------------------------------
# Limit Area Reference (Animation_Area_Reference collection)
# ---------------------------------------------------------------------------


class OBJECT_OT_import_dcl_limit_area(bpy.types.Operator):
    bl_idname = "object.import_dcl_limit_area"
    bl_label = "Limit Area Reference"
    bl_description = "Import the Animation Area Reference from Avatar_File.blend (ground + boundary guides)"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        coll = _import_collection_from_rig(context, "Animation_Area_Reference", self)
        if coll is None:
            return {"CANCELLED"}

        self.report({"INFO"}, "Animation Area Reference imported (ground + boundary guides).")
        return {"FINISHED"}
