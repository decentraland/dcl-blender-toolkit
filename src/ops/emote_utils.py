import re

AVATAR_ROOT_BONE = "Avatar_Hips"
PROP_ROOT_BONE = "Prop_Root"

# Armature object names Decentraland expects inside an emote GLB.
AVATAR_EXPORT_NAME = "Armature"
PROP_EXPORT_NAME = "Armature_Prop"


def sanitize_emote_name(raw_name):
    """Format input as Capitalized_Words with no special characters."""
    parts = re.findall(r"[A-Za-z0-9]+", raw_name or "")
    if not parts:
        return "My_Emote"
    normalized = []
    for part in parts:
        if part.isdigit():
            normalized.append(part)
        else:
            normalized.append(part[0].upper() + part[1:].lower())
    return "_".join(normalized)


def find_target_armature(context):
    """
    Find the armature to operate on.
    Preference order:
    1) Active object if armature
    2) Selected armature
    3) First scene armature
    """
    obj = context.active_object
    if obj and obj.type == "ARMATURE":
        return obj

    for candidate in context.selected_objects:
        if candidate.type == "ARMATURE":
            return candidate

    for candidate in context.scene.objects:
        if candidate.type == "ARMATURE":
            return candidate
    return None


def is_avatar_armature(obj):
    """True when the armature carries the Decentraland avatar bone hierarchy."""
    if not obj or obj.type != "ARMATURE" or not obj.data:
        return False
    bones = obj.data.bones
    if AVATAR_ROOT_BONE in bones:
        return True
    return any(bone.name.startswith("Avatar_") for bone in bones)


def is_prop_armature(obj):
    """True when the armature looks like an emote prop rig rather than the avatar rig."""
    if not obj or obj.type != "ARMATURE" or not obj.data:
        return False
    return not is_avatar_armature(obj)


def find_avatar_armature(context):
    """
    Find the avatar rig specifically, so having a prop armature active does not
    make the prop stand in for the avatar.
    Preference order mirrors find_target_armature, but only considers avatar rigs;
    falls back to find_target_armature when no avatar rig is present.
    """
    obj = context.active_object
    if is_avatar_armature(obj):
        return obj

    for candidate in context.selected_objects:
        if is_avatar_armature(candidate):
            return candidate

    for candidate in context.scene.objects:
        if is_avatar_armature(candidate):
            return candidate

    return find_target_armature(context)


def find_prop_armatures(context, avatar_armature=None):
    """Return every scene armature that is not the avatar rig."""
    if avatar_armature is None:
        avatar_armature = find_avatar_armature(context)
    return [obj for obj in context.scene.objects if obj is not avatar_armature and is_prop_armature(obj)]


def collect_armature_geometry(context, armature_obj):
    """
    Return objects driven by an armature: descendants of the armature object plus
    anything carrying an Armature modifier pointing at it.
    """
    if not armature_obj:
        return []

    found = []
    seen = {armature_obj.name}

    def add(obj):
        if obj.name in seen:
            return
        seen.add(obj.name)
        found.append(obj)

    def add_descendants(parent):
        for obj in context.scene.objects:
            if obj.parent is parent:
                add(obj)
                add_descendants(obj)

    add_descendants(armature_obj)

    for obj in context.scene.objects:
        for modifier in getattr(obj, "modifiers", []):
            if modifier.type == "ARMATURE" and modifier.object is armature_obj:
                add(obj)

    return found


def collect_emote_export_objects(context, avatar_armature, prop_armatures=None):
    """
    Build the object set a Decentraland emote GLB must contain.

    The avatar armature is exported on its own - the avatar body meshes come from
    the wearer in-world, so only its bones and animation belong in the file. Prop
    armatures are exported together with their geometry, which is the visible part
    of a prop emote.
    """
    if prop_armatures is None:
        prop_armatures = find_prop_armatures(context, avatar_armature)

    objects = []
    seen = set()

    def add(obj):
        if obj is None or obj.name in seen:
            return
        seen.add(obj.name)
        objects.append(obj)

    add(avatar_armature)
    for prop_armature in prop_armatures:
        add(prop_armature)
        for obj in collect_armature_geometry(context, prop_armature):
            add(obj)

    return objects


