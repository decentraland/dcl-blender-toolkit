import bpy

class OBJECT_OT_avatar_limitations(bpy.types.Operator):
    bl_idname = "object.avatar_limitations"
    bl_label = "Avatar Limitations Calculator"
    bl_description = "Calculate wearable limitations based on selected wearable type"
    bl_options = {'REGISTER', 'UNDO'}

    wearable_type: bpy.props.EnumProperty(
        name="Wearable Type",
        description="Select the type of wearable to calculate limitations for",
        items=[
            ('HAT', 'Hat', 'Hat wearable (1.5K triangles max)'),
            ('HELMET', 'Helmet', 'Helmet wearable (1.5K triangles max)'),
            ('UPPER_BODY', 'Upper Body', 'Upper body wearable (1.5K triangles max)'),
            ('LOWER_BODY', 'Lower Body', 'Lower body wearable (1.5K triangles max)'),
            ('FEET', 'Feet', 'Feet wearable (1.5K triangles max)'),
            ('HAIR', 'Hair', 'Hair wearable (1.5K triangles max)'),
            ('MASK', 'Mask', 'Mask wearable (500 triangles max)'),
            ('EYEWEAR', 'Eyewear', 'Eyewear wearable (500 triangles max)'),
            ('EARRING', 'Earring', 'Earring wearable (500 triangles max)'),
            ('TIARA', 'Tiara', 'Tiara wearable (500 triangles max)'),
            ('TOP_HEAD', 'Top Head', 'Top head wearable (500 triangles max)'),
            ('FACIAL_HAIR', 'Facial Hair', 'Facial hair wearable (500 triangles max)'),
            ('HAND_ACCESSORY', 'Hand Accessory', 'Hand accessory wearable (1K triangles max)'),
            ('HAND_ACCESSORY_HIDE', 'Hand Accessory (Hide Hand)', 'Hand accessory that hides base hand (1.5K triangles max)'),
            ('SKIN', 'Skin', 'Skin wearable (5K triangles max, 5 textures max)'),
        ],
        default='HAT',
    )

    def calculate_limitations(self, wearable_type):
        """Calculate limitations based on wearable type"""
        
        # Triangle limits
        if wearable_type in ['HAT', 'HELMET', 'UPPER_BODY', 'LOWER_BODY', 'FEET', 'HAIR', 'HAND_ACCESSORY_HIDE']:
            triangle_limit = 1500
        elif wearable_type in ['MASK', 'EYEWEAR', 'EARRING', 'TIARA', 'TOP_HEAD', 'FACIAL_HAIR']:
            triangle_limit = 500
        elif wearable_type == 'HAND_ACCESSORY':
            triangle_limit = 1000
        elif wearable_type == 'SKIN':
            triangle_limit = 5000
        else:
            triangle_limit = 0
        
        # Texture limits
        if wearable_type == 'SKIN':
            texture_limit = 5
        else:
            texture_limit = 2
        
        # Material limits (excluding AvatarSkin_MAT)
        material_limit = 2
        
        return {
            'triangles': triangle_limit,
            'textures': texture_limit,
            'materials': material_limit,
            'texture_resolution': '512x512px or lower',
            'texture_requirements': 'Square textures at 72 pixel/inch resolution'
        }

    def count_current_usage(self):
        """Count current wearable usage"""

        # Count triangles in selected objects
        triangle_count = 0
        for obj in bpy.context.selected_objects:
            if obj.type == 'MESH' and obj.data:
                obj.data.calc_loop_triangles()
                triangle_count += len(obj.data.loop_triangles)
        
        # Count materials used by selected objects
        materials_used = set()
        for obj in bpy.context.selected_objects:
            if obj.type == 'MESH' and obj.data:
                for slot in obj.material_slots:
                    if slot.material and slot.material.name != 'AvatarSkin_MAT':
                        materials_used.add(slot.material.name)
        
        material_count = len(materials_used)
        
        # Count textures used by materials
        textures_used = set()
        for material in bpy.data.materials:
            if material.name in materials_used:
                if material.use_nodes:
                    for node in material.node_tree.nodes:
                        if node.type == 'TEX_IMAGE' and node.image:
                            textures_used.add(node.image.name)
        
        texture_count = len(textures_used)
        
        return {
            'triangles': triangle_count,
            'materials': material_count,
            'textures': texture_count
        }

    def execute(self, context):
        if not bpy.context.selected_objects:
            self.report({'WARNING'}, "No objects selected. Please select your wearable objects first.")
            return {'CANCELLED'}
        
        limitations = self.calculate_limitations(self.wearable_type)
        current_usage = self.count_current_usage()
        
        # Create a detailed report
        report_lines = [
            f"=== AVATAR WEARABLE LIMITATIONS ===",
            f"Wearable Type: {self.wearable_type.replace('_', ' ').title()}",
            f"Selected Objects: {len(bpy.context.selected_objects)}",
            f"",
            f"LIMITATIONS (Current / Limit):",
            f"• Triangles: {current_usage['triangles']:,} / {limitations['triangles']:,} ({self._get_percentage(current_usage['triangles'], limitations['triangles'])}%)",
            f"• Materials: {current_usage['materials']} / {limitations['materials']} ({self._get_percentage(current_usage['materials'], limitations['materials'])}%)",
            f"• Textures: {current_usage['textures']} / {limitations['textures']} ({self._get_percentage(current_usage['textures'], limitations['textures'])}%)",
            f"",
            f"TEXTURE REQUIREMENTS:",
            f"• Resolution: {limitations['texture_resolution']}",
            f"• Format: {limitations['texture_requirements']}",
            f"",
            f"IMPORTANT NOTES:",
            f"• Only selected objects are counted",
            f"• AvatarSkin_MAT material is not counted toward material limit",
            f"• All textures must be square and 72 pixel/inch resolution",
            f"• Hand accessories that hide base hand get 1.5K triangle budget",
            f"• Skin wearables get 5K triangle and 5 texture budget"
        ]
        
        # Check for warnings
        warnings = []
        if current_usage['triangles'] > limitations['triangles']:
            warnings.append(f"⚠️  TRIANGLES: Exceeding limit by {current_usage['triangles'] - limitations['triangles']:,}")
        if current_usage['materials'] > limitations['materials']:
            warnings.append(f"⚠️  MATERIALS: Exceeding limit by {current_usage['materials'] - limitations['materials']}")
        if current_usage['textures'] > limitations['textures']:
            warnings.append(f"⚠️  TEXTURES: Exceeding limit by {current_usage['textures'] - limitations['textures']}")
        
        if warnings:
            report_lines.extend(["", "⚠️  WARNINGS:"] + warnings)
        
        # Show in Blender
        if warnings:
            self.report({'WARNING'}, f"Wearable analysis complete - {len(warnings)} warnings found. Check console for details.")
        else:
            self.report({'INFO'}, f"Wearable analysis complete - All limits within bounds. Check console for details.")
        
        return {'FINISHED'}

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
            layout.label(text=f"Selected Objects: {len(bpy.context.selected_objects)}", icon='INFO')
        else:
            layout.separator()
            box = layout.box()
            box.label(text="⚠️ No objects selected", icon='ERROR')
            box.label(text="Please select your wearable objects first")
        
        # Calculate and show preview
        if bpy.context.selected_objects:
            limitations = self.calculate_limitations(self.wearable_type)
            current_usage = self.count_current_usage()
            
            layout.separator()
            layout.label(text="Current Usage vs Limits:", icon='INFO')
            
            box = layout.box()
            col = box.column(align=True)
            
            # Show current usage vs limits
            triangles_pct = self._get_percentage(current_usage['triangles'], limitations['triangles'])
            materials_pct = self._get_percentage(current_usage['materials'], limitations['materials'])
            textures_pct = self._get_percentage(current_usage['textures'], limitations['textures'])
            
            # Color coding for usage levels
            def get_icon(percentage_str):
                if percentage_str == "N/A":
                    return 'INFO'
                pct = float(percentage_str.replace('%', ''))
                if pct >= 100:
                    return 'ERROR'
                elif pct >= 80:
                    return 'WARNING'
                else:
                    return 'CHECKMARK'
            
            col.label(text=f"Triangles: {current_usage['triangles']:,} / {limitations['triangles']:,} ({triangles_pct}%)", icon=get_icon(triangles_pct))
            col.label(text=f"Materials: {current_usage['materials']} / {limitations['materials']} ({materials_pct}%)", icon=get_icon(materials_pct))
            col.label(text=f"Textures: {current_usage['textures']} / {limitations['textures']} ({textures_pct}%)", icon=get_icon(textures_pct))
            
            layout.separator()
            layout.label(text="Texture Requirements:", icon='IMAGE_DATA')
            box2 = layout.box()
            col2 = box2.column(align=True)
            col2.label(text=f"Resolution: {limitations['texture_resolution']}")
            col2.label(text="Format: Square, 72 pixel/inch")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
