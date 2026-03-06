import bpy


class OBJECT_OT_rename_add_collider_suffix(bpy.types.Operator):
    bl_idname = "object.rename_add_collider_suffix"
    bl_label = "Add _collider Suffix"
    bl_description = "Add '_collider' suffix to selected objects"
    bl_options = {"REGISTER", "UNDO"}

    only_meshes: bpy.props.BoolProperty(
        name="Only Mesh Objects",
        description="Only rename mesh objects",
        default=True,
    )

    def execute(self, context):
        renamed = 0
        for obj in context.selected_objects:
            if self.only_meshes and obj.type != "MESH":
                continue
            if not obj.name.endswith("_collider"):
                obj.name = f"{obj.name}_collider"
                renamed += 1
        self.report({"INFO"}, f"Renamed {renamed} objects")
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "only_meshes")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
