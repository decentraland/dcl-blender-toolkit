import bpy
from .. import icon_loader


def draw_lod_panel(layout, context):
    """Draw the full LOD Generator panel section with visual LOD indicators."""
    scene = context.scene
    levels = scene.dcl_lod_levels

    # Level count control
    layout.prop(scene, "dcl_lod_levels")
    layout.separator()

    # ---- LOD level rows with visual factor sliders ----
    lod_box = layout.box()
    col = lod_box.column(align=True)

    # LOD 0 — always 100% (the original mesh, not editable)
    row = col.row(align=True)
    row.label(text="LOD 0  (Original)", icon='MESH_DATA')
    sub = row.row()
    sub.alignment = 'RIGHT'
    sub.label(text="100%")

    # LOD 1-4 — editable FACTOR sliders that double as visual bars
    if levels >= 1:
        col.prop(scene, "dcl_lod1_ratio", text="LOD 1", slider=True)
    if levels >= 2:
        col.prop(scene, "dcl_lod2_ratio", text="LOD 2", slider=True)
    if levels >= 3:
        col.prop(scene, "dcl_lod3_ratio", text="LOD 3", slider=True)
    if levels >= 4:
        col.prop(scene, "dcl_lod4_ratio", text="LOD 4", slider=True)

    # Culled indicator
    row = col.row(align=True)
    row.alert = True
    row.label(text="Culled", icon='CANCEL')

    layout.separator()

    # Options
    layout.prop(scene, "dcl_lod_create_collection")

    # Generate button
    layout.separator()
    row = layout.row(align=True)
    row.scale_y = 1.4
    ico = icon_loader.get_icon("CUBE_SPARK")
    if ico:
        op = row.operator(
            OBJECT_OT_generate_lod.bl_idname,
            text="Generate LODs",
            icon_value=ico,
        )
    else:
        op = row.operator(
            OBJECT_OT_generate_lod.bl_idname,
            text="Generate LODs",
            icon='MOD_DECIM',
        )
    # Pass panel settings to the operator
    op.lod_levels = scene.dcl_lod_levels
    op.lod1_ratio = scene.dcl_lod1_ratio
    op.lod2_ratio = scene.dcl_lod2_ratio
    op.lod3_ratio = scene.dcl_lod3_ratio
    op.lod4_ratio = scene.dcl_lod4_ratio
    op.create_collection = scene.dcl_lod_create_collection
    op.skip_dialog = True

    # Selection info
    mesh_count = len([o for o in context.selected_objects if o.type == 'MESH'])
    layout.label(text=f"{mesh_count} mesh object(s) selected", icon='INFO')


