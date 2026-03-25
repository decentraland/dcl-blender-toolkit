import bmesh
import bpy

from .. import icon_loader

# Origin offsets: (x_offset, y_offset) as fractions of total size
ORIGIN_OFFSETS = {
    "CENTER": (-0.5, -0.5),
    "BOTTOM_LEFT": (0.0, 0.0),
    "BOTTOM_RIGHT": (-1.0, 0.0),
    "TOP_LEFT": (0.0, -1.0),
    "TOP_RIGHT": (-1.0, -1.0),
}

# Map origin enum values to custom icon names
ORIGIN_ICONS = {
    "TOP_LEFT": "ORIGIN_TL",
    "TOP_RIGHT": "ORIGIN_TR",
    "CENTER": "ORIGIN_CENTER",
    "BOTTOM_LEFT": "ORIGIN_BL",
    "BOTTOM_RIGHT": "ORIGIN_BR",
}


def _create_checker_material():
    """Create a procedural checker material with parcel-level and meter-level grids."""
    mat_name = "DCL_Parcel_Checker"

    # Remove old version and recreate to ensure correct settings
    if mat_name in bpy.data.materials:
        old = bpy.data.materials[mat_name]
        if old.users == 0:
            bpy.data.materials.remove(old)
        else:
            return old

    mat = bpy.data.materials.new(name=mat_name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links

    # Clear default nodes
    nodes.clear()

    # --- Nodes ---
    output = nodes.new("ShaderNodeOutputMaterial")
    output.location = (1000, 0)

    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    bsdf.location = (800, 0)
    links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

    # Add/Subtract meter grid on top of parcel base
    # MixRGB Add mode: parcel_base + meter_offset
    add_node = nodes.new("ShaderNodeMix")
    add_node.data_type = "RGBA"
    add_node.blend_type = "ADD"
    add_node.location = (600, 0)
    add_node.inputs["Factor"].default_value = 1.0
    links.new(add_node.outputs["Result"], bsdf.inputs["Base Color"])

    # Parcel-level checker (16m scale) — strong contrast dark/light grey
    parcel_checker = nodes.new("ShaderNodeTexChecker")
    parcel_checker.location = (0, 100)
    parcel_checker.inputs["Color1"].default_value = (0.20, 0.20, 0.20, 1.0)  # dark grey
    parcel_checker.inputs["Color2"].default_value = (0.27, 0.27, 0.27, 1.0)  # light grey
    parcel_checker.inputs["Scale"].default_value = 1.0

    # Meter-level checker (1m scale) — subtle offset (black / slight bump)
    meter_checker = nodes.new("ShaderNodeTexChecker")
    meter_checker.location = (0, -200)
    meter_checker.inputs["Color1"].default_value = (0.0, 0.0, 0.0, 1.0)     # no offset
    meter_checker.inputs["Color2"].default_value = (0.05, 0.05, 0.05, 1.0)   # slight lighten
    meter_checker.inputs["Scale"].default_value = 1.0

    # Object coordinates
    tex_coord = nodes.new("ShaderNodeTexCoord")
    tex_coord.location = (-600, 0)

    # Mapping for parcel scale: 1/16 so each checker cell = 16m
    parcel_mapping = nodes.new("ShaderNodeMapping")
    parcel_mapping.location = (-300, 100)
    parcel_mapping.inputs["Scale"].default_value = (1.0 / 16.0, 1.0 / 16.0, 1.0)

    # Mapping for meter scale: 1.0 so each checker cell = 1m
    meter_mapping = nodes.new("ShaderNodeMapping")
    meter_mapping.location = (-300, -200)
    meter_mapping.inputs["Scale"].default_value = (1.0, 1.0, 1.0)

    # Connect coordinates -> mappings -> checkers
    links.new(tex_coord.outputs["Object"], parcel_mapping.inputs["Vector"])
    links.new(tex_coord.outputs["Object"], meter_mapping.inputs["Vector"])
    links.new(parcel_mapping.outputs["Vector"], parcel_checker.inputs["Vector"])
    links.new(meter_mapping.outputs["Vector"], meter_checker.inputs["Vector"])

    # Parcel checker is base (A), meter checker adds subtle grid (B)
    links.new(parcel_checker.outputs["Color"], add_node.inputs["A"])
    links.new(meter_checker.outputs["Color"], add_node.inputs["B"])

    return mat


class OBJECT_OT_set_parcel_origin(bpy.types.Operator):
    """Helper operator to set the parcel origin from icon buttons."""
    bl_idname = "object.set_parcel_origin"
    bl_label = "Set Origin"
    bl_options = {"INTERNAL"}

    origin_value: bpy.props.StringProperty()

    def execute(self, context):
        context.scene["_dcl_parcel_origin"] = self.origin_value
        return {"FINISHED"}


def _draw_origin_btn(layout, value, is_active):
    """Draw an origin button with custom icon. Returns the operator for property assignment."""
    ico = icon_loader.get_icon(ORIGIN_ICONS[value])
    if ico:
        op = layout.operator(
            "object.set_parcel_origin",
            text="",
            icon_value=ico,
            depress=is_active,
        )
    else:
        op = layout.operator(
            "object.set_parcel_origin",
            text=" ",
            depress=is_active,
        )
    op.origin_value = value


class OBJECT_OT_create_parcels(bpy.types.Operator):
    bl_idname = "object.create_parcels"
    bl_label = "Create Parcels"
    bl_description = "Create a grid of Decentraland parcels with customizable dimensions"
    bl_options = {"REGISTER", "UNDO"}

    parcels_x: bpy.props.IntProperty(
        name="Parcels X",
        description="Number of parcels in X direction",
        default=2,
        min=1,
        max=200,
        soft_max=50,
    )

    parcels_y: bpy.props.IntProperty(
        name="Parcels Y",
        description="Number of parcels in Y direction",
        default=2,
        min=1,
        max=200,
        soft_max=50,
    )

    origin: bpy.props.EnumProperty(
        name="Origin",
        description="Position of the world origin relative to the parcel grid",
        items=[
            ("CENTER", "Center", "Origin at the center of the grid"),
            ("BOTTOM_LEFT", "Bottom Left", "Origin at the bottom-left corner"),
            ("BOTTOM_RIGHT", "Bottom Right", "Origin at the bottom-right corner"),
            ("TOP_LEFT", "Top Left", "Origin at the top-left corner"),
            ("TOP_RIGHT", "Top Right", "Origin at the top-right corner"),
        ],
        default="BOTTOM_LEFT",
    )

    def execute(self, context):
        # Read origin from scene temp property if set by icon buttons
        origin = context.scene.pop("_dcl_parcel_origin", None)
        if origin and origin in ORIGIN_OFFSETS:
            self.origin = origin

        parcel_size = 16.0

        total_width = self.parcels_x * parcel_size
        total_height = self.parcels_y * parcel_size

        # Origin offset
        ox, oy = ORIGIN_OFFSETS[self.origin]

        # Create/replace collection for parcels
        collection_name = f"Parcels_{self.parcels_x}x{self.parcels_y}"
        if collection_name in bpy.data.collections:
            existing_collection = bpy.data.collections[collection_name]
            for obj in list(existing_collection.objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.collections.remove(existing_collection)

        parcels_collection = bpy.data.collections.new(collection_name)
        context.scene.collection.children.link(parcels_collection)

        mesh = bpy.data.meshes.new(f"Parcels_Grid_{self.parcels_x}x{self.parcels_y}")
        parcels_obj = bpy.data.objects.new(f"Parcels_Grid_{self.parcels_x}x{self.parcels_y}", mesh)
        parcels_collection.objects.link(parcels_obj)

        # Build the parcel grid with bmesh
        bm = bmesh.new()

        vertices = []
        for y in range(self.parcels_y + 1):
            for x in range(self.parcels_x + 1):
                pos_x = (x / self.parcels_x + ox) * total_width
                pos_y = (y / self.parcels_y + oy) * total_height
                vert = bm.verts.new((pos_x, pos_y, 0.0))
                vertices.append(vert)

        # Create faces - one per parcel
        cols = self.parcels_x + 1
        for y in range(self.parcels_y):
            for x in range(self.parcels_x):
                v1 = vertices[y * cols + x]
                v2 = vertices[y * cols + x + 1]
                v3 = vertices[(y + 1) * cols + x + 1]
                v4 = vertices[(y + 1) * cols + x]
                bm.faces.new([v1, v2, v3, v4])

        bm.to_mesh(mesh)
        bm.free()
        mesh.update()

        # Make it the active selected object
        context.view_layer.objects.active = parcels_obj
        parcels_obj.select_set(True)

        # Center view on parcels
        try:
            bpy.ops.view3d.view_selected()
        except RuntimeError:
            pass

        self.report(
            {"INFO"},
            f"Created {self.parcels_x}x{self.parcels_y} parcel grid ({total_width}m x {total_height}m) - origin: {self.origin}",
        )
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "parcels_x")
        layout.prop(self, "parcels_y")

        # Show total dimensions
        total_width = self.parcels_x * 16.0
        total_height = self.parcels_y * 16.0
        layout.label(text=f"Total size: {total_width}m x {total_height}m")
        layout.label(text="Each parcel: 16m x 16m (Decentraland standard)")

        layout.separator()
        layout.label(text="Origin Point:")

        # Read current origin (check scene temp or operator property)
        current = context.scene.get("_dcl_parcel_origin", self.origin)

        # 3x3 grid: corners + center with custom icons
        grid = layout.grid_flow(row_major=True, columns=3, even_columns=True, even_rows=True, align=True)
        grid.scale_y = 1.5

        # Row 1: [TL] [  ] [TR]
        _draw_origin_btn(grid, "TOP_LEFT", current == "TOP_LEFT")
        grid.label(text="")
        _draw_origin_btn(grid, "TOP_RIGHT", current == "TOP_RIGHT")

        # Row 2: [  ] [C ] [  ]
        grid.label(text="")
        _draw_origin_btn(grid, "CENTER", current == "CENTER")
        grid.label(text="")

        # Row 3: [BL] [  ] [BR]
        _draw_origin_btn(grid, "BOTTOM_LEFT", current == "BOTTOM_LEFT")
        grid.label(text="")
        _draw_origin_btn(grid, "BOTTOM_RIGHT", current == "BOTTOM_RIGHT")

        layout.label(text="Bottom Left is recommended for DCL scenes", icon="INFO")

    def invoke(self, context, event):
        # Initialize scene temp property
        context.scene["_dcl_parcel_origin"] = self.origin
        return context.window_manager.invoke_props_dialog(self, width=300)


class OBJECT_OT_apply_checker_map(bpy.types.Operator):
    bl_idname = "object.apply_checker_map"
    bl_label = "Checker Map"
    bl_description = "Apply a checker material to the parcel grid to visualize 16m parcels and 1m subdivisions"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        # Find parcel grid objects
        applied = 0
        for obj in context.scene.objects:
            if obj.type == "MESH" and obj.name.startswith("Parcels_Grid_"):
                checker_mat = _create_checker_material()
                # Don't add if already assigned
                if checker_mat.name not in [m.name for m in obj.data.materials if m]:
                    obj.data.materials.append(checker_mat)
                    applied += 1

        if applied:
            self.report({"INFO"}, f"Applied checker map to {applied} parcel grid(s)")
        else:
            self.report({"WARNING"}, "No parcel grids found (or checker already applied)")
        return {"FINISHED"}


class OBJECT_OT_cleanup_checker_map(bpy.types.Operator):
    bl_idname = "object.cleanup_checker_map"
    bl_label = "Cleanup All Checker Maps"
    bl_description = "Remove all checker map materials from parcel grids"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        mat_name = "DCL_Parcel_Checker"
        cleaned = 0

        for obj in context.scene.objects:
            if obj.type == "MESH":
                # Remove checker material slots
                for i in range(len(obj.data.materials) - 1, -1, -1):
                    if obj.data.materials[i] and obj.data.materials[i].name == mat_name:
                        obj.data.materials.pop(index=i)
                        cleaned += 1

        # Remove the material data block if no longer used
        if mat_name in bpy.data.materials:
            mat = bpy.data.materials[mat_name]
            if mat.users == 0:
                bpy.data.materials.remove(mat)

        if cleaned:
            self.report({"INFO"}, f"Removed checker map from {cleaned} object(s)")
        else:
            self.report({"WARNING"}, "No checker maps found to remove")
        return {"FINISHED"}
