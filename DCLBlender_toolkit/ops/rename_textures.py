import bpy

class OBJECT_OT_rename_textures(bpy.types.Operator):
    bl_idname = "object.rename_textures"
    bl_label = "Rename Textures by Usage"
    bl_description = "Automatically rename textures based on their usage in materials (Base Color, HRM, Normal, Emissive)"
    bl_options = {'REGISTER', 'UNDO'}

    def analyze_material_nodes(self, material):
        """Analyze material nodes to determine texture usage"""
        if not material or not material.use_nodes:
            return {}
        
        texture_usage = {}
        nodes = material.node_tree.nodes
        
        for node in nodes:
            if node.type == 'TEX_IMAGE' and node.image:
                texture_name = node.image.name
                usage = self.determine_texture_usage(node, material)
                if usage:
                    texture_usage[texture_name] = {
                        'usage': usage,
                        'material_name': material.name
                    }
        
        return texture_usage

    def determine_texture_usage(self, image_node, material):
        """Determine how a texture is being used in the material"""
        # Check what the image node is connected to
        for output in image_node.outputs:
            for link in output.links:
                target_node = link.to_node
                
                # Check if connected to Principled BSDF
                if target_node.type == 'BSDF_PRINCIPLED':
                    # Check which input it's connected to
                    if link.to_socket.name == 'Base Color':
                        return 'baseColor'
                    elif link.to_socket.name == 'Roughness':
                        return 'hrm'
                    elif link.to_socket.name == 'Metallic':
                        return 'hrm'
                    elif link.to_socket.name == 'Normal':
                        return 'normal'
                    elif link.to_socket.name == 'Emission':
                        return 'emissive'
                    elif link.to_socket.name == 'Emission Color':
                        return 'emissive'
                
                # Check if connected to Separate Color node (for HRM)
                elif target_node.type == 'SEPARATE_COLOR':
                    # Check if the Separate Color is connected to roughness or metallic
                    for sep_output in target_node.outputs:
                        for sep_link in sep_output.links:
                            if sep_link.to_node.type == 'BSDF_PRINCIPLED':
                                if sep_link.to_socket.name in ['Roughness', 'Metallic']:
                                    return 'hrm'
                
                # Check if connected to Normal Map node
                elif target_node.type == 'NORMAL_MAP':
                    return 'normal'
                
                # Check if connected to Emission node
                elif target_node.type == 'EMISSION':
                    return 'emissive'
        
        return None

    def rename_texture(self, old_name, usage, material_name):
        """Rename texture based on usage and material name"""
        import re
        
        # Clean the old name to remove Blender's .001, .002 suffixes
        clean_old_name = old_name
        # Remove .001, .002, etc. suffixes that Blender adds (including after file extensions)
        clean_old_name = re.sub(r'\.\d{3}$', '', clean_old_name)
        
        # Get the file extension from the cleaned name
        if clean_old_name.lower().endswith('.png'):
            extension = '.png'
        elif clean_old_name.lower().endswith('.jpg') or clean_old_name.lower().endswith('.jpeg'):
            extension = '.jpg'
        else:
            extension = '.png'  # Default to png
        
        # Clean material name (remove spaces, special characters)
        clean_material_name = material_name.replace(' ', '_').replace('.', '_').replace('-', '_')
        
        # Add appropriate suffix based on usage
        if usage == 'baseColor':
            new_name = f"{clean_material_name}_baseColor{extension}"
        elif usage == 'hrm':
            new_name = f"{clean_material_name}_hrm{extension}"
        elif usage == 'normal':
            new_name = f"{clean_material_name}_normal{extension}"
        elif usage == 'emissive':
            new_name = f"{clean_material_name}_emissive{extension}"
        else:
            return old_name
        
        # Final cleanup: ensure no .001, .002 suffixes remain
        new_name = re.sub(r'\.\d{3}$', '', new_name)
        
        return new_name

    def execute(self, context):
        renamed_count = 0
        texture_usage_map = {}
        
        # Analyze all materials in the scene
        for material in bpy.data.materials:
            if material.use_nodes:
                usage_map = self.analyze_material_nodes(material)
                for texture_name, texture_info in usage_map.items():
                    if texture_name not in texture_usage_map:
                        texture_usage_map[texture_name] = texture_info
                    elif texture_usage_map[texture_name]['usage'] != texture_info['usage']:
                        # Texture used for multiple purposes, use the first one found
                        pass
        
        # Rename textures based on usage and material name
        for texture_name, texture_info in texture_usage_map.items():
            if texture_name in bpy.data.images:
                usage = texture_info['usage']
                material_name = texture_info['material_name']
                new_name = self.rename_texture(texture_name, usage, material_name)
                
                if new_name != texture_name:
                    # Check if new name already exists
                    if new_name not in bpy.data.images:
                        # Temporarily rename to avoid conflicts
                        temp_name = f"temp_{texture_name}_{renamed_count}"
                        bpy.data.images[texture_name].name = temp_name
                        
                        # Now rename to final name
                        bpy.data.images[temp_name].name = new_name
                        renamed_count += 1
                        self.report({'INFO'}, f"Renamed '{texture_name}' to '{new_name}'")
                    else:
                        self.report({'WARNING'}, f"Texture '{new_name}' already exists, skipping '{texture_name}'")
        
        if renamed_count > 0:
            self.report({'INFO'}, f"Successfully renamed {renamed_count} textures based on their usage")
        else:
            self.report({'INFO'}, "No textures needed renaming")
        
        return {'FINISHED'}

    def draw(self, context):
        layout = self.layout
        layout.label(text="This tool will analyze all materials and rename textures based on their usage:")
        layout.label(text="• Base Color → MaterialName_baseColor.png/jpg")
        layout.label(text="• Roughness/Metallic → MaterialName_hrm.png/jpg")
        layout.label(text="• Normal → MaterialName_normal.png/jpg")
        layout.label(text="• Emissive → MaterialName_emissive.png/jpg")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
