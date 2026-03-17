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
    sanitize_filename,
)


class TestPositionConversion:
    def test_blender_to_dcl(self):
        result = blender_pos_to_dcl((1.0, 2.0, 3.0))
        assert result == {"x": -1.0, "y": 3.0, "z": -2.0}

    def test_dcl_to_blender(self):
        result = dcl_pos_to_blender({"x": -1.0, "y": 3.0, "z": -2.0})
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
        assert len(result["components"]) == 3

        names = [c["name"] for c in result["components"]]
        assert "core::Transform" in names
        assert "core::GltfContainer" in names
        assert "core-schema::Name" in names

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
