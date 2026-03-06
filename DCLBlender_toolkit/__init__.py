bl_info = {
    "name": "Decentraland Tools",
    "author": "Decentraland Foundation",
    "version": (1, 2, 0),
    "blender": (2, 80, 0),
    "location": "3D Viewport > Sidebar (N) > Decentraland Tools",
    "description": "Collection of tools for Decentraland asset creation and optimization (Blender 2.80 - 5.0+)",
    "category": "Object",
}

import bpy
from bpy.utils import register_class, unregister_class

from . import icon_loader

from .ops.remove_uvs import OBJECT_OT_remove_uvs_from_colliders
from .ops.strip_materials import OBJECT_OT_strip_materials_from_colliders
from .ops.rename_add_suffix import OBJECT_OT_rename_add_collider_suffix
from .ops.simplify_colliders import OBJECT_OT_simplify_colliders
from .ops.cleanup_colliders import OBJECT_OT_cleanup_colliders
from .ops.export_lights import OBJECT_OT_export_lights
from .ops.create_parcels import OBJECT_OT_create_parcels
from .ops.rename_textures import OBJECT_OT_rename_textures
from .ops.enable_backface_culling import OBJECT_OT_enable_backface_culling
from .ops.link_avatar_wearables import OBJECT_OT_link_avatar_wearables
from .ops.scene_limitations import OBJECT_OT_scene_limitations
from .ops.documentation import OBJECT_OT_open_documentation, OBJECT_OT_scene_limits_guide, OBJECT_OT_asset_guidelines
from .ops.remove_empty_objects import OBJECT_OT_remove_empty_objects
from .ops.toggle_display_mode import OBJECT_OT_toggle_display_mode
from .ops.particle_to_armature import OBJECT_OT_particles_to_armature_converter
from .ops.import_dcl_rig import OBJECT_OT_import_dcl_rig, OBJECT_OT_import_dcl_prop, OBJECT_OT_import_dcl_limit_area
from .ops.validate_emote import OBJECT_OT_validate_emote
from .ops.export_emote_glb import OBJECT_OT_export_emote_glb
from .ops.emote_actions import OBJECT_OT_create_emote_action, OBJECT_OT_set_emote_boundary_keyframes
from .ops.resize_textures import OBJECT_OT_resize_textures
from .ops.apply_transforms import OBJECT_OT_apply_transforms
from .ops.avatar_limitations import OBJECT_OT_avatar_limitations
from .ops.rename_mesh_data import OBJECT_OT_rename_mesh_data
from .ops.replace_materials import (
    MaterialListItem,
    OBJECT_OT_replace_materials,
    OBJECT_OT_add_source_material_to_list,
    OBJECT_OT_remove_source_material_from_list,
)
from .ops.clean_unused_materials import OBJECT_OT_clean_unused_materials
from .ops.validate_textures import OBJECT_OT_validate_textures
from .ops.validate_scene import OBJECT_OT_validate_scene
from .ops.batch_rename import OBJECT_OT_batch_rename
from .ops.generate_lod import OBJECT_OT_generate_lod, draw_lod_panel
from .ops.quick_export_gltf import OBJECT_OT_quick_export_gltf


# ---------------------------------------------------------------------------
# Helper: draw a collapsible section header
# ---------------------------------------------------------------------------

