"""
Shared helpers for Decentraland scene limit calculations and usage counting.
Used by scene_limitations.py and validate_scene.py.
"""

import math

import bpy
import mathutils


def calculate_limits(parcel_count):
    """Calculate Decentraland scene limits based on parcel count.

    Returns a dict with keys: triangles, entities, bodies, materials,
    textures, height, total_file_size_mb, max_file_size_mb, file_count.
    """
    n = parcel_count
    log_factor = math.log2(n + 1)

    if n <= 20:
        total_file_size_mb = n * 15
        max_file_size_mb = min(50, total_file_size_mb)
    else:
        total_file_size_mb = 300
        max_file_size_mb = 50

    return {
        "triangles": n * 10000,
        "entities": n * 200,
        "bodies": n * 300,
        "materials": int(log_factor * 20),
        "textures": int(log_factor * 10),
        "height": int(log_factor * 20),
        "total_file_size_mb": total_file_size_mb,
        "max_file_size_mb": max_file_size_mb,
        "file_count": n * 200,
    }


def _is_internal_image(img):
    """Return True for Blender-internal images that aren't real textures."""
    return img.name.startswith("Render Result") or img.name.startswith("Viewer Node")


def count_current_usage():
    """Count current scene usage against Decentraland limits.

    Returns a dict with keys: triangles, entities, bodies, materials,
    textures, height.
    """
    triangle_count = 0
    entity_count = 0
    body_count = 0

    for obj in bpy.data.objects:
        is_mesh = obj.type == "MESH" and obj.data
        visible = not obj.hide_viewport

        if is_mesh:
            mesh = obj.data
            mesh.calc_loop_triangles()
            triangle_count += len(mesh.loop_triangles)

        if obj.type in {"MESH", "EMPTY", "LIGHT", "CAMERA"} and visible:
            entity_count += 1

        if is_mesh and visible:
            body_count += 1

    material_count = len(bpy.data.materials)

    texture_count = len(
        [img for img in bpy.data.images if not _is_internal_image(img)]
    )

    max_height = 0.0
    for obj in bpy.data.objects:
        if (
            obj.type == "MESH"
            and not obj.hide_viewport
            and obj.data
            and len(obj.users_collection) > 0
        ):
            bbox_corners = [
                obj.matrix_world @ mathutils.Vector(c) for c in obj.bound_box
            ]
            highest_z = max(corner.z for corner in bbox_corners)
            if highest_z >= 0:
                max_height = max(max_height, highest_z)

    return {
        "triangles": triangle_count,
        "entities": entity_count,
        "bodies": body_count,
        "materials": material_count,
        "textures": texture_count,
        "height": int(max_height),
    }


def usage_percentage(current, limit):
    """Return usage as a formatted percentage string, or 'N/A'."""
    if limit == 0:
        return "N/A"
    return f"{(current / limit) * 100:.1f}"


def status_icon(percentage_str):
    """Return a Blender icon name based on a percentage string."""
    if percentage_str == "N/A":
        return "INFO"
    pct = float(percentage_str)
    if pct >= 100:
        return "ERROR"
    elif pct >= 80:
        return "WARNING"
    return "CHECKMARK"
