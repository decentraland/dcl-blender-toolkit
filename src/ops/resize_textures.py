import os

import bpy


class OBJECT_OT_resize_textures(bpy.types.Operator):
    bl_idname = "object.resize_textures"
    bl_label = "Resize Textures"
    bl_description = "Resize textures to reduce file size and optimize for Decentraland"
    bl_options = {"REGISTER", "UNDO"}

    target_size: bpy.props.EnumProperty(
        name="Target Size",
        description="Target texture resolution",
        items=[
            ("1024", "1024x1024", "Resize to 1024x1024 pixels"),
            ("512", "512x512", "Resize to 512x512 pixels"),
            ("256", "256x256", "Resize to 256x256 pixels"),
            ("128", "128x128", "Resize to 128x128 pixels"),
            ("64", "64x64", "Resize to 64x64 pixels"),
        ],
        default="512",
    )

    scope_all_textures: bpy.props.BoolProperty(
        name="All Textures",
        description="Resize all textures in the scene (recommended if some textures are missing)",
        default=False,
    )

    scope_selected_objects: bpy.props.BoolProperty(
        name="Selected Objects Only",
        description="Resize only textures used by selected objects",
        default=True,
    )

    backup_original: bpy.props.BoolProperty(
        name="Backup Original",
        description="Keep backup of original textures",
        default=True,
    )

    def execute(self, context):
        if not bpy.data.images:
            self.report({"WARNING"}, "No textures found in the scene")
            return {"CANCELLED"}

        target_size_int = int(self.target_size)
        processed_count = 0
        skipped_count = 0

        # Determine which textures to process
        textures_to_process = []

        if self.scope_all_textures:
            for img in bpy.data.images:
                if not img.name.startswith("Render Result") and not img.name.startswith("Viewer Node"):
                    textures_to_process.append(img)
        elif self.scope_selected_objects and context.selected_objects:
            for obj in context.selected_objects:
                if obj.type == "MESH" and obj.data.materials:
                    for mat in obj.data.materials:
                        if mat and mat.use_nodes:
                            for node in mat.node_tree.nodes:
                                if node.type == "TEX_IMAGE" and node.image:
                                    if node.image not in textures_to_process:
                                        textures_to_process.append(node.image)
        else:
            self.report({"WARNING"}, "Please select objects or choose 'All Textures'")
            return {"CANCELLED"}

        if not textures_to_process:
            self.report({"WARNING"}, "No textures found to resize")
            return {"CANCELLED"}

        # Process each texture
        for image in textures_to_process:
            try:
                # Skip if already at target size or smaller
                if image.size[0] <= target_size_int and image.size[1] <= target_size_int:
                    skipped_count += 1
                    continue

                # Create backup if requested
                if self.backup_original:
                    backup_name = f"{image.name}_backup_{image.size[0]}x{image.size[1]}"
                    if backup_name not in bpy.data.images:
                        backup_image = bpy.data.images.new(backup_name, image.size[0], image.size[1])
                        backup_image.pixels[:] = image.pixels[:]
                        backup_image.filepath = image.filepath

                original_size = f"{image.size[0]}x{image.size[1]}"
                original_name = image.name
                original_filepath = image.filepath

                image.update()
                image.scale(target_size_int, target_size_int)
                image.update()

                if image.size[0] == target_size_int and image.size[1] == target_size_int:
                    # Update name
                    name_base, name_ext = os.path.splitext(original_name)
                    if name_ext.lower() in (".png", ".jpg", ".jpeg", ".tga", ".bmp", ".tiff", ".exr", ".hdr"):
                        image.name = f"{name_base}_{target_size_int}x{target_size_int}{name_ext}"
                    else:
                        image.name = f"{original_name}_{target_size_int}x{target_size_int}"

                    # Save the resized image to disk
                    if original_filepath:
                        filepath = bpy.path.abspath(original_filepath)
                        if os.path.exists(filepath):
                            name, ext = os.path.splitext(filepath)
                            new_filepath = f"{name}_{target_size_int}x{target_size_int}{ext}"

                            try:
                                image.save_render(new_filepath)
                            except Exception:
                                try:
                                    image.filepath = new_filepath
                                    image.save()
                                except Exception:
                                    pass

                    processed_count += 1
                    self.report(
                        {"INFO"}, f"Resized '{image.name}' from {original_size} to {target_size_int}x{target_size_int}"
                    )
                else:
                    self.report({"WARNING"}, f"Failed to resize '{image.name}' - size unchanged")

            except Exception as e:
                self.report({"ERROR"}, f"Failed to resize '{image.name}': {str(e)}")

        if processed_count > 0:
            self.report(
                {"INFO"}, f"Successfully resized {processed_count} texture(s) to {target_size_int}x{target_size_int}"
            )
        if skipped_count > 0:
            self.report({"INFO"}, f"Skipped {skipped_count} texture(s) (already at target size or smaller)")

        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout

        col = layout.column()
        col.prop(self, "target_size", expand=True)

        layout.separator()
        layout.prop(self, "scope_all_textures")
        layout.prop(self, "scope_selected_objects")

        layout.separator()
        layout.prop(self, "backup_original")

        layout.separator()
        layout.label(text="This will resize textures to reduce file size")
        layout.label(text="and optimize performance for Decentraland")
        layout.separator()
        layout.label(text="Tip: Use 'All Textures' if some textures", icon="INFO")
        layout.label(text="are not being detected from selected objects")
        layout.separator()
        layout.label(text="Note: This modifies the actual image data", icon="ERROR")
        layout.label(text="Use backup option to preserve originals")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
