"""Shared test helpers; kept out of src/ imports so plain pytest runs without bpy."""

import importlib.util
import os

SRC_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")


def read_source(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def load_emote_utils():
    """Load emote_utils standalone; importing src/ would pull in bpy."""
    path = os.path.join(SRC_DIR, "ops", "emote_utils.py")
    spec = importlib.util.spec_from_file_location("emote_utils", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_toolkit_module(dotted):
    """Import src/<dotted> inside a synthetic package with a stub bpy, so relative imports resolve without Blender."""
    import importlib
    import sys
    import types

    if "bpy" not in sys.modules:
        bpy = types.ModuleType("bpy")
        bpy.types = types.SimpleNamespace(Operator=object, Panel=object, PropertyGroup=object)
        bpy.props = types.SimpleNamespace(
            **{
                name: (lambda **kwargs: None)
                for name in ("EnumProperty", "IntProperty", "BoolProperty", "StringProperty", "FloatProperty")
            }
        )
        bpy.data = types.SimpleNamespace(actions=[], materials=[], objects={}, images=[])
        bpy.context = types.SimpleNamespace(selected_objects=[], active_object=None)
        sys.modules["bpy"] = bpy

    package = "toolkit_under_test"
    if package not in sys.modules:
        for name, path in ((package, SRC_DIR), (f"{package}.ops", os.path.join(SRC_DIR, "ops"))):
            module = types.ModuleType(name)
            module.__path__ = [path]
            sys.modules[name] = module
    return importlib.import_module(f"{package}.{dotted}")
