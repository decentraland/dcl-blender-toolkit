import math
import os

import bpy
from mathutils import Vector


def _get_active_mesh(context):
    obj = context.active_object
    if obj and obj.type == "MESH":
        return obj
    return None


def _get_object_bounds(obj):
    corners = [obj.matrix_world @ Vector(corner) for corner in obj.bound_box]
    min_corner = Vector(
        (
            min(c.x for c in corners),
            min(c.y for c in corners),
            min(c.z for c in corners),
        )
    )
    max_corner = Vector(
        (
            max(c.x for c in corners),
            max(c.y for c in corners),
            max(c.z for c in corners),
        )
    )
    center = (min_corner + max_corner) * 0.5
    size = max((max_corner - min_corner).length, 0.2)
    return center, size


def _set_track_to(obj, target):
    track = None
    for c in obj.constraints:
        if c.type == "TRACK_TO" and c.name == "DCL_ThumbnailTrack":
            track = c
            break
    if track is None:
        track = obj.constraints.new(type="TRACK_TO")
        track.name = "DCL_ThumbnailTrack"
    track.target = target
    track.track_axis = "TRACK_NEGATIVE_Z"
    track.up_axis = "UP_Y"


def _ensure_thumbnail_target(context, center):
    props = context.scene.dcl_tools
    target = bpy.data.objects.get(props.thumbnail_target_name) if props.thumbnail_target_name else None

    if not target:
        target = bpy.data.objects.new("DCL_Thumbnail_Target", None)
        target.empty_display_size = 0.15
        target.empty_display_type = "PLAIN_AXES"
        target["dcl_thumbnail_target"] = True
        context.scene.collection.objects.link(target)
        props.thumbnail_target_name = target.name

    target.location = center
    return target


def apply_thumbnail_camera_controls(context):
    props = context.scene.dcl_tools
    cam = bpy.data.objects.get(props.thumbnail_camera_name) if props.thumbnail_camera_name else None
    target = bpy.data.objects.get(props.thumbnail_target_name) if props.thumbnail_target_name else None
    if not cam or not target:
        return False

    base_dist = max(props.thumbnail_camera_base_distance, 0.08)
    angle = math.radians(props.thumbnail_camera_rotate)
    radial = Vector((math.cos(angle), math.sin(angle), 0.0)) * base_dist
    lateral = Vector((-math.sin(angle), math.cos(angle), 0.0)) * props.thumbnail_camera_side
    vertical = Vector((0.0, 0.0, (base_dist * 0.55) + props.thumbnail_camera_up))
    raw_offset = radial + lateral + vertical
    if raw_offset.length < 1e-6:
        raw_offset = Vector((0.0, -1.0, 0.6))
    zoomed_distance = max(raw_offset.length * props.thumbnail_camera_zoom, 0.08)
    cam.location = target.location + raw_offset.normalized() * zoomed_distance
    _set_track_to(cam, target)
    return True


def _get_thumbnail_lights():
    lights = []
    for obj in bpy.data.objects:
        if obj.type == "LIGHT" and obj.get("dcl_thumbnail_light"):
            lights.append(obj)
    lights.sort(key=lambda x: int(x.get("dcl_thumbnail_light_index", 0)))
    return lights


def _get_scene_lights(context):
    return [obj for obj in context.scene.objects if obj.type == "LIGHT" and not obj.hide_render]


def _resolve_render_camera(context):
    props = context.scene.dcl_tools

    cam = bpy.data.objects.get(props.thumbnail_camera_name) if props.thumbnail_camera_name else None
    if cam and cam.type == "CAMERA":
        return cam

    scene_cam = context.scene.camera
    if scene_cam and scene_cam.type == "CAMERA":
        props.thumbnail_camera_name = scene_cam.name
        return scene_cam

    active = context.active_object
    if active and active.type == "CAMERA":
        props.thumbnail_camera_name = active.name
        return active

    first_scene_cam = next((obj for obj in context.scene.objects if obj.type == "CAMERA"), None)
    if first_scene_cam:
        props.thumbnail_camera_name = first_scene_cam.name
    return first_scene_cam


def _resolve_render_lights(context):
    tagged = _get_thumbnail_lights()
    if tagged:
        return tagged
    return _get_scene_lights(context)


def _switch_to_camera_view(context, camera_obj):
    # Switch every visible 3D viewport to camera view when possible.
    wm = context.window_manager
    for window in wm.windows:
        screen = window.screen
        if not screen:
            continue
        for area in screen.areas:
            if area.type != "VIEW_3D":
                continue
            for space in area.spaces:
                if space.type == "VIEW_3D":
                    if hasattr(space, "camera"):
                        space.camera = camera_obj
                    region_3d = getattr(space, "region_3d", None)
                    if region_3d:
                        region_3d.view_perspective = "CAMERA"


