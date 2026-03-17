"""Shared coordinate conversion and composite format helpers.

No ``bpy`` dependency so this module can be tested standalone.
"""

import re

COMPOSITE_VERSION = 1
FIRST_ENTITY_ID = 512

# ---------------------------------------------------------------------------
# Coordinate conversions  (Blender Z-up ↔ DCL Y-up)
# ---------------------------------------------------------------------------


def blender_pos_to_dcl(vec):
    """Blender position → DCL position dict."""
    return {"x": -vec[0], "y": vec[2], "z": -vec[1]}


def dcl_pos_to_blender(pos):
    """DCL position dict → Blender (x, y, z) tuple."""
    return (-pos["x"], -pos["z"], pos["y"])


def blender_quat_to_dcl(q):
    """Blender quaternion (w,x,y,z) → DCL rotation dict."""
    return {"x": -q[1], "y": q[3], "z": -q[2], "w": q[0]}


def dcl_quat_to_blender(r):
    """DCL rotation dict → Blender (w, x, y, z) tuple."""
    return (r["w"], -r["x"], -r["z"], r["y"])


def blender_scale_to_dcl(s):
    """Blender scale → DCL scale dict (axis swap, no sign flip)."""
    return {"x": s[0], "y": s[2], "z": s[1]}


def dcl_scale_to_blender(s):
    """DCL scale dict → Blender (x, y, z) tuple."""
    return (s["x"], s["z"], s["y"])


# ---------------------------------------------------------------------------
# Filename sanitisation
# ---------------------------------------------------------------------------

_UNSAFE_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')


def sanitize_filename(name):
    """Return a filesystem-safe version of *name*."""
    safe = _UNSAFE_RE.sub("_", name).strip(". ")
    return safe or "unnamed"


# ---------------------------------------------------------------------------
# Composite JSON builder
# ---------------------------------------------------------------------------

_TRANSFORM_SCHEMA = {
    "type": "object",
    "properties": {
        "position": {
            "type": "object",
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"},
                "z": {"type": "number"},
            },
        },
        "scale": {
            "type": "object",
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"},
                "z": {"type": "number"},
            },
        },
        "rotation": {
            "type": "object",
            "properties": {
                "x": {"type": "number"},
                "y": {"type": "number"},
                "z": {"type": "number"},
                "w": {"type": "number"},
            },
        },
        "parent": {"type": "integer"},
    },
    "serializationType": "transform",
}

_GLTF_CONTAINER_SCHEMA = {
    "type": "object",
    "properties": {},
    "serializationType": "protocol-buffer",
    "protocolBuffer": "PBGltfContainer",
}

_NAME_SCHEMA = {
    "type": "object",
    "properties": {
        "value": {
            "type": "string",
            "serializationType": "utf8-string",
        },
    },
    "serializationType": "map",
}


def build_composite(entities_data):
    """Build a complete composite dict from a list of entity dicts.

    Each entry in *entities_data* must have:
      - ``entity_id``: int
      - ``transform``: dict with position/rotation/scale/parent
      - ``gltf_src``: str  (e.g. ``"assets/models/Cube.glb"``)
      - ``name``: str
    """
    transform_data = {}
    gltf_data = {}
    name_data = {}

    for ent in entities_data:
        eid = str(ent["entity_id"])
        transform_data[eid] = {"json": ent["transform"]}
        gltf_data[eid] = {"json": {"src": ent["gltf_src"]}}
        name_data[eid] = {"json": {"value": ent["name"]}}

    return {
        "version": COMPOSITE_VERSION,
        "components": [
            {
                "name": "core::Transform",
                "jsonSchema": _TRANSFORM_SCHEMA,
                "data": transform_data,
            },
            {
                "name": "core::GltfContainer",
                "jsonSchema": _GLTF_CONTAINER_SCHEMA,
                "data": gltf_data,
            },
            {
                "name": "core-schema::Name",
                "jsonSchema": _NAME_SCHEMA,
                "data": name_data,
            },
        ],
    }
