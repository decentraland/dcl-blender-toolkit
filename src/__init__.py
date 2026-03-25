bl_info = {
    "name": "Decentraland Tools",
    "author": "Decentraland Foundation",
    "version": (1, 2, 2),
    "blender": (2, 80, 0),
    "location": "3D Viewport > Sidebar (N) > Decentraland Tools",
    "description": "Collection of tools for Decentraland asset creation and optimization (Blender 2.80 - 5.0+)",
    "category": "Object",
}

import bpy
from bpy.utils import register_class, unregister_class

from . import icon_loader
from .ops.avatar_limitations import OBJECT_OT_avatar_limitations
from .ops.cleanup_colliders import OBJECT_OT_cleanup_colliders
from .ops.create_parcels import (
    OBJECT_OT_apply_checker_map,
    OBJECT_OT_cleanup_checker_map,
    OBJECT_OT_create_parcels,
    OBJECT_OT_set_parcel_origin,
)
from .ops.documentation import OBJECT_OT_asset_guidelines, OBJECT_OT_open_documentation, OBJECT_OT_scene_limits_guide
from .ops.emote_actions import OBJECT_OT_create_emote_action, OBJECT_OT_set_emote_boundary_keyframes
from .ops.enable_backface_culling import OBJECT_OT_enable_backface_culling
from .ops.export_composite import OBJECT_OT_export_composite
from .ops.export_emote_glb import OBJECT_OT_export_emote_glb
from .ops.export_lights import OBJECT_OT_export_lights
from .ops.generate_lod import OBJECT_OT_generate_lod, draw_lod_panel
from .ops.import_composite import OBJECT_OT_import_composite
from .ops.import_dcl_rig import OBJECT_OT_import_dcl_limit_area, OBJECT_OT_import_dcl_prop, OBJECT_OT_import_dcl_rig
from .ops.install_theme import OBJECT_OT_install_dcl_theme
from .ops.link_avatar_wearables import OBJECT_OT_link_avatar_wearables
from .ops.particle_to_armature import OBJECT_OT_particles_to_armature_converter
from .ops.quick_export_gltf import OBJECT_OT_export_scene, OBJECT_OT_quick_export_gltf, OBJECT_OT_update_all_exported
from .ops.remove_empty_objects import OBJECT_OT_remove_empty_objects
from .ops.remove_uvs import OBJECT_OT_remove_uvs_from_colliders
from .ops.rename_add_suffix import OBJECT_OT_rename_add_collider_suffix
from .ops.rename_textures import OBJECT_OT_rename_textures
from .ops.replace_materials import (
    MaterialListItem,
    OBJECT_OT_add_source_material_to_list,
    OBJECT_OT_remove_source_material_from_list,
    OBJECT_OT_replace_materials,
)
from .ops.resize_textures import OBJECT_OT_resize_textures
from .ops.scene_limitations import OBJECT_OT_scene_limitations
from .ops.simplify_colliders import OBJECT_OT_simplify_colliders
from .ops.strip_materials import OBJECT_OT_strip_materials_from_colliders
from .ops.validate_emote import OBJECT_OT_validate_emote
from .ops.validate_scene import OBJECT_OT_validate_scene
from .ops.validate_textures import OBJECT_OT_validate_textures

# Tab constants
TAB_ALL = "ALL"
TAB_SCENES = "SCENES"
TAB_WEARABLES = "WEARABLES"

# ---------------------------------------------------------------------------
# PropertyGroup: all Scene-level properties in one group
# ---------------------------------------------------------------------------


