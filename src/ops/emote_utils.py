import re


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
