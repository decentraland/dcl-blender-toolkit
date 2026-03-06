import bpy


class OBJECT_OT_validate_textures(bpy.types.Operator):
    bl_idname = "object.validate_textures"
    bl_label = "Validate Textures"
    bl_description = "Check all textures for Decentraland/glTF compatibility (power-of-two, size, format)"
    bl_options = {"REGISTER", "UNDO"}

    max_size: bpy.props.IntProperty(
        name="Max Size (px)",
        description="Maximum recommended texture dimension in pixels",
        default=1024,
        min=64,
        max=4096,
    )

    def _is_power_of_two(self, n):
        return n > 0 and (n & (n - 1)) == 0

    def _get_all_textures(self):
        """Collect all texture images, skipping internal ones."""
        textures = []
        for img in bpy.data.images:
            if img.name.startswith("Render Result") or img.name.startswith("Viewer Node"):
                continue
            if img.size[0] == 0 or img.size[1] == 0:
                continue
            textures.append(img)
        return textures

    def _validate_texture(self, image):
        """Return a list of (level, message) tuples for one image."""
        issues = []
        w, h = image.size[0], image.size[1]
        name = image.name

        # Power-of-two check
        if not self._is_power_of_two(w) or not self._is_power_of_two(h):
            issues.append(("ERROR", f"Non-power-of-two ({w}x{h})"))

        # Oversized check
        if w > self.max_size or h > self.max_size:
            issues.append(("WARNING", f"Oversized ({w}x{h} > {self.max_size})"))

        # Non-square check
        if w != h:
            issues.append(("WARNING", f"Non-square ({w}x{h})"))

        # Format check for glTF compatibility
        filepath = image.filepath.lower() if image.filepath else ""
        if image.packed_file:
            fmt = image.file_format.upper() if image.file_format else ""
            if fmt not in ("PNG", "JPEG", "JPG", ""):
                issues.append(("ERROR", f"Unsupported format '{fmt}' (glTF needs PNG/JPG)"))
        elif filepath:
            if not filepath.endswith((".png", ".jpg", ".jpeg")):
                ext = filepath.rsplit(".", 1)[-1] if "." in filepath else "unknown"
                issues.append(("ERROR", f"Unsupported format '.{ext}' (glTF needs PNG/JPG)"))

        return issues

    def execute(self, context):
        textures = self._get_all_textures()
        if not textures:
            self.report({"INFO"}, "No textures found in the scene")
            return {"FINISHED"}

        total_issues = 0
        for img in textures:
            issues = self._validate_texture(img)
            total_issues += len(issues)

        if total_issues == 0:
            self.report({"INFO"}, f"All {len(textures)} textures passed validation")
        else:
            self.report(
                {"WARNING"}, f"Found {total_issues} issue(s) across {len(textures)} textures. See dialog for details."
            )
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "max_size")
        layout.separator()

        textures = self._get_all_textures()
        if not textures:
            layout.label(text="No textures found in the scene", icon="INFO")
            return

        passed = []
        warned = []
        errored = []

        for img in textures:
            issues = self._validate_texture(img)
            if not issues:
                passed.append(img)
            else:
                has_error = any(level == "ERROR" for level, _ in issues)
                if has_error:
                    errored.append((img, issues))
                else:
                    warned.append((img, issues))

        # Errors
        if errored:
            box = layout.box()
            box.label(text=f"{len(errored)} texture(s) with errors:", icon="ERROR")
            for img, issues in errored[:15]:
                col = box.column(align=True)
                col.label(text=f"{img.name} ({img.size[0]}x{img.size[1]})")
                for level, msg in issues:
                    icon = "ERROR" if level == "ERROR" else "WARNING"
                    col.label(text=f"    {msg}", icon=icon)
            if len(errored) > 15:
                box.label(text=f"    ... and {len(errored) - 15} more")

        # Warnings
        if warned:
            box = layout.box()
            box.label(text=f"{len(warned)} texture(s) with warnings:", icon="WARNING")
            for img, issues in warned[:15]:
                col = box.column(align=True)
                col.label(text=f"{img.name} ({img.size[0]}x{img.size[1]})")
                for _level, msg in issues:
                    col.label(text=f"    {msg}", icon="WARNING")
            if len(warned) > 15:
                box.label(text=f"    ... and {len(warned) - 15} more")

        # Passed
        if passed:
            box = layout.box()
            box.label(text=f"{len(passed)} texture(s) OK", icon="CHECKMARK")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=450)
