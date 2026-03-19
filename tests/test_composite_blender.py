"""
Integration test for Export/Import Composite — runs inside Blender.

Usage:
    blender --background --python tests/test_composite_blender.py

Installs the addon from the built zip, creates a test scene, exercises the
full export → edit → import round-trip, and asserts correctness.
"""

import json
import math
import os
import shutil
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------------------
# Bootstrap: build zip, install addon
# ---------------------------------------------------------------------------

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT_DIR, "scripts"))

import build  # noqa: E402

version = build.read_bl_info_version()
zip_path = build.build_zip(version)

import bpy  # noqa: E402

bpy.ops.preferences.addon_install(filepath=zip_path, overwrite=True)
bpy.ops.preferences.addon_enable(module="decentraland_tools")

# Verify addon loaded
import decentraland_tools  # noqa: E402

assert decentraland_tools.bl_info["name"] == "Decentraland Tools", "Addon did not load"

# Also import the utils directly for verification helpers
sys.path.insert(0, os.path.join(ROOT_DIR, "src"))
from ops.composite_utils import FIRST_ENTITY_ID  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

passed = 0
failed = 0


def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS: {name}")
    else:
        failed += 1
        msg = f"  FAIL: {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)


# ---------------------------------------------------------------------------
# Test 1: Export Composite
# ---------------------------------------------------------------------------

print("\n=== Test 1: Export Composite ===")

# Clear default scene and build a fresh one
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.preferences.addon_enable(module="decentraland_tools")

# Create parent cube at (2, 3, 4)
bpy.ops.mesh.primitive_cube_add(location=(2.0, 3.0, 4.0))
parent_obj = bpy.context.active_object
parent_obj.name = "ParentCube"

# Create child sphere at world (5, 6, 7), parented to cube
bpy.ops.mesh.primitive_uv_sphere_add(location=(5.0, 6.0, 7.0))
child_obj = bpy.context.active_object
child_obj.name = "ChildSphere"
child_obj.parent = parent_obj

# Create standalone cylinder at (0, 0, 0)
bpy.ops.mesh.primitive_cylinder_add(location=(0.0, 0.0, 0.0))
standalone_obj = bpy.context.active_object
standalone_obj.name = "StandaloneCylinder"

# Force depsgraph update
bpy.context.view_layer.update()

