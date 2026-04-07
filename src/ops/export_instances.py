"""Export Instance Collections – exports unique GLBs + a JSON with all instance transforms."""

import json
import os

import bpy


class OBJECT_OT_export_instances(bpy.types.Operator):
    bl_idname = "object.export_instances"
    bl_label = "Export Instances"
    bl_description = (
        "Export collection instances as individual GLBs and a JSON file "
        "with Decentraland-compatible transforms"
    )
    bl_options = {"REGISTER", "UNDO"}

    export_dir: bpy.props.StringProperty(
        name="Output Directory",
        description="Folder where GLBs and JSON will be saved",
        default="",
        subtype="DIR_PATH",
    )

    collection_name: bpy.props.StringProperty(
        name="Source Collection",
        description="Name of the collection that contains the instance empties",
        default="",
    )

    apply_modifiers: bpy.props.BoolProperty(
        name="Apply Modifiers",
        description="Apply modifiers on exported meshes",
        default=True,
    )

    export_animations: bpy.props.BoolProperty(
        name="Export Animations",
        description="Include animations in exported GLBs",
        default=False,
    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_export_dir(self):
        raw = self.export_dir.strip()
        if raw:
            return os.path.normpath(bpy.path.abspath(raw))
        if bpy.data.filepath:
            return os.path.join(os.path.dirname(bpy.data.filepath), "instances_export")
        return os.path.join(os.path.expanduser("~"), "Desktop", "instances_export")

    @staticmethod
    def _collect_instances_recursive(collection):
        """Walk *collection* and its children, yielding objects that reference an instance_collection."""
        for ob in collection.objects:
            if ob.instance_collection:
                yield ob
        for child_col in collection.children:
            yield from OBJECT_OT_export_instances._collect_instances_recursive(child_col)

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def draw(self, context):
        layout = self.layout
        layout.prop_search(self, "collection_name", bpy.data, "collections", icon="OUTLINER_COLLECTION")
        layout.prop(self, "export_dir")
        out = self._resolve_export_dir()
        layout.label(text=f"Output: {out}", icon="FILE_FOLDER")
        layout.separator()
        layout.prop(self, "apply_modifiers")
        layout.prop(self, "export_animations")

    def invoke(self, context, event):
        # Pre-fill from the collection the user has selected in the Outliner
        col = context.collection
        if col and col != context.scene.collection:
            self.collection_name = col.name

        # Pre-fill export dir from blend file location
        if not self.export_dir and bpy.data.filepath:
            self.export_dir = os.path.dirname(bpy.data.filepath)

        return context.window_manager.invoke_props_dialog(self, width=450)

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    def execute(self, context):
        col_name = self.collection_name.strip()
        if not col_name:
            self.report({"ERROR"}, "No source collection specified.")
            return {"CANCELLED"}

        if col_name not in bpy.data.collections:
            self.report({"ERROR"}, f"Collection '{col_name}' not found.")
            return {"CANCELLED"}

        master_collection = bpy.data.collections[col_name]
        export_dir = self._resolve_export_dir()
        glb_dir = os.path.join(export_dir, "instances")
        os.makedirs(glb_dir, exist_ok=True)

        # Deselect everything
        bpy.ops.object.select_all(action="DESELECT")
        bpy.context.view_layer.objects.active = None

        # Ensure depsgraph is up-to-date
        depsgraph = context.evaluated_depsgraph_get()
        depsgraph.update()

        # Collect all instance objects
        instance_objects = list(self._collect_instances_recursive(master_collection))
        if not instance_objects:
            self.report({"WARNING"}, f"No instance objects found in '{col_name}'.")
            return {"CANCELLED"}

        exported_glbs = set()
        objs_data = []
        temporarily_linked = []

        for ob in instance_objects:
            inst_col = ob.instance_collection
            glb_name = inst_col.name

            # Export GLB if not already exported
            if glb_name not in exported_glbs:
                exported_glbs.add(glb_name)
                self._export_instance_glb(context, inst_col, glb_dir, glb_name, temporarily_linked)

            # Collect transform data
            objs_data.append(self._build_transform_data(ob, glb_name))

        # Unlink any collections we temporarily linked (fix for original bug)
        scene_col = context.scene.collection
        for col in temporarily_linked:
            try:
                scene_col.children.unlink(col)
            except RuntimeError:
                pass

        # Write JSON
        json_path = os.path.join(export_dir, f"{col_name}.json")
        with open(json_path, "w") as f:
            json.dump(objs_data, f, indent=4)

        self.report(
            {"INFO"},
            f"Exported {len(exported_glbs)} GLB(s), {len(objs_data)} instance(s) → {export_dir}",
        )
        return {"FINISHED"}

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------

    def _export_instance_glb(self, context, inst_col, glb_dir, glb_name, temporarily_linked):
        """Select the objects inside *inst_col*, export as GLB, then clean up."""
        scene_col = context.scene.collection

        # Temporarily link the instance collection so its objects become exportable
        was_linked = inst_col.name in [c.name for c in scene_col.children]
        if not was_linked:
            scene_col.children.link(inst_col)
            temporarily_linked.append(inst_col)

        bpy.ops.object.select_all(action="DESELECT")

        for child_obj in inst_col.objects:
            child_obj.select_set(True)

        filepath = os.path.join(glb_dir, glb_name + ".glb")
        bpy.ops.export_scene.gltf(
            filepath=filepath,
            use_selection=True,
            export_animations=self.export_animations,
            export_apply=self.apply_modifiers,
        )

        bpy.ops.object.select_all(action="DESELECT")

    @staticmethod
    def _build_transform_data(ob, glb_name):
        """Build a dict with Decentraland-compatible position/scale/rotation."""
        matrix_world = ob.matrix_world.copy()

        bpos = matrix_world.to_translation()
        bscale = matrix_world.to_scale()
        brot = matrix_world.to_quaternion()

        return {
            "name": ob.name,
            "instance": glb_name,
            "position": {"x": -bpos.x, "y": bpos.z, "z": -bpos.y},
            "scale": {"x": bscale.x, "y": bscale.z, "z": bscale.y},
            "rotation": {"w": brot.w, "x": brot.x, "y": -brot.z, "z": brot.y},
        }
