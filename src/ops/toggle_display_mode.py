import bpy


class OBJECT_OT_toggle_display_mode(bpy.types.Operator):
    bl_idname = "object.toggle_display_mode"
    bl_label = "Toggle Display Mode"
    bl_description = "Toggle viewport display mode for objects (Bounds, Wire, Textured, Solid)"
    bl_options = {"REGISTER", "UNDO"}

    display_mode: bpy.props.EnumProperty(
        name="Display Mode",
        description="Set the viewport display mode",
        items=[
            ("BOUNDS", "Bounds", "Display as bounding box"),
            ("WIRE", "Wire", "Display as wireframe"),
            ("TEXTURED", "Textured", "Display with textures"),
            ("SOLID", "Solid", "Display as solid"),
        ],
        default="BOUNDS",
    )

    scope_selected: bpy.props.BoolProperty(
        name="Only Selected",
        description="Affect only selected objects",
        default=True,
    )

    def execute(self, context):
        if bpy.context.mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except Exception:
                pass

        # Determine which objects to affect
        if self.scope_selected:
            objects_to_affect = context.selected_objects.copy()
            if not objects_to_affect:
                self.report({"WARNING"}, "No objects selected")
                return {"CANCELLED"}
        else:
            objects_to_affect = list(bpy.data.objects)

        affected_count = 0

        for obj in objects_to_affect:
            if obj.type in {"MESH", "CURVE", "SURFACE", "META", "FONT", "VOLUME", "POINTCLOUD"}:
                # Set the display mode
                obj.display_type = self.display_mode
                affected_count += 1

        # Report results
        scope_text = "selected" if self.scope_selected else "all"
        mode_text = self.display_mode.title()

        if affected_count > 0:
            self.report({"INFO"}, f"Set {affected_count} {scope_text} objects to {mode_text} display")
        else:
            self.report({"WARNING"}, f"No suitable objects found in {scope_text} objects")

        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout

        col = layout.column()
        col.prop(self, "display_mode", expand=True)

        layout.separator()
        layout.prop(self, "scope_selected")

        layout.separator()
        layout.label(text="This will change how objects are displayed in the viewport:")
        layout.label(text="• Bounds: Show bounding boxes only")
        layout.label(text="• Wire: Show wireframe")
        layout.label(text="• Textured: Show with materials/textures")
        layout.label(text="• Solid: Show solid without textures")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
