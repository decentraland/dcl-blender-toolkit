"""Import Decentraland Composite – reads main.composite and imports GLBs."""

import json
import os

import bpy
from mathutils import Matrix, Quaternion, Vector

from .composite_utils import (
    COMPOSITE_VERSION,
    dcl_pos_to_blender,
    dcl_quat_to_blender,
    dcl_scale_to_blender,
)


class OBJECT_OT_import_composite(bpy.types.Operator):
    bl_idname = "object.import_composite"
    bl_label = "Import Composite"
    bl_description = "Import a Decentraland main.composite file into the scene"
    bl_options = {"REGISTER", "UNDO"}

    filepath: bpy.props.StringProperty(
        name="File Path",
        description="Path to the .composite file",
        default="",
        subtype="FILE_PATH",
    )

    filter_glob: bpy.props.StringProperty(
        default="*.composite",
        options={"HIDDEN"},
    )

    update_existing: bpy.props.BoolProperty(
        name="Update Existing",
        description="Update transforms of existing objects by name instead of reimporting GLBs",
        default=True,
    )

    # ------------------------------------------------------------------

    def _parse_composite(self, path):
        with open(path) as f:
            data = json.load(f)
        if data.get("version") != COMPOSITE_VERSION:
            raise ValueError(f"Unsupported composite version: {data.get('version')}")
        return data

    def _build_entity_map(self, data):
        """Return ``{entity_id: {transform, gltf, name}}``."""
        entities = {}
        for comp in data.get("components", []):
            cname = comp["name"]
            for eid_str, entry in comp.get("data", {}).items():
                eid = int(eid_str)
                entities.setdefault(eid, {})
                payload = entry.get("json", {})
                if cname == "core::Transform":
                    entities[eid]["transform"] = payload
                elif cname == "core::GltfContainer":
                    entities[eid]["gltf"] = payload
                elif cname == "core-schema::Name":
                    entities[eid]["name"] = payload.get("value", "")
        return entities

    def _topo_sort(self, entities):
        """Return entity IDs sorted parents-first."""
        visited = set()
        order = []

        def visit(eid):
            if eid in visited:
                return
            visited.add(eid)
            parent = entities.get(eid, {}).get("transform", {}).get("parent", 0)
            if parent and parent in entities:
                visit(parent)
            order.append(eid)

        for eid in entities:
            visit(eid)
        return order

    def _apply_transform(self, obj, transform):
        pos = transform.get("position", {"x": 0, "y": 0, "z": 0})
        rot = transform.get("rotation", {"x": 0, "y": 0, "z": 0, "w": 1})
        scl = transform.get("scale", {"x": 1, "y": 1, "z": 1})

        obj.rotation_mode = "QUATERNION"
        obj.location = Vector(dcl_pos_to_blender(pos))
        obj.rotation_quaternion = Quaternion(dcl_quat_to_blender(rot))
        obj.scale = Vector(dcl_scale_to_blender(scl))

    def execute(self, context):
        path = self.filepath.strip()
        if not path or not os.path.isfile(path):
            self.report({"ERROR"}, "Choose a valid .composite file.")
            return {"CANCELLED"}

        try:
            data = self._parse_composite(path)
        except (json.JSONDecodeError, ValueError) as exc:
            self.report({"ERROR"}, str(exc))
            return {"CANCELLED"}

        entities = self._build_entity_map(data)
        if not entities:
            self.report({"WARNING"}, "Composite contains no entities.")
            return {"CANCELLED"}

        # Resolve scene root: go up from assets/scene/main.composite
        scene_dir = os.path.dirname(os.path.dirname(os.path.dirname(path)))

        sorted_ids = self._topo_sort(entities)
        imported = {}  # entity_id → blender object
        count = 0
        skipped = 0

        for eid in sorted_ids:
            ent = entities[eid]
            gltf = ent.get("gltf", {})
            src = gltf.get("src", "")
            name = ent.get("name", f"Entity_{eid}")
            transform = ent.get("transform", {})

            if not src:
                skipped += 1
                continue

            # Check for existing object to update
            existing = context.scene.objects.get(name) if self.update_existing else None

            if existing:
                self._apply_transform(existing, transform)
                imported[eid] = existing
                count += 1
            else:
                glb_path = os.path.join(scene_dir, src)
                if not os.path.isfile(glb_path):
                    self.report({"WARNING"}, f"Missing GLB: {src}")
                    skipped += 1
                    continue

                before = set(context.scene.objects)
                bpy.ops.import_scene.gltf(filepath=glb_path)
                after = set(context.scene.objects)
                new_objs = after - before

                if not new_objs:
                    skipped += 1
                    continue

                # Find root of imported hierarchy
                root = None
                for obj in new_objs:
                    if obj.parent is None or obj.parent not in new_objs:
                        root = obj
                        break
                if root is None:
                    root = next(iter(new_objs))

                root.name = name
                self._apply_transform(root, transform)
                imported[eid] = root
                count += 1

        # Second pass: restore parent-child hierarchy
        for eid in sorted_ids:
            ent = entities[eid]
            parent_eid = ent.get("transform", {}).get("parent", 0)
            if parent_eid and parent_eid in imported and eid in imported:
                child = imported[eid]
                parent = imported[parent_eid]
                child.parent = parent
                child.matrix_parent_inverse = Matrix.Identity(4)
                # Re-apply local transform after parenting
                self._apply_transform(child, ent.get("transform", {}))

        self.report({"INFO"}, f"Imported {count} entities from {os.path.basename(path)}")
        if skipped:
            self.report({"WARNING"}, f"Skipped {skipped} entities (missing GLB or no GltfContainer)")
        return {"FINISHED"}

    def invoke(self, context, event):
        if not self.filepath:
            base_dir = os.path.dirname(bpy.data.filepath) if bpy.data.filepath else os.path.expanduser("~")
            self.filepath = os.path.join(base_dir, "assets", "scene", "main.composite")
        context.window_manager.fileselect_add(self)
        return {"RUNNING_MODAL"}
