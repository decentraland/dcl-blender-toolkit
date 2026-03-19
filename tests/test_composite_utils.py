"""Tests for composite_utils (no bpy dependency)."""

import os
import sys

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "src"))

from ops.composite_utils import (
    COMPOSITE_VERSION,
    FIRST_ENTITY_ID,
    blender_pos_to_dcl,
    blender_quat_to_dcl,
    blender_scale_to_dcl,
    build_composite,
    dcl_pos_to_blender,
    dcl_quat_to_blender,
    dcl_scale_to_blender,
    merge_composite,
    sanitize_filename,
)


class TestPositionConversion:
    def test_blender_to_dcl(self):
        # Blender (x=1, y=2, z=3) → DCL (x=1, y=3, z=2) — axis swap only
        result = blender_pos_to_dcl((1.0, 2.0, 3.0))
        assert result == {"x": 1.0, "y": 3.0, "z": 2.0}

    def test_dcl_to_blender(self):
        result = dcl_pos_to_blender({"x": 1.0, "y": 3.0, "z": 2.0})
        assert result == (1.0, 2.0, 3.0)

    def test_roundtrip(self):
        original = (5.0, -3.0, 7.0)
        dcl = blender_pos_to_dcl(original)
        back = dcl_pos_to_blender(dcl)
        assert back == original

    def test_origin(self):
        result = blender_pos_to_dcl((0, 0, 0))
        assert result == {"x": 0, "y": 0, "z": 0}


