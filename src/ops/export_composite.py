"""Export Decentraland Composite – exports individual GLBs + main.composite."""

import json
import os
import struct

import bpy

from .composite_utils import (
    ENTITY_ID_PROP,
    FIRST_ENTITY_ID,
    build_composite,
    merge_composite,
    sanitize_filename,
)


class OBJECT_OT_export_composite(bpy.types.Operator):
    bl_idname = "object.export_composite"
    bl_label = "Export Composite"
    bl_description = "Export scene objects as individual GLBs with a Decentraland main.composite"
    bl_options = {"REGISTER", "UNDO"}

    scene_dir: bpy.props.StringProperty(
        name="Scene Directory",
        description="Root directory of the Decentraland scene project",
        default="",
        subtype="DIR_PATH",
    )

    scene_title: bpy.props.StringProperty(
        name="Scene Title",
        description="Display title for scene.json",
        default="My Scene",
    )

    export_hidden: bpy.props.BoolProperty(
        name="Include Hidden",
        description="Export hidden objects as well",
        default=False,
    )

    overwrite_scene_json: bpy.props.BoolProperty(
        name="Overwrite scene.json",
        description="Overwrite scene.json even if it already exists",
        default=False,
    )

    # ------------------------------------------------------------------

    def _resolve_scene_dir(self):
        raw = self.scene_dir.strip()
        if raw:
            return os.path.normpath(bpy.path.abspath(raw))
        if bpy.data.filepath:
            return os.path.dirname(bpy.data.filepath)
        return os.path.join(os.path.expanduser("~"), "Desktop", "dcl_scene")

    def _collect_objects(self, context):
        """Return mesh objects sorted by name."""
        objs = []
        for obj in context.scene.objects:
            if obj.type != "MESH":
                continue
            if not self.export_hidden and not obj.visible_get():
                continue
            objs.append(obj)
        objs.sort(key=lambda o: o.name)
        return objs

    @staticmethod
    def _center_glb_vertices(filepath):
        """Shift GLB vertex positions to center at origin, return the center.

        Reads the GLB binary, computes the overall bounds center across ALL
        primitives, subtracts it from every vertex position in every primitive,
        updates the accessor min/max, and writes the file back.

        Returns the center as ``[x, y, z]`` in glTF Y-up space (ready for
        use as the composite position).
        """
        with open(filepath, "rb") as f:
            header = f.read(12)
            json_hdr = f.read(8)
            json_len = struct.unpack("<I", json_hdr[:4])[0]
            json_bytes = f.read(json_len)
            bin_hdr = f.read(8)
            bin_len = struct.unpack("<I", bin_hdr[:4])[0]
            bin_data = bytearray(f.read(bin_len))

        data = json.loads(json_bytes)

        # Strip any node transform
        for node in data.get("nodes", []):
            node.pop("translation", None)
            node.pop("rotation", None)
            node.pop("scale", None)

        # Collect ALL position accessors across all primitives
        pos_accessors = []
        for mesh in data.get("meshes", []):
            for prim in mesh.get("primitives", []):
                idx = prim.get("attributes", {}).get("POSITION")
                if idx is not None:
                    pos_accessors.append(data["accessors"][idx])

        if not pos_accessors:
            return [0, 0, 0]

        # Compute overall bounds center across all primitives
        global_min = [float("inf")] * 3
        global_max = [float("-inf")] * 3
        for acc in pos_accessors:
            mn = acc.get("min", [0, 0, 0])
            mx = acc.get("max", [0, 0, 0])
            for i in range(3):
                global_min[i] = min(global_min[i], mn[i])
                global_max[i] = max(global_max[i], mx[i])

        cx = (global_min[0] + global_max[0]) / 2
        cy = (global_min[1] + global_max[1]) / 2
        cz = (global_min[2] + global_max[2]) / 2

        # Subtract center from vertex positions in ALL primitives
        for acc in pos_accessors:
            bv = data["bufferViews"][acc["bufferView"]]
            acc_offset = bv.get("byteOffset", 0) + acc.get("byteOffset", 0)
            count = acc["count"]
            stride = bv.get("byteStride", 12)

            for i in range(count):
                off = acc_offset + i * stride
                x, y, z = struct.unpack_from("<fff", bin_data, off)
                struct.pack_into("<fff", bin_data, off, x - cx, y - cy, z - cz)

            # Update this accessor's min/max
            mn = acc.get("min", [0, 0, 0])
            mx = acc.get("max", [0, 0, 0])
            acc["min"] = [mn[0] - cx, mn[1] - cy, mn[2] - cz]
            acc["max"] = [mx[0] - cx, mx[1] - cy, mx[2] - cz]

        # Write modified GLB
        new_json = json.dumps(data, separators=(",", ":")).encode("utf-8")
        while len(new_json) % 4 != 0:
            new_json += b" "

        with open(filepath, "wb") as f:
            total = 12 + 8 + len(new_json) + 8 + len(bin_data)
            f.write(struct.pack("<III", 0x46546C67, 2, total))
            f.write(struct.pack("<II", len(new_json), 0x4E4F534A))
            f.write(new_json)
            f.write(struct.pack("<II", len(bin_data), 0x004E4942))
            f.write(bin_data)

        return [cx, cy, cz]

    def _export_glb(self, context, obj, filepath):
        """Export a single object as GLB with all transforms baked, then centered.

        1. Creates a temporary copy, applies ALL transforms to mesh data
        2. Exports via glTF (vertices at world positions)
        3. Post-processes the GLB binary to center vertices at origin
        4. Stores the center as the composite position
        """
        prev_selected = list(context.selected_objects)
        prev_active = context.view_layer.objects.active

        # Create a temporary copy with its own mesh data
        temp_obj = obj.copy()
        temp_obj.data = obj.data.copy()
        context.scene.collection.objects.link(temp_obj)

        # Set world transform from original, clear parent
        temp_obj.parent = None
        temp_obj.matrix_world = obj.matrix_world.copy()

        try:
            for o in prev_selected:
                o.select_set(False)
            obj.select_set(False)
            temp_obj.select_set(True)
            context.view_layer.objects.active = temp_obj

            # Bake ALL transforms into vertices (world positions)
            bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

            # Export
            bpy.ops.export_scene.gltf(
                filepath=filepath,
                export_format="GLB",
                use_selection=True,
                export_apply=True,
                export_yup=True,
            )

            # Post-process: center vertices at origin, capture center for composite
            self._last_glb_center = self._center_glb_vertices(filepath)
        finally:
            bpy.data.objects.remove(temp_obj, do_unlink=True)

            for o in prev_selected:
                if o.name in context.scene.objects:
                    o.select_set(True)
            if prev_active and prev_active.name in context.scene.objects:
                context.view_layer.objects.active = prev_active

    def _unique_filename(self, models_dir, base_name, used):
        """Return a unique GLB filename inside *models_dir*."""
        candidate = base_name
        counter = 1
        while candidate in used:
            candidate = f"{base_name}_{counter:03d}"
            counter += 1
        used.add(candidate)
        return candidate + ".glb"

    def _center_in_parcels(self, scene_dir, entities_data):
        """Offset root entity positions so content is centered in the parcel grid.

        Only called on fresh exports (no existing composite). Reads the parcel
        layout from scene.json to determine the grid center, then shifts all
        root entities (parent==0) so the content bounding box is centered.
        """
        # Read parcel layout from scene.json if it exists
        scene_json_path = os.path.join(scene_dir, "scene.json")
        parcels = [(0, 0)]
        if os.path.isfile(scene_json_path):
            try:
                with open(scene_json_path) as f:
                    sj = json.load(f)
                raw_parcels = sj.get("scene", {}).get("parcels", ["0,0"])
                parcels = []
                for p in raw_parcels:
                    if isinstance(p, str):
                        x, y = p.split(",")
                        parcels.append((int(x), int(y)))
                    elif isinstance(p, dict):
                        parcels.append((p.get("x", 0), p.get("y", 0)))
            except (json.JSONDecodeError, OSError, ValueError):
                parcels = [(0, 0)]

        if not parcels:
            return

        # Parcel grid center in DCL world coords (each parcel = 16m)
        min_px = min(p[0] for p in parcels)
        max_px = max(p[0] for p in parcels)
        min_pz = min(p[1] for p in parcels)
        max_pz = max(p[1] for p in parcels)
        grid_center_x = (min_px + max_px + 1) * 16 / 2
        grid_center_z = (min_pz + max_pz + 1) * 16 / 2

        # Content bounding box center (DCL coords, root entities only)
        root_positions = [ent["transform"]["position"] for ent in entities_data if ent["transform"]["parent"] == 0]
        if not root_positions:
            return

        content_min_x = min(p["x"] for p in root_positions)
        content_max_x = max(p["x"] for p in root_positions)
        content_min_z = min(p["z"] for p in root_positions)
        content_max_z = max(p["z"] for p in root_positions)
        content_center_x = (content_min_x + content_max_x) / 2
        content_center_z = (content_min_z + content_max_z) / 2

        # Offset to apply
        offset_x = grid_center_x - content_center_x
        offset_z = grid_center_z - content_center_z

        # Apply offset to root entities only (children use local coords)
        for ent in entities_data:
            if ent["transform"]["parent"] == 0:
                ent["transform"]["position"]["x"] += offset_x
                ent["transform"]["position"]["z"] += offset_z

    def _build_entity_map(self, objects):
        """Build ``{obj.name: entity_id}`` reusing stored IDs when available."""
        entity_map = {}
        used_ids = set()

        # First pass: collect objects that already have an entity ID
        for obj in objects:
            stored = obj.get(ENTITY_ID_PROP)
            if stored is not None:
                eid = int(stored)
                entity_map[obj.name] = eid
                used_ids.add(eid)

        # Second pass: assign new IDs to objects without one
        next_id = FIRST_ENTITY_ID
        for obj in objects:
            if obj.name in entity_map:
                continue
            while next_id in used_ids:
                next_id += 1
            entity_map[obj.name] = next_id
            used_ids.add(next_id)
            next_id += 1

        return entity_map

    def execute(self, context):
        scene_dir = self._resolve_scene_dir()
        models_dir = os.path.join(scene_dir, "assets", "models")
        composite_dir = os.path.join(scene_dir, "assets", "scene")
        os.makedirs(models_dir, exist_ok=True)
        os.makedirs(composite_dir, exist_ok=True)

        objects = self._collect_objects(context)
        if not objects:
            self.report({"WARNING"}, "No mesh objects to export.")
            return {"CANCELLED"}

        # Build entity ID map, reusing stored IDs from prior imports
        entity_map = self._build_entity_map(objects)

        # Load existing composite for merging (preserves unknown components)
        composite_path = os.path.join(composite_dir, "main.composite")
        existing_composite = None
        if os.path.isfile(composite_path):
            try:
                with open(composite_path) as f:
                    existing_composite = json.load(f)
            except (json.JSONDecodeError, OSError):
                existing_composite = None

        used_filenames = set()
        entities_data = []

        for obj in objects:
            eid = entity_map[obj.name]
            safe_name = sanitize_filename(obj.name)
            glb_name = self._unique_filename(models_dir, safe_name, used_filenames)
            glb_path = os.path.join(models_dir, glb_name)

            self._export_glb(context, obj, glb_path)

            # Position is the geometry bounds center (in glTF Y-up space),
            # captured during GLB post-processing.
            # Rotation and scale are baked into the GLB vertices.
            parent_eid = 0
            if obj.parent and obj.parent.name in entity_map:
                parent_eid = entity_map[obj.parent.name]

            c = self._last_glb_center
            transform = {
                "position": {"x": c[0], "y": c[1], "z": c[2]},
                "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
                "scale": {"x": 1, "y": 1, "z": 1},
                "parent": parent_eid,
            }

            entities_data.append(
                {
                    "entity_id": eid,
                    "transform": transform,
                    "gltf_src": f"assets/models/{glb_name}",
                    "name": obj.name,
                }
            )

            # Store entity ID on the Blender object for future re-exports
            obj[ENTITY_ID_PROP] = eid

        # Write main.composite — merge if existing, build fresh otherwise
        if existing_composite:
            composite = merge_composite(existing_composite, entities_data)
        else:
            composite = build_composite(entities_data)
        with open(composite_path, "w") as f:
            json.dump(composite, f, indent=2)

        # Write scene.json
        scene_json_path = os.path.join(scene_dir, "scene.json")
        if not os.path.exists(scene_json_path) or self.overwrite_scene_json:
            scene_json = {
                "ecs7": True,
                "runtimeVersion": "7",
                "display": {"title": self.scene_title},
                "main": "bin/index.js",
                "scene": {"parcels": ["0,0"], "base": "0,0"},
            }
            with open(scene_json_path, "w") as f:
                json.dump(scene_json, f, indent=2)

        self.report({"INFO"}, f"Exported {len(entities_data)} entities to {composite_path}")
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "scene_dir")
        layout.prop(self, "scene_title")
        layout.separator()
        layout.prop(self, "export_hidden")
        layout.prop(self, "overwrite_scene_json")
        layout.separator()
        out = self._resolve_scene_dir()
        layout.label(text=f"Output: {out}/assets/scene/main.composite", icon="FILE")

    def invoke(self, context, event):
        if not self.scene_dir and bpy.data.filepath:
            self.scene_dir = os.path.dirname(bpy.data.filepath) + os.sep
        return context.window_manager.invoke_props_dialog(self, width=500)
