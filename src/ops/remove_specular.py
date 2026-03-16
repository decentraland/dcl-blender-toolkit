import bpy


class OBJECT_OT_remove_specular(bpy.types.Operator):
    bl_idname = "object.remove_specular"
    bl_label = "Remove Specular"
    bl_description = (
        "Remove specular tint textures and set specular values to 0 "
        "on Principled BSDF materials to reduce file size"
    )
    bl_options = {"REGISTER", "UNDO"}

    scope_all_materials: bpy.props.BoolProperty(
        name="All Materials",
        description="Process every material in the file",
        default=False,
    )

    scope_selected_objects: bpy.props.BoolProperty(
        name="Selected Objects Only",
        description="Process only materials used by selected objects",
        default=True,
    )

    remove_specular_tint_textures: bpy.props.BoolProperty(
        name="Remove Specular Tint Textures",
        description="Disconnect and remove texture nodes linked to specular tint",
        default=True,
    )

    set_specular_zero: bpy.props.BoolProperty(
        name="Set Specular to 0",
        description="Set Specular / Specular IOR Level inputs to 0 on Principled BSDF",
        default=True,
    )

    # ------------------------------------------------------------------ #

    _SPECULAR_TINT_KEYWORDS = ("specular_tint", "spectint", "spec_tint", "specular tint")

    def _collect_materials(self, context):
        materials = []

        if self.scope_all_materials:
            for mat in bpy.data.materials:
                if mat.users > 0:
                    materials.append(mat)

        elif self.scope_selected_objects and context.selected_objects:
            seen = set()
            for obj in context.selected_objects:
                if obj.type != "MESH" or not obj.data.materials:
                    continue
                for mat in obj.data.materials:
                    if mat and mat.name not in seen:
                        seen.add(mat.name)
                        materials.append(mat)

        return materials

    def _is_specular_tint_node(self, node):
        """Check both the image name and the node name for specular-tint keywords."""
        targets = []
        if node.type == "TEX_IMAGE" and node.image:
            targets.append(node.image.name.lower())
        targets.append(node.name.lower())
        return any(kw in t for t in targets for kw in self._SPECULAR_TINT_KEYWORDS)

    def _clean_material(self, material):
        """Strip specular from one material. Returns (textures_removed, inputs_zeroed)."""
        textures_removed = 0
        inputs_zeroed = 0

        if not material.use_nodes:
            if self.set_specular_zero:
                if hasattr(material, "specular_intensity"):
                    material.specular_intensity = 0.0
                    inputs_zeroed += 1
            return textures_removed, inputs_zeroed

        tree = material.node_tree
        nodes_to_remove = []
        links_to_remove = []

        for node in tree.nodes:
            if self.remove_specular_tint_textures and self._is_specular_tint_node(node):
                for output in node.outputs:
                    for link in output.links:
                        links_to_remove.append(link)
                nodes_to_remove.append(node)

            elif node.type == "BSDF_PRINCIPLED" and self.set_specular_zero:
                for input_name in ("Specular", "Specular IOR Level", "Specular Tint"):
                    if input_name not in node.inputs:
                        continue
                    sock = node.inputs[input_name]

                    for link in sock.links:
                        links_to_remove.append(link)

                    try:
                        cur = sock.default_value
                        if input_name == "Specular Tint":
                            if isinstance(cur, (int, float)):
                                sock.default_value = 1.0
                            else:
                                sock.default_value = (1.0, 1.0, 1.0, 1.0)
                        else:
                            if isinstance(cur, (int, float)):
                                sock.default_value = 0.0
                            else:
                                sock.default_value = (0.0, 0.0, 0.0, 1.0)
                        inputs_zeroed += 1
                    except Exception:
                        pass

        for link in links_to_remove:
            try:
                tree.links.remove(link)
            except Exception:
                pass

        for node in nodes_to_remove:
            try:
                tree.nodes.remove(node)
                textures_removed += 1
            except Exception:
                pass

        return textures_removed, inputs_zeroed

    # ------------------------------------------------------------------ #

    def execute(self, context):
        materials = self._collect_materials(context)
        if not materials:
            self.report({"WARNING"}, "No materials found. Select objects or enable 'All Materials'")
            return {"CANCELLED"}

        total_tex = 0
        total_inp = 0
        processed = 0

        for mat in materials:
            tex, inp = self._clean_material(mat)
            if tex or inp:
                processed += 1
            total_tex += tex
            total_inp += inp

        parts = []
        if total_tex:
            parts.append(f"{total_tex} specular texture(s) removed")
        if total_inp:
            parts.append(f"{total_inp} input(s) zeroed")
        detail = ", ".join(parts) if parts else "nothing to change"

        self.report({"INFO"}, f"Processed {processed} material(s): {detail}")
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "remove_specular_tint_textures")
        layout.prop(self, "set_specular_zero")

        layout.separator()
        layout.prop(self, "scope_all_materials")
        layout.prop(self, "scope_selected_objects")

        layout.separator()
        layout.label(text="Removes specular tint textures and sets", icon="INFO")
        layout.label(text="specular to 0 to reduce file size")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=350)
