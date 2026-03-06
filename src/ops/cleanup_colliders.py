import bpy


class OBJECT_OT_cleanup_colliders(bpy.types.Operator):
    bl_idname = "object.cleanup_colliders"
    bl_label = "Cleanup Colliders"
    bl_description = "Remove doubles, limit dissolve, and optimize collider meshes"
    bl_options = {"REGISTER", "UNDO"}

    merge_distance: bpy.props.FloatProperty(
        name="Merge Distance",
        description="Distance for merging vertices",
        default=0.001,
        min=0.0001,
        max=1.0,
    )

    scope_selected: bpy.props.BoolProperty(
        name="Only Selected",
        description="Affect only selected objects",
        default=False,
    )

    def execute(self, context):
        if bpy.context.mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except Exception:
                pass

        objects = context.selected_objects if self.scope_selected else bpy.data.objects
        affected = 0

        for obj in objects:
            if obj.type != "MESH":
                continue

            # Check if object name contains "_collider" (handles .001, .002 suffixes)
            # OR if it's a child of a collider object
            is_collider = False

            # Direct collider check
            if "_collider" in obj.name:
                is_collider = True
            else:
                # Check if parent is a collider
                parent = obj.parent
                while parent:
                    if "_collider" in parent.name:
                        is_collider = True
                        break
                    parent = parent.parent

            if not is_collider:
                continue

            # Select and make active
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)
            bpy.context.view_layer.objects.active = obj

            # Enter edit mode
            bpy.ops.object.mode_set(mode="EDIT")

            # Select all vertices
            bpy.ops.mesh.select_all(action="SELECT")

            # Remove doubles
            bpy.ops.mesh.remove_doubles(threshold=self.merge_distance)

            # Dissolve degenerate faces
            bpy.ops.mesh.dissolve_degenerate()

            # Return to object mode
            bpy.ops.object.mode_set(mode="OBJECT")

            affected += 1

        self.report({"INFO"}, f"Cleaned up {affected} collider objects")
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "merge_distance")
        layout.prop(self, "scope_selected")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