def _section_header(layout, scene, prop_name, label):
    """Draw a collapsible section box and return (box, is_expanded)."""
    box = layout.box()
    row = box.row()
    expanded = getattr(scene, prop_name)
    row.prop(
        scene, prop_name,
        text=label,
        icon='TRIA_DOWN' if expanded else 'TRIA_RIGHT',
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
# Panel
# ---------------------------------------------------------------------------

class VIEW3D_PT_dcl_tools(bpy.types.Panel):
    bl_label = "Decentraland Tools"
    bl_idname = "VIEW3D_PT_dcl_tools"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "Decentraland Tools"

    def draw(self, context):
        layout = self.layout
        scene = context.scene

        # ---- Header ----
        header = layout.row(align=True)
        dcl_icon = icon_loader.get_icon("DCL_LOGO")
        if dcl_icon:
            header.label(text="  Decentraland Tools", icon_value=dcl_icon)
        else:
            header.label(text="  Decentraland Tools", icon='TOOL_SETTINGS')

        # ================================================================
        # Scene Creation
        # ================================================================
        box, expanded = _section_header(layout, scene, "dcl_tools_scene_expanded", "Scene Creation")
        if expanded:
            col = box.column(align=True)
            col.scale_y = 1.2
            _op(col, OBJECT_OT_create_parcels.bl_idname, "Create Parcels", "GRID_DOTS", 'MESH_PLANE')
            row = col.row(align=True)
            _op(row, OBJECT_OT_scene_limitations.bl_idname, "Scene Limitations", "RULER", 'INFO')
            _op(row, OBJECT_OT_validate_scene.bl_idname, "Scene Validator", "SHIELD_CHECK", 'SEQUENCE')

        # ================================================================
        # Avatars
        # ================================================================
        box, expanded = _section_header(layout, scene, "dcl_tools_avatars_expanded", "Avatars")
        if expanded:
            col = box.column(align=True)
            col.scale_y = 1.2
            row = col.row(align=True)
            _op(row, OBJECT_OT_link_avatar_wearables.bl_idname, "Avatar Shapes", "FRIENDS", 'ARMATURE_DATA')
            _op(row, OBJECT_OT_avatar_limitations.bl_idname, "Wearable Limits", "SHIRT_SPORT", 'INFO')

        # ================================================================
        # Emotes
        # ================================================================
        box, expanded = _section_header(layout, scene, "dcl_tools_emotes_expanded", "Emotes")
        if expanded:
            col = box.column(align=True)
            col.scale_y = 1.2

            _op(col, OBJECT_OT_import_dcl_rig.bl_idname, "Import DCL Rig", "ASSET", 'ARMATURE_DATA')
            row = col.row(align=True)
            _op(row, OBJECT_OT_import_dcl_prop.bl_idname, "Add Prop", "EMOTE_PROPS", 'OBJECT_DATA')
            _op(row, OBJECT_OT_import_dcl_limit_area.bl_idname, "Limit Area Reference", "DIMENSIONS", 'MESH_GRID')
            col.separator(factor=0.3)

            row = col.row(align=True)
            _op(row, OBJECT_OT_create_emote_action.bl_idname, "Create Emote Action", "EDIT", 'ACTION')
            _op(row, OBJECT_OT_set_emote_boundary_keyframes.bl_idname, "Set Boundary Keys", "PROGRESS_CHECK", 'KEYTYPE_JITTER_VEC')
            col.separator(factor=0.3)

            _op(col, OBJECT_OT_validate_emote.bl_idname, "Validate Emote", "PROGRESS_CHECK", 'CHECKMARK')
            col.separator(factor=0.3)

            settings = col.box()
            settings.label(text="Emote Settings")
            settings.prop(scene, "dcl_emote_start_frame")
            settings.prop(scene, "dcl_emote_end_frame")
            settings.prop(scene, "dcl_emote_sampling_rate")
            settings.prop(scene, "dcl_emote_strict_validation")

        # ================================================================
        # Materials & Textures
        # ================================================================
        box, expanded = _section_header(layout, scene, "dcl_tools_materials_expanded", "Materials & Textures")
        if expanded:
            col = box.column(align=True)
            col.scale_y = 1.2
            row = col.row(align=True)
            _op(row, OBJECT_OT_replace_materials.bl_idname, "Replace Materials", "REPLACE", 'MATERIAL_DATA')
            _op(row, OBJECT_OT_clean_unused_materials.bl_idname, "Clean Unused", "ERASER", 'BRUSH_DATA')
            col.separator(factor=0.3)
            row = col.row(align=True)
            _op(row, OBJECT_OT_resize_textures.bl_idname, "Resize Textures", "IMAGE_IN_PICTURE", 'IMAGE_DATA')
            _op(row, OBJECT_OT_validate_textures.bl_idname, "Validate Textures", "PHOTO_CHECK", 'TEXTURE')
            col.separator(factor=0.3)
            _op(col, OBJECT_OT_enable_backface_culling.bl_idname, "Enable Backface Culling", "FLIP_VERTICAL", 'NORMALS_FACE')

        # ================================================================
        # LOD Generator
        # ================================================================
        box, expanded = _section_header(layout, scene, "dcl_tools_lod_expanded", "LOD Generator")
        if expanded:
            draw_lod_panel(box, context)

        # ================================================================
        # Viewer
        # ================================================================
        box, expanded = _section_header(layout, scene, "dcl_tools_viewer_expanded", "Viewer")
        if expanded:
            col = box.column(align=True)
            col.scale_y = 1.2
            _op(col, OBJECT_OT_toggle_display_mode.bl_idname, "Toggle Display Mode", "EYE_DOTTED", 'RESTRICT_VIEW_OFF')

        # ================================================================
        # CleanUp
        # ================================================================
        box, expanded = _section_header(layout, scene, "dcl_tools_cleanup_expanded", "CleanUp")
        if expanded:
            col = box.column(align=True)
            col.scale_y = 1.2
            row = col.row(align=True)
            _op(row, OBJECT_OT_remove_empty_objects.bl_idname, "Remove Empty Objects", "TRASH_X", 'X')
            _op(row, OBJECT_OT_apply_transforms.bl_idname, "Apply Transforms", "TRANSFORM", 'SNAP_ON')
            col.separator(factor=0.3)
            row = col.row(align=True)
            _op(row, OBJECT_OT_rename_mesh_data.bl_idname, "Rename Mesh Data", "FORMS", 'MESH_DATA')
            _op(row, OBJECT_OT_rename_textures.bl_idname, "Rename Textures", "PHOTO_EDIT", 'TEXTURE')
            col.separator(factor=0.3)
            _op(col, OBJECT_OT_batch_rename.bl_idname, "Batch Rename Objects", "EDIT", 'SORTALPHA')

        # ================================================================
        # Collider Management
        # ================================================================
        box, expanded = _section_header(layout, scene, "dcl_tools_manage_expanded", "Collider Management")
        if expanded:
            col = box.column(align=True)
            col.scale_y = 1.2
            row = col.row(align=True)
            _op(row, OBJECT_OT_rename_add_collider_suffix.bl_idname, "Add Suffix", "TAG", 'OUTLINER_OB_MESH')
            _op(row, OBJECT_OT_remove_uvs_from_colliders.bl_idname, "Remove UVs", "MAP_OFF", 'UV')
            row = col.row(align=True)
            _op(row, OBJECT_OT_strip_materials_from_colliders.bl_idname, "Strip Materials", "SPHERE_OFF", 'MATERIAL')
            _op(row, OBJECT_OT_simplify_colliders.bl_idname, "Simplify", "POLYGON", 'MOD_DECIM')
            _op(col, OBJECT_OT_cleanup_colliders.bl_idname, "Clean Up Colliders", "ERASER", 'BRUSH_DATA')

        # ================================================================
        # Export
        # ================================================================
        box, expanded = _section_header(layout, scene, "dcl_tools_export_expanded", "Export")
        if expanded:
            col = box.column(align=True)
            col.scale_y = 1.2
            row = col.row(align=True)
            _op(row, OBJECT_OT_quick_export_gltf.bl_idname, "Export glTF", "PACKAGE_EXPORT", 'EXPORT')
            _op(row, OBJECT_OT_export_emote_glb.bl_idname, "Export Emote GLB", "EMOTE_EXPORT", 'EXPORT')

        # ================================================================
        # Documentation
        # ================================================================
        box, expanded = _section_header(layout, scene, "dcl_tools_docs_expanded", "Documentation")
        if expanded:
            col = box.column(align=True)
            col.scale_y = 1.3
            row = col.row(align=True)
            _op(row, OBJECT_OT_open_documentation.bl_idname, "Documentation", "BOOK", 'HELP')
            _op(row, OBJECT_OT_scene_limits_guide.bl_idname, "Limits Guide", "BOOK_2", 'INFO')
            _op(row, OBJECT_OT_asset_guidelines.bl_idname, "Asset Guide", "FILE_DESC", 'FILE_TEXT')

        # ================================================================
        # Experimental
        # ================================================================
        box, expanded = _section_header(layout, scene, "dcl_tools_experimental_expanded", "Experimental")
        if expanded:
            col = box.column(align=True)
            col.scale_y = 1.2
            row = col.row(align=True)
            _op(row, OBJECT_OT_export_lights.bl_idname, "Export Lights", "BULB", 'LIGHT_DATA')
            _op(row, OBJECT_OT_particles_to_armature_converter.bl_idname, "Particle to Armature", "BONE", 'PARTICLES')


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------

classes = (
    MaterialListItem,
    OBJECT_OT_remove_uvs_from_colliders,
    OBJECT_OT_strip_materials_from_colliders,
    OBJECT_OT_rename_add_collider_suffix,
    OBJECT_OT_simplify_colliders,
    OBJECT_OT_cleanup_colliders,
    OBJECT_OT_remove_empty_objects,
    OBJECT_OT_toggle_display_mode,
    OBJECT_OT_export_lights,
    OBJECT_OT_import_dcl_rig,
    OBJECT_OT_import_dcl_prop,
    OBJECT_OT_import_dcl_limit_area,
    OBJECT_OT_validate_emote,
    OBJECT_OT_export_emote_glb,
    OBJECT_OT_create_emote_action,
    OBJECT_OT_set_emote_boundary_keyframes,
    OBJECT_OT_create_parcels,
    OBJECT_OT_rename_textures,
    OBJECT_OT_resize_textures,
    OBJECT_OT_enable_backface_culling,
    OBJECT_OT_link_avatar_wearables,
    OBJECT_OT_particles_to_armature_converter,
    OBJECT_OT_scene_limitations,
    OBJECT_OT_apply_transforms,
    OBJECT_OT_avatar_limitations,
    OBJECT_OT_rename_mesh_data,
    OBJECT_OT_replace_materials,
    OBJECT_OT_add_source_material_to_list,
    OBJECT_OT_remove_source_material_from_list,
    OBJECT_OT_clean_unused_materials,
    OBJECT_OT_validate_textures,
    OBJECT_OT_validate_scene,
    OBJECT_OT_batch_rename,
    OBJECT_OT_generate_lod,
    OBJECT_OT_quick_export_gltf,
    OBJECT_OT_open_documentation,
    OBJECT_OT_scene_limits_guide,
    OBJECT_OT_asset_guidelines,
    VIEW3D_PT_dcl_tools,
)


def register():
    # Load custom icons first
    icon_loader.register()

    # Register properties
    bpy.types.Scene.dcl_tools_scene_expanded = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.dcl_tools_export_expanded = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.dcl_tools_avatars_expanded = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.dcl_tools_emotes_expanded = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.dcl_tools_materials_expanded = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.dcl_tools_cleanup_expanded = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.dcl_tools_viewer_expanded = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.dcl_tools_manage_expanded = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.dcl_tools_lod_expanded = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.dcl_tools_docs_expanded = bpy.props.BoolProperty(default=True)
    bpy.types.Scene.dcl_tools_experimental_expanded = bpy.props.BoolProperty(default=False)

    # Emotes workflow properties
    bpy.types.Scene.dcl_emote_start_frame = bpy.props.IntProperty(
        name="Start Frame",
        description="First frame of the emote clip",
        default=1,
        min=1,
        max=300,
    )
    bpy.types.Scene.dcl_emote_end_frame = bpy.props.IntProperty(
        name="End Frame",
        description="Last frame of the emote clip (max 300)",
        default=300,
        min=1,
        max=300,
    )
    bpy.types.Scene.dcl_emote_sampling_rate = bpy.props.IntProperty(
        name="Sampling Rate",
        description="Export bake step. 2 is recommended, 3 for extra size reduction",
        default=2,
        min=1,
        max=6,
    )
    bpy.types.Scene.dcl_emote_strict_validation = bpy.props.BoolProperty(
        name="Strict Validation",
        description="Treat warnings as blocking errors for export",
        default=False,
    )

    # LOD Generator panel properties
    bpy.types.Scene.dcl_lod_levels = bpy.props.IntProperty(
        name="LOD Levels",
        description="Number of LOD levels to generate",
        default=3,
        min=1,
        max=4,
    )
    bpy.types.Scene.dcl_lod1_ratio = bpy.props.FloatProperty(
        name="LOD 1 Ratio",
        description="Decimation ratio for LOD 1 (e.g. 0.5 = keep 50%)",
        default=0.50,
        min=0.01,
        max=0.99,
        subtype='FACTOR',
    )
    bpy.types.Scene.dcl_lod2_ratio = bpy.props.FloatProperty(
        name="LOD 2 Ratio",
        description="Decimation ratio for LOD 2",
        default=0.15,
        min=0.01,
        max=0.99,
        subtype='FACTOR',
    )
    bpy.types.Scene.dcl_lod3_ratio = bpy.props.FloatProperty(
        name="LOD 3 Ratio",
        description="Decimation ratio for LOD 3",
        default=0.05,
        min=0.01,
        max=0.99,
        subtype='FACTOR',
    )
    bpy.types.Scene.dcl_lod4_ratio = bpy.props.FloatProperty(
        name="LOD 4 Ratio",
        description="Decimation ratio for LOD 4",
        default=0.02,
        min=0.01,
        max=0.99,
        subtype='FACTOR',
    )
    bpy.types.Scene.dcl_lod_create_collection = bpy.props.BoolProperty(
        name="Create LOD Collection",
        description="Place generated LODs in a dedicated collection",
        default=True,
    )

    # Particle System Converter properties
    bpy.types.Scene.ps_converter_out_collection = bpy.props.StringProperty(
        name="Output Collection",
        description="Collection name for converted armature and objects",
        default="ParticleArmature_Output"
    )
    bpy.types.Scene.ps_converter_start_frame = bpy.props.IntProperty(
        name="Start Frame",
        description="Start frame for animation conversion",
        default=1,
        min=1
    )
    bpy.types.Scene.ps_converter_end_frame = bpy.props.IntProperty(
        name="End Frame",
        description="End frame for animation conversion",
        default=250,
        min=1
    )

    # Replace Materials operator properties
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

    for cls in classes:
        register_class(cls)


def unregister():
    for cls in reversed(classes):
        unregister_class(cls)

    # Unregister properties
    del bpy.types.Scene.dcl_tools_scene_expanded
    del bpy.types.Scene.dcl_tools_export_expanded
    del bpy.types.Scene.dcl_tools_avatars_expanded
    del bpy.types.Scene.dcl_tools_emotes_expanded
    del bpy.types.Scene.dcl_tools_materials_expanded
    del bpy.types.Scene.dcl_tools_cleanup_expanded
    del bpy.types.Scene.dcl_tools_viewer_expanded
    del bpy.types.Scene.dcl_tools_manage_expanded
    del bpy.types.Scene.dcl_tools_lod_expanded
    del bpy.types.Scene.dcl_tools_docs_expanded
    del bpy.types.Scene.dcl_tools_experimental_expanded

    # Unregister Emotes properties
    del bpy.types.Scene.dcl_emote_start_frame
    del bpy.types.Scene.dcl_emote_end_frame
    del bpy.types.Scene.dcl_emote_sampling_rate
    del bpy.types.Scene.dcl_emote_strict_validation

    # Unregister LOD Generator properties
    del bpy.types.Scene.dcl_lod_levels
    del bpy.types.Scene.dcl_lod1_ratio
    del bpy.types.Scene.dcl_lod2_ratio
    del bpy.types.Scene.dcl_lod3_ratio
    del bpy.types.Scene.dcl_lod4_ratio
    del bpy.types.Scene.dcl_lod_create_collection

    # Unregister Particle System Converter properties
    del bpy.types.Scene.ps_converter_out_collection
    del bpy.types.Scene.ps_converter_start_frame
    del bpy.types.Scene.ps_converter_end_frame

    # Unregister Replace Materials properties
    if hasattr(bpy.types.WindowManager, 'replace_materials_add'):
        del bpy.types.WindowManager.replace_materials_add
    if hasattr(bpy.types.WindowManager, 'replace_materials_remove'):
        del bpy.types.WindowManager.replace_materials_remove

    # Unload custom icons last
    icon_loader.unregister()


if __name__ == "__main__":
    register()
