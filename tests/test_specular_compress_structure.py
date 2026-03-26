"""Regression tests for specular/compression feature wiring."""

import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestSpecularCompressionFiles:
    def test_compress_textures_module_exists(self):
        assert os.path.isfile(os.path.join(SRC_DIR, "ops", "compress_textures.py"))

    def test_remove_specular_module_exists(self):
        assert os.path.isfile(os.path.join(SRC_DIR, "ops", "remove_specular.py"))


class TestSpecularCompressionPanelWiring:
    def test_operators_are_imported_in_init(self):
        init_src = _read(os.path.join(SRC_DIR, "__init__.py"))
        assert "OBJECT_OT_compress_textures" in init_src
        assert "OBJECT_OT_remove_specular" in init_src

    def test_operators_are_registered(self):
        init_src = _read(os.path.join(SRC_DIR, "__init__.py"))
        assert "OBJECT_OT_compress_textures," in init_src
        assert "OBJECT_OT_remove_specular," in init_src

    def test_materials_section_contains_buttons(self):
        init_src = _read(os.path.join(SRC_DIR, "__init__.py"))
        assert '"Compress Images"' in init_src
        assert '"Remove Specular"' in init_src
