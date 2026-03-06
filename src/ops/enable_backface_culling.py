import bpy


class OBJECT_OT_enable_backface_culling(bpy.types.Operator):
    bl_idname = "object.enable_backface_culling"
    bl_label = "Enable Backface Culling"
    bl_description = "Enable backface culling for all materials in the scene"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        materials_updated = 0

        # Process all materials in the scene
        for material in bpy.data.materials:
            if material.use_nodes:
                # Enable backface culling
                material.use_backface_culling = True
                materials_updated += 1

        if materials_updated > 0:
            self.report({"INFO"}, f"Enabled backface culling for {materials_updated} materials")
        else:
            self.report({"INFO"}, "No materials found to update")

        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.label(text="This tool will enable backface culling for all materials.")
        layout.label(text="Backface culling improves performance by not rendering")
        layout.label(text="the back faces of geometry.")
        layout.separator()
        layout.label(text="Settings applied:")
        layout.label(text="• Camera: ON")
        layout.label(text="• Shadow: OFF")
        layout.label(text="• Light Probe Volume: ON")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
