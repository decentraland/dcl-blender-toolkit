"""Install and apply the Decentraland Theme from the Blender Extensions Platform."""

import os

import bpy


class OBJECT_OT_install_dcl_theme(bpy.types.Operator):
    bl_idname = "object.install_dcl_theme"
    bl_label = "Apply DCL Theme"
    bl_description = "Install and enable the Decentraland Theme from the Blender Extensions Platform"

    def _find_repo_index(self):
        """Find the index of the blender_org extensions repo."""
        for i, repo in enumerate(bpy.context.preferences.extensions.repos):
            if repo.module == "blender_org":
                return i
        return None

    def execute(self, context):
        pkg_id = "Decentraland_Theme"

        repo_index = self._find_repo_index()
        if repo_index is None:
            self.report({"ERROR"}, "Blender Extensions repository not found. Enable it in Preferences.")
            return {"CANCELLED"}

        # Check if already installed
        ext_dir = bpy.utils.user_resource("EXTENSIONS")
        theme_dir = os.path.join(ext_dir, "blender_org", pkg_id)

        if not os.path.isdir(theme_dir):
            try:
                bpy.ops.extensions.package_install(repo_index=repo_index, pkg_id=pkg_id)
            except Exception as exc:
                self.report({"ERROR"}, f"Failed to install theme: {exc}")
                return {"CANCELLED"}

        # Enable the theme
        try:
            bpy.ops.extensions.package_theme_enable(repo_index=repo_index, pkg_id=pkg_id)
            self.report({"INFO"}, "Decentraland Theme applied")
        except Exception as exc:
            self.report({"ERROR"}, f"Failed to enable theme: {exc}")
            return {"CANCELLED"}

        return {"FINISHED"}
