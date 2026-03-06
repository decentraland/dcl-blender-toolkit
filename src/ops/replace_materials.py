import bpy


class MaterialListItem(bpy.types.PropertyGroup):
    """Property group for material list items"""

    material_name: bpy.props.StringProperty(
        name="Material Name",
        description="Name of the material to replace",
        default="",
    )


class OBJECT_OT_replace_materials(bpy.types.Operator):
    bl_idname = "object.replace_materials"
    bl_label = "Replace Materials"
    bl_description = "Replace one or more materials with another across all objects or selected objects"
    bl_options = {"REGISTER", "UNDO"}

    scope_selected: bpy.props.BoolProperty(
        name="Only Selected Objects",
        description="Replace materials only on selected objects",
        default=False,
    )

    source_material_temp: bpy.props.StringProperty(
        name="Source Material",
        description="Material to add to replacement list",
        default="",
    )

    target_material: bpy.props.StringProperty(
        name="Target Material",
        description="Material to replace with",
        default="",
    )

    source_materials: bpy.props.CollectionProperty(type=MaterialListItem)
    source_material_index: bpy.props.IntProperty(default=0)

    def execute(self, context):
        if bpy.context.mode != "OBJECT":
            try:
                bpy.ops.object.mode_set(mode="OBJECT")
            except Exception:
                pass

        # Get target material
        target_mat_name = self.target_material

        if not target_mat_name:
            self.report({"ERROR"}, "Please select a target material")
            return {"CANCELLED"}

        # Get source materials from collection
        source_mat_names = [item.material_name for item in self.source_materials if item.material_name]

        if not source_mat_names:
            self.report({"ERROR"}, "Please add at least one source material to replace")
            return {"CANCELLED"}

        # Validate target material
        if target_mat_name not in bpy.data.materials:
            self.report({"ERROR"}, f"Target material '{target_mat_name}' not found")
            return {"CANCELLED"}

        target_material = bpy.data.materials[target_mat_name]

        # Validate and get source materials
        source_materials = []
        for mat_name in source_mat_names:
            if mat_name == target_mat_name:
                self.report({"WARNING"}, f"Skipping '{mat_name}' - source and target cannot be the same")
                continue
            if mat_name not in bpy.data.materials:
                self.report({"WARNING"}, f"Source material '{mat_name}' not found, skipping")
                continue
            source_materials.append(bpy.data.materials[mat_name])

        if not source_materials:
            self.report({"ERROR"}, "No valid source materials to replace")
            return {"CANCELLED"}

        # Get objects to process
        objects = context.selected_objects if self.scope_selected else bpy.data.objects
        affected_objects = 0
        replaced_slots = 0

        for obj in objects:
            if obj.type != "MESH":
                continue

            obj_affected = False
            # Check each material slot
            for slot in obj.material_slots:
                if slot.material in source_materials:
                    slot.material = target_material
                    replaced_slots += 1
                    obj_affected = True

            if obj_affected:
                affected_objects += 1

        source_list = ", ".join([mat.name for mat in source_materials])
        self.report(
            {"INFO"},
            f"Replaced {len(source_materials)} material(s) ({source_list}) with '{target_mat_name}' on {affected_objects} objects ({replaced_slots} slots)",
        )
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout

        # Handle add/remove operations from window manager
        wm = context.window_manager

        # Check if we need to add a material
        if hasattr(bpy.types.WindowManager, "replace_materials_add") and hasattr(wm, "replace_materials_add"):
            if wm.replace_materials_add:
                mat_name = wm.replace_materials_add
                if mat_name and mat_name in bpy.data.materials:
                    # Check if already in list
                    if not any(item.material_name == mat_name for item in self.source_materials):
                        item = self.source_materials.add()
                        item.material_name = mat_name
                wm.replace_materials_add = ""

        # Check if we need to remove a material
        if hasattr(bpy.types.WindowManager, "replace_materials_remove") and hasattr(wm, "replace_materials_remove"):
            if wm.replace_materials_remove >= 0:
                idx = wm.replace_materials_remove
                if 0 <= idx < len(self.source_materials):
                    self.source_materials.remove(idx)
                wm.replace_materials_remove = -1

        # Source materials list
        col = layout.column()
        col.label(text="Source Materials (to replace):")

        # Search box to add materials
        row = col.row()
        row.prop_search(self, "source_material_temp", bpy.data, "materials", text="", icon="MATERIAL")

        # Add button
        if self.source_material_temp and self.source_material_temp in bpy.data.materials:
            mat_name = self.source_material_temp
            if not any(item.material_name == mat_name for item in self.source_materials):
                add_op = row.operator("object.add_source_material_to_list", text="Add", icon="ADD")
                add_op.material_name = mat_name
            else:
                row.label(text="(Already in list)", icon="INFO")
        else:
            row.label(text="(Select a material)", icon="INFO")

        # List of selected source materials
        if len(self.source_materials) > 0:
            box = col.box()
            box.label(text=f"{len(self.source_materials)} material(s) to replace:", icon="MATERIAL_DATA")
            for idx, item in enumerate(self.source_materials):
                if item.material_name:
                    row = box.row()
                    row.label(text=item.material_name, icon="MATERIAL")
                    # Remove button
                    remove_op = row.operator("object.remove_source_material_from_list", text="", icon="X")
                    remove_op.item_index = idx
        else:
            col.label(text="No materials added yet", icon="INFO")

        layout.separator()

        # Target material selector with search
        col = layout.column()
        col.label(text="Target Material (replacement):")
        col.prop_search(self, "target_material", bpy.data, "materials", text="", icon="MATERIAL")

        layout.separator()

        # Scope option
        layout.prop(self, "scope_selected")

    def invoke(self, context, event):
        # Reset material selections
        self.source_material_temp = ""
        self.target_material = ""
        self.source_materials.clear()

        # Initialize window manager properties (they should be registered, but check anyway)
        wm = context.window_manager
        if hasattr(bpy.types.WindowManager, "replace_materials_add"):
            wm.replace_materials_add = ""
        if hasattr(bpy.types.WindowManager, "replace_materials_remove"):
            wm.replace_materials_remove = -1

        return context.window_manager.invoke_props_dialog(self, width=450)


class OBJECT_OT_add_source_material_to_list(bpy.types.Operator):
    """Add a material to the source materials list"""

    bl_idname = "object.add_source_material_to_list"
    bl_label = "Add Source Material"
    bl_options = {"INTERNAL"}

    material_name: bpy.props.StringProperty()

    def execute(self, context):
        mat_name = self.material_name
        if not mat_name or mat_name not in bpy.data.materials:
            return {"CANCELLED"}

        # Store in window manager for the draw method to pick up
        wm = context.window_manager
        if hasattr(bpy.types.WindowManager, "replace_materials_add"):
            wm.replace_materials_add = mat_name

        return {"FINISHED"}


class OBJECT_OT_remove_source_material_from_list(bpy.types.Operator):
    """Remove a material from the source materials list"""

    bl_idname = "object.remove_source_material_from_list"
    bl_label = "Remove Source Material"
    bl_options = {"INTERNAL"}

    item_index: bpy.props.IntProperty()

    def execute(self, context):
        # Store the index to remove
        wm = context.window_manager
        if hasattr(bpy.types.WindowManager, "replace_materials_remove"):
            wm.replace_materials_remove = self.item_index
        return {"FINISHED"}
