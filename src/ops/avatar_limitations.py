import bpy

from ..rules import (
    is_skin_material,
    manifest,
    material_limit,
    rules_version,
    triangle_limit,
    triangle_status,
    triangle_tolerated_limit,
)

# Toolkit wearable types mapped to the rule book's category and hidden slots.
WEARABLE_TYPES = {
    "HAT": ("Hat", "hat", ()),
    "HELMET": ("Helmet", "helmet", ()),
    "HELMET_HIDE_HEAD": ("Helmet (Hide Head)", "helmet", ("head",)),
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


def triangles_icon(count, limit):
    """The dialog icon for a triangle count, by the rule book's severity: only a rejection shows the error icon."""
    state = triangle_status(count, limit)
    if state == "error":
        return "ERROR"
    if state == "warning":
        return "WARNING_LARGE"
    # within the budget, the count at exactly the limit included: nudge from 80% of it, as the other rows do
    return "WARNING_LARGE" if limit and count / limit >= 0.8 else "CHECKMARK"


def _principled_node(material):
    """The Principled BSDF that feeds the material's output, or the first one in the tree when that can't be followed."""
    tree = getattr(material, "node_tree", None)
    if not getattr(material, "use_nodes", False) or tree is None:
        return None
    principled = [node for node in tree.nodes if node.type == "BSDF_PRINCIPLED"]
    for node in tree.nodes:
        if node.type != "OUTPUT_MATERIAL" or not getattr(node, "is_active_output", True):
            continue
        surface = node.inputs.get("Surface")
        for link in getattr(surface, "links", None) or ():
            if link.from_node.type == "BSDF_PRINCIPLED":
                return link.from_node
    return principled[0] if principled else None


def _input(node, *names):
    """An input of the node by name (names differ between Blender versions), or None."""
    for name in names:
        socket = node.inputs.get(name)
        if socket is not None:
            return socket
    return None


def material_is_emissive(material):
    """Approximates what the glTF exporter writes as emission: a strength above zero and a colour that is not black."""
    node = _principled_node(material)
    if node is None:
        return False
    strength = _input(node, "Emission Strength")
    color = _input(node, "Emission Color", "Emission")
    if color is None:
        return False
    if strength is not None and not strength.is_linked and strength.default_value <= 0:
        return False
    return bool(color.is_linked or any(channel > 0 for channel in tuple(color.default_value)[:3]))


def material_is_transparent(material):
    """Approximates the alpha mode the glTF exporter writes, which it decides differently before and after Blender 4.2."""
    # Before 4.2 the exporter writes alphaMode from the blend mode alone, whatever the Alpha input says. From 4.2 on
    # the blend mode mirrors the render method and says nothing about the export, so only the Alpha input counts there.
    version = tuple(getattr(getattr(bpy, "app", None), "version", (4, 2, 0)))
    if version < (4, 2, 0):
        return getattr(material, "blend_method", "OPAQUE") in {"BLEND", "CLIP", "HASHED"}
    node = _principled_node(material)
    alpha = _input(node, "Alpha") if node is not None else None
    return alpha is not None and bool(alpha.is_linked or alpha.default_value < 1)


def effective_material_limit(limits, usage):
    """The material limit for what is selected: the rule book allows one more with emission or transparency."""
    return material_limit(limits["category"], usage.get("emission_or_alpha", False))


def wearable_limits(wearable_type):
    """Triangle, material and texture limits for a toolkit wearable type, from the vendored rule book."""
    rules = manifest()
    _label, category, hides = WEARABLE_TYPES[wearable_type]
    bucket = "skin" if category == "skin" else "default"
    max_size = rules["textures"]["maxSize"]
    triangles = triangle_limit(category, hides)
    return {
        "triangles": triangles,
        "triangles_tolerated": triangle_tolerated_limit(triangles),
        "textures": rules["textures"][bucket],
        "materials": rules["materials"][bucket],
        "category": category,
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
        # The skin material is left out as the engine recognises it: any material with "skin" in its name.
        materials_used = set()
        emission_or_alpha = False
        for obj in bpy.context.selected_objects:
            if obj.type == "MESH" and obj.data:
                for slot in obj.material_slots:
                    if slot.material and not is_skin_material(slot.material.name):
                        materials_used.add(slot.material.name)
                        if material_is_emissive(slot.material) or material_is_transparent(slot.material):
                            emission_or_alpha = True

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

        return {
            "triangles": triangle_count,
            "materials": material_count,
            "textures": texture_count,
            "emission_or_alpha": emission_or_alpha,
        }

    def execute(self, context):
        if not bpy.context.selected_objects:
            self.report({"WARNING"}, "No objects selected. Please select your wearable objects first.")
            return {"CANCELLED"}

        limitations = self.calculate_limitations(self.wearable_type)
        current_usage = self.count_current_usage()
        materials_limit = effective_material_limit(limitations, current_usage)

        # Create a detailed report
        report_lines = [
            "=== AVATAR WEARABLE LIMITATIONS ===",
            f"Wearable Type: {self.wearable_type.replace('_', ' ').title()}",
            f"Selected Objects: {len(bpy.context.selected_objects)}",
            "",
            "LIMITATIONS (Current / Limit):",
            f"• Triangles: {current_usage['triangles']:,} / {limitations['triangles']:,} ({self._get_percentage(current_usage['triangles'], limitations['triangles'])}%)",
            f"• Materials: {current_usage['materials']} / {materials_limit} ({self._get_percentage(current_usage['materials'], materials_limit)}%)",
            f"• Textures: {current_usage['textures']} / {limitations['textures']} ({self._get_percentage(current_usage['textures'], limitations['textures'])}%)",
            "",
            "TEXTURE REQUIREMENTS:",
            f"• Resolution: {limitations['texture_resolution']}",
            f"• Format: {limitations['texture_requirements']}",
            "",
            "IMPORTANT NOTES:",
            "• Only selected objects are counted",
            f'• Skin materials (any with "skin" in the name, such as {limitations["skin_material"]}) are not counted',
            "• One more material is allowed when the item uses emission or transparency (approximate: read from the",
            "  Principled BSDF; the Builder reads the exported GLB)",
            "• All textures must be square and 72 pixel/inch resolution",
            f"• Limits follow the Decentraland rule book v{rules_version()}",
        ]

        # Check for warnings
        warnings = []
        triangles_over = current_usage["triangles"] - limitations["triangles"]
        triangles_state = triangle_status(current_usage["triangles"], limitations["triangles"])
        if triangles_state == "warning":
            warnings.append(
                f"⚠️  TRIANGLES: {triangles_over:,} over the budget. Up to {limitations['triangles_tolerated']:,} "
                "is accepted with a warning; trim geometry to stay within the budget"
            )
        elif triangles_state == "error":
            warnings.append(
                f"❌ TRIANGLES: Exceeding limit by {triangles_over:,}. Above {limitations['triangles_tolerated']:,} "
                "the item is rejected"
            )
        if current_usage["materials"] > materials_limit:
            with_extra = material_limit(limitations["category"], True)
            hint = (
                f". Up to {with_extra} are accepted only when one of them is emissive or transparent"
                if materials_limit < with_extra and current_usage["materials"] <= with_extra
                else ""
            )
            warnings.append(f"⚠️  MATERIALS: Exceeding limit by {current_usage['materials'] - materials_limit}{hint}")
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
            materials_limit = effective_material_limit(limitations, current_usage)
            materials_pct = self._get_percentage(current_usage["materials"], materials_limit)
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
                icon=triangles_icon(current_usage["triangles"], limitations["triangles"]),
            )
            col.label(
                text=f"Materials: {current_usage['materials']} / {materials_limit} ({materials_pct}%)",
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
