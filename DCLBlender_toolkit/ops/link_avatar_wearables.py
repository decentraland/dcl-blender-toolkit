import bpy
import os


def safe_deselect_all():
    """Deselect all objects without using bpy.ops (context-safe)."""
    for obj in bpy.data.objects:
        try:
            obj.select_set(False)
        except RuntimeError:
            pass


def safe_ensure_object_mode():
    """Ensure we are in object mode, handling context issues."""
    try:
        if bpy.context.mode != 'OBJECT':
            bpy.ops.object.mode_set(mode='OBJECT')
    except (RuntimeError, Exception):
        pass


class OBJECT_OT_link_avatar_wearables(bpy.types.Operator):
    bl_idname = "object.link_avatar_wearables"
    bl_label = "Avatar Shapes"
    bl_description = "Import and create editable Decentraland avatar collections for wearable development (Shape A and B)"
    bl_options = {'REGISTER', 'UNDO'}

    avatar_shape: bpy.props.EnumProperty(
        name="Avatar Shape",
        description="Choose the avatar shape to import for wearable development",
        items=[
            ('A', 'Shape A', 'Import DCLAvatar_ShapeA collection from AvatarShape_A.blend'),
            ('B', 'Shape B', 'Import DCLAvatar_ShapeB collection from AvatarShape_B.blend'),
            ('BOTH', 'Both Shapes', 'Import both Shape A and Shape B collections'),
        ],
        default='A',
    )

    def execute(self, context):
        # Get the addon directory - handle both development and installed addon paths
        addon_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        
        # For installed addons, the structure might be different
        # Try to find the assets directory
        possible_asset_paths = [
            os.path.join(addon_dir, "assets"),
            os.path.join(addon_dir, "DCLBlender_toolkit", "assets"),
            os.path.join(os.path.dirname(addon_dir), "assets"),
            os.path.join(os.path.dirname(os.path.dirname(addon_dir)), "assets"),
        ]
        
        assets_dir = None
        for path in possible_asset_paths:
            if os.path.exists(path):
                assets_dir = path
                break
        
        # Create temp directory for extracted avatars if it doesn't exist
        temp_dir = os.path.join(os.path.expanduser("~"), ".decentraland_tools", "avatars")
        os.makedirs(temp_dir, exist_ok=True)
        
        # Extract avatar files if they don't exist in temp directory
        if not assets_dir:
            self.report({'ERROR'}, "Could not find assets directory in add-on")
            return {'CANCELLED'}
        
        if not self._extract_avatar_files(assets_dir, temp_dir):
            self.report({'ERROR'}, "Failed to extract avatar files")
            return {'CANCELLED'}
        
        current_selection = list(context.selected_objects)
        current_active = context.active_object
        
        imported_collections = []
        
        try:
            if self.avatar_shape in ['A', 'BOTH']:
                # Import Shape A
                blend_file_a = os.path.join(temp_dir, "AvatarShape_A.blend")
                collection_name_a = "DCLAvatar_ShapeA"
                
                if os.path.exists(blend_file_a):
                    with bpy.data.libraries.load(blend_file_a, link=True) as (data_from, data_to):
                        if collection_name_a in data_from.collections:
                            data_to.collections = [collection_name_a]
                        else:
                            self.report({'WARNING'}, f"Collection '{collection_name_a}' not found in {blend_file_a}")
                    
                    if collection_name_a in bpy.data.collections:
                        collection_a = bpy.data.collections[collection_name_a]
                        if collection_a.name not in context.scene.collection.children:
                            context.scene.collection.children.link(collection_a)
                        imported_collections.append(collection_name_a)
                    else:
                        self.report({'ERROR'}, f"Failed to link collection '{collection_name_a}'")
                else:
                    self.report({'WARNING'}, f"Blend file not found: {blend_file_a}")
            
            if self.avatar_shape in ['B', 'BOTH']:
                # Import Shape B
                blend_file_b = os.path.join(temp_dir, "AvatarShape_B.blend")
                collection_name_b = "DCLAvatar_ShapeB"
                
                if os.path.exists(blend_file_b):
                    with bpy.data.libraries.load(blend_file_b, link=True) as (data_from, data_to):
                        if collection_name_b in data_from.collections:
                            data_to.collections = [collection_name_b]
                        else:
                            self.report({'WARNING'}, f"Collection '{collection_name_b}' not found in {blend_file_b}")
                    
                    if collection_name_b in bpy.data.collections:
                        collection_b = bpy.data.collections[collection_name_b]
                        if collection_b.name not in context.scene.collection.children:
                            context.scene.collection.children.link(collection_b)
                        imported_collections.append(collection_name_b)
                    else:
                        self.report({'ERROR'}, f"Failed to link collection '{collection_name_b}'")
                else:
                    self.report({'WARNING'}, f"Blend file not found: {blend_file_b}")
            
            if imported_collections:
                # Duplicate collections to make them editable
                editable_collections = []
                for collection_name in imported_collections:
                    if collection_name in bpy.data.collections:
                        original_collection = bpy.data.collections[collection_name]
                        
                        # Create a new editable collection
                        editable_name = f"{collection_name}_Editable"
                        if editable_name in bpy.data.collections:
                            # Remove existing editable collection
                            bpy.data.collections.remove(bpy.data.collections[editable_name])
                        
                        editable_collection = bpy.data.collections.new(editable_name)
                        context.scene.collection.children.link(editable_collection)
                        
                        # Store original scales before duplication
                        original_scales = {}
                        for obj in original_collection.objects:
                            original_scales[obj.name] = obj.scale.copy()
                        
                        # Store original parenting relationships
                        original_parents = {}
                        for obj in original_collection.objects:
                            if obj.parent:
                                original_parents[obj.name] = obj.parent.name
                        
                        # NEW APPROACH: Process objects individually to avoid transform_apply on armatures
                        safe_deselect_all()
                        
                        # Create mapping of original names to new objects
                        name_mapping = {}
                        
                        # Process each object individually
                        for obj in original_collection.objects:
                            # Select only this object
                            obj.select_set(True)
                            bpy.context.view_layer.objects.active = obj
                            
                            # Duplicate this single object
                            bpy.ops.object.duplicate(linked=False)
                            
                            # Get the duplicated object
                            duplicated_obj = context.active_object
                            
                            # Store the name mapping
                            name_mapping[obj.name] = duplicated_obj
                            
                            # Unlink from current collections
                            for collection in duplicated_obj.users_collection:
                                collection.objects.unlink(duplicated_obj)
                            
                            # Link to our editable collection
                            editable_collection.objects.link(duplicated_obj)
                            
                            # Make sure it's local (not linked)
                            duplicated_obj.make_local()
                            
                            # Make all materials single-user (unlinked) so they can be edited
                            if duplicated_obj.type == 'MESH' and duplicated_obj.data.materials:
                                for slot in duplicated_obj.material_slots:
                                    if slot.material:
                                        slot.material.make_local()
                            
                            # Only apply transforms to MESH objects, skip ARMATURE
                            if duplicated_obj.type == 'MESH':
                                bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
                            
                            # Deselect for next iteration
                            duplicated_obj.select_set(False)
                        
                        # Restore parenting relationships using proper Blender commands
                        for child_name, parent_name in original_parents.items():
                            if child_name in name_mapping and parent_name in name_mapping:
                                child_obj = name_mapping[child_name]
                                parent_obj = name_mapping[parent_name]
                                
                                # Use proper Blender parenting commands for armature deformation
                                if parent_obj.type == 'ARMATURE' and child_obj.type == 'MESH':
                                    # Select the mesh object and set armature as active
                                    safe_deselect_all()
                                    child_obj.select_set(True)
                                    bpy.context.view_layer.objects.active = parent_obj
                                    
                                    # First parent with keep_transform to preserve positioning
                                    bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)
                                    
                                    # Then parent with armature deformation
                                    bpy.ops.object.parent_set(type='ARMATURE')
                                else:
                                    # For non-armature parenting, use direct assignment
                                    child_obj.parent = parent_obj
                        
                        # The built-in duplication should preserve all armature weighting and modifiers
                        # No need for complex manual copying
                        
                        # Remove the original linked collection
                        try:
                            # Unlink from scene collection first
                            if original_collection.name in context.scene.collection.children:
                                context.scene.collection.children.unlink(original_collection)
                            
                            # Remove the collection
                            bpy.data.collections.remove(original_collection)
                            self.report({'INFO'}, f"Removed original linked collection '{collection_name}'")
                            
                        except Exception as e:
                            self.report({'WARNING'}, f"Could not remove original collection: {str(e)}")
                        
                        editable_collections.append(editable_name)
                
                # Select and view the editable collections
                safe_deselect_all()
                
                for collection_name in editable_collections:
                    if collection_name in bpy.data.collections:
                        collection = bpy.data.collections[collection_name]
                        
                        # Select all objects in the collection
                        for obj in collection.objects:
                            obj.select_set(True)
                            # Set armature as active if available
                            if obj.type == 'ARMATURE':
                                context.view_layer.objects.active = obj
                
                # View the selected objects
                if context.selected_objects:
                    bpy.ops.view3d.view_selected()
                
                self.report({'INFO'}, f"Successfully created editable avatar collections: {', '.join(editable_collections)}")
                self.report({'INFO'}, "Avatars are now fully editable and ready for manipulation!")
                return {'FINISHED'}
            else:
                self.report({'ERROR'}, "No avatar collections were imported")
                return {'CANCELLED'}
                
        except Exception as e:
            self.report({'ERROR'}, f"Error importing avatar collections: {str(e)}")
            return {'CANCELLED'}
        finally:
            # Restore selection
            safe_deselect_all()
            for obj in current_selection:
                try:
                    if obj and obj.name in bpy.data.objects:
                        bpy.data.objects[obj.name].select_set(True)
                except (ReferenceError, RuntimeError):
                    pass
            if current_active:
                try:
                    if current_active.name in bpy.data.objects:
                        context.view_layer.objects.active = bpy.data.objects[current_active.name]
                except (ReferenceError, RuntimeError):
                    pass

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "avatar_shape", expand=True)
        layout.separator()
        layout.label(text="This tool imports and creates editable avatar collections:")
        layout.label(text="• Shape A: Male avatar base (fully editable)")
        layout.label(text="• Shape B: Female avatar base (fully editable)") 
        layout.label(text="• Both: Import both avatar shapes (fully editable)")
        layout.separator()
        layout.label(text="Avatars will be immediately ready for posing and manipulation!")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
    
    def _extract_avatar_files(self, assets_dir, temp_dir):
        """Extract avatar blend files from addon package to temp directory."""
        import shutil

        avatar_files = ["AvatarShape_A.blend", "AvatarShape_B.blend"]

        for avatar_file in avatar_files:
            source_path = os.path.join(assets_dir, avatar_file)
            dest_path = os.path.join(temp_dir, avatar_file)

            if os.path.exists(dest_path):
                continue

            if os.path.exists(source_path):
                try:
                    shutil.copy2(source_path, dest_path)
                    self.report({'INFO'}, f"Extracted {avatar_file}")
                except Exception as e:
                    self.report({'WARNING'}, f"Could not extract {avatar_file}: {str(e)}")
            else:
                self.report({'ERROR'}, f"Avatar file not found in addon: {avatar_file}")
                return False

        return True
