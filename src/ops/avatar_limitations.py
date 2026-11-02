import bpy

from ..rules import manifest, rules_version, triangle_limit

# Toolkit wearable types mapped to the rule book's category and hidden slots.
WEARABLE_TYPES = {
    "HAT": ("Hat", "hat", ()),
    "HELMET": ("Helmet", "helmet", ()),
    "UPPER_BODY": ("Upper Body", "upper_body", ()),
    "LOWER_BODY": ("Lower Body", "lower_body", ()),
    "FEET": ("Feet", "feet", ()),
    "HAIR": ("Hair", "hair", ()),
    "MASK": ("Mask", "mask", ()),
    "EYEWEAR": ("Eyewear", "eyewear", ()),
    "EARRING": ("Earring", "earring", ()),
    "TIARA": ("Tiara", "tiara", ()),
    "TOP_HEAD": ("Top Head", "top_head", ()),
    "FACIAL_HAIR": ("Facial Hair", "facial_hair", ()),
    "HAND_ACCESSORY": ("Hand Accessory", "hands_wear", ()),
    "HAND_ACCESSORY_HIDE": ("Hand Accessory (Hide Hand)", "hands_wear", ("hands",)),
    "SKIN": ("Skin", "skin", ()),
}


def _format_count(value):
    return f"{value / 1000:g}K" if value >= 1000 else str(value)


def wearable_limits(wearable_type):
    """Triangle, material and texture limits for a toolkit wearable type, from the vendored rule book."""
    rules = manifest()
    _label, category, hides = WEARABLE_TYPES[wearable_type]
    bucket = "skin" if category == "skin" else "default"
    max_size = rules["textures"]["maxSize"]
    return {
        "triangles": triangle_limit(category, hides),
        "textures": rules["textures"][bucket],
        "materials": rules["materials"][bucket],
        "skin_material": rules["materials"]["avatarSkinMat"],
        "texture_resolution": f"{max_size}x{max_size}px or lower",
        "texture_requirements": "Square textures at 72 pixel/inch resolution",
    }


def _enum_items():
    items = []
    for identifier, (label, category, _hides) in WEARABLE_TYPES.items():
        limits = wearable_limits(identifier)
        extra = f", {limits['textures']} textures max" if category == "skin" else ""
        items.append(
            (identifier, label, f"{label} wearable ({_format_count(limits['triangles'])} triangles max{extra})")
        )
    return items


