import bpy
import mathutils
import math

def create_bone(_ps_armature, _particle, _index):
    if (bpy.context.active_object.mode != 'EDIT'):
        bpy.ops.object.mode_set(mode='EDIT')

    bone = _ps_armature.data.edit_bones.new('bone_' + str(_index))
    bone.head = _particle.location
    bone.tail = (_particle.location.x, _particle.location.y + 1 , _particle.location.z)
    
def set_keyframe_bone_particle(_ps_armature, _particle, _index):
    if (bpy.context.active_object.mode != 'POSE'):
        bpy.ops.object.mode_set(mode='POSE')
    
    pose_bone = _ps_armature.pose.bones[_index]
    
    start_frame = bpy.context.scene.ps_converter_start_frame
    end_frame = bpy.context.scene.ps_converter_end_frame
    SAMPLING = 1
    
    for frame in range(start_frame, end_frame + 1):
        if((frame - start_frame) % SAMPLING != 0):
            continue
        
        bpy.context.scene.frame_set(frame)
        
        pose_bone.location = _ps_armature.matrix_world.inverted() @ pose_bone.bone.matrix_local.inverted() @ _particle.location
        pose_bone.keyframe_insert("location")
        
        pose_bone.rotation_quaternion = _particle.rotation
        pose_bone.keyframe_insert("rotation_quaternion")
        
        if _particle.alive_state == 'ALIVE':
            pose_bone.scale = (_particle.size, _particle.size, _particle.size)
        else:
            pose_bone.scale = (0, 0, 0)
            
        pose_bone.keyframe_insert("scale")
        

def duplicate_n_attach_obj_to_bone(_ps_armature, _object_to_copy, _index):
    if (bpy.context.active_object.mode != 'OBJECT'):
        bpy.ops.object.mode_set(mode='OBJECT')
    bpy.context.scene.frame_set(1)
    
    
    dupli_obj = bpy.data.objects.new(name='particle_'+str(_index), object_data=_object_to_copy.data.copy())
    #dupli = object_to_copy.copy()
    bpy.data.collections[bpy.context.scene.ps_converter_out_collection].objects.link(dupli_obj)
    dupli_obj.location = _ps_armature.data.bones[_index].head
    
    vertex_group = dupli_obj.vertex_groups.new(name='bone_'+str(_index))
    
    verticesToAdd = []
    for vertex in dupli_obj.data.vertices:
        verticesToAdd.append(vertex.index)
        vertex_group.add(verticesToAdd, 1.0, "ADD")
        
    dupli_obj.select_set(True)
    _ps_armature.select_set(True)
    bpy.context.view_layer.objects.active = _ps_armature
    
    bpy.ops.object.parent_set(type='ARMATURE_NAME', xmirror=False, keep_transform=True)
    

class OBJECT_OT_particles_to_armature_converter(bpy.types.Operator):
    """Convert Particle System to Armature Animation"""
    bl_idname = "object.particles_to_armature_converter"
    bl_label = "Particle System to Armature"
    bl_description = "Convert particle system animations to armature-based animations for better control and export"
    bl_options = {'REGISTER', 'UNDO'}
    
    def convert_particle_system(self, context):
        selected_objs = context.selected_objects
        
        for ob in selected_objs:
            ob.select_set(False)
        
        particle_list, particle_object_list = self.anaylize_particles(selected_objs)

        if (len(particle_list) == 0):
            self.report({'WARNING'}, "No particle systems found in selected objects")
            return

        # setup collection
        coll_name = bpy.data.collections.get(context.scene.ps_converter_out_collection)
        if(coll_name is None):
            out_collection = bpy.data.collections.new(name=context.scene.ps_converter_out_collection)
            context.scene.collection.children.link(out_collection)

        # setup armature
        armature_data = bpy.data.armatures.new("armature_data")
        PS_ARMATURE_OBJS = bpy.data.objects.new("armature_ps", armature_data)
        PS_ARMATURE_OBJS.location = (0, 0, 0)
        bpy.data.armatures[armature_data.name].display_type = 'STICK'
        bpy.data.collections[context.scene.ps_converter_out_collection].objects.link(PS_ARMATURE_OBJS)
        
        context.view_layer.objects.active = PS_ARMATURE_OBJS

        bpy.ops.object.mode_set(mode='EDIT')
        context.scene.frame_set(1)
        index = 0
        
        for particle in particle_list:
            create_bone(PS_ARMATURE_OBJS, particle, index)
            index += 1
        
        bpy.ops.object.mode_set(mode='POSE')
        index = 0
        for particle in particle_list:
            set_keyframe_bone_particle(PS_ARMATURE_OBJS, particle, index)
            index += 1
        
        bpy.ops.object.mode_set(mode='OBJECT')
        index = 0
        for particle in particle_list:
            duplicate_n_attach_obj_to_bone(PS_ARMATURE_OBJS, particle_object_list[index], index)
            index += 1

        self.report({'INFO'}, f"Converted {len(particle_list)} particles to armature animation")

    def anaylize_particles(self, _selected_objs):
        depsgraph = bpy.context.evaluated_depsgraph_get()

        particle_list = []
        particle_object_list = []

        for obj in _selected_objs:
            obj_evaluated = depsgraph.objects[obj.name]
            if obj_evaluated.particle_systems.active == None:
                continue
            
            for particle_system in obj_evaluated.particle_systems:
                ps_settings = particle_system.settings
                instance_object = ps_settings.instance_object
                object_index = 0
                object_index_count = 0

                for particle in particle_system.particles:
                    particle_list.append(particle)

                    object_to_copy = ''
                    if(ps_settings.render_type == 'COLLECTION'):
                        object_name = ps_settings.instance_weights[object_index].name.split(': ')[0]
                        object_to_copy = bpy.data.objects[object_name]
                        
                        object_index_count += 1
                        
                        if(ps_settings.use_collection_count):
                            if(object_index_count >= ps_settings.instance_weights[object_index].count):
                                object_index = (object_index + 1) % len(ps_settings.instance_weights)
                                object_index_count = 0
                        else:
                            object_index = (object_index + 1) % len(ps_settings.instance_weights)
                        
                    else:
                        object_to_copy = instance_object

                    particle_object_list.append(object_to_copy)
        
        return particle_list, particle_object_list

    def execute(self, context):
        if not context.selected_objects:
            self.report({'WARNING'}, "Please select objects with particle systems")
            return {'CANCELLED'}
        
        try:
            self.convert_particle_system(context)
            return {'FINISHED'}
        except Exception as e:
            self.report({'ERROR'}, f"Conversion failed: {str(e)}")
            return {'CANCELLED'}

    def draw(self, context):
        layout = self.layout
        layout.prop(context.scene, 'ps_converter_out_collection')
        layout.prop(context.scene, 'ps_converter_start_frame')
        layout.prop(context.scene, 'ps_converter_end_frame')
        layout.separator()
        layout.label(text="Select objects with particle systems to convert")
        layout.label(text="Creates armature with animated bones for each particle")
        layout.separator()
        layout.label(text="⚠️ IMPORTANT: Apply scale to particle instance objects", icon='ERROR')
        layout.label(text="before running this converter to prevent scaling issues")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
