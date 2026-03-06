import bpy


class OBJECT_OT_clean_unused_materials(bpy.types.Operator):
    bl_idname = "object.clean_unused_materials"
    bl_label = "Clean Unused Materials"
    bl_description = (
        "Remove unused materials: slots not referenced by any face, and/or globally orphan materials with zero users"
    )
    bl_options = {"REGISTER", "UNDO"}

    clean_unused_slots: bpy.props.BoolProperty(
        name="Remove Unused Slots from Objects",
        description=("Remove material slots that are assigned to an object but not used by any face in the mesh"),
        default=True,
    )

    clean_orphan_materials: bpy.props.BoolProperty(
        name="Remove Orphan Materials",
        description="Remove materials with zero users in the blend file",
        default=True,
    )

    include_fake_user: bpy.props.BoolProperty(
        name="Include Fake-User Materials",
        description="Also remove orphan materials that only have a fake user",
        default=False,
    )

    scope_selected: bpy.props.BoolProperty(
        name="Selected Objects Only",
        description="Only clean material slots on selected objects (otherwise all objects)",
        default=False,
    )

    # ---- analysis helpers ----

    def _get_unused_slots(self):
        """Find material slots on mesh objects that no face references.

        Returns a list of (object, slot_index, material_name) tuples.
        """
        unused = []
        objects = bpy.context.selected_objects if self.scope_selected else list(bpy.data.objects)

        for obj in objects:
            if obj.type != "MESH" or obj.data is None:
                continue
            if not obj.material_slots:
                continue

            # Gather which slot indices are actually used by polygons
            used_indices = set()
            for poly in obj.data.polygons:
                used_indices.add(poly.material_index)

            for idx, slot in enumerate(obj.material_slots):
                if idx not in used_indices:
                    mat_name = slot.material.name if slot.material else "<Empty>"
                    unused.append((obj, idx, mat_name))

        return unused

    def _get_orphan_materials(self):
        """Find materials with zero real users in the blend file."""
        orphans = []
        for mat in bpy.data.materials:
            real_users = mat.users
            if mat.use_fake_user:
                real_users -= 1
            if real_users <= 0:
                orphans.append(mat)
        return orphans

    # ---- execute ----

    def execute(self, context):
        slots_removed = 0
        orphans_removed = 0

        # --- Phase 1: remove unused material slots from objects ---
        if self.clean_unused_slots:
            objects = context.selected_objects if self.scope_selected else list(bpy.data.objects)
            # Save and restore selection after slot removal
            original_active = context.active_object
            original_selection = list(context.selected_objects)

            for obj in objects:
                if obj.type != "MESH" or obj.data is None:
                    continue
                if not obj.material_slots:
                    continue

                used_indices = set()
                for poly in obj.data.polygons:
                    used_indices.add(poly.material_index)

                # Collect unused slot indices (reverse order for safe removal)
                unused_indices = sorted(
                    [i for i in range(len(obj.material_slots)) if i not in used_indices],
                    reverse=True,
                )
                if not unused_indices:
                    continue

                # Activate the object so we can remove slots
                bpy.ops.object.select_all(action="DESELECT")
                obj.select_set(True)
                context.view_layer.objects.active = obj

                for idx in unused_indices:
                    obj.active_material_index = idx
                    bpy.ops.object.material_slot_remove()
                    slots_removed += 1

            # Restore selection
            bpy.ops.object.select_all(action="DESELECT")
            for obj in original_selection:
                try:
                    if obj.name in bpy.data.objects:
                        bpy.data.objects[obj.name].select_set(True)
                except (ReferenceError, RuntimeError):
                    pass
            if original_active:
                try:
                    if original_active.name in bpy.data.objects:
                        context.view_layer.objects.active = bpy.data.objects[original_active.name]
                except (ReferenceError, RuntimeError):
                    pass

        # --- Phase 2: remove globally orphan materials ---
        if self.clean_orphan_materials:
            orphans = self._get_orphan_materials()
            if not self.include_fake_user:
                orphans = [m for m in orphans if not m.use_fake_user]

            for mat in orphans:
                bpy.data.materials.remove(mat)
                orphans_removed += 1

        # Report
        parts = []
        if slots_removed:
            parts.append(f"{slots_removed} unused slot(s) removed")
        if orphans_removed:
            parts.append(f"{orphans_removed} orphan material(s) deleted")
        if parts:
            self.report({"INFO"}, " | ".join(parts))
        else:
            self.report({"INFO"}, "No unused materials found")

        return {"FINISHED"}

    # ---- dialog UI ----

    def draw(self, context):
        layout = self.layout

        # --- Unused slots section ---
        layout.prop(self, "clean_unused_slots")

        if self.clean_unused_slots:
            box = layout.box()
            box.prop(self, "scope_selected")

            unused_slots = self._get_unused_slots()
            if unused_slots:
                box.label(
                    text=f"{len(unused_slots)} unused slot(s) on objects:",
                    icon="ERROR",
                )
                # Group by object
                by_obj = {}
                for obj, _idx, mat_name in unused_slots:
                    by_obj.setdefault(obj.name, []).append(mat_name)

                shown = 0
                for obj_name, mats in sorted(by_obj.items()):
                    if shown >= 12:
                        remaining = sum(len(v) for v in by_obj.values()) - shown
                        box.label(text=f"  ... and {remaining} more")
                        break
                    mat_list = ", ".join(mats[:3])
                    if len(mats) > 3:
                        mat_list += f" (+{len(mats) - 3})"
                    box.label(text=f"  {obj_name}: {mat_list}")
                    shown += len(mats)
            else:
                box.label(text="All slots are in use", icon="CHECKMARK")

        layout.separator()

        # --- Orphan materials section ---
        layout.prop(self, "clean_orphan_materials")

        if self.clean_orphan_materials:
            box = layout.box()
            box.prop(self, "include_fake_user")

            orphans = self._get_orphan_materials()
            fake_only = [m for m in orphans if m.use_fake_user]
            no_users = [m for m in orphans if not m.use_fake_user]

            if no_users:
                box.label(
                    text=f"{len(no_users)} with zero users:",
                    icon="ERROR",
                )
                for mat in no_users[:10]:
                    box.label(text=f"  {mat.name}")
                if len(no_users) > 10:
                    box.label(text=f"  ... and {len(no_users) - 10} more")

            if fake_only:
                box.label(
                    text=f"{len(fake_only)} with fake user only:",
                    icon="WARNING",
                )
                for mat in fake_only[:6]:
                    box.label(text=f"  {mat.name}")
                if len(fake_only) > 6:
                    box.label(text=f"  ... and {len(fake_only) - 6} more")

            if not no_users and not fake_only:
                box.label(text="No orphan materials", icon="CHECKMARK")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=420)