def _new_thumbnail_light(context, index, target):
    light_data = bpy.data.lights.new(name=f"DCL_Thumbnail_Area_{index + 1}", type="AREA")
    light_obj = bpy.data.objects.new(light_data.name, light_data)
    light_obj["dcl_thumbnail_light"] = True
    light_obj["dcl_thumbnail_light_index"] = index
    context.scene.collection.objects.link(light_obj)
    _set_track_to(light_obj, target)
    return light_obj


def apply_thumbnail_lighting_controls(context):
    props = context.scene.dcl_tools
    target = bpy.data.objects.get(props.thumbnail_target_name) if props.thumbnail_target_name else None
    if not target:
        return False

    lights = _get_thumbnail_lights()
    desired_count = max(1, int(props.thumbnail_light_count))

    if len(lights) < desired_count:
        for index in range(len(lights), desired_count):
            lights.append(_new_thumbnail_light(context, index, target))
    elif len(lights) > desired_count:
        for light in lights[desired_count:]:
            bpy.data.objects.remove(light, do_unlink=True)
        lights = lights[:desired_count]

    distance = max(props.thumbnail_light_distance, 0.1)
    height = props.thumbnail_light_height
    strength = max(props.thumbnail_light_strength, 0.0)

    for index, light in enumerate(lights):
        light["dcl_thumbnail_light_index"] = index
        angle = (math.pi * 2.0 * index) / desired_count
        light.location = target.location + Vector((math.cos(angle) * distance, math.sin(angle) * distance, height))
        _set_track_to(light, target)
        light.hide_viewport = False
        light.hide_render = False

        if light.data:
            light.data.energy = strength
            light.data.shape = "RECTANGLE"
            light.data.size = max(distance * 0.45, 0.2)
            light.data.size_y = max(distance * 0.25, 0.1)

    return True


def _on_thumbnail_camera_property_update(self, context):
    if context and context.scene and hasattr(context.scene, "dcl_tools"):
        apply_thumbnail_camera_controls(context)


def _on_thumbnail_lighting_property_update(self, context):
    if context and context.scene and hasattr(context.scene, "dcl_tools"):
        apply_thumbnail_lighting_controls(context)


def _on_thumbnail_transparent_background_update(self, context):
    if context and context.scene:
        context.scene.render.film_transparent = bool(self.thumbnail_transparent_background)


def apply_thumbnail_output_resolution(context):
    if not context or not context.scene or not hasattr(context.scene, "dcl_tools"):
        return
    scene = context.scene
    props = scene.dcl_tools
    if props.thumbnail_resolution_preset == "CUSTOM":
        scene.render.resolution_x = int(props.thumbnail_resolution_x)
        scene.render.resolution_y = int(props.thumbnail_resolution_y)
    else:
        size = int(props.thumbnail_resolution_preset)
        scene.render.resolution_x = size
        scene.render.resolution_y = size


def _on_thumbnail_resolution_update(self, context):
    apply_thumbnail_output_resolution(context)


class OBJECT_OT_add_thumbnail_camera(bpy.types.Operator):
    bl_idname = "object.add_thumbnail_camera"
    bl_label = "Add Thumbnail Camera"
    bl_description = "Create a thumbnail camera aimed at the active mesh"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        active_mesh = _get_active_mesh(context)
        if not active_mesh:
            self.report({"WARNING"}, "Select a mesh object first")
            return {"CANCELLED"}

        props = context.scene.dcl_tools
        center, size = _get_object_bounds(active_mesh)
        target = _ensure_thumbnail_target(context, center)

        cam_data = bpy.data.cameras.new("DCL_Thumbnail_Camera")
        cam_data.lens = 55
        cam_obj = bpy.data.objects.new(cam_data.name, cam_data)
        cam_obj["dcl_thumbnail_camera"] = True
        context.scene.collection.objects.link(cam_obj)

        props.thumbnail_camera_name = cam_obj.name
        props.thumbnail_camera_base_distance = max(size * 1.8, 1.8)
        props.thumbnail_camera_zoom = 1.0
        props.thumbnail_camera_rotate = -90.0
        props.thumbnail_camera_side = 0.0
        props.thumbnail_camera_up = 0.0
        props.thumbnail_camera_controls_expanded = True

        context.scene.camera = cam_obj
        context.scene.render.film_transparent = bool(props.thumbnail_transparent_background)
        apply_thumbnail_camera_controls(context)
        apply_thumbnail_output_resolution(context)
        _set_track_to(cam_obj, target)
        _switch_to_camera_view(context, cam_obj)
        if context and context.area:
            context.area.tag_redraw()

        self.report({"INFO"}, "Thumbnail camera created and aimed at active mesh")
        return {"FINISHED"}


