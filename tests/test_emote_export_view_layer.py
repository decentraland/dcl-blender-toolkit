"""Regression tests: exporting an emote whose prop lives in a disabled collection.

select_set() raises "Object cannot be selected because it is not in View Layer"
for objects in excluded collections, and hidden collections silently drop their
objects from a use_visible export. The exporter must make the export objects
available for the duration of the export and put every flag back afterwards.
"""

import importlib.util
import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def _load_emote_utils():
    """Load emote_utils standalone; importing src/ would pull in bpy."""
    path = os.path.join(SRC_DIR, "ops", "emote_utils.py")
    spec = importlib.util.spec_from_file_location("emote_utils", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


emote_utils = _load_emote_utils()


class FakeObject:
    def __init__(self, name):
        self.name = name


class FakeCollection:
    def __init__(self, name, objects=(), hide_viewport=False):
        self.name = name
        self.all_objects = list(objects)
        self.hide_viewport = hide_viewport


class FakeLayerCollection:
    def __init__(self, collection, children=(), exclude=False, hide_viewport=False):
        self.collection = collection
        self.children = list(children)
        self.exclude = exclude
        self.hide_viewport = hide_viewport


class FakeViewLayer:
    def __init__(self, layer_collection):
        self.layer_collection = layer_collection


def _scene():
    prop = FakeObject("Armature_Prop")
    gun = FakeObject("Space_Gun")
    avatar = FakeObject("Armature")
    props_layer = FakeLayerCollection(
        FakeCollection("Props", [prop, gun]),
        exclude=True,
    )
    other_layer = FakeLayerCollection(
        FakeCollection("Reference", [FakeObject("Reference_Ground")]),
        exclude=True,
    )
    root = FakeLayerCollection(
        FakeCollection("Master", [avatar, prop, gun]),
        children=[props_layer, other_layer],
    )
    return FakeViewLayer(root), [avatar, prop, gun], props_layer, other_layer


class TestViewLayerPreparation:
    def test_excluded_collection_with_export_objects_is_enabled(self):
        view_layer, export_objects, props_layer, _ = _scene()
        emote_utils.prepare_view_layer_for_export(view_layer, export_objects)
        assert not props_layer.exclude

    def test_unrelated_excluded_collection_is_left_alone(self):
        view_layer, export_objects, _, other_layer = _scene()
        emote_utils.prepare_view_layer_for_export(view_layer, export_objects)
        assert other_layer.exclude

    def test_hidden_collections_are_revealed(self):
        view_layer, export_objects, props_layer, _ = _scene()
        props_layer.exclude = False
        props_layer.hide_viewport = True
        props_layer.collection.hide_viewport = True
        emote_utils.prepare_view_layer_for_export(view_layer, export_objects)
        assert not props_layer.hide_viewport
        assert not props_layer.collection.hide_viewport

    def test_nested_collections_on_the_path_are_enabled(self):
        prop = FakeObject("Armature_Prop")
        inner = FakeLayerCollection(FakeCollection("Inner", [prop]), exclude=True)
        outer = FakeLayerCollection(FakeCollection("Outer", [prop]), children=[inner], exclude=True)
        root = FakeLayerCollection(FakeCollection("Master", [prop]), children=[outer])
        emote_utils.prepare_view_layer_for_export(FakeViewLayer(root), [prop])
        assert not outer.exclude
        assert not inner.exclude

    def test_restore_puts_every_flag_back(self):
        view_layer, export_objects, props_layer, other_layer = _scene()
        props_layer.collection.hide_viewport = True
        undo = emote_utils.prepare_view_layer_for_export(view_layer, export_objects)
        emote_utils.restore_view_layer_state(undo)
        assert props_layer.exclude
        assert props_layer.collection.hide_viewport
        assert other_layer.exclude

    def test_nothing_to_undo_when_everything_is_available(self):
        view_layer, export_objects, props_layer, _ = _scene()
        props_layer.exclude = False
        assert emote_utils.prepare_view_layer_for_export(view_layer, export_objects) == []


class TestExporterWiring:
    def test_exporter_prepares_and_restores_the_view_layer(self):
        src = _read(os.path.join(SRC_DIR, "ops", "export_emote_glb.py"))
        assert "prepare_view_layer_for_export" in src
        assert "restore_view_layer_state" in src

    def test_select_set_is_guarded_by_view_layer_membership(self):
        src = _read(os.path.join(SRC_DIR, "ops", "export_emote_glb.py"))
        assert "selectable_names" in src
