import bpy


class OBJECT_OT_simplify_colliders(bpy.types.Operator):
    bl_idname = "object.simplify_colliders"
    bl_label = "Simplify Colliders"
    bl_description = "Apply decimation modifier to reduce polygon count on selected collider objects"
    bl_options = {"REGISTER", "UNDO"}

    ratio: bpy.props.FloatProperty(
        name="Decimation Ratio",
        description="Ratio of faces to keep (0.1 = 10% of original faces)",
        default=0.5,
        min=0.01,
        max=1.0,
    )

    def execute(self, context):
        if bpy.context.mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except Exception:
                pass

        # Work on selected objects only for individual control
        if not context.selected_objects:
            self.report({"WARNING"}, "Please select one or more collider objects to simplify")
            return {"CANCELLED"}

        affected = 0

        for obj in context.selected_objects:
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
                self.report({"WARNING"}, f"Object '{obj.name}' is not a collider, skipping")
                continue

            # Store original selection
            original_selection = list(context.selected_objects)
            original_active = context.active_object

            # Select only this object
            bpy.ops.object.select_all(action="DESELECT")
            obj.select_set(True)
            context.view_layer.objects.active = obj

            # Add decimation modifier
            decimate_mod = obj.modifiers.new(name="Decimate", type="DECIMATE")
            decimate_mod.ratio = self.ratio
            decimate_mod.use_collapse_triangulate = True

            # Apply the modifier
            bpy.ops.object.modifier_apply(modifier=decimate_mod.name)

            affected += 1
            self.report({"INFO"}, f"Simplified '{obj.name}' with ratio {self.ratio}")

            # Restore original selection
            bpy.ops.object.select_all(action="DESELECT")
            for sel_obj in original_selection:
                sel_obj.select_set(True)
            if original_active:
                context.view_layer.objects.active = original_active

        if affected > 0:
            self.report({"INFO"}, f"Successfully simplified {affected} collider object(s)")
        else:
            self.report({"WARNING"}, "No collider objects found in selection")

        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "ratio")
        layout.separator()
        layout.label(text="Select collider objects to simplify")
        layout.label(text="Each object will be processed individually")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