class OBJECT_OT_add_thumbnail_lighting(bpy.types.Operator):
    bl_idname = "object.add_thumbnail_lighting"
    bl_label = "Add Thumbnail Lighting"
    bl_description = "Create an even area-light rig around the active mesh"
    bl_options = {"REGISTER", "UNDO"}

    def execute(self, context):
        active_mesh = _get_active_mesh(context)
        if not active_mesh:
            self.report({"WARNING"}, "Select a mesh object first")
            return {"CANCELLED"}

        props = context.scene.dcl_tools
        center, size = _get_object_bounds(active_mesh)
        _ensure_thumbnail_target(context, center)

        if props.thumbnail_light_distance <= 0.2:
            props.thumbnail_light_distance = max(size * 1.6, 1.6)
        if props.thumbnail_light_height == 0.0:
            props.thumbnail_light_height = size * 0.45
        props.thumbnail_lighting_controls_expanded = True

        apply_thumbnail_lighting_controls(context)
        if context and context.area:
            context.area.tag_redraw()
        self.report({"INFO"}, f"Thumbnail lighting rig generated ({props.thumbnail_light_count} lights)")
        return {"FINISHED"}


class OBJECT_OT_render_thumbnail(bpy.types.Operator):
    bl_idname = "object.render_thumbnail"
    bl_label = "Render Thumbnail"
    bl_description = "Render thumbnail image and save as compressed PNG"
    bl_options = {"REGISTER"}

    filepath: bpy.props.StringProperty(
        name="File Path",
        description="Destination thumbnail image path",
        default="",
        subtype="FILE_PATH",
    )

    @classmethod
    def poll(cls, context):
        return context.scene is not None

    def _validate_thumbnail_setup(self, context):
        cam = _resolve_render_camera(context)
        if not cam:
            self.report({"WARNING"}, "Add Camera before rendering a thumbnail")
            return False

        lights = _resolve_render_lights(context)
        if not lights:
            self.report({"WARNING"}, "Add Lighting before rendering a thumbnail")
            return False
        return True

    def execute(self, context):
        scene = context.scene
        props = scene.dcl_tools

        if not self._validate_thumbnail_setup(context):
            return {"CANCELLED"}

        render_cam = _resolve_render_camera(context)
        if render_cam:
            scene.camera = render_cam

        out_path = self.filepath.strip()
        if not out_path:
            self.report({"ERROR"}, "Choose a destination path")
            return {"CANCELLED"}
        if not out_path.lower().endswith(".png"):
            out_path += ".png"

        out_dir = os.path.dirname(out_path)
        if out_dir:
            os.makedirs(out_dir, exist_ok=True)

        original_engine = scene.render.engine
        original_filepath = scene.render.filepath
        original_format = scene.render.image_settings.file_format
        original_color = scene.render.image_settings.color_mode
        original_compression = scene.render.image_settings.compression

        try:
            if props.thumbnail_render_engine == "EEVEE":
                engine_items = {item.identifier for item in scene.render.bl_rna.properties["engine"].enum_items}
                if "BLENDER_EEVEE_NEXT" in engine_items:
                    scene.render.engine = "BLENDER_EEVEE_NEXT"
                elif "BLENDER_EEVEE" in engine_items:
                    scene.render.engine = "BLENDER_EEVEE"
                else:
                    self.report({"ERROR"}, "Eevee render engine is not available in this Blender build")
                    return {"CANCELLED"}
            else:
                scene.render.engine = "CYCLES"

            scene.render.film_transparent = props.thumbnail_transparent_background
            scene.render.image_settings.file_format = "PNG"
            scene.render.image_settings.color_mode = "RGBA" if props.thumbnail_transparent_background else "RGB"
            scene.render.image_settings.compression = int(props.thumbnail_png_compression)
            apply_thumbnail_output_resolution(context)
            scene.render.filepath = out_path

            bpy.ops.render.render(write_still=True)
        except Exception as exc:
            self.report({"ERROR"}, f"Render failed: {exc}")
            return {"CANCELLED"}
        finally:
            scene.render.engine = original_engine
            scene.render.filepath = original_filepath
            scene.render.image_settings.file_format = original_format
            scene.render.image_settings.color_mode = original_color
            scene.render.image_settings.compression = original_compression

        self.report({"INFO"}, f"Thumbnail rendered to: {out_path}")
        return {"FINISHED"}

    def invoke(self, context, event):
        if not self._validate_thumbnail_setup(context):
            return {"CANCELLED"}
        if not self.filepath:
            base_dir = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.path.expanduser("~/Desktop")
            self.filepath = os.path.join(base_dir, "Thumbnail.png")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}
