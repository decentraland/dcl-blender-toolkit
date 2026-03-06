import bpy
import os
import json

class OBJECT_OT_export_lights(bpy.types.Operator):
    bl_idname = "object.export_lights"
    bl_label = "Export Lights (EXPERIMENTAL)"
    bl_description = "Export lights from LightsEXPORT collection to JSON file"
    bl_options = {'REGISTER', 'UNDO'}

    export_folder: bpy.props.StringProperty(
        name="Export Folder",
        description="Folder name to export lights JSON file (will be created in Desktop)",
        default="lights_export",
    )

    collection_name: bpy.props.StringProperty(
        name="Collection Name",
        description="Name of the collection containing lights",
        default="LightsEXPORT",
    )

    def get_lights_collection_data(self, collection):
        objs_data = []

        for ob in collection.objects:
            if ob.type != "LIGHT":
                continue

            matrix_world = ob.matrix_world.copy()
            blender_pos = matrix_world.to_translation()
            sdk_pos = {
                'x': -blender_pos.x,
                'y': blender_pos.z,
                'z': -blender_pos.y,
            }

            color = ob.data.color
            sdk_color = {'r': color.r, 'g': color.g, 'b': color.b}

            intensity = ob.data.energy * 100
            range_val = getattr(ob.data, 'range', 10)
            if not range_val:
                range_val = 10

            objs_data.append({
                'name': ob.name,
                'position': sdk_pos,
                'color': sdk_color,
                'intensity': intensity,
                'range': range_val,
            })

        return objs_data

    def execute(self, context):
        depsgraph = bpy.context.evaluated_depsgraph_get()
        depsgraph.update()

        for ob in bpy.context.selected_objects:
            ob.select_set(False)
        bpy.ops.object.select_all(action='DESELECT')
        bpy.context.view_layer.objects.active = None

        if self.collection_name not in bpy.data.collections:
            self.report({'ERROR'}, f"Collection '{self.collection_name}' not found!")
            return {'CANCELLED'}

        master_collection = bpy.data.collections[self.collection_name]
        lights_in_master = [obj for obj in master_collection.objects if obj.type == "LIGHT"]
        sub_collections = master_collection.children

        lights_data = {}

        if lights_in_master:
            light_data = self.get_lights_collection_data(master_collection)
            if light_data:
                lights_data[self.collection_name] = light_data

        for collection in sub_collections:
            light_data = self.get_lights_collection_data(collection)
            if light_data:
                lights_data[collection.name] = light_data

        if not lights_data:
            self.report({'WARNING'}, "No light data found to export!")
            return {'CANCELLED'}

        lights_json = json.dumps(lights_data, indent=4)

        # Use blend file directory with user-specified folder name
        if bpy.data.filepath:
            blend_dir = os.path.dirname(bpy.data.filepath)
            export_path = os.path.join(blend_dir, self.export_folder)
        else:
            home_dir = os.path.expanduser("~")
            export_path = os.path.join(home_dir, "Desktop", self.export_folder)

        try:
            os.makedirs(export_path, exist_ok=True)
        except Exception:
            export_path = os.path.join(os.getcwd(), self.export_folder)
            os.makedirs(export_path, exist_ok=True)

        output_file = os.path.join(export_path, master_collection.name + ".json")

        try:
            with open(output_file, "w") as f:
                f.write(lights_json)
            total = sum(len(lights) for lights in lights_data.values())
            self.report({'INFO'}, f"Exported {total} lights to: {output_file}")
        except Exception as e:
            self.report({'ERROR'}, f"Error writing file: {e}")
            return {'CANCELLED'}

        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "export_folder")
        layout.prop(self, "collection_name")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
