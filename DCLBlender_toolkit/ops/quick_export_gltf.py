import bpy
import os
from mathutils import Matrix

from .export_material_atlas import run_material_atlas_optimization

# Object types that carry exportable geometry
_GEOMETRY_TYPES = {'MESH', 'CURVE', 'SURFACE', 'FONT', 'META'}


class OBJECT_OT_quick_export_gltf(bpy.types.Operator):
    bl_idname = "object.quick_export_gltf"
    bl_label = "Quick Export glTF"
    bl_description = "One-click glTF/GLB export with Decentraland-optimized settings"
    bl_options = {'REGISTER', 'UNDO'}

    export_format: bpy.props.EnumProperty(
        name="Format",
        description="Export file format",
        items=[
            ('GLB', 'glTF Binary (.glb)', 'Single binary file (recommended for DCL)'),
            ('GLTF_SEPARATE', 'glTF Separate (.gltf + .bin)', 'Separate files'),
        ],
        default='GLB',
    )

    export_selected: bpy.props.BoolProperty(
        name="Selected Only",
        description="Export only selected objects",
        default=False,
    )

    apply_modifiers: bpy.props.BoolProperty(
        name="Apply Modifiers",
        description="Apply modifiers before exporting",
        default=True,
    )

    export_cameras: bpy.props.BoolProperty(
        name="Export Cameras",
        description="Include cameras in the export",
        default=False,
    )

    export_lights: bpy.props.BoolProperty(
        name="Export Lights",
        description="Include lights in the export (punctual lights extension)",
        default=False,
    )

    atlas_optimize_enabled: bpy.props.BoolProperty(
        name="Atlas Optimizer",
        description="Merge compatible materials into texture atlases to reduce draw calls (non-destructive)",
        default=False,
    )

    atlas_mode: bpy.props.EnumProperty(
        name="Mode",
        description="Choose which textures to include in the atlas",
        items=[
            ('CONSERVATIVE', 'Conservative (512 only)',
             'Only merge materials that already have 512px textures. '
             '1024px textures are left untouched for higher quality'),
            ('AGGRESSIVE', 'Aggressive (resize 1024→512)',
             'Downscale 1024px textures to 512px before merging. '
             'Maximum draw-call reduction at the cost of some quality'),
        ],
        default='AGGRESSIVE',
    )

    atlas_debug_report: bpy.props.BoolProperty(
        name="Show Debug Report",
        description="Show detailed atlas warnings in the export report",
        default=True,
    )

    export_path: bpy.props.StringProperty(
        name="Export Path",
        description="Folder where the file will be exported. Use the folder icon to browse",
        default="",
        subtype='DIR_PATH',
    )

    filename: bpy.props.StringProperty(
        name="Filename",
        description="Name of the exported file (without extension)",
        default="scene",
    )

    def _target_export_objects(self, context):
        if self.export_selected:
            return list(context.selected_objects)
        return list(context.scene.objects)

    # ------------------------------------------------------------------
    # Collection-instance realization  (non-destructive)
    # ------------------------------------------------------------------

    def _realize_collection_instances(self, context):
        """Create real mesh copies from every collection-instance empty in the
        export scope.  The originals are never modified.

        Returns
        -------
        realized : list[bpy.types.Object]
            Temporary objects that must be deleted after export.
        instance_empties : list[bpy.types.Object]
            The source empties (used to hide them during export so they
            don't produce empty glTF nodes).
        """
        target = self._target_export_objects(context)
        instance_empties = [
            obj for obj in target
            if obj.type == 'EMPTY'
            and getattr(obj, 'instance_type', 'NONE') == 'COLLECTION'
            and obj.instance_collection is not None
        ]
        if not instance_empties:
            return [], []

        realized = []
        scene_col = context.scene.collection

        for emp in instance_empties:
            coll = emp.instance_collection
            offset_inv = Matrix.Translation(-coll.instance_offset)

            self._realize_from_collection(
                context, emp, coll, offset_inv,
                emp.matrix_world, scene_col, realized,
            )

        # Force a depsgraph update so the new objects are valid
        if realized:
            context.view_layer.update()

        return realized, instance_empties

    def _realize_from_collection(self, context, emp, coll, offset_inv,
                                  parent_matrix, scene_col, realized):
        """Recursively duplicate geometry from *coll* (and nested
        sub-collection instances) applying *parent_matrix*."""
        for src in coll.objects:
            # Nested collection instance inside this collection
            if (src.type == 'EMPTY'
                    and getattr(src, 'instance_type', 'NONE') == 'COLLECTION'
                    and src.instance_collection is not None):
                nested_coll = src.instance_collection
                nested_offset_inv = Matrix.Translation(-nested_coll.instance_offset)
                nested_parent = parent_matrix @ offset_inv @ src.matrix_local
                self._realize_from_collection(
                    context, emp, nested_coll, nested_offset_inv,
                    nested_parent, scene_col, realized,
                )
                continue

            if src.type not in _GEOMETRY_TYPES:
                continue

            new_obj = src.copy()
            if src.data:
                new_obj.data = src.data.copy()

            # Compose: empty world × (–collection offset) × object local
            new_obj.matrix_world = parent_matrix @ offset_inv @ src.matrix_local
            new_obj.parent = None

            scene_col.objects.link(new_obj)
            realized.append(new_obj)

    def _cleanup_realized(self, context, realized, empties_were_hidden):
        """Delete temporary realized objects and un-hide the empties."""
        for obj in realized:
            try:
                bpy.data.objects.remove(obj, do_unlink=True)
            except Exception:
                pass
        for emp, was_hidden in empties_were_hidden:
            try:
                emp.hide_set(was_hidden)
            except Exception:
                pass

    def _export_with_temp_selection(self, context, objects, kwargs):
        view_layer = context.view_layer
        prev_selected = list(context.selected_objects)
        prev_active = view_layer.objects.active

        try:
            for obj in prev_selected:
                obj.select_set(False)

            active = None
            for obj in objects:
                if obj.name in context.scene.objects:
                    obj.select_set(True)
                    if active is None:
                        active = obj

            if active:
                view_layer.objects.active = active

            bpy.ops.export_scene.gltf(**kwargs)
        finally:
            current_selected = list(context.selected_objects)
            for obj in current_selected:
                obj.select_set(False)

            for obj in prev_selected:
                if obj.name in context.scene.objects:
                    obj.select_set(True)

            if prev_active and prev_active.name in context.scene.objects:
                view_layer.objects.active = prev_active

    def _format_optimization_report(self, report):
        summary = (
            f"Atlas candidates: {report.get('candidate_materials', 0)} | "
            f"Merged quartets: {report.get('merged_quartets', 0)} | "
            f"Merged pairs: {report.get('merged_pairs', 0)} | "
            f"Leftovers: {report.get('leftover_materials', 0)} | "
            f"Est. draw-call reduction: -{report.get('drawcall_reduction_estimate', 0)} | "
            f"Resized to 512: {report.get('resized_textures_to_512', 0)}"
        )

        stats = (
            f"Materials {report.get('before_materials', 0)}->{report.get('after_materials', 0)} | "
            f"Textures {report.get('before_textures', 0)}->{report.get('after_textures', 0)}"
        )

        warnings = report.get('warnings', [])
        if warnings and self.atlas_debug_report:
            return f"{summary} | {stats} | Warnings: {len(warnings)}"
        return f"{summary} | {stats}"

    def _resolve_export_dir(self):
        """Return the absolute export directory from *export_path*.

        Blender's DIR_PATH subtype may store paths with '//' prefix
        (blend-file relative).  ``bpy.path.abspath`` resolves that.
        """
        raw = self.export_path.strip()
        if raw:
            resolved = bpy.path.abspath(raw)
            return os.path.normpath(resolved)

        # Fallback when the field is empty: <blend dir>/export
        if bpy.data.filepath:
            return os.path.join(os.path.dirname(bpy.data.filepath), "export")
        return os.path.join(os.path.expanduser("~"), "Desktop", "export")

    def execute(self, context):
        out_dir = self._resolve_export_dir()

        os.makedirs(out_dir, exist_ok=True)

        ext = ".glb" if self.export_format == 'GLB' else ".gltf"
        filepath = os.path.join(out_dir, self.filename + ext)

        # Build export kwargs
        kwargs = {
            'filepath': filepath,
            'export_format': self.export_format,
            'use_selection': self.export_selected,
            'export_apply': self.apply_modifiers,
            'export_cameras': self.export_cameras,
            'export_lights': self.export_lights,
            'export_yup': True,
        }

        atlas_state = None
        optimization_report = None
        realized_objects = []
        empties_hidden_state = []  # list of (empty, was_hidden_before)

        try:
            # ----- Realize collection instances -----
            realized_objects, instance_empties = self._realize_collection_instances(context)

            if realized_objects:
                inst_count = len(instance_empties)
                obj_count = len(realized_objects)
                self.report(
                    {'INFO'},
                    f"Realized {inst_count} collection instance(s) → {obj_count} object(s)",
                )

                # Hide the source empties so they don't appear as empty
                # glTF nodes; remember previous state for restore.
                for emp in instance_empties:
                    empties_hidden_state.append((emp, emp.hide_get()))
                    emp.hide_set(True)

                # If exporting selected only, make sure realized objects are
                # selected so the glTF exporter picks them up.
                if self.export_selected:
                    for obj in realized_objects:
                        obj.select_set(True)

            # ----- Main export -----
            if self.atlas_optimize_enabled:
                export_objects = self._target_export_objects(context)
                # Include realized objects in atlas scope
                if realized_objects:
                    export_objects = [
                        o for o in export_objects
                        if o not in instance_empties
                    ] + realized_objects

                atlas_state, optimization_report = run_material_atlas_optimization(
                    context,
                    export_objects,
                    resize_mode=self.atlas_mode,
                    debug_report=self.atlas_debug_report,
                )

                atlas_kwargs = dict(kwargs)
                atlas_kwargs['use_selection'] = True
                self._export_with_temp_selection(context, atlas_state.export_objects, atlas_kwargs)
            else:
                bpy.ops.export_scene.gltf(**kwargs)

            file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
            size_str = self._format_size(file_size)

            if optimization_report:
                self.report({'INFO'}, f"Exported to {filepath} ({size_str})")
                self.report({'INFO'}, self._format_optimization_report(optimization_report))

                if self.atlas_debug_report:
                    for warning in optimization_report.get('warnings', [])[:8]:
                        self.report({'WARNING'}, warning)
                    extra = len(optimization_report.get('warnings', [])) - 8
                    if extra > 0:
                        self.report({'WARNING'}, f"... and {extra} more atlas warnings")
            else:
                self.report({'INFO'}, f"Exported to {filepath} ({size_str})")

        except Exception as e:
            if self.atlas_optimize_enabled:
                self.report({'WARNING'}, f"Atlas optimization failed, exporting without atlas: {str(e)}")
                try:
                    bpy.ops.export_scene.gltf(**kwargs)
                    file_size = os.path.getsize(filepath) if os.path.exists(filepath) else 0
                    size_str = self._format_size(file_size)
                    self.report({'INFO'}, f"Exported to {filepath} ({size_str})")
                    return {'FINISHED'}
                except Exception as fallback_err:
                    self.report({'ERROR'}, f"Fallback export failed: {str(fallback_err)}")
                    return {'CANCELLED'}

            self.report({'ERROR'}, f"Export failed: {str(e)}")
            return {'CANCELLED'}
        finally:
            if atlas_state:
                atlas_state.cleanup()
            # Always clean up realized instances
            if realized_objects:
                self._cleanup_realized(context, realized_objects, empties_hidden_state)

        return {'FINISHED'}

    def _format_size(self, size_bytes):
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 * 1024:
            return f"{size_bytes / 1024:.1f} KB"
        else:
            return f"{size_bytes / (1024 * 1024):.2f} MB"

    def draw(self, context):
        layout = self.layout

        layout.prop(self, "export_format")
        layout.separator()

        layout.prop(self, "filename")
        layout.prop(self, "export_path")
        layout.separator()

        col = layout.column(align=True)
        col.prop(self, "export_selected")
        col.prop(self, "apply_modifiers")
        col.prop(self, "export_cameras")
        col.prop(self, "export_lights")

        layout.separator()
        box = layout.box()
        box.prop(self, "atlas_optimize_enabled")
        if self.atlas_optimize_enabled:
            sub = box.column(align=True)
            sub.prop(self, "atlas_mode")
            sub.prop(self, "atlas_debug_report")

        layout.separator()
        # Show resolved output path preview
        out_dir = self._resolve_export_dir()
        ext = ".glb" if self.export_format == 'GLB' else ".gltf"
        layout.label(text=f"Output: {out_dir}/{self.filename}{ext}", icon='FILE')

    def invoke(self, context, event):
        # Default filename from blend file
        if bpy.data.filepath:
            blend_name = os.path.splitext(os.path.basename(bpy.data.filepath))[0]
            self.filename = blend_name
            # Default export path: "export" subfolder next to the .blend file
            if not self.export_path:
                self.export_path = os.path.join(
                    os.path.dirname(bpy.data.filepath), "export"
                ) + os.sep
        return context.window_manager.invoke_props_dialog(self, width=500)