class OBJECT_OT_generate_lod(bpy.types.Operator):
    bl_idname = "object.generate_lod"
    bl_label = "Generate LODs"
    bl_description = "Create Level of Detail copies of selected objects using decimation"
    bl_options = {'REGISTER', 'UNDO'}

    lod_levels: bpy.props.IntProperty(
        name="LOD Levels",
        description="Number of LOD levels to generate",
        default=3,
        min=1,
        max=4,
    )

    lod1_ratio: bpy.props.FloatProperty(
        name="LOD1 Ratio",
        description="Decimation ratio for LOD1 (e.g. 0.5 = 50% of original)",
        default=0.50,
        min=0.01,
        max=0.99,
        subtype='FACTOR',
    )

    lod2_ratio: bpy.props.FloatProperty(
        name="LOD2 Ratio",
        description="Decimation ratio for LOD2",
        default=0.15,
        min=0.01,
        max=0.99,
        subtype='FACTOR',
    )

    lod3_ratio: bpy.props.FloatProperty(
        name="LOD3 Ratio",
        description="Decimation ratio for LOD3",
        default=0.05,
        min=0.01,
        max=0.99,
        subtype='FACTOR',
    )

    lod4_ratio: bpy.props.FloatProperty(
        name="LOD4 Ratio",
        description="Decimation ratio for LOD4",
        default=0.02,
        min=0.01,
        max=0.99,
        subtype='FACTOR',
    )

    create_collection: bpy.props.BoolProperty(
        name="Create LOD Collection",
        description="Place generated LODs in a dedicated collection",
        default=True,
    )

    skip_dialog: bpy.props.BoolProperty(
        name="Skip Dialog",
        description="Skip confirmation dialog (used when invoked from the panel)",
        default=False,
        options={'HIDDEN'},
    )

    def execute(self, context):
        if bpy.context.mode != 'OBJECT':
            try:
                bpy.ops.object.mode_set(mode='OBJECT')
            except Exception:
                pass

        source_objects = [obj for obj in context.selected_objects if obj.type == 'MESH']
        if not source_objects:
            self.report({'WARNING'}, "No mesh objects selected")
            return {'CANCELLED'}

        ratios = [self.lod1_ratio, self.lod2_ratio, self.lod3_ratio, self.lod4_ratio]
        levels = min(self.lod_levels, 4)

        # Optional collection
        lod_collection = None
        if self.create_collection:
            col_name = "LOD_Generated"
            if col_name not in bpy.data.collections:
                lod_collection = bpy.data.collections.new(col_name)
                context.scene.collection.children.link(lod_collection)
            else:
                lod_collection = bpy.data.collections[col_name]

        total_created = 0

        for src_obj in source_objects:
            for lod_idx in range(levels):
                ratio = ratios[lod_idx]
                lod_name = f"{src_obj.name}_LOD{lod_idx + 1}"

                # Duplicate mesh data
                new_mesh = src_obj.data.copy()
                new_obj = bpy.data.objects.new(lod_name, new_mesh)

                # Copy transforms
                new_obj.location = src_obj.location
                new_obj.rotation_euler = src_obj.rotation_euler
                new_obj.scale = src_obj.scale

                # Link to collection
                if lod_collection:
                    lod_collection.objects.link(new_obj)
                else:
                    context.scene.collection.objects.link(new_obj)

                # Apply decimation
                bpy.ops.object.select_all(action='DESELECT')
                new_obj.select_set(True)
                context.view_layer.objects.active = new_obj

                mod = new_obj.modifiers.new(name="Decimate_LOD", type='DECIMATE')
                mod.ratio = ratio
                mod.use_collapse_triangulate = True
                bpy.ops.object.modifier_apply(modifier=mod.name)

                total_created += 1

        # Restore selection to source objects
        bpy.ops.object.select_all(action='DESELECT')
        for obj in source_objects:
            obj.select_set(True)
        if source_objects:
            context.view_layer.objects.active = source_objects[0]

        self.report({'INFO'}, f"Generated {total_created} LOD object(s) from {len(source_objects)} source(s)")
        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout

        layout.prop(self, "lod_levels")
        layout.separator()

        # LOD levels with visual factor sliders
        lod_box = layout.box()
        col = lod_box.column(align=True)

        row = col.row(align=True)
        row.label(text="LOD 0  (Original)", icon='MESH_DATA')
        sub = row.row()
        sub.alignment = 'RIGHT'
        sub.label(text="100%")

        if self.lod_levels >= 1:
            col.prop(self, "lod1_ratio", text="LOD 1", slider=True)
        if self.lod_levels >= 2:
            col.prop(self, "lod2_ratio", text="LOD 2", slider=True)
        if self.lod_levels >= 3:
            col.prop(self, "lod3_ratio", text="LOD 3", slider=True)
        if self.lod_levels >= 4:
            col.prop(self, "lod4_ratio", text="LOD 4", slider=True)

        row = col.row(align=True)
        row.alert = True
        row.label(text="Culled", icon='CANCEL')

        layout.separator()
        layout.prop(self, "create_collection")

        layout.separator()
        count = len([o for o in bpy.context.selected_objects if o.type == 'MESH'])
        layout.label(text=f"{count} mesh object(s) selected", icon='INFO')

    def invoke(self, context, event):
        if self.skip_dialog:
            return self.execute(context)
        return context.window_manager.invoke_props_dialog(self, width=400)