class OBJECT_OT_avatar_limitations(bpy.types.Operator):
    bl_idname = "object.avatar_limitations"
    bl_label = "Avatar Limitations Calculator"
    bl_description = "Calculate wearable limitations based on selected wearable type"
    bl_options = {"REGISTER", "UNDO"}

    wearable_type: bpy.props.EnumProperty(
        name="Wearable Type",
        description="Select the type of wearable to calculate limitations for",
        items=_enum_items(),
        default="HAT",
    )

    def calculate_limitations(self, wearable_type):
        return wearable_limits(wearable_type)

    def count_current_usage(self):
        """Count current wearable usage"""

        # Count triangles in selected objects
        triangle_count = 0
        for obj in bpy.context.selected_objects:
            if obj.type == "MESH" and obj.data:
                obj.data.calc_loop_triangles()
                triangle_count += len(obj.data.loop_triangles)

        # Count materials used by selected objects
        materials_used = set()
        for obj in bpy.context.selected_objects:
            if obj.type == "MESH" and obj.data:
                for slot in obj.material_slots:
                    if slot.material and slot.material.name != manifest()["materials"]["avatarSkinMat"]:
                        materials_used.add(slot.material.name)

        material_count = len(materials_used)

        # Count textures used by materials
        textures_used = set()
        for material in bpy.data.materials:
            if material.name in materials_used:
                if material.use_nodes:
                    for node in material.node_tree.nodes:
                        if node.type == "TEX_IMAGE" and node.image:
                            textures_used.add(node.image.name)

        texture_count = len(textures_used)

        return {"triangles": triangle_count, "materials": material_count, "textures": texture_count}

    def execute(self, context):
        if not bpy.context.selected_objects:
            self.report({"WARNING"}, "No objects selected. Please select your wearable objects first.")
            return {"CANCELLED"}

        limitations = self.calculate_limitations(self.wearable_type)
        current_usage = self.count_current_usage()

        # Create a detailed report
        report_lines = [
            "=== AVATAR WEARABLE LIMITATIONS ===",
            f"Wearable Type: {self.wearable_type.replace('_', ' ').title()}",
            f"Selected Objects: {len(bpy.context.selected_objects)}",
            "",
            "LIMITATIONS (Current / Limit):",
            f"• Triangles: {current_usage['triangles']:,} / {limitations['triangles']:,} ({self._get_percentage(current_usage['triangles'], limitations['triangles'])}%)",
            f"• Materials: {current_usage['materials']} / {limitations['materials']} ({self._get_percentage(current_usage['materials'], limitations['materials'])}%)",
            f"• Textures: {current_usage['textures']} / {limitations['textures']} ({self._get_percentage(current_usage['textures'], limitations['textures'])}%)",
            "",
            "TEXTURE REQUIREMENTS:",
            f"• Resolution: {limitations['texture_resolution']}",
            f"• Format: {limitations['texture_requirements']}",
            "",
            "IMPORTANT NOTES:",
            "• Only selected objects are counted",
            f"• {limitations['skin_material']} material is not counted toward material limit",
            "• All textures must be square and 72 pixel/inch resolution",
            f"• Limits follow the Decentraland rule book v{rules_version()}",
        ]

        # Check for warnings
        warnings = []
        if current_usage["triangles"] > limitations["triangles"]:
            warnings.append(
                f"⚠️  TRIANGLES: Exceeding limit by {current_usage['triangles'] - limitations['triangles']:,}"
            )
        if current_usage["materials"] > limitations["materials"]:
            warnings.append(f"⚠️  MATERIALS: Exceeding limit by {current_usage['materials'] - limitations['materials']}")
        if current_usage["textures"] > limitations["textures"]:
            warnings.append(f"⚠️  TEXTURES: Exceeding limit by {current_usage['textures'] - limitations['textures']}")

        if warnings:
            report_lines.extend(["", "⚠️  WARNINGS:"] + warnings)

        # Show in Blender
        if warnings:
            self.report(
                {"WARNING"}, f"Wearable analysis complete - {len(warnings)} warnings found. Check console for details."
            )
        else:
            self.report({"INFO"}, "Wearable analysis complete - All limits within bounds. Check console for details.")

        return {"FINISHED"}

    def _get_percentage(self, current, limit):
        """Calculate percentage usage"""
        if limit == 0:
            return "N/A"
        percentage = (current / limit) * 100
        return f"{percentage:.1f}"

    def draw(self, context):
        layout = self.layout

        # Wearable type selection
        col = layout.column(align=True)
        col.label(text="Select Wearable Type:")
        col.prop(self, "wearable_type", text="")

        # Show current selection info
        if bpy.context.selected_objects:
            layout.separator()
            layout.label(text=f"Selected Objects: {len(bpy.context.selected_objects)}", icon="INFO")
        else:
            layout.separator()
            box = layout.box()
            box.label(text="⚠️ No objects selected", icon="ERROR")
            box.label(text="Please select your wearable objects first")

        # Calculate and show preview
        if bpy.context.selected_objects:
            limitations = self.calculate_limitations(self.wearable_type)
            current_usage = self.count_current_usage()

            layout.separator()
            layout.label(text="Current Usage vs Limits:", icon="INFO")

            box = layout.box()
            col = box.column(align=True)

            # Show current usage vs limits
            triangles_pct = self._get_percentage(current_usage["triangles"], limitations["triangles"])
            materials_pct = self._get_percentage(current_usage["materials"], limitations["materials"])
            textures_pct = self._get_percentage(current_usage["textures"], limitations["textures"])

            # Color coding for usage levels
            def get_icon(percentage_str):
                if percentage_str == "N/A":
                    return "INFO"
                pct = float(percentage_str.replace("%", ""))
                if pct >= 100:
                    return "ERROR"
                elif pct >= 80:
                    return "WARNING_LARGE"
                else:
                    return "CHECKMARK"

            col.label(
                text=f"Triangles: {current_usage['triangles']:,} / {limitations['triangles']:,} ({triangles_pct}%)",
                icon=get_icon(triangles_pct),
            )
            col.label(
                text=f"Materials: {current_usage['materials']} / {limitations['materials']} ({materials_pct}%)",
                icon=get_icon(materials_pct),
            )
            col.label(
                text=f"Textures: {current_usage['textures']} / {limitations['textures']} ({textures_pct}%)",
                icon=get_icon(textures_pct),
            )

            layout.separator()
            layout.label(text="Texture Requirements:", icon="IMAGE_DATA")
            box2 = layout.box()
            col2 = box2.column(align=True)
            col2.label(text=f"Resolution: {limitations['texture_resolution']}")
            col2.label(text="Format: Square, 72 pixel/inch")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
