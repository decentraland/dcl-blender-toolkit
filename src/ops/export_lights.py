import json
import math
import os

import bpy
import mathutils


class OBJECT_OT_export_lights(bpy.types.Operator):
    bl_idname = "object.export_lights"
    bl_label = "Export Lights (EXPERIMENTAL)"
    bl_description = "Export lights from LightsEXPORT collection to JSON file"
    bl_options = {"REGISTER", "UNDO"}

    export_dir: bpy.props.StringProperty(
        name="Output Directory",
        description="Folder where the lights JSON will be saved",
        default="",
        subtype="DIR_PATH",
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

            # Position: Blender -> SDK coordinate conversion
            blender_pos = matrix_world.to_translation()
            sdk_pos = {
                "x": -blender_pos.x,
                "y": blender_pos.z,
                "z": -blender_pos.y,
            }

            # Rotation: Blender -> SDK quaternion conversion
            blender_rot = matrix_world.to_quaternion()
            sdk_quat = mathutils.Quaternion((blender_rot.w, blender_rot.x, -blender_rot.z, blender_rot.y))

            # For spot lights: apply direction correction
            # Blender spots point along local -Z (downward in Z-up)
            # DCL/Unity spots point along local forward (+Z in Y-up)
            # Correction: +90 degrees around X to point spots downward in DCL
            if ob.data.type == "SPOT":
                correction = mathutils.Quaternion((1, 0, 0), math.radians(90))
                sdk_quat = sdk_quat @ correction

            sdk_rot = {
                "w": sdk_quat.w,
                "x": sdk_quat.x,
                "y": sdk_quat.y,
                "z": sdk_quat.z,
            }

            # Color
            color = ob.data.color
            sdk_color = {"r": color.r, "g": color.g, "b": color.b}

            # Intensity: use custom property 'intensity' if set (direct DCL value),
            # otherwise convert Blender watts to DCL intensity (× 400)
            intensity = ob.data.get("intensity")
            if not intensity:
                intensity = ob.data.energy * 400

            # Range (custom property or default)
            range_val = ob.data.get("range")
            if not range_val:
                range_val = 10

            # Shadow: use Blender's native Cast Shadow setting
            shadow = ob.data.use_shadow

            # Light type: POINT or SPOT
            light_type = "POINT"
            spot_inner_angle = 21.8
            spot_outer_angle = 30.0

            if ob.data.type == "SPOT":
                light_type = "SPOT"
                # Blender spot_size is the full cone angle in radians
                # Blender spot_blend is 0-1, controls softness (1 = fully soft)
                full_angle_deg = math.degrees(ob.data.spot_size)
                blend = ob.data.spot_blend

                # DCL angle mapping calibrated from Blender:
                # outerAngle ≈ full Blender angle
                # innerAngle = full_angle * blend * 0.26
                spot_outer_angle = full_angle_deg
                spot_inner_angle = full_angle_deg * blend * 0.26
                # Clamp to DCL limits (0-179)
                spot_inner_angle = max(0, min(179, spot_inner_angle))
                spot_outer_angle = max(0, min(179, spot_outer_angle))

            ob_data = {
                "name": ob.name,
                "type": light_type,
                "position": sdk_pos,
                "rotation": sdk_rot,
                "color": sdk_color,
                "intensity": intensity,
                "range": range_val,
                "shadow": shadow,
            }

            if light_type == "SPOT":
                ob_data["innerAngle"] = spot_inner_angle
                ob_data["outerAngle"] = spot_outer_angle

            objs_data.append(ob_data)

        return objs_data

    def execute(self, context):
        depsgraph = bpy.context.evaluated_depsgraph_get()
        depsgraph.update()

        for ob in bpy.context.selected_objects:
            ob.select_set(False)
        bpy.ops.object.select_all(action="DESELECT")
        bpy.context.view_layer.objects.active = None

        if self.collection_name not in bpy.data.collections:
            self.report({"ERROR"}, f"Collection '{self.collection_name}' not found!")
            return {"CANCELLED"}

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
            self.report({"WARNING"}, "No light data found to export!")
            return {"CANCELLED"}

        lights_json = json.dumps(lights_data, indent=4)

        export_path = self._resolve_export_dir()
        os.makedirs(export_path, exist_ok=True)

        output_file = os.path.join(export_path, master_collection.name + ".json")

        try:
            with open(output_file, "w") as f:
                f.write(lights_json)
            total = sum(len(lights) for lights in lights_data.values())
            self.report({"INFO"}, f"Exported {total} lights to: {output_file}")
        except Exception as e:
            self.report({"ERROR"}, f"Error writing file: {e}")
            return {"CANCELLED"}

        return {"FINISHED"}

    def _resolve_export_dir(self):
        raw = self.export_dir.strip()
        if raw:
            return os.path.normpath(bpy.path.abspath(raw))
        if bpy.data.filepath:
            return os.path.join(os.path.dirname(bpy.data.filepath), "lights_export")
        return os.path.join(os.path.expanduser("~"), "Desktop", "lights_export")

    def draw(self, context):
        layout = self.layout
        layout.prop_search(self, "collection_name", bpy.data, "collections", icon="OUTLINER_COLLECTION")
        layout.prop(self, "export_dir")
        out = self._resolve_export_dir()
        layout.label(text=f"Output: {out}", icon="FILE_FOLDER")

    def invoke(self, context, event):
        col = context.collection
        if col and col != context.scene.collection:
            self.collection_name = col.name

        if not self.export_dir and bpy.data.filepath:
            self.export_dir = os.path.dirname(bpy.data.filepath)

        return context.window_manager.invoke_props_dialog(self, width=450)
