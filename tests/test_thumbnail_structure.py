"""Regression tests for thumbnail feature wiring."""

import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestThumbnailFiles:
    def test_generate_thumbnail_module_exists(self):
        assert os.path.isfile(os.path.join(SRC_DIR, "ops", "generate_thumbnail.py"))


class TestThumbnailPanelWiring:
    def test_thumbnail_operators_are_imported(self):
        init_src = _read(os.path.join(SRC_DIR, "__init__.py"))
        assert "OBJECT_OT_add_thumbnail_camera" in init_src
        assert "OBJECT_OT_add_thumbnail_lighting" in init_src
        assert "OBJECT_OT_render_thumbnail" in init_src

    def test_thumbnail_section_is_drawn(self):
        init_src = _read(os.path.join(SRC_DIR, "__init__.py"))
        assert "def _draw_generate_thumbnail(layout, props):" in init_src
        assert '"Generate Thumbnail"' in init_src

    def test_thumbnail_operators_are_registered(self):
        init_src = _read(os.path.join(SRC_DIR, "__init__.py"))
        assert "OBJECT_OT_add_thumbnail_camera," in init_src
        assert "OBJECT_OT_add_thumbnail_lighting," in init_src
        assert "OBJECT_OT_render_thumbnail," in init_src


class TestThumbnailReadmeDocs:
    def test_readme_contains_thumbnail_section(self):
        readme_src = _read(os.path.join(ROOT_DIR, "README.md"))
        assert "### Generate Thumbnail" in readme_src
        assert "| **Add Camera** |" in readme_src
        assert "| **Add Lighting** |" in readme_src
        assert "| **Render Image** |" in readme_src
"""Regression tests for thumbnail feature wiring."""

import os

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


class TestThumbnailFiles:
    def test_generate_thumbnail_module_exists(self):
        assert os.path.isfile(os.path.join(SRC_DIR, "ops", "generate_thumbnail.py"))


class TestThumbnailPanelWiring:
    def test_thumbnail_operators_are_imported(self):
        init_src = _read(os.path.join(SRC_DIR, "__init__.py"))
        assert "OBJECT_OT_add_thumbnail_camera" in init_src
        assert "OBJECT_OT_add_thumbnail_lighting" in init_src
        assert "OBJECT_OT_render_thumbnail" in init_src

    def test_thumbnail_section_is_drawn(self):
        init_src = _read(os.path.join(SRC_DIR, "__init__.py"))
        assert 'def _draw_generate_thumbnail(layout, props):' in init_src
        assert '"Generate Thumbnail"' in init_src

    def test_thumbnail_operators_are_registered(self):
        init_src = _read(os.path.join(SRC_DIR, "__init__.py"))
        assert "OBJECT_OT_add_thumbnail_camera," in init_src
        assert "OBJECT_OT_add_thumbnail_lighting," in init_src
        assert "OBJECT_OT_render_thumbnail," in init_src


class TestThumbnailReadmeDocs:
    def test_readme_contains_thumbnail_section(self):
        readme_src = _read(os.path.join(ROOT_DIR, "README.md"))
        assert "### Generate Thumbnail" in readme_src
        assert "| **Add Camera** |" in readme_src
        assert "| **Add Lighting** |" in readme_src
        assert "| **Render Image** |" in readme_src
