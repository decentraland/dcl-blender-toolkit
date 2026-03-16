import os
import tempfile

import bpy


def _has_alpha_channel(image):
    """Check if image actually uses its alpha channel (has non-opaque pixels)."""
    try:
        if not image or not image.pixels:
            return False
        if len(image.pixels) % 4 != 0:
            return False

        pixels = image.pixels[:]
        alpha_values = pixels[3::4]

        sample_step = max(1, len(alpha_values) // 1000)
        for i in range(0, len(alpha_values), sample_step):
            if alpha_values[i] < 0.98:
                return True
        return False
    except Exception:
        return False


class OBJECT_OT_compress_textures(bpy.types.Operator):
    bl_idname = "object.compress_textures"
    bl_label = "Compress Images"
    bl_description = (
        "Compress textures to JPEG or PNG to reduce file size. "
        "Optionally force JPEG for images without alpha transparency"
    )
    bl_options = {"REGISTER", "UNDO"}

    texture_format: bpy.props.EnumProperty(
        name="Format",
        description="Output compression format",
        items=[
            ("AUTO", "Auto", "JPEG for opaque images, PNG for images with alpha"),
            ("JPEG", "JPEG", "Convert all textures to JPEG (discards alpha)"),
            ("PNG", "PNG", "Keep all textures as PNG"),
        ],
        default="AUTO",
    )

    jpeg_quality: bpy.props.IntProperty(
        name="JPEG Quality",
        description="JPEG compression quality (lower = smaller file, worse quality)",
        default=80,
        min=1,
        max=100,
    )

    force_jpeg_no_alpha: bpy.props.BoolProperty(
        name="Force JPEG When No Alpha",
        description=(
            "Convert PNG textures to JPEG when they don't use transparency. "
            "Significantly reduces file size for opaque textures"
        ),
        default=True,
    )

    scope_all_textures: bpy.props.BoolProperty(
        name="All Textures",
        description="Compress all textures in the scene",
        default=False,
    )

    scope_selected_objects: bpy.props.BoolProperty(
        name="Selected Objects Only",
        description="Compress only textures used by selected objects",
        default=True,
    )

    def _collect_textures(self, context):
        """Gather the set of images to process based on scope settings."""
        images = []

        if self.scope_all_textures:
            for img in bpy.data.images:
                if img.name.startswith("Render Result") or img.name.startswith("Viewer Node"):
                    continue
                if img.size[0] == 0 or img.size[1] == 0:
                    continue
                images.append(img)

        elif self.scope_selected_objects and context.selected_objects:
            seen = set()
            for obj in context.selected_objects:
                if obj.type != "MESH" or not obj.data.materials:
                    continue
                for mat in obj.data.materials:
                    if not mat or not mat.use_nodes:
                        continue
                    for node in mat.node_tree.nodes:
                        if node.type == "TEX_IMAGE" and node.image and node.image.name not in seen:
                            seen.add(node.image.name)
                            images.append(node.image)

        return images

    def _choose_format(self, image):
        """Decide whether to output JPEG or PNG for a given image."""
        if self.texture_format == "JPEG":
            return "JPEG"
        if self.texture_format == "PNG":
            return "PNG"

        # AUTO mode
        if self.force_jpeg_no_alpha:
            if _has_alpha_channel(image):
                return "PNG"
            return "JPEG"

        # AUTO without force: keep original format
        if image.file_format in ("JPEG", "JPG"):
            return "JPEG"
        return "PNG"

    def _compress_image(self, image, target_format):
        """Apply compression by re-encoding the image data in-place."""
        was_packed = image.packed_file is not None
        original_format = image.file_format

        if target_format == "JPEG":
            temp_path = os.path.join(tempfile.gettempdir(), f"dcl_compress_{image.name}.jpg")

            saved_quality = bpy.context.scene.render.image_settings.quality
            saved_format = bpy.context.scene.render.image_settings.file_format

            try:
                bpy.context.scene.render.image_settings.file_format = "JPEG"
                bpy.context.scene.render.image_settings.quality = self.jpeg_quality
                image.save_render(temp_path)

                image.filepath = temp_path
                image.file_format = "JPEG"
                image.source = "FILE"
                image.reload()

                if was_packed:
                    image.pack()
            finally:
                bpy.context.scene.render.image_settings.quality = saved_quality
                bpy.context.scene.render.image_settings.file_format = saved_format
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

        elif target_format == "PNG":
            if original_format == "PNG" and was_packed:
                return

            temp_path = os.path.join(tempfile.gettempdir(), f"dcl_compress_{image.name}.png")

            saved_format = bpy.context.scene.render.image_settings.file_format
            saved_compression = bpy.context.scene.render.image_settings.compression

            try:
                bpy.context.scene.render.image_settings.file_format = "PNG"
                bpy.context.scene.render.image_settings.compression = 90
                image.save_render(temp_path)

                image.filepath = temp_path
                image.file_format = "PNG"
                image.source = "FILE"
                image.reload()

                if was_packed:
                    image.pack()
            finally:
                bpy.context.scene.render.image_settings.file_format = saved_format
                bpy.context.scene.render.image_settings.compression = saved_compression
                try:
                    os.remove(temp_path)
                except OSError:
                    pass

        image.update()

    def execute(self, context):
        images = self._collect_textures(context)
        if not images:
            self.report({"WARNING"}, "No textures found. Select objects or enable 'All Textures'")
            return {"CANCELLED"}

        compressed = 0
        jpeg_count = 0
        png_count = 0

        for image in images:
            try:
                fmt = self._choose_format(image)
                self._compress_image(image, fmt)
                compressed += 1
                if fmt == "JPEG":
                    jpeg_count += 1
                else:
                    png_count += 1
            except Exception as e:
                self.report({"ERROR"}, f"Failed to compress '{image.name}': {e}")

        parts = []
        if jpeg_count:
            parts.append(f"{jpeg_count} as JPEG")
        if png_count:
            parts.append(f"{png_count} as PNG")
        detail = ", ".join(parts)

        self.report({"INFO"}, f"Compressed {compressed} texture(s) ({detail})")
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout

        layout.prop(self, "texture_format")

        col = layout.column()
        col.enabled = self.texture_format in ("AUTO", "JPEG")
        col.prop(self, "jpeg_quality", slider=True)

        col = layout.column()
        col.enabled = self.texture_format == "AUTO"
        col.prop(self, "force_jpeg_no_alpha")

        layout.separator()
        layout.prop(self, "scope_all_textures")
        layout.prop(self, "scope_selected_objects")

        layout.separator()
        layout.label(text="AUTO: uses JPEG for opaque, PNG for transparent", icon="INFO")
        layout.label(text="Force JPEG skips alpha check and always converts", icon="INFO")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=380)