class TestQuaternionConversion:
    def test_blender_to_dcl(self):
        # Blender quat: (w, x, y, z)
        result = blender_quat_to_dcl((1.0, 0.0, 0.0, 0.0))
        assert result == {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}

    def test_dcl_to_blender(self):
        result = dcl_quat_to_blender({"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0})
        assert result == (1.0, 0.0, 0.0, 0.0)

    def test_roundtrip(self):
        original = (0.707, 0.1, 0.2, 0.3)
        dcl = blender_quat_to_dcl(original)
        back = dcl_quat_to_blender(dcl)
        for a, b in zip(original, back, strict=True):
            assert abs(a - b) < 1e-9


class TestScaleConversion:
    def test_blender_to_dcl(self):
        result = blender_scale_to_dcl((1.0, 2.0, 3.0))
        assert result == {"x": 1.0, "y": 3.0, "z": 2.0}

    def test_dcl_to_blender(self):
        result = dcl_scale_to_blender({"x": 1.0, "y": 3.0, "z": 2.0})
        assert result == (1.0, 2.0, 3.0)

    def test_roundtrip(self):
        original = (2.0, 3.0, 4.0)
        dcl = blender_scale_to_dcl(original)
        back = dcl_scale_to_blender(dcl)
        assert back == original


class TestSanitizeFilename:
    def test_normal_name(self):
        assert sanitize_filename("Cube") == "Cube"

    def test_special_chars(self):
        assert sanitize_filename('a<b>c:d"e') == "a_b_c_d_e"

    def test_empty(self):
        assert sanitize_filename("") == "unnamed"

    def test_dots_only(self):
        assert sanitize_filename("...") == "unnamed"

    def test_spaces_preserved(self):
        assert sanitize_filename("My Object") == "My Object"


class TestBuildComposite:
    def test_basic_structure(self):
        entities = [
            {
                "entity_id": FIRST_ENTITY_ID,
                "transform": {
                    "position": {"x": 0, "y": 0, "z": 0},
                    "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
                    "scale": {"x": 1, "y": 1, "z": 1},
                    "parent": 0,
                },
                "gltf_src": "assets/models/Cube.glb",
                "name": "Cube",
            }
        ]
        result = build_composite(entities)

        assert result["version"] == COMPOSITE_VERSION
        assert len(result["components"]) == 4

        names = [c["name"] for c in result["components"]]
        assert "core::Transform" in names
        assert "core::GltfContainer" in names
        assert "core-schema::Name" in names
        assert "inspector::Nodes" in names

    def test_entity_data_format(self):
        entities = [
            {
                "entity_id": 512,
                "transform": {
                    "position": {"x": 1, "y": 2, "z": 3},
                    "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
                    "scale": {"x": 1, "y": 1, "z": 1},
                    "parent": 0,
                },
                "gltf_src": "assets/models/Cube.glb",
                "name": "Cube",
            }
        ]
        result = build_composite(entities)

        # Check Transform data uses "json" wrapper
        transform_comp = next(c for c in result["components"] if c["name"] == "core::Transform")
        assert "512" in transform_comp["data"]
        assert "json" in transform_comp["data"]["512"]

        # Check GltfContainer
        gltf_comp = next(c for c in result["components"] if c["name"] == "core::GltfContainer")
        assert gltf_comp["data"]["512"]["json"]["src"] == "assets/models/Cube.glb"

        # Check Name
        name_comp = next(c for c in result["components"] if c["name"] == "core-schema::Name")
        assert name_comp["data"]["512"]["json"]["value"] == "Cube"

    def test_multiple_entities(self):
        entities = [
            {
                "entity_id": 512,
                "transform": {
                    "position": {"x": 0, "y": 0, "z": 0},
                    "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
                    "scale": {"x": 1, "y": 1, "z": 1},
                    "parent": 0,
                },
                "gltf_src": "assets/models/A.glb",
                "name": "A",
            },
            {
                "entity_id": 513,
                "transform": {
                    "position": {"x": 1, "y": 0, "z": 0},
                    "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
                    "scale": {"x": 1, "y": 1, "z": 1},
                    "parent": 512,
                },
                "gltf_src": "assets/models/B.glb",
                "name": "B",
            },
        ]
        result = build_composite(entities)

        transform_comp = next(c for c in result["components"] if c["name"] == "core::Transform")
        assert "512" in transform_comp["data"]
        assert "513" in transform_comp["data"]
        assert transform_comp["data"]["513"]["json"]["parent"] == 512

    def test_json_schema_present(self):
        entities = [
            {
                "entity_id": 512,
                "transform": {
                    "position": {"x": 0, "y": 0, "z": 0},
                    "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
                    "scale": {"x": 1, "y": 1, "z": 1},
                    "parent": 0,
                },
                "gltf_src": "assets/models/X.glb",
                "name": "X",
            }
        ]
        result = build_composite(entities)
        for comp in result["components"]:
            assert "jsonSchema" in comp

    def test_constants(self):
        assert FIRST_ENTITY_ID == 512
        assert COMPOSITE_VERSION == 1


class TestMergeComposite:
    def _make_entity(self, eid, name="E", pos_x=0):
        return {
            "entity_id": eid,
            "transform": {
                "position": {"x": pos_x, "y": 0, "z": 0},
                "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
                "scale": {"x": 1, "y": 1, "z": 1},
                "parent": 0,
            },
            "gltf_src": f"assets/models/{name}.glb",
            "name": name,
        }

    def test_preserves_unknown_components(self):
        existing = {
            "version": 1,
            "components": [
                {
                    "name": "core::Transform",
                    "jsonSchema": {},
                    "data": {"512": {"json": {"position": {"x": 0, "y": 0, "z": 0}}}},
                },
                {
                    "name": "core::GltfContainer",
                    "jsonSchema": {},
                    "data": {"512": {"json": {"src": "old.glb"}}},
                },
                {
                    "name": "core-schema::Name",
                    "jsonSchema": {},
                    "data": {"512": {"json": {"value": "Old"}}},
                },
                {
                    "name": "core::PointerEvents",
                    "jsonSchema": {"type": "object"},
                    "data": {"512": {"json": {"pointerEvents": [{"eventType": 1}]}}},
                },
                {
                    "name": "asset-packs::ScriptComponent",
                    "jsonSchema": {"type": "object"},
                    "data": {"512": {"json": {"src": "some-script.ts"}}},
                },
            ],
        }
        updated = [self._make_entity(512, "Updated", pos_x=99)]
        result = merge_composite(existing, updated)

        comp_names = [c["name"] for c in result["components"]]
        assert "core::PointerEvents" in comp_names
        assert "asset-packs::ScriptComponent" in comp_names

        # Verify unknown component data is untouched
        pointer_comp = next(c for c in result["components"] if c["name"] == "core::PointerEvents")
        assert pointer_comp["data"]["512"]["json"]["pointerEvents"] == [{"eventType": 1}]

        script_comp = next(c for c in result["components"] if c["name"] == "asset-packs::ScriptComponent")
        assert script_comp["data"]["512"]["json"]["src"] == "some-script.ts"

    def test_updates_managed_components(self):
        existing = {
            "version": 1,
            "components": [
                {
                    "name": "core::Transform",
                    "jsonSchema": {},
                    "data": {"512": {"json": {"position": {"x": 0, "y": 0, "z": 0}}}},
                },
                {
                    "name": "core::GltfContainer",
                    "jsonSchema": {},
                    "data": {"512": {"json": {"src": "old.glb"}}},
                },
                {
                    "name": "core-schema::Name",
                    "jsonSchema": {},
                    "data": {"512": {"json": {"value": "Old"}}},
                },
            ],
        }
        updated = [self._make_entity(512, "New", pos_x=42)]
        result = merge_composite(existing, updated)

        transform = next(c for c in result["components"] if c["name"] == "core::Transform")
        assert transform["data"]["512"]["json"]["position"]["x"] == 42

        gltf = next(c for c in result["components"] if c["name"] == "core::GltfContainer")
        assert gltf["data"]["512"]["json"]["src"] == "assets/models/New.glb"

        name = next(c for c in result["components"] if c["name"] == "core-schema::Name")
        assert name["data"]["512"]["json"]["value"] == "New"

    def test_preserves_entities_not_in_blender(self):
        """Entities that exist in the composite but not in Blender should be kept."""
        existing = {
            "version": 1,
            "components": [
                {
                    "name": "core::Transform",
                    "jsonSchema": {},
                    "data": {
                        "512": {"json": {"position": {"x": 1, "y": 0, "z": 0}}},
                        "513": {"json": {"position": {"x": 2, "y": 0, "z": 0}}},
                    },
                },
                {
                    "name": "core::GltfContainer",
                    "jsonSchema": {},
                    "data": {
                        "512": {"json": {"src": "a.glb"}},
                        "513": {"json": {"src": "b.glb"}},
                    },
                },
                {
                    "name": "core-schema::Name",
                    "jsonSchema": {},
                    "data": {
                        "512": {"json": {"value": "A"}},
                        "513": {"json": {"value": "B"}},
                    },
                },
            ],
        }
        # Only update entity 512, leave 513 alone
        updated = [self._make_entity(512, "A_Updated", pos_x=99)]
        result = merge_composite(existing, updated)

        transform = next(c for c in result["components"] if c["name"] == "core::Transform")
        # Entity 512 updated
        assert transform["data"]["512"]["json"]["position"]["x"] == 99
        # Entity 513 preserved
        assert transform["data"]["513"]["json"]["position"]["x"] == 2

    def test_adds_new_entity_to_existing(self):
        existing = {
            "version": 1,
            "components": [
                {
                    "name": "core::Transform",
                    "jsonSchema": {},
                    "data": {"512": {"json": {"position": {"x": 0, "y": 0, "z": 0}}}},
                },
                {
                    "name": "core::GltfContainer",
                    "jsonSchema": {},
                    "data": {"512": {"json": {"src": "a.glb"}}},
                },
                {
                    "name": "core-schema::Name",
                    "jsonSchema": {},
                    "data": {"512": {"json": {"value": "A"}}},
                },
            ],
        }
        updated = [
            self._make_entity(512, "A"),
            self._make_entity(513, "B", pos_x=5),
        ]
        result = merge_composite(existing, updated)

        transform = next(c for c in result["components"] if c["name"] == "core::Transform")
        assert "512" in transform["data"]
        assert "513" in transform["data"]
        assert transform["data"]["513"]["json"]["position"]["x"] == 5

    def test_preserves_version(self):
        existing = {"version": 1, "components": []}
        result = merge_composite(existing, [self._make_entity(512, "X")])
        assert result["version"] == 1
