import bmesh
import bpy


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
        max=20,
    )

    parcels_y: bpy.props.IntProperty(
        name="Parcels Y",
        description="Number of parcels in Y direction",
        default=2,
        min=1,
        max=20,
    )

    def execute(self, context):
        # Fixed parcel size for Decentraland
        parcel_size = 16.0

        # Calculate total dimensions
        total_width = self.parcels_x * parcel_size
        total_height = self.parcels_y * parcel_size

        # Create/replace collection for parcels
        collection_name = f"Parcels_{self.parcels_x}x{self.parcels_y}"
        if collection_name in bpy.data.collections:
            existing_collection = bpy.data.collections[collection_name]
            for obj in list(existing_collection.objects):
                bpy.data.objects.remove(obj, do_unlink=True)
            bpy.data.collections.remove(existing_collection)

        parcels_collection = bpy.data.collections.new(collection_name)
        context.scene.collection.children.link(parcels_collection)

        # Create mesh data and object directly (no bpy.ops)
        mesh = bpy.data.meshes.new(f"Parcels_Grid_{self.parcels_x}x{self.parcels_y}")
        parcels_obj = bpy.data.objects.new(f"Parcels_Grid_{self.parcels_x}x{self.parcels_y}", mesh)

        # Link only to the parcels collection (not the scene collection)
        parcels_collection.objects.link(parcels_obj)

        # Build the parcel grid with bmesh
        # Each face = one 16m x 16m parcel
        bm = bmesh.new()

        vertices = []
        for y in range(self.parcels_y + 1):
            for x in range(self.parcels_x + 1):
                pos_x = (x / self.parcels_x - 0.5) * total_width
                pos_y = (y / self.parcels_y - 0.5) * total_height
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

        # Write bmesh to mesh and free
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
            f"Created {self.parcels_x}x{self.parcels_y} parcel grid ({total_width}m x {total_height}m) - each face is one 16m x 16m parcel",
        )
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "parcels_x")
        layout.prop(self, "parcels_y")

        # Show total dimensions (fixed 16m per parcel)
        total_width = self.parcels_x * 16.0
        total_height = self.parcels_y * 16.0
        layout.label(text=f"Total size: {total_width}m x {total_height}m")
        layout.label(text="Each parcel: 16m x 16m (Decentraland standard)")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
