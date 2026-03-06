import bpy

class OBJECT_OT_rename_mesh_data(bpy.types.Operator):
    bl_idname = "object.rename_mesh_data"
    bl_label = "Rename Mesh Data to Object Name"
    bl_description = "Rename mesh data blocks to match their object names (e.g., 'Cube.001' becomes 'Cube.001')"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        renamed_count = 0
        skipped_count = 0

        # Process selected objects or all objects in the scene
        objects_to_process = bpy.context.selected_objects if bpy.context.selected_objects else list(bpy.data.objects)

        for obj in objects_to_process:
            if obj.type == 'MESH' and obj.data:
                old_name = obj.data.name
                new_name = obj.name

                if old_name != new_name:
                    try:
                        obj.data.name = new_name
                        renamed_count += 1
                    except Exception:
                        skipped_count += 1
                else:
                    skipped_count += 1

        if renamed_count > 0:
            self.report({'INFO'}, f"Renamed {renamed_count} mesh data block(s)")
        else:
            self.report({'INFO'}, "No mesh data blocks needed renaming")

        return {'FINISHED'}