# Export to temp directory
export_dir = tempfile.mkdtemp(prefix="dcl_composite_test_")
try:
    bpy.ops.object.export_composite(
        scene_dir=export_dir + os.sep,
        scene_title="Test Scene",
        export_hidden=False,
        overwrite_scene_json=True,
    )

    # Check files exist
    composite_path = os.path.join(export_dir, "assets", "scene", "main.composite")
    scene_json_path = os.path.join(export_dir, "scene.json")
    models_dir = os.path.join(export_dir, "assets", "models")

    check("main.composite exists", os.path.isfile(composite_path))
    check("scene.json exists", os.path.isfile(scene_json_path))
    check("models dir exists", os.path.isdir(models_dir))

    # Check GLB files
    glb_files = [f for f in os.listdir(models_dir) if f.endswith(".glb")]
    check("3 GLB files exported", len(glb_files) == 3, f"got {len(glb_files)}: {glb_files}")

    # Parse composite
    with open(composite_path) as f:
        composite = json.load(f)

    check("composite version is 1", composite.get("version") == 1)
    check("3 component types", len(composite.get("components", [])) == 3)

    # Extract component data
    comp_by_name = {c["name"]: c for c in composite["components"]}
    check("has core::Transform", "core::Transform" in comp_by_name)
    check("has core::GltfContainer", "core::GltfContainer" in comp_by_name)
    check("has core-schema::Name", "core-schema::Name" in comp_by_name)

    transform_data = comp_by_name["core::Transform"]["data"]
    name_data = comp_by_name["core-schema::Name"]["data"]
    gltf_data = comp_by_name["core::GltfContainer"]["data"]

    check("3 entities in Transform", len(transform_data) == 3, f"got {len(transform_data)}")
    check("3 entities in Name", len(name_data) == 3)
    check("3 entities in GltfContainer", len(gltf_data) == 3)

    # Check entity IDs start at 512
    entity_ids = sorted(int(k) for k in transform_data)
    check("entity IDs start at 512", entity_ids[0] == FIRST_ENTITY_ID, f"got {entity_ids}")

    # Check names are present
    names_in_composite = {v["json"]["value"] for v in name_data.values()}
    check("ParentCube in names", "ParentCube" in names_in_composite)
    check("ChildSphere in names", "ChildSphere" in names_in_composite)
    check("StandaloneCylinder in names", "StandaloneCylinder" in names_in_composite)

    # Check parent-child relationship
    # Find ChildSphere entity and verify its parent points to ParentCube entity
    child_eid = None
    parent_eid = None
    for eid_str, entry in name_data.items():
        if entry["json"]["value"] == "ChildSphere":
            child_eid = eid_str
        elif entry["json"]["value"] == "ParentCube":
            parent_eid = eid_str

    child_transform = transform_data[child_eid]["json"]
    check(
        "ChildSphere parent is ParentCube",
        child_transform["parent"] == int(parent_eid),
        f"parent={child_transform['parent']}, expected={parent_eid}",
    )

    # StandaloneCylinder should have parent=0
    standalone_eid = None
    for eid_str, entry in name_data.items():
        if entry["json"]["value"] == "StandaloneCylinder":
            standalone_eid = eid_str
    standalone_transform = transform_data[standalone_eid]["json"]
    check("StandaloneCylinder has no parent", standalone_transform["parent"] == 0)

    # Check jsonSchema present on all components
    for comp in composite["components"]:
        check(f"jsonSchema in {comp['name']}", "jsonSchema" in comp)

    # Check json wrapper format (not $case)
    sample_entry = next(iter(transform_data.values()))
    check("uses 'json' wrapper", "json" in sample_entry, f"keys: {list(sample_entry.keys())}")

    # Check scene.json content
    with open(scene_json_path) as f:
        scene_json = json.load(f)
    check("scene.json has ecs7", scene_json.get("ecs7") is True)
    check("scene.json has title", scene_json.get("display", {}).get("title") == "Test Scene")
    check("scene.json has parcels", scene_json.get("scene", {}).get("parcels") == ["0,0"])

    # ---------------------------------------------------------------------------
    # Test 2: Import Composite into clean scene
    # ---------------------------------------------------------------------------

    print("\n=== Test 2: Import Composite ===")

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_enable(module="decentraland_tools")

    # Should have no mesh objects
    mesh_objs_before = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    check("clean scene has no meshes", len(mesh_objs_before) == 0, f"got {len(mesh_objs_before)}")

    bpy.ops.object.import_composite(filepath=composite_path, update_existing=False)

    # Check objects were imported
    mesh_objs_after = [o for o in bpy.context.scene.objects if o.type == "MESH"]
    # glTF import may create additional child meshes, so check >= 3
    check("at least 3 mesh objects imported", len(mesh_objs_after) >= 3, f"got {len(mesh_objs_after)}")

    # Check named objects exist
    scene_names = {o.name for o in bpy.context.scene.objects}
    check("ParentCube exists after import", "ParentCube" in scene_names, f"names: {scene_names}")
    check("ChildSphere exists after import", "ChildSphere" in scene_names)
    check("StandaloneCylinder exists after import", "StandaloneCylinder" in scene_names)

    # Check parent-child restored
    imported_child = bpy.context.scene.objects.get("ChildSphere")
    imported_parent = bpy.context.scene.objects.get("ParentCube")
    if imported_child and imported_parent:
        check(
            "parent-child hierarchy restored",
            imported_child.parent == imported_parent,
            f"child.parent={imported_child.parent}",
        )

    # ---------------------------------------------------------------------------
    # Test 3: Round-trip update — edit composite, re-import with update_existing
    # ---------------------------------------------------------------------------

    print("\n=== Test 3: Round-trip Transform Update ===")

    # Modify the composite: move StandaloneCylinder to a new position
    # DCL position {"x": 10, "y": 20, "z": 30} → Blender (10, 30, 20)
    new_dcl_pos = {"x": 10.0, "y": 20.0, "z": 30.0}
    standalone_transform["position"] = new_dcl_pos

    with open(composite_path, "w") as f:
        json.dump(composite, f, indent=2)

    # Re-import with update_existing=True
    bpy.ops.object.import_composite(filepath=composite_path, update_existing=True)

    updated_obj = bpy.context.scene.objects.get("StandaloneCylinder")
    if updated_obj:
        loc = updated_obj.location
        # Expected Blender coords: (10, 30, 20) — axis swap only, no sign flip
        check(
            "updated X position",
            abs(loc.x - 10.0) < 0.01,
            f"got {loc.x}, expected 10.0",
        )
        check(
            "updated Y position",
            abs(loc.y - 30.0) < 0.01,
            f"got {loc.y}, expected 30.0",
        )
        check(
            "updated Z position",
            abs(loc.z - 20.0) < 0.01,
            f"got {loc.z}, expected 20.0",
        )
    else:
        check("StandaloneCylinder found for update test", False, "object missing")

    # ---------------------------------------------------------------------------
    # Test 4: Edge cases
    # ---------------------------------------------------------------------------

    print("\n=== Test 4: Edge Cases ===")

    # 4a: Export with no mesh objects
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_enable(module="decentraland_tools")
    empty_dir = tempfile.mkdtemp(prefix="dcl_empty_test_")
    try:
        try:
            result = bpy.ops.object.export_composite(
                scene_dir=empty_dir + os.sep,
                scene_title="Empty",
            )
            check("export empty scene returns CANCELLED", result == {"CANCELLED"})
        except RuntimeError:
            check("export empty scene raises error (background mode)", True)
    finally:
        shutil.rmtree(empty_dir, ignore_errors=True)

    # 4b: Import invalid composite
    # In background mode, operators that report ERROR raise RuntimeError
    bad_composite = os.path.join(export_dir, "bad.composite")
    with open(bad_composite, "w") as f:
        json.dump({"version": 999}, f)
    try:
        result = bpy.ops.object.import_composite(filepath=bad_composite, update_existing=False)
        check("import bad version returns CANCELLED", result == {"CANCELLED"})
    except RuntimeError:
        check("import bad version raises error (background mode)", True)

    # 4c: Import composite with missing GLB
    missing_composite = os.path.join(export_dir, "assets", "scene", "missing.composite")
    missing_data = {
        "version": 1,
        "components": [
            {
                "name": "core::Transform",
                "jsonSchema": {},
                "data": {
                    "512": {
                        "json": {
                            "position": {"x": 0, "y": 0, "z": 0},
                            "rotation": {"x": 0, "y": 0, "z": 0, "w": 1},
                            "scale": {"x": 1, "y": 1, "z": 1},
                            "parent": 0,
                        }
                    }
                },
            },
            {
                "name": "core::GltfContainer",
                "jsonSchema": {},
                "data": {"512": {"json": {"src": "assets/models/nonexistent.glb"}}},
            },
            {
                "name": "core-schema::Name",
                "jsonSchema": {},
                "data": {"512": {"json": {"value": "Ghost"}}},
            },
        ],
    }
    with open(missing_composite, "w") as f:
        json.dump(missing_data, f)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_enable(module="decentraland_tools")
    result = bpy.ops.object.import_composite(filepath=missing_composite, update_existing=False)
    check("import with missing GLB still finishes", result == {"FINISHED"})
    ghost = bpy.context.scene.objects.get("Ghost")
    check("missing GLB entity not created", ghost is None)

    # 4d: Export with hidden object (export_hidden=False)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_enable(module="decentraland_tools")
    bpy.ops.mesh.primitive_cube_add()
    visible_obj = bpy.context.active_object
    visible_obj.name = "Visible"
    bpy.ops.mesh.primitive_cube_add()
    hidden_obj = bpy.context.active_object
    hidden_obj.name = "Hidden"
    hidden_obj.hide_set(True)
    bpy.context.view_layer.update()

    hidden_test_dir = tempfile.mkdtemp(prefix="dcl_hidden_test_")
    try:
        bpy.ops.object.export_composite(
            scene_dir=hidden_test_dir + os.sep,
            scene_title="Hidden Test",
            export_hidden=False,
        )
        comp_path = os.path.join(hidden_test_dir, "assets", "scene", "main.composite")
        with open(comp_path) as f:
            comp_data = json.load(f)
        name_comp = next(c for c in comp_data["components"] if c["name"] == "core-schema::Name")
        exported_names = {v["json"]["value"] for v in name_comp["data"].values()}
        check("hidden object excluded", "Hidden" not in exported_names, f"names: {exported_names}")
        check("visible object included", "Visible" in exported_names)
    finally:
        shutil.rmtree(hidden_test_dir, ignore_errors=True)

    # ---------------------------------------------------------------------------
    # Test 5: Validate output matches real DCL composite format
    # ---------------------------------------------------------------------------

    print("\n=== Test 5: DCL Format Conformance ===")

    # Re-export a clean scene to validate the full composite structure
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.preferences.addon_enable(module="decentraland_tools")
    bpy.ops.mesh.primitive_cube_add(location=(8, 0, 1))
    bpy.context.active_object.name = "TestCube"
    bpy.context.view_layer.update()

    format_test_dir = tempfile.mkdtemp(prefix="dcl_format_test_")
    try:
        bpy.ops.object.export_composite(
            scene_dir=format_test_dir + os.sep,
            scene_title="Format Test",
        )
        comp_path = os.path.join(format_test_dir, "assets", "scene", "main.composite")
        with open(comp_path) as f:
            comp_data = json.load(f)

        # Top-level structure
        check("has 'version' key", "version" in comp_data)
        check("has 'components' key", "components" in comp_data)
        check("version is int 1", comp_data["version"] == 1)
        check("components is a list", isinstance(comp_data["components"], list))

        # Validate each component has required fields
        for comp in comp_data["components"]:
            check(f"{comp['name']} has 'name'", "name" in comp)
            check(f"{comp['name']} has 'jsonSchema'", "jsonSchema" in comp)
            check(f"{comp['name']} has 'data'", "data" in comp)
            check(
                f"{comp['name']} data values use 'json' wrapper",
                all("json" in v for v in comp["data"].values()),
            )

        # Validate Transform jsonSchema matches DCL SDK format
        transform_comp = next(c for c in comp_data["components"] if c["name"] == "core::Transform")
        t_schema = transform_comp["jsonSchema"]
        check(
            "Transform serializationType is 'transform'",
            t_schema.get("serializationType") == "transform",
            f"got '{t_schema.get('serializationType')}'",
        )
        check("Transform schema has position prop", "position" in t_schema.get("properties", {}))
        check("Transform schema has rotation prop", "rotation" in t_schema.get("properties", {}))
        check("Transform schema has scale prop", "scale" in t_schema.get("properties", {}))
        check("Transform schema has parent prop", "parent" in t_schema.get("properties", {}))
        check(
            "Transform parent type is integer",
            t_schema["properties"]["parent"].get("type") == "integer",
        )

        # Validate position sub-schema has x/y/z
        pos_props = t_schema["properties"]["position"].get("properties", {})
        check("position has x/y/z", {"x", "y", "z"} == set(pos_props.keys()))

        # Validate GltfContainer jsonSchema
        gltf_comp = next(c for c in comp_data["components"] if c["name"] == "core::GltfContainer")
        g_schema = gltf_comp["jsonSchema"]
        check(
            "GltfContainer serializationType is 'protocol-buffer'",
            g_schema.get("serializationType") == "protocol-buffer",
        )
        check(
            "GltfContainer protocolBuffer is 'PBGltfContainer'",
            g_schema.get("protocolBuffer") == "PBGltfContainer",
        )

        # Validate Name jsonSchema matches DCL SDK format
        name_comp = next(c for c in comp_data["components"] if c["name"] == "core-schema::Name")
        n_schema = name_comp["jsonSchema"]
        check(
            "Name serializationType is 'map'",
            n_schema.get("serializationType") == "map",
            f"got '{n_schema.get('serializationType')}'",
        )
        check("Name schema has 'value' prop", "value" in n_schema.get("properties", {}))
        check(
            "Name value serializationType is 'utf8-string'",
            n_schema["properties"]["value"].get("serializationType") == "utf8-string",
        )

        # Validate Transform data has correct shape
        t_data = next(iter(transform_comp["data"].values()))["json"]
        check("transform data has position", "position" in t_data)
        check("transform data has rotation", "rotation" in t_data)
        check("transform data has scale", "scale" in t_data)
        check("transform data has parent", "parent" in t_data)
        check(
            "position has x/y/z numbers",
            all(isinstance(t_data["position"][k], (int, float)) for k in ("x", "y", "z")),
        )
        check(
            "rotation has x/y/z/w numbers",
            all(isinstance(t_data["rotation"][k], (int, float)) for k in ("x", "y", "z", "w")),
        )
        check("parent is int", isinstance(t_data["parent"], int))

        # Validate GltfContainer data has 'src' string
        g_data = next(iter(gltf_comp["data"].values()))["json"]
        check("gltf data has 'src'", "src" in g_data)
        check("gltf src is string", isinstance(g_data["src"], str))
        check("gltf src starts with 'assets/'", g_data["src"].startswith("assets/"))

        # Validate scene.json
        scene_path = os.path.join(format_test_dir, "scene.json")
        with open(scene_path) as f:
            scene = json.load(f)
        check("scene.json has 'ecs7': true", scene.get("ecs7") is True)
        check("scene.json has 'runtimeVersion': '7'", scene.get("runtimeVersion") == "7")
        check("scene.json has 'main': 'bin/index.js'", scene.get("main") == "bin/index.js")
        check("scene.json has 'display.title'", scene.get("display", {}).get("title") == "Format Test")
        check("scene.json has 'scene.base'", scene.get("scene", {}).get("base") == "0,0")
    finally:
        shutil.rmtree(format_test_dir, ignore_errors=True)

    # ---------------------------------------------------------------------------
    # Test 6: DCL SDK build validation (Blender → Inspector round-trip)
    # ---------------------------------------------------------------------------

    print("\n=== Test 6: DCL SDK Build Validation ===")

    # Check if npx is available
    npx_available = shutil.which("npx") is not None
    if not npx_available:
        print("  SKIP: npx not available, cannot test SDK build")
    else:
        sdk_test_dir = tempfile.mkdtemp(prefix="dcl_sdk_test_")
        try:
            # Initialize a DCL scene project
            init_result = subprocess.run(
                ["npx", "@dcl/sdk-commands", "init", "--yes"],
                cwd=sdk_test_dir,
                capture_output=True,
                text=True,
                timeout=120,
            )
            check(
                "SDK init succeeds",
                init_result.returncode == 0,
                init_result.stderr[-200:] if init_result.stderr else "",
            )

            if init_result.returncode == 0:
                # Export Blender composite into the SDK project
                bpy.ops.wm.read_factory_settings(use_empty=True)
                bpy.ops.preferences.addon_enable(module="decentraland_tools")

                bpy.ops.mesh.primitive_cube_add(location=(8.0, 0.0, 1.0))
                bpy.context.active_object.name = "SDKTestCube"
                bpy.ops.mesh.primitive_uv_sphere_add(location=(12.0, 0.0, 3.0))
                bpy.context.active_object.name = "SDKTestSphere"
                bpy.context.view_layer.update()

                bpy.ops.object.export_composite(
                    scene_dir=sdk_test_dir + os.sep,
                    scene_title="SDK Build Test",
                    export_hidden=False,
                    overwrite_scene_json=False,
                )

                # Verify our composite landed
                comp_path = os.path.join(sdk_test_dir, "assets", "scene", "main.composite")
                check("composite exists in SDK project", os.path.isfile(comp_path))

                # SDK build parses our composite with Composite.fromJson()
                build_result = subprocess.run(
                    ["npx", "@dcl/sdk-commands", "build"],
                    cwd=sdk_test_dir,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                check(
                    "SDK build succeeds with our composite",
                    build_result.returncode == 0,
                    build_result.stderr[-300:] if build_result.stderr else build_result.stdout[-300:],
                )
                bin_index = os.path.join(sdk_test_dir, "bin", "index.js")
                check("build output bin/index.js exists", os.path.isfile(bin_index))

        except subprocess.TimeoutExpired:
            check("SDK commands completed within timeout", False, "timed out")
        except Exception as exc:
            check("SDK test ran without exception", False, str(exc))
        finally:
            shutil.rmtree(sdk_test_dir, ignore_errors=True)

finally:
    shutil.rmtree(export_dir, ignore_errors=True)

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------

print(f"\n{'=' * 50}")
print(f"Results: {passed} passed, {failed} failed out of {passed + failed}")
print(f"{'=' * 50}")

if failed:
    sys.exit(1)