class DCLToolsSceneProperties(bpy.types.PropertyGroup):
    """All Decentraland Tools scene-level properties."""

    # Tab selection
    active_tab: bpy.props.EnumProperty(
        name="Tab",
        items=[
            (TAB_ALL, "All Tools", "Show all tools"),
            (TAB_SCENES, "Scenes", "Show scene tools"),
            (TAB_WEARABLES, "Wearables", "Show wearable and emote tools"),
        ],
        default=TAB_ALL,
    )

    # Experimental features toggle
    show_experimental: bpy.props.BoolProperty(
        name="Experimental Features",
        description="Show experimental features (LOD Generator, Other)",
        default=False,
    )

    # Panel expansion states
    scene_expanded: bpy.props.BoolProperty(default=True)
    avatars_expanded: bpy.props.BoolProperty(default=True)
    emotes_expanded: bpy.props.BoolProperty(default=True)
    materials_expanded: bpy.props.BoolProperty(default=True)
    cleanup_expanded: bpy.props.BoolProperty(default=True)
    manage_expanded: bpy.props.BoolProperty(default=True)
    lod_expanded: bpy.props.BoolProperty(default=True)
    other_expanded: bpy.props.BoolProperty(default=True)

    # Emote workflow
    emote_start_frame: bpy.props.IntProperty(
        name="Start Frame",
        description="First frame of the emote clip",
        default=1,
        min=1,
        max=300,
    )
    emote_end_frame: bpy.props.IntProperty(
        name="End Frame",
        description="Last frame of the emote clip (max 300)",
        default=300,
        min=1,
        max=300,
    )
    emote_sampling_rate: bpy.props.IntProperty(
        name="Sampling Rate",
        description="Export bake step. 1 = full fidelity, 2 recommended, 3 for extra size reduction",
        default=1,
        min=1,
        max=6,
    )
    emote_strict_validation: bpy.props.BoolProperty(
        name="Strict Validation",
        description="Treat warnings as blocking errors for export",
        default=False,
    )

    # LOD Generator
    lod_levels: bpy.props.IntProperty(
        name="LOD Levels",
        description="Number of LOD levels to generate",
        default=3,
        min=1,
        max=4,
    )
    lod1_ratio: bpy.props.FloatProperty(
        name="LOD 1 Ratio",
        description="Decimation ratio for LOD 1 (e.g. 0.5 = keep 50%)",
        default=0.50,
        min=0.01,
        max=0.99,
        subtype="FACTOR",
    )
    lod2_ratio: bpy.props.FloatProperty(
        name="LOD 2 Ratio",
        description="Decimation ratio for LOD 2",
        default=0.15,
        min=0.01,
        max=0.99,
        subtype="FACTOR",
    )
    lod3_ratio: bpy.props.FloatProperty(
        name="LOD 3 Ratio",
        description="Decimation ratio for LOD 3",
        default=0.05,
        min=0.01,
        max=0.99,
        subtype="FACTOR",
    )
    lod4_ratio: bpy.props.FloatProperty(
        name="LOD 4 Ratio",
        description="Decimation ratio for LOD 4",
        default=0.02,
        min=0.01,
        max=0.99,
        subtype="FACTOR",
    )
    lod_create_collection: bpy.props.BoolProperty(
        name="Create LOD Collection",
        description="Place generated LODs in a dedicated collection",
        default=True,
    )

    # Particle System Converter
    ps_converter_out_collection: bpy.props.StringProperty(
        name="Output Collection",
        description="Collection name for converted armature and objects",
        default="ParticleArmature_Output",
    )
    ps_converter_start_frame: bpy.props.IntProperty(
        name="Start Frame", description="Start frame for animation conversion", default=1, min=1
    )
    ps_converter_end_frame: bpy.props.IntProperty(
        name="End Frame", description="End frame for animation conversion", default=250, min=1
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _section_header(layout, props, prop_name, label):
    """Draw a collapsible section box and return (box, is_expanded)."""
    box = layout.box()
    row = box.row()
    expanded = getattr(props, prop_name)
    row.prop(
        props,
        prop_name,
        text=label,
        icon="TRIA_DOWN" if expanded else "TRIA_RIGHT",
        emboss=False,
    )
    return box, expanded


def _op(target, bl_idname, text, icon_name, fallback_icon):
    """Draw an operator button using a custom Tabler icon if available, otherwise fallback."""
    ico = icon_loader.get_icon(icon_name)
    if ico:
        target.operator(bl_idname, text=text, icon_value=ico)
    else:
        target.operator(bl_idname, text=text, icon=fallback_icon)


# ---------------------------------------------------------------------------
# Section drawing functions
# ---------------------------------------------------------------------------


def _draw_scene_creation(layout, props):
    box, expanded = _section_header(layout, props, "scene_expanded", "Scene Creation")
    if expanded:
        col = box.column(align=True)
        col.scale_y = 1.2
        _op(col, OBJECT_OT_create_parcels.bl_idname, "Create Parcels", "GRID_DOTS", "MESH_PLANE")
        row = col.row(align=True)
        _op(row, OBJECT_OT_scene_limitations.bl_idname, "Scene Limitations", "RULER", "INFO")
        _op(row, OBJECT_OT_validate_scene.bl_idname, "Scene Validator", "SHIELD_CHECK", "SEQUENCE")
        row = col.row(align=True)
        _op(row, OBJECT_OT_apply_checker_map.bl_idname, "Checker Map", "GRID_DOTS", "TEXTURE")
        _op(row, OBJECT_OT_cleanup_checker_map.bl_idname, "Cleanup All Checker Maps", "TRASH_X", "CANCEL")


def _draw_avatars(layout, props):
    box, expanded = _section_header(layout, props, "avatars_expanded", "Avatars")
    if expanded:
        col = box.column(align=True)
        col.scale_y = 1.2
        row = col.row(align=True)
        _op(row, OBJECT_OT_link_avatar_wearables.bl_idname, "Avatar Shapes", "FRIENDS", "ARMATURE_DATA")
        _op(row, OBJECT_OT_avatar_limitations.bl_idname, "Wearable Limits", "SHIRT_SPORT", "INFO")


def _draw_emotes(layout, props):
    box, expanded = _section_header(layout, props, "emotes_expanded", "Emotes")
    if expanded:
        col = box.column(align=True)
        col.scale_y = 1.2

        _op(col, OBJECT_OT_import_dcl_rig.bl_idname, "Import DCL Rig", "ASSET", "ARMATURE_DATA")
        row = col.row(align=True)
        _op(row, OBJECT_OT_import_dcl_prop.bl_idname, "Add Prop", "EMOTE_PROPS", "OBJECT_DATA")
        _op(row, OBJECT_OT_import_dcl_limit_area.bl_idname, "Limit Area Reference", "DIMENSIONS", "MESH_GRID")
        col.separator(factor=0.3)

        row = col.row(align=True)
        _op(row, OBJECT_OT_create_emote_action.bl_idname, "Create Emote Action", "EDIT", "ACTION")
        _op(
            row,
            OBJECT_OT_set_emote_boundary_keyframes.bl_idname,
            "Set Boundary Keys",
            "PROGRESS_CHECK",
            "KEYTYPE_JITTER_VEC",
        )
        col.separator(factor=0.3)

        _op(col, OBJECT_OT_validate_emote.bl_idname, "Validate Emote", "PROGRESS_CHECK", "CHECKMARK")
        col.separator(factor=0.3)

        settings = col.box()
        settings.label(text="Emote Settings")
        settings.prop(props, "emote_start_frame")
        settings.prop(props, "emote_end_frame")
        settings.prop(props, "emote_sampling_rate")
        settings.prop(props, "emote_strict_validation")


def _draw_materials(layout, props):
    box, expanded = _section_header(layout, props, "materials_expanded", "Materials & Textures")
    if expanded:
        col = box.column(align=True)
        col.scale_y = 1.2
        row = col.row(align=True)
        _op(row, OBJECT_OT_replace_materials.bl_idname, "Replace Materials", "REPLACE", "MATERIAL_DATA")
        _op(row, OBJECT_OT_resize_textures.bl_idname, "Resize Textures", "IMAGE_IN_PICTURE", "IMAGE_DATA")
        col.separator(factor=0.3)
        row = col.row(align=True)
        _op(row, OBJECT_OT_validate_textures.bl_idname, "Validate Textures", "PHOTO_CHECK", "TEXTURE")
        _op(
            row,
            OBJECT_OT_enable_backface_culling.bl_idname,
            "Enable Backface Culling",
            "FLIP_VERTICAL",
            "NORMALS_FACE",
        )


def _draw_lod(layout, props, context):
    box, expanded = _section_header(layout, props, "lod_expanded", "LOD Generator")
    if expanded:
        draw_lod_panel(box, context)


def _draw_cleanup(layout, props):
    box, expanded = _section_header(layout, props, "cleanup_expanded", "CleanUp")
    if expanded:
        col = box.column(align=True)
        col.scale_y = 1.2
        row = col.row(align=True)
        _op(row, OBJECT_OT_remove_empty_objects.bl_idname, "Remove Empty Objects", "TRASH_X", "X")
        _op(row, OBJECT_OT_rename_textures.bl_idname, "Rename Textures", "PHOTO_EDIT", "TEXTURE")


def _draw_colliders(layout, props):
    box, expanded = _section_header(layout, props, "manage_expanded", "Collider Management")
    if expanded:
        col = box.column(align=True)
        col.scale_y = 1.2
        row = col.row(align=True)
        _op(row, OBJECT_OT_rename_add_collider_suffix.bl_idname, "Add Suffix", "TAG", "OUTLINER_OB_MESH")
        _op(row, OBJECT_OT_remove_uvs_from_colliders.bl_idname, "Remove UVs", "MAP_OFF", "UV")
        row = col.row(align=True)
        _op(row, OBJECT_OT_strip_materials_from_colliders.bl_idname, "Strip Materials", "SPHERE_OFF", "MATERIAL")
        _op(row, OBJECT_OT_simplify_colliders.bl_idname, "Simplify", "POLYGON", "MOD_DECIM")
        _op(col, OBJECT_OT_cleanup_colliders.bl_idname, "Clean Up Colliders", "ERASER", "BRUSH_DATA")


def _draw_other(layout, props):
    box, expanded = _section_header(layout, props, "other_expanded", "Other")
    if expanded:
        col = box.column(align=True)
        col.scale_y = 1.2
        row = col.row(align=True)
        _op(row, OBJECT_OT_export_lights.bl_idname, "Export Lights", "BULB", "LIGHT_DATA")
        _op(row, OBJECT_OT_particles_to_armature_converter.bl_idname, "Particle2Armat...", "BONE", "PARTICLES")


# ---------------------------------------------------------------------------
# Panel
# ---------------------------------------------------------------------------


class VIEW3D_PT_dcl_tools(bpy.types.Panel):
    bl_label = "Decentraland Tools"
    bl_idname = "VIEW3D_PT_dcl_tools"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Decentraland Tools"

    def draw(self, context):
        layout = self.layout
        props = context.scene.dcl_tools
        tab = props.active_tab

        # ---- Tab bar ----
        row = layout.row(align=True)
        row.prop(props, "active_tab", expand=True)

        # ---- Experimental toggle ----
        layout.prop(props, "show_experimental")

        layout.separator(factor=0.5)

        # ---- Tab content ----
        if tab == TAB_ALL:
            _draw_scene_creation(layout, props)
            _draw_avatars(layout, props)
            _draw_emotes(layout, props)
            _draw_materials(layout, props)
            if props.show_experimental:
                _draw_lod(layout, props, context)
            _draw_cleanup(layout, props)
            _draw_colliders(layout, props)
            if props.show_experimental:
                _draw_other(layout, props)

        elif tab == TAB_SCENES:
            _draw_scene_creation(layout, props)
            _draw_materials(layout, props)
            if props.show_experimental:
                _draw_lod(layout, props, context)
            _draw_cleanup(layout, props)
            _draw_colliders(layout, props)
            if props.show_experimental:
                _draw_other(layout, props)

        elif tab == TAB_WEARABLES:
            _draw_avatars(layout, props)
            _draw_emotes(layout, props)
            _draw_materials(layout, props)
            if props.show_experimental:
                _draw_other(layout, props)


class VIEW3D_PT_dcl_export(bpy.types.Panel):
    bl_label = "Export"
    bl_idname = "VIEW3D_PT_dcl_export"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Decentraland Tools"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.scale_y = 1.2
        _op(col, OBJECT_OT_export_scene.bl_idname, "Export Scene", "DCL_LOGO", "SCENE_DATA")
        _op(col, OBJECT_OT_update_all_exported.bl_idname, "Update All Exported Objects", "REFRESH", "FILE_REFRESH")
        row = col.row(align=True)
        _op(row, OBJECT_OT_quick_export_gltf.bl_idname, "Export glTF", "PACKAGE_EXPORT", "EXPORT")
        _op(row, OBJECT_OT_export_emote_glb.bl_idname, "Export Emote G...", "EMOTE_EXPORT", "EXPORT")
        col.separator(factor=0.5)
        row = col.row(align=True)
        _op(row, OBJECT_OT_export_composite.bl_idname, "Export Composite", "COMPOSITE_EXPORT", "EXPORT")
        _op(row, OBJECT_OT_import_composite.bl_idname, "Import Composite", "COMPOSITE_IMPORT", "IMPORT")


class VIEW3D_PT_dcl_help(bpy.types.Panel):
    bl_label = "Help"
    bl_idname = "VIEW3D_PT_dcl_help"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "Decentraland Tools"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        col = layout.column(align=True)
        col.scale_y = 1.2
        _op(col, OBJECT_OT_open_documentation.bl_idname, "Creator Docs", "BOOK", "HELP")
        _op(col, OBJECT_OT_scene_limits_guide.bl_idname, "Limits Guide", "BOOK_2", "INFO")
        _op(col, OBJECT_OT_asset_guidelines.bl_idname, "Assets Guide", "FILE_DESC", "FILE_TEXT")
        col.separator(factor=0.5)
        _op(col, OBJECT_OT_install_dcl_theme.bl_idname, "Apply DCL Theme", "DCL_LOGO", "BRUSHES_ALL")


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (
    DCLToolsSceneProperties,
    MaterialListItem,
    OBJECT_OT_remove_uvs_from_colliders,
    OBJECT_OT_strip_materials_from_colliders,
    OBJECT_OT_rename_add_collider_suffix,
    OBJECT_OT_simplify_colliders,
    OBJECT_OT_cleanup_colliders,
    OBJECT_OT_remove_empty_objects,
    OBJECT_OT_export_lights,
    OBJECT_OT_import_dcl_rig,
    OBJECT_OT_import_dcl_prop,
    OBJECT_OT_import_dcl_limit_area,
    OBJECT_OT_validate_emote,
    OBJECT_OT_export_emote_glb,
    OBJECT_OT_create_emote_action,
    OBJECT_OT_set_emote_boundary_keyframes,
    OBJECT_OT_create_parcels,
    OBJECT_OT_set_parcel_origin,
    OBJECT_OT_apply_checker_map,
    OBJECT_OT_cleanup_checker_map,
    OBJECT_OT_rename_textures,
    OBJECT_OT_resize_textures,
    OBJECT_OT_enable_backface_culling,
    OBJECT_OT_link_avatar_wearables,
    OBJECT_OT_particles_to_armature_converter,
    OBJECT_OT_scene_limitations,
    OBJECT_OT_avatar_limitations,
    OBJECT_OT_replace_materials,
    OBJECT_OT_add_source_material_to_list,
    OBJECT_OT_remove_source_material_from_list,
    OBJECT_OT_validate_textures,
    OBJECT_OT_validate_scene,
    OBJECT_OT_generate_lod,
    OBJECT_OT_quick_export_gltf,
    OBJECT_OT_export_scene,
    OBJECT_OT_update_all_exported,
    OBJECT_OT_export_composite,
    OBJECT_OT_import_composite,
    OBJECT_OT_open_documentation,
    OBJECT_OT_scene_limits_guide,
    OBJECT_OT_asset_guidelines,
    OBJECT_OT_install_dcl_theme,
    VIEW3D_PT_dcl_tools,
    VIEW3D_PT_dcl_export,
    VIEW3D_PT_dcl_help,
)


def register():
    # Load custom icons first
    icon_loader.register()

    for cls in classes:
        register_class(cls)

    # Register the single PropertyGroup pointer on Scene
    bpy.types.Scene.dcl_tools = bpy.props.PointerProperty(type=DCLToolsSceneProperties)

    # Replace Materials operator properties (on WindowManager)
    bpy.types.WindowManager.replace_materials_add = bpy.props.StringProperty(
        name="Replace Materials Add",
        description="Temporary property for adding materials to replacement list",
        default="",
    )
    bpy.types.WindowManager.replace_materials_remove = bpy.props.IntProperty(
        name="Replace Materials Remove",
        description="Temporary property for removing materials from replacement list",
        default=-1,
    )


def unregister():
    for cls in reversed(classes):
        unregister_class(cls)

    # Unregister PropertyGroup pointer
    del bpy.types.Scene.dcl_tools

    # Unregister Replace Materials properties
    if hasattr(bpy.types.WindowManager, "replace_materials_add"):
        del bpy.types.WindowManager.replace_materials_add
    if hasattr(bpy.types.WindowManager, "replace_materials_remove"):
        del bpy.types.WindowManager.replace_materials_remove

    # Unload custom icons last
    icon_loader.unregister()


if __name__ == "__main__":
    register()
