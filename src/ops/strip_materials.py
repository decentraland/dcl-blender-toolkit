import bpy


class OBJECT_OT_strip_materials_from_colliders(bpy.types.Operator):
    bl_idname = "object.strip_materials_from_colliders"
    bl_label = "Strip Materials from Colliders"
    bl_description = "Remove all material slots from objects with '_collider' suffix"
    bl_options = {"REGISTER", "UNDO"}

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

        # Store original selection and active object
        original_selection = list(context.selected_objects)
        original_active = context.active_object

        objects = context.selected_objects if self.scope_selected else bpy.data.objects
        affected = 0
        slots_removed = 0

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

            # Clear material slots
            count = len(obj.material_slots)
            if count > 0:
                # Select and activate the object
                bpy.ops.object.select_all(action="DESELECT")
                obj.select_set(True)
                context.view_layer.objects.active = obj

                # Remove all material slots
                for i in range(count - 1, -1, -1):
                    obj.active_material_index = i
                    bpy.ops.object.material_slot_remove()

                affected += 1
                slots_removed += count

        # Restore original selection using fresh references
        bpy.ops.object.select_all(action="DESELECT")
        for orig_obj in original_selection:
            try:
                if orig_obj and orig_obj.name in bpy.data.objects:
                    bpy.data.objects[orig_obj.name].select_set(True)
            except ReferenceError:
                pass
        if original_active:
            try:
                if original_active.name in bpy.data.objects:
                    context.view_layer.objects.active = bpy.data.objects[original_active.name]
            except ReferenceError:
                pass

        self.report({"INFO"}, f"Removed {slots_removed} material slots from {affected} collider meshes")
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "scope_selected")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
