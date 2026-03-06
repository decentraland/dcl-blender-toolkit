import bpy


class OBJECT_OT_remove_empty_objects(bpy.types.Operator):
    bl_idname = "object.remove_empty_objects"
    bl_label = "Remove Empty Objects"
    bl_description = "Remove empty objects from selected objects (objects with no mesh data, materials, or modifiers)"
    bl_options = {"REGISTER", "UNDO"}

    remove_empties: bpy.props.BoolProperty(
        name="Remove Empty Types",
        description="Remove objects of type 'Empty'",
        default=True,
    )

    remove_mesh_without_data: bpy.props.BoolProperty(
        name="Remove Empty Meshes",
        description="Remove mesh objects that have no geometry (0 vertices/faces)",
        default=True,
    )

    remove_mesh_without_materials: bpy.props.BoolProperty(
        name="Remove Meshes Without Materials",
        description="Remove mesh objects that have no materials assigned",
        default=False,
    )

    scope_selected: bpy.props.BoolProperty(
        name="Only Selected",
        description="Only remove empty objects from selected objects",
        default=True,
    )

    def execute(self, context):
        if bpy.context.mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except Exception:
                pass

        # Determine which objects to check
        if self.scope_selected:
            objects_to_check = context.selected_objects.copy()
            if not objects_to_check:
                self.report({"WARNING"}, "No objects selected")
                return {"CANCELLED"}
        else:
            objects_to_check = list(bpy.data.objects)

        removed_count = 0
        removed_names = []

        # Store original selection to restore later (as names to avoid reference issues)
        original_selection = [obj.name for obj in context.selected_objects]
        original_active_name = context.active_object.name if context.active_object else None

        for obj in objects_to_check:
            should_remove = False
            reason = ""

            # Check if it's an Empty object
            if self.remove_empties and obj.type == "EMPTY":
                should_remove = True
                reason = "Empty object"

            # Check if it's a mesh with no geometry
            elif self.remove_mesh_without_data and obj.type == "MESH":
                if obj.data and len(obj.data.vertices) == 0:
                    should_remove = True
                    reason = "Mesh with no geometry"

            # Check if it's a mesh without materials
            elif self.remove_mesh_without_materials and obj.type == "MESH":
                if not obj.data.materials or len(obj.data.materials) == 0:
                    should_remove = True
                    reason = "Mesh with no materials"

            if should_remove:
                # Store object info before deletion
                obj_name = obj.name
                removed_names.append(f"{obj_name} ({reason})")

                # Remove from all collections
                for collection in obj.users_collection:
                    collection.objects.unlink(obj)

                # Remove the object
                bpy.data.objects.remove(obj, do_unlink=True)
                removed_count += 1

        # Restore original selection (excluding removed objects)
        bpy.ops.object.select_all(action="DESELECT")
        for obj_name in original_selection:
            # Check if object still exists by name
            if obj_name in bpy.data.objects:
                # Get fresh reference to the object
                fresh_obj = bpy.data.objects[obj_name]
                fresh_obj.select_set(True)
        if original_active_name and original_active_name in bpy.data.objects:
            context.view_layer.objects.active = bpy.data.objects[original_active_name]

        # Report results
        if removed_count > 0:
            self.report({"INFO"}, f"Removed {removed_count} empty object(s)")
            for name in removed_names:
                self.report({"INFO"}, f"Removed: {name}")
        else:
            self.report({"INFO"}, "No empty objects found to remove")

        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout

        col = layout.column()
        col.prop(self, "remove_empties")
        col.prop(self, "remove_mesh_without_data")
        col.prop(self, "remove_mesh_without_materials")

        layout.separator()
        layout.prop(self, "scope_selected")

        layout.separator()
        layout.label(text="This will remove objects that match the selected criteria")
        layout.label(text="from either selected objects or all objects in the scene")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
