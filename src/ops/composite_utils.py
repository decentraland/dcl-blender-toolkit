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
    """Blender position → DCL position dict (Z-up → Y-up axis swap)."""
    return {"x": vec[0], "y": vec[2], "z": vec[1]}


def dcl_pos_to_blender(pos):
    """DCL position dict → Blender (x, y, z) tuple."""
    return (pos["x"], pos["z"], pos["y"])


def blender_quat_to_dcl(q):
    """Blender quaternion (w,x,y,z) → DCL rotation dict (Z-up → Y-up axis swap)."""
    return {"x": q[1], "y": q[3], "z": q[2], "w": q[0]}


def dcl_quat_to_blender(r):
    """DCL rotation dict → Blender (w, x, y, z) tuple."""
    return (r["w"], r["x"], r["z"], r["y"])


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


MANAGED_COMPONENTS = {"core::Transform", "core::GltfContainer", "core-schema::Name", "inspector::Nodes"}

_NODES_SCHEMA = {
    "type": "object",
    "properties": {
        "value": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "entity": {"type": "integer", "serializationType": "entity"},
                    "open": {
                        "type": "boolean",
                        "serializationType": "optional",
                        "optionalJsonSchema": {"type": "boolean", "serializationType": "boolean"},
                    },
                    "children": {
                        "type": "array",
                        "items": {"type": "integer", "serializationType": "entity"},
                        "serializationType": "array",
                    },
                },
                "serializationType": "map",
            },
            "serializationType": "array",
        },
    },
    "serializationType": "map",
}

# Custom property key used to store the DCL entity ID on Blender objects
ENTITY_ID_PROP = "dcl_entity_id"


def _build_nodes_data(entity_ids):
    """Build ``inspector::Nodes`` data so all entities appear in the Inspector tree."""
    # Root node (entity 0) has all top-level entities as children
    nodes = [{"entity": 0, "open": True, "children": sorted(entity_ids)}]
    # Each entity gets a leaf node
    for eid in sorted(entity_ids):
        nodes.append({"entity": eid, "children": []})
    # Standard system entities
    nodes.append({"entity": 1, "children": []})
    nodes.append({"entity": 2, "children": []})
    return {"0": {"json": {"value": nodes}}}


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

    entity_ids = [ent["entity_id"] for ent in entities_data]

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
            {
                "name": "inspector::Nodes",
                "jsonSchema": _NODES_SCHEMA,
                "data": _build_nodes_data(entity_ids),
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

    # Collect all entity IDs for the Nodes tree: new entities + existing ones from Transform
    all_entity_ids = {ent["entity_id"] for ent in entities_data}
    for comp in existing.get("components", []):
        if comp["name"] == "core::Transform":
            for eid_str in comp.get("data", {}):
                all_entity_ids.add(int(eid_str))

    new_managed = {
        "core::Transform": (_TRANSFORM_SCHEMA, new_transform),
        "core::GltfContainer": (_GLTF_CONTAINER_SCHEMA, new_gltf),
        "core-schema::Name": (_NAME_SCHEMA, new_name),
        "inspector::Nodes": (_NODES_SCHEMA, _build_nodes_data(all_entity_ids)),
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
    for cname in ("core::Transform", "core::GltfContainer", "core-schema::Name", "inspector::Nodes"):
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
