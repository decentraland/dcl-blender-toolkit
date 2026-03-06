import bpy

from .scene_utils import calculate_limits, count_current_usage, status_icon, usage_percentage


class OBJECT_OT_validate_scene(bpy.types.Operator):
    bl_idname = "object.validate_scene"
    bl_label = "Scene Validator"
    bl_description = "Pre-flight check: validate the entire scene against Decentraland limits"
    bl_options = {"REGISTER", "UNDO"}

    parcel_count: bpy.props.IntProperty(
        name="Parcel Count",
        description="Number of parcels in your scene (e.g., 2x2 = 4 parcels)",
        default=4,
        min=1,
        max=100,
    )

    # --- extra checks ---

    def _check_non_applied_transforms(self):
        """Return objects with non-identity rotation or scale."""
        objs = []
        for obj in bpy.data.objects:
            if obj.type != "MESH":
                continue
            rot = obj.rotation_euler
            scl = obj.scale
            if (
                abs(scl.x - 1) > 0.001
                or abs(scl.y - 1) > 0.001
                or abs(scl.z - 1) > 0.001
                or abs(rot.x) > 0.001
                or abs(rot.y) > 0.001
                or abs(rot.z) > 0.001
            ):
                objs.append(obj.name)
        return objs

    def _check_missing_materials(self):
        """Return objects that have empty material slots."""
        objs = []
        for obj in bpy.data.objects:
            if obj.type != "MESH":
                continue
            for slot in obj.material_slots:
                if slot.material is None:
                    objs.append(obj.name)
                    break
        return objs

    def _check_non_pot_textures(self):
        """Return textures that are not power-of-two."""
        bad = []
        for img in bpy.data.images:
            if img.name.startswith("Render Result") or img.name.startswith("Viewer Node"):
                continue
            if img.size[0] == 0 or img.size[1] == 0:
                continue
            w, h = img.size[0], img.size[1]
            if not (w > 0 and (w & (w - 1)) == 0) or not (h > 0 and (h & (h - 1)) == 0):
                bad.append(f"{img.name} ({w}x{h})")
        return bad

    # --- operator ---

    def execute(self, context):
        limits = calculate_limits(self.parcel_count)
        usage = count_current_usage()

        warnings = 0
        for key in ("triangles", "entities", "bodies", "materials", "textures", "height"):
            if usage[key] > limits[key]:
                warnings += 1

        transforms = self._check_non_applied_transforms()
        missing_mats = self._check_missing_materials()
        non_pot = self._check_non_pot_textures()

        if transforms:
            warnings += 1
        if missing_mats:
            warnings += 1
        if non_pot:
            warnings += 1

        if warnings == 0:
            self.report({"INFO"}, "Scene validation passed - all checks OK")
        else:
            self.report({"WARNING"}, f"Scene validation: {warnings} issue(s) found")
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "parcel_count")
        layout.separator()

        limits = calculate_limits(self.parcel_count)
        usage = count_current_usage()

        # Limit checks
        box = layout.box()
        box.label(text="DCL Limits:", icon="INFO")
        col = box.column(align=True)

        for key, label in [
            ("triangles", "Triangles"),
            ("entities", "Entities"),
            ("bodies", "Bodies"),
            ("materials", "Materials"),
            ("textures", "Textures"),
            ("height", "Height (m)"),
        ]:
            pct = usage_percentage(usage[key], limits[key])
            icon = status_icon(pct)
            col.label(text=f"{label}: {usage[key]:,} / {limits[key]:,} ({pct}%)", icon=icon)

        # Extra checks
        transforms = self._check_non_applied_transforms()
        missing_mats = self._check_missing_materials()
        non_pot = self._check_non_pot_textures()

        layout.separator()
        box = layout.box()
        box.label(text="Additional Checks:", icon="INFO")
        col = box.column(align=True)

        # Transforms
        if transforms:
            col.label(text=f"Non-applied transforms: {len(transforms)} object(s)", icon="WARNING")
            for name in transforms[:5]:
                col.label(text=f"    {name}")
            if len(transforms) > 5:
                col.label(text=f"    ... and {len(transforms) - 5} more")
        else:
            col.label(text="Transforms: All applied", icon="CHECKMARK")

        # Missing materials
        if missing_mats:
            col.label(text=f"Missing materials: {len(missing_mats)} object(s)", icon="WARNING")
            for name in missing_mats[:5]:
                col.label(text=f"    {name}")
            if len(missing_mats) > 5:
                col.label(text=f"    ... and {len(missing_mats) - 5} more")
        else:
            col.label(text="Materials: All assigned", icon="CHECKMARK")

        # Non-PoT textures
        if non_pot:
            col.label(text=f"Non-power-of-two textures: {len(non_pot)}", icon="ERROR")
            for t in non_pot[:5]:
                col.label(text=f"    {t}")
            if len(non_pot) > 5:
                col.label(text=f"    ... and {len(non_pot) - 5} more")
        else:
            col.label(text="Textures: All power-of-two", icon="CHECKMARK")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=450)