def mute_armature_nla_strips(armatures):
    """
    Mute every NLA strip on the given rigs so only their active actions become
    GLB animations. Stashed or parked actions (other emotes, WIP takes) would
    otherwise export as extra clips. Returns (strip, previous_mute) pairs for
    restore_nla_mutes.
    """
    cache = []
    for rig in armatures:
        animation_data = getattr(rig, "animation_data", None)
        if not animation_data:
            continue
        for track in getattr(animation_data, "nla_tracks", None) or []:
            for strip in getattr(track, "strips", None) or []:
                cache.append((strip, strip.mute))
                strip.mute = True
    return cache


def restore_nla_mutes(cache):
    for strip, was_muted in cache:
        strip.mute = was_muted


def claim_export_names(avatar_armature, prop_armatures, find_object):
    """
    Give the exported rigs the object names Decentraland expects in the GLB:
    'Armature' for the avatar and 'Armature_Prop' for a single prop rig. An
    object already holding the name (typically a reference rig) is parked
    under a temporary name so ours doesn't get auto-suffixed to 'Armature.001'.
    find_object resolves a name to the object holding it (bpy.data.objects.get).
    Returns (object, original_name) pairs; undo with restore_names.
    """
    cache = []

    def claim(obj, name):
        if obj is None or obj.name == name:
            return
        if getattr(obj, "library", None) is not None:
            return
        holder = find_object(name)
        if holder is not None and holder is not obj:
            # Linked (library) objects can't be renamed; leave everything as is
            # rather than exporting under an auto-suffixed name anyway.
            if getattr(holder, "library", None) is not None:
                return
            cache.append((holder, holder.name))
            holder.name = f"{name}.dclexport"
        cache.append((obj, obj.name))
        obj.name = name

    claim(avatar_armature, AVATAR_EXPORT_NAME)
    if len(prop_armatures) == 1:
        claim(prop_armatures[0], PROP_EXPORT_NAME)
    return cache


def restore_names(cache):
    for obj, original_name in reversed(cache):
        obj.name = original_name


def get_deform_pose_bones(armature_obj):
    """Return deform pose bones, falling back to all pose bones."""
    if not armature_obj or armature_obj.type != "ARMATURE" or not armature_obj.pose:
        return []
    deform = [pb for pb in armature_obj.pose.bones if pb.bone.use_deform]
    return deform if deform else list(armature_obj.pose.bones)


def iter_action_fcurves(action):
    """
    Iterate FCurves for both legacy and slotted Actions.
    Supports Blender versions where Action.fcurves is unavailable.
    """
    if not action:
        return []

    fcurves = []
    seen_ids = set()

    def add_curve_list(curves):
        if not curves:
            return
        for curve in curves:
            key = id(curve)
            if key in seen_ids:
                continue
            seen_ids.add(key)
            fcurves.append(curve)

    # Legacy API (Blender <= 4.x)
    add_curve_list(getattr(action, "fcurves", None))

    # Slotted Actions API (Blender 5+)
    slots = list(getattr(action, "slots", []) or [])
    layers = list(getattr(action, "layers", []) or [])
    for layer in layers:
        for strip in list(getattr(layer, "strips", []) or []):
            if hasattr(strip, "channelbag"):
                for slot in slots:
                    try:
                        channelbag = strip.channelbag(slot)
                    except Exception:
                        channelbag = None
                    if channelbag is not None:
                        add_curve_list(getattr(channelbag, "fcurves", None))
            add_curve_list(getattr(strip, "fcurves", None))
            for bags_attr in ("channelbags", "channel_bags"):
                bags = getattr(strip, bags_attr, None)
                if not bags:
                    continue
                for bag in bags:
                    add_curve_list(getattr(bag, "fcurves", None))

    # Extra fallbacks for possible API variants.
    for attr in ("channelbags", "channel_bags"):
        bags = getattr(action, attr, None)
        if not bags:
            continue
        for bag in bags:
            add_curve_list(getattr(bag, "fcurves", None))

    return fcurves


def keyframe_exists(action, data_path, frame):
    if not action:
        return False
    for fcurve in iter_action_fcurves(action):
        if fcurve.data_path != data_path:
            continue
        for kp in fcurve.keyframe_points:
            if abs(kp.co.x - frame) < 0.01:
                return True
    return False


def pose_bone_world_location(armature_obj, pose_bone):
    """Get world-space location of a pose bone."""
    return armature_obj.matrix_world @ pose_bone.matrix.translation
