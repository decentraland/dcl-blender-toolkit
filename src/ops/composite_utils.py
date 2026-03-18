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


MANAGED_COMPONENTS = {"core::Transform", "core::GltfContainer", "core-schema::Name"}

# Custom property key used to store the DCL entity ID on Blender objects
ENTITY_ID_PROP = "dcl_entity_id"


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


def merge_composite(existing, entities_data):
    """Merge updated entity data into an existing composite, preserving unknown components.

    *existing* is the full composite dict loaded from disk.
    *entities_data* is the same format as ``build_composite`` accepts.

    Returns a new composite dict where:
      - ``core::Transform``, ``core::GltfContainer``, ``core-schema::Name`` are
        updated for entities in *entities_data*
      - All other components (scripts, pointer events, etc.) are kept as-is
      - Entities not in *entities_data* are kept unchanged in all components
    """
    # Build lookup of new entity data keyed by entity ID string
    new_transform = {}
    new_gltf = {}
    new_name = {}
    for ent in entities_data:
        eid = str(ent["entity_id"])
        new_transform[eid] = {"json": ent["transform"]}
        new_gltf[eid] = {"json": {"src": ent["gltf_src"]}}
        new_name[eid] = {"json": {"value": ent["name"]}}

    new_managed = {
        "core::Transform": (_TRANSFORM_SCHEMA, new_transform),
        "core::GltfContainer": (_GLTF_CONTAINER_SCHEMA, new_gltf),
        "core-schema::Name": (_NAME_SCHEMA, new_name),
    }

    result_components = []
    seen_managed = set()

    for comp in existing.get("components", []):
        cname = comp["name"]
        if cname in MANAGED_COMPONENTS:
            # Merge: start from existing data, overlay with new
            seen_managed.add(cname)
            schema, new_data = new_managed[cname]
            merged_data = dict(comp.get("data", {}))
            merged_data.update(new_data)
            result_components.append(
                {
                    "name": cname,
                    "jsonSchema": schema,
                    "data": merged_data,
                }
            )
        else:
            # Preserve unknown components untouched
            result_components.append(comp)

    # Add any managed components that weren't in the existing composite
    for cname in ("core::Transform", "core::GltfContainer", "core-schema::Name"):
        if cname not in seen_managed:
            schema, new_data = new_managed[cname]
            result_components.append(
                {
                    "name": cname,
                    "jsonSchema": schema,
                    "data": new_data,
                }
            )

    return {
        "version": existing.get("version", COMPOSITE_VERSION),
        "components": result_components,
    }
