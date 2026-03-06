import bpy


class OBJECT_OT_remove_uvs_from_colliders(bpy.types.Operator):
    bl_idname = "object.remove_uvs_from_colliders"
    bl_label = "Remove UVs from Colliders"
    bl_description = "Remove UV mapping data from objects with '_collider' suffix"
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

        objects = context.selected_objects if self.scope_selected else bpy.data.objects
        affected_objects = 0
        removed_layers = 0

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

            mesh = obj.data

            # Blender 2.80+ API
            uv_layers = getattr(mesh, "uv_layers", None)
            if uv_layers is not None and len(uv_layers) > 0:
                count_before = len(uv_layers)
                while len(uv_layers) > 0:
                    uv_layers.remove(uv_layers[0])
                affected_objects += 1
                removed_layers += count_before

            # 2.79 legacy (if present in old data)
            uv_textures = getattr(mesh, "uv_textures", None)
            if uv_textures is not None and len(uv_textures) > 0:
                count_before = len(uv_textures)
                while len(uv_textures) > 0:
                    uv_textures.remove(uv_textures[0])
                affected_objects += 1
                removed_layers += count_before

        self.report({"INFO"}, f"Removed {removed_layers} UV layers from {affected_objects} collider meshes")
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "scope_selected")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
