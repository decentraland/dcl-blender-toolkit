import bpy


class OBJECT_OT_apply_transforms(bpy.types.Operator):
    bl_idname = "object.apply_transforms"
    bl_label = "Apply Transforms"
    bl_description = "Apply location, rotation, and scale transforms to selected objects or all objects in the scene"
    bl_options = {"REGISTER", "UNDO"}

    scope: bpy.props.EnumProperty(
        name="Scope",
        description="Which objects to apply transforms to",
        items=[
            ("SELECTED", "Selected Objects", "Apply transforms only to selected objects"),
            ("ALL", "All Objects", "Apply transforms to all objects in the scene"),
            ("COLLECTION", "Collection", "Apply transforms to all objects in a specific collection"),
        ],
        default="SELECTED",
    )

    target_collection: bpy.props.StringProperty(
        name="Target Collection",
        description="Collection to apply transforms to (if Collection scope selected)",
        default="",
    )

    apply_location: bpy.props.BoolProperty(
        name="Apply Location",
        description="Apply location transforms",
        default=True,
    )

    apply_rotation: bpy.props.BoolProperty(
        name="Apply Rotation",
        description="Apply rotation transforms",
        default=True,
    )

    apply_scale: bpy.props.BoolProperty(
        name="Apply Scale",
        description="Apply scale transforms",
        default=True,
    )

    def execute(self, context):
        # Store original selection and active object
        original_selection = list(context.selected_objects)
        original_active = context.active_object

        # Determine which objects to process
        objects_to_process = []

        if self.scope == "SELECTED":
            if not context.selected_objects:
                self.report({"WARNING"}, "No objects selected")
                return {"CANCELLED"}
            objects_to_process = list(context.selected_objects)

        elif self.scope == "ALL":
            objects_to_process = [
                obj for obj in bpy.data.objects if obj.type in {"MESH", "CURVE", "SURFACE", "META", "FONT", "ARMATURE"}
            ]

        elif self.scope == "COLLECTION":
            if not self.target_collection:
                self.report({"WARNING"}, "No collection specified")
                return {"CANCELLED"}

            collection = bpy.data.collections.get(self.target_collection)
            if not collection:
                self.report({"WARNING"}, f"Collection '{self.target_collection}' not found")
                return {"CANCELLED"}

            objects_to_process = [
                obj
                for obj in collection.objects
                if obj.type in {"MESH", "CURVE", "SURFACE", "META", "FONT", "ARMATURE"}
            ]

        if not objects_to_process:
            self.report({"WARNING"}, "No valid objects found to process")
            return {"CANCELLED"}

        # Process each object
        processed_count = 0

        for obj in objects_to_process:
            # Select only this object
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)
            context.view_layer.objects.active = obj

            # Apply transforms based on user selection
            try:
                bpy.ops.object.transform_apply(
                    location=self.apply_location, rotation=self.apply_rotation, scale=self.apply_scale
                )
                processed_count += 1

            except Exception as e:
                self.report({"WARNING"}, f"Failed to apply transforms to {obj.name}: {str(e)}")

        # Restore original selection
        bpy.ops.object.select_all(action="DESELECT")
        for obj in original_selection:
            if obj and obj.name in bpy.data.objects:
                fresh_obj = bpy.data.objects[obj.name]
                fresh_obj.select_set(True)

        if original_active and original_active.name in bpy.data.objects:
            context.view_layer.objects.active = bpy.data.objects[original_active.name]

        # Report results
        transform_types = []
        if self.apply_location:
            transform_types.append("Location")
        if self.apply_rotation:
            transform_types.append("Rotation")
        if self.apply_scale:
            transform_types.append("Scale")

        transform_str = ", ".join(transform_types)
        self.report({"INFO"}, f"Applied {transform_str} to {processed_count} object(s)")

        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout

        # Scope selection
        col = layout.column(align=True)
        col.label(text="Apply to:")
        col.prop(self, "scope", text="")

        if self.scope == "COLLECTION":
            col.prop(self, "target_collection")

        layout.separator()

        # Transform options
        col = layout.column(align=True)
        col.label(text="Transform Types:")
        col.prop(self, "apply_location")
        col.prop(self, "apply_rotation")
        col.prop(self, "apply_scale")

        # Warning about scale
        if self.apply_scale:
            box = layout.box()
            box.label(text="⚠️ Warning:", icon="ERROR")
            box.label(text="Applying scale may affect:")
            box.label(text="• Armature deformation")
            box.label(text="• Animation keyframes")
            box.label(text="• Modifier effects")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    @classmethod
    def poll(cls, context):
        return context.mode == "OBJECT"
