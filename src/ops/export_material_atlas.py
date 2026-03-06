"""
Non-destructive material atlas optimizer for glTF/GLB export.

Merges 2 or 4 compatible PBR materials into a single atlas material
(BaseColor + ORM + Normal) to reduce draw calls.

Layout:
  4 × 512 → 1 × 1024×1024  (quad atlas)
  2 × 512 → 1 × 512×1024   (pair atlas, top/bottom)
"""

import math

import bpy

# ---------------------------------------------------------------------------
# sRGB ↔ Linear conversion (matches Blender / glTF colour pipeline)
# ---------------------------------------------------------------------------


def _srgb_to_linear(v):
    """Convert a single sRGB channel value to linear."""
    if v <= 0.04045:
        return v / 12.92
    return math.pow((v + 0.055) / 1.055, 2.4)


def _linear_to_srgb(v):
    """Convert a single linear channel value to sRGB."""
    if v <= 0.0031308:
        return v * 12.92
    return 1.055 * math.pow(v, 1.0 / 2.4) - 0.055


# ---------------------------------------------------------------------------
# Atlas tile layouts
# ---------------------------------------------------------------------------

TILE_SIZE = 512

LAYOUT_4 = {
    "name": "4x512_to_1024",
    "width": 1024,
    "height": 1024,
    "tiles": [
        (0, TILE_SIZE),  # Top-left
        (TILE_SIZE, TILE_SIZE),  # Top-right
        (0, 0),  # Bottom-left
        (TILE_SIZE, 0),  # Bottom-right
    ],
}

LAYOUT_2 = {
    "name": "2x512_to_512x1024",
    "width": 512,
    "height": 1024,
    "tiles": [
        (0, TILE_SIZE),  # Top   (tile 0)
        (0, 0),  # Bottom (tile 1)
    ],
}


# ---------------------------------------------------------------------------
# Helper data classes
# ---------------------------------------------------------------------------


class ExportAtlasState:
    """Holds temporary scene data created for export and cleans it up."""

    def __init__(self, scene, temp_collection, export_objects, created_images, created_materials):
        self.scene = scene
        self.temp_collection = temp_collection
        self.export_objects = export_objects
        self.created_images = created_images
        self.created_materials = created_materials

    def cleanup(self):
        if self.temp_collection:
            if self.scene and self.temp_collection.name in self.scene.collection.children:
                self.scene.collection.children.unlink(self.temp_collection)

            objs = list(self.temp_collection.objects)
            for obj in objs:
                data = getattr(obj, "data", None)
                bpy.data.objects.remove(obj, do_unlink=True)
                if data and hasattr(data, "users") and data.users == 0:
                    data_type = type(data).__name__
                    if data_type == "Mesh":
                        bpy.data.meshes.remove(data)
                    elif data_type == "Camera":
                        bpy.data.cameras.remove(data)
                    elif data_type == "Light":
                        bpy.data.lights.remove(data)
                    elif data_type == "Armature":
                        bpy.data.armatures.remove(data)
            if self.temp_collection.users == 0:
                bpy.data.collections.remove(self.temp_collection)

        for mat in self.created_materials:
            if mat and mat.name in bpy.data.materials and bpy.data.materials[mat.name].users == 0:
                bpy.data.materials.remove(bpy.data.materials[mat.name])

        for img in self.created_images:
            if img and img.name in bpy.data.images and bpy.data.images[img.name].users == 0:
                bpy.data.images.remove(bpy.data.images[img.name])


class MaterialAnalysis:
    """Result of analyzing one Principled BSDF material for atlas compatibility."""

    def __init__(
        self,
        material,
        key,
        base_image,
        normal_image,
        rough_source,
        metal_source,
        uses_alpha=False,
        base_color_tint=None,
        emissive_image=None,
        emissive_strength=0.0,
    ):
        self.material = material
        self.key = key
        self.base_image = base_image
        self.normal_image = normal_image
        self.rough_source = rough_source
        self.metal_source = metal_source
        self.uses_alpha = uses_alpha
        # (R, G, B) multiply tint from MixRGB/MixColor/ColorFactor nodes
        # between the texture and the Principled BSDF.  None = no tint (1,1,1).
        self.base_color_tint = base_color_tint
        # Emissive channel
        self.emissive_image = emissive_image  # bpy.types.Image or None
        self.emissive_strength = emissive_strength  # float (Emission Strength)


class ChannelSource:
    """Describes how a scalar PBR channel (Roughness / Metallic) is sourced."""

    def __init__(self, mode, image=None, channel=0, scalar=0.0):
        self.mode = mode  # "SCALAR" or "IMAGE"
        self.image = image  # bpy.types.Image or None
        self.channel = channel  # RGBA channel index (0-3)
        self.scalar = scalar  # constant value when mode == "SCALAR"


# ---------------------------------------------------------------------------
# Main optimizer class
# ---------------------------------------------------------------------------


class MaterialAtlasOptimizer:
    def __init__(self, context, export_objects, resize_mode="AGGRESSIVE", debug_report=True):
        self.context = context
        self.scene = context.scene
        self.export_objects = export_objects
        self.resize_mode = resize_mode  # 'CONSERVATIVE' or 'AGGRESSIVE'
        self.debug_report = debug_report
        self.created_images = []
        self.created_materials = []
        self.pixel_cache = {}
        self.resized_from_sources = set()

    # -------------------------------------------------------------------
    # Public entry point
    # -------------------------------------------------------------------

    def run(self):
        temp_collection, duplicated = self._duplicate_export_objects()
        mesh_objects = [obj for obj in duplicated if obj.type == "MESH"]
        before_mats, before_tex = self._count_used(mesh_objects)

        report = {
            "candidate_materials": 0,
            "merged_quartets": 0,
            "merged_pairs": 0,
            "leftover_materials": 0,
            "drawcall_reduction_estimate": 0,
            "resized_textures_to_512": 0,
            "before_materials": before_mats,
            "before_textures": before_tex,
            "warnings": [],
        }

        analysis = self._collect_candidates(mesh_objects, report)
        report["candidate_materials"] = len(analysis)

        groups = self._build_groups(analysis, report)

        for group_index, group in enumerate(groups):
            try:
                atlas_mat = self._build_atlas_material(group_index, group["items"], group["layout"])
                self._apply_group(mesh_objects, group["items"], group["layout"], atlas_mat)
                if len(group["items"]) == 4:
                    report["merged_quartets"] += 1
                elif len(group["items"]) == 2:
                    report["merged_pairs"] += 1
            except Exception as exc:
                report["warnings"].append(f"Group {group_index + 1} skipped: {exc}")

        merged_count = (report["merged_quartets"] * 4) + (report["merged_pairs"] * 2)
        report["leftover_materials"] = max(0, len(analysis) - merged_count)
        report["drawcall_reduction_estimate"] = (report["merged_quartets"] * 3) + (report["merged_pairs"] * 1)
        report["resized_textures_to_512"] = len(self.resized_from_sources)

        after_mats, after_tex = self._count_used(mesh_objects)
        report["after_materials"] = after_mats
        report["after_textures"] = after_tex

        state = ExportAtlasState(
            self.scene,
            temp_collection,
            duplicated,
            self.created_images,
            self.created_materials,
        )
        return state, report

    # -------------------------------------------------------------------
    # Duplication (non-destructive: work on copies)
    # -------------------------------------------------------------------

    def _duplicate_export_objects(self):
        temp_collection = bpy.data.collections.new("DCL_AtlasExport_Temp")
        self.scene.collection.children.link(temp_collection)

        obj_map = {}
        duplicated = []

        for obj in self.export_objects:
            dup = obj.copy()
            if obj.data:
                dup.data = obj.data.copy()
            temp_collection.objects.link(dup)
            obj_map[obj] = dup
            duplicated.append(dup)

        for orig, dup in obj_map.items():
            if orig.parent and orig.parent in obj_map:
                dup.parent = obj_map[orig.parent]
                dup.matrix_parent_inverse = orig.matrix_parent_inverse.copy()

        # Force a depsgraph evaluation so all duplicated mesh internals
        # (UV layers, loop data, material slots) are fully synced.
        # Without this, foreach_get on UV data can see stale sizes.
        try:
            depsgraph = self.context.evaluated_depsgraph_get()
            depsgraph.update()
        except Exception:
            pass

        # Also call mesh.update() on each duplicated mesh for good measure.
        for obj in duplicated:
            if obj.type == "MESH" and obj.data:
                try:
                    obj.data.update()
                except Exception:
                    pass

        return temp_collection, duplicated

    # -------------------------------------------------------------------
    # Counting helpers
    # -------------------------------------------------------------------

    def _count_used(self, mesh_objects):
        mats = set()
        images = set()
        for obj in mesh_objects:
            if not obj.data or not obj.data.materials:
                continue
            for mat in obj.data.materials:
                if not mat:
                    continue
                mats.add(mat.name)
                if mat.use_nodes and mat.node_tree:
                    for node in mat.node_tree.nodes:
                        if node.type == "TEX_IMAGE" and node.image:
                            images.add(node.image.name)
        return len(mats), len(images)

    # -------------------------------------------------------------------
    # Candidate collection — only materials actually used by polygons
    # -------------------------------------------------------------------

    def _material_max_texture_size(self, material):
        """Return the largest dimension among all image textures used by *material*."""
        max_size = 0
        if not material.use_nodes or not material.node_tree:
            return max_size
        for node in material.node_tree.nodes:
            if node.type == "TEX_IMAGE" and node.image:
                w = int(node.image.size[0])
                h = int(node.image.size[1])
                max_size = max(max_size, w, h)
        return max_size

    def _collect_candidates(self, mesh_objects, report):
        unique_materials = []
        seen = set()
        # Track which materials use tiled UVs (any coord outside 0-1 range).
        tiled_materials = set()

        # UV bounds threshold — small margin for floating-point imprecision.
        UV_MIN = -0.01
        UV_MAX = 1.01

        for obj in mesh_objects:
            mesh = obj.data
            if not mesh or not mesh.materials:
                continue

            # Read UV data once per mesh.
            uv_layer = self._get_source_uv_layer(mesh)
            uv_data = None
            if uv_layer and len(uv_layer.data) > 0:
                uv_data = self._read_uv_data(uv_layer)

            used_indices = set()
            for poly in mesh.polygons:
                used_indices.add(poly.material_index)

            for idx in sorted(used_indices):
                if idx < 0 or idx >= len(mesh.materials):
                    continue
                mat = mesh.materials[idx]
                if not mat:
                    continue

                # Check if this material's UVs exceed the unit square on this mesh.
                if uv_data and mat.name not in tiled_materials:
                    for poly in mesh.polygons:
                        if poly.material_index != idx:
                            continue
                        for li in poly.loop_indices:
                            bi = li * 2
                            if bi + 1 < len(uv_data):
                                u = uv_data[bi]
                                v = uv_data[bi + 1]
                                if u < UV_MIN or u > UV_MAX or v < UV_MIN or v > UV_MAX:
                                    tiled_materials.add(mat.name)
                                    break
                        if mat.name in tiled_materials:
                            break

                if mat.name not in seen:
                    unique_materials.append(mat)
                    seen.add(mat.name)

        unique_materials.sort(key=lambda m: m.name)

        analysis = []
        for mat in unique_materials:
            if mat.name in tiled_materials:
                if self.debug_report:
                    report["warnings"].append(f"Material '{mat.name}' uses tiled UVs (outside 0-1) — skipped")
                continue

            # In conservative mode, skip materials whose textures are
            # larger than the tile size (512px).  This preserves the
            # quality of 1024px textures by leaving them untouched.
            if self.resize_mode == "CONSERVATIVE":
                max_tex = self._material_max_texture_size(mat)
                if max_tex > TILE_SIZE:
                    if self.debug_report:
                        report["warnings"].append(
                            f"Material '{mat.name}' has {max_tex}px textures — "
                            f"skipped (conservative mode keeps 1024px textures intact)"
                        )
                    continue

            result = self._analyze_material(mat)
            if result:
                analysis.append(result)
            elif self.debug_report:
                report["warnings"].append(f"Material '{mat.name}' not compatible with atlas rules")
        return analysis

    # -------------------------------------------------------------------
    # Group building — bucket by compatibility key, form 4s then 2s
    # -------------------------------------------------------------------

    def _build_groups(self, analysis, report):
        buckets = {}
        for item in analysis:
            buckets.setdefault(item.key, []).append(item)

        groups = []
        allow_pairs = True  # always merge pairs (2 -> 512x1024) and quartets (4 -> 1024x1024)

        for key in sorted(buckets.keys(), key=lambda x: str(x)):
            bucket = sorted(buckets[key], key=lambda x: x.material.name)

            # Form quartets first
            while len(bucket) >= 4:
                groups.append({"items": bucket[:4], "layout": LAYOUT_4})
                bucket = bucket[4:]

            # Then pairs
            if allow_pairs:
                while len(bucket) >= 2:
                    groups.append({"items": bucket[:2], "layout": LAYOUT_2})
                    bucket = bucket[2:]

        return groups

    # -------------------------------------------------------------------
    # Material analysis — extract PBR textures from Principled BSDF
    # -------------------------------------------------------------------

    def _analyze_material(self, material):
        if not material.use_nodes or not material.node_tree:
            return None

        principled = self._find_principled(material)
        if not principled:
            return None

        base_input = self._socket_by_names(principled.inputs, ["Base Color"])
        normal_input = self._socket_by_names(principled.inputs, ["Normal"])
        rough_input = self._socket_by_names(principled.inputs, ["Roughness"])
        metal_input = self._socket_by_names(principled.inputs, ["Metallic"])
        emission_input = self._socket_by_names(principled.inputs, ["Emission Color", "Emission"])
        emission_str_input = self._socket_by_names(principled.inputs, ["Emission Strength"])

        if not base_input:
            return None

        base_result = self._extract_base_image(base_input)
        if not base_result:
            return None

        base_image, base_color_tint = base_result

        normal_image = None
        if normal_input:
            normal_extract = self._extract_normal_image_and_strength(normal_input)
            if normal_extract:
                normal_image, _strength = normal_extract

        rough_source = ChannelSource(mode="SCALAR", scalar=0.5)
        if rough_input:
            rough_source = self._extract_scalar_or_texture_source(rough_input)

        metal_source = ChannelSource(mode="SCALAR", scalar=0.0)
        if metal_input:
            metal_source = self._extract_scalar_or_texture_source(metal_input)

        # Emissive channel — extract texture and strength.
        emissive_image = None
        emissive_strength = 0.0
        if emission_str_input:
            emissive_strength = float(getattr(emission_str_input, "default_value", 0.0))
        if emission_input and emission_input.is_linked:
            tex_node = self._trace_to_tex_image(emission_input)
            if tex_node and tex_node.image:
                emissive_image = tex_node.image
                # If strength socket is missing, assume 1.0 when a texture is connected
                if emissive_strength == 0.0 and emission_str_input is None:
                    emissive_strength = 1.0

        # Detect whether alpha is actually used (wired to the Principled BSDF).
        uses_alpha = False
        alpha_input = self._socket_by_names(principled.inputs, ["Alpha"])
        blend = getattr(material, "blend_method", "OPAQUE")
        if blend not in {"OPAQUE", ""} and alpha_input and alpha_input.is_linked:
            uses_alpha = True

        # Compatibility key — only blend mode + alpha threshold matter.
        # Normal/roughness/metallic/emissive differences are handled at blit time
        # (flat fill, scalar fill) so they don't prevent merging.
        alpha_key = 0.0
        if blend == "CLIP":
            alpha_key = round(float(getattr(material, "alpha_threshold", 0.5)), 4)

        key = (blend, alpha_key, uses_alpha)

        return MaterialAnalysis(
            material=material,
            key=key,
            base_image=base_image,
            normal_image=normal_image,
            rough_source=rough_source,
            metal_source=metal_source,
            uses_alpha=uses_alpha,
            base_color_tint=base_color_tint,
            emissive_image=emissive_image,
            emissive_strength=emissive_strength,
        )

    def _find_principled(self, material):
        tree = material.node_tree
        # Try via active Material Output first.
        for node in tree.nodes:
            if node.type == "OUTPUT_MATERIAL" and getattr(node, "is_active_output", False):
                surf = node.inputs.get("Surface")
                if surf and surf.is_linked:
                    from_node = surf.links[0].from_node
                    if from_node and from_node.type == "BSDF_PRINCIPLED":
                        return from_node
        # Fallback: first Principled in tree.
        for node in tree.nodes:
            if node.type == "BSDF_PRINCIPLED":
                return node
        return None

    def _socket_by_names(self, socket_collection, names):
        for name in names:
            sock = socket_collection.get(name)
            if sock:
                return sock
        return None

    def _extract_base_image(self, input_socket):
        """
        Extract the base color image and any multiply tint applied to it.

        Handles common patterns:
          - TexImage → Base Color  (no tint)
          - TexImage → MixRGB/MixColor [Multiply] → Base Color  (tint from B socket)
          - TexImage → ColorFactor → Base Color  (tint from factor/color)

        Returns (image, tint) where tint is (R,G,B) or None.
        """
        result = self._extract_base_image_and_tint(input_socket)
        if result:
            return result  # (image, tint_or_None)
        # Fallback: plain trace with no tint.
        tex_node = self._trace_to_tex_image(input_socket)
        if tex_node:
            return (tex_node.image, None)
        return None

    def _extract_base_image_and_tint(self, input_socket):
        """Detect MixRGB/MixColor Multiply node between texture and BSDF.

        Handles both legacy MixRGB and Blender 4.x ShaderNodeMix.
        """
        if not input_socket.is_linked:
            return None

        from_node = input_socket.links[0].from_node
        if not from_node:
            return None

        # Detect Mix / MixRGB nodes.
        is_mix = from_node.type in {"MIX_RGB", "MIX"}
        if not is_mix:
            is_mix = getattr(from_node, "bl_idname", "") in {
                "ShaderNodeMixRGB",
                "ShaderNodeMix",
            }
        if not is_mix:
            return None

        # Get the blend type.
        blend_type = getattr(from_node, "blend_type", None)
        if blend_type not in {"MULTIPLY", "MIX", None}:
            return None

        # --- Find the two color inputs robustly across Blender versions ---
        # MixRGB:       "Fac", "Color1", "Color2"
        # ShaderNodeMix: multiple "Factor"/"A"/"B" for different data types.
        #                We need the COLOR-type "A" and "B", not the float/vector ones.
        input_a, input_b = self._find_mix_color_inputs(from_node)
        if not input_a or not input_b:
            return None

        # Determine which input has the texture and which has the tint color.
        tex_node_a = self._trace_to_tex_image(input_a) if input_a.is_linked else None
        tex_node_b = self._trace_to_tex_image(input_b) if input_b.is_linked else None

        tex_node = None
        tint_color = None

        if tex_node_a and not tex_node_b:
            tex_node = tex_node_a
            tint_color = self._read_socket_color(input_b)
        elif tex_node_b and not tex_node_a:
            tex_node = tex_node_b
            tint_color = self._read_socket_color(input_a)
        elif tex_node_a and tex_node_b:
            tex_node = tex_node_a
            tint_color = None
        else:
            return None

        if not tex_node or not tex_node.image:
            return None

        # For MIX blend type, check the factor.
        if blend_type == "MIX" and tint_color:
            fac_input = self._find_mix_factor_input(from_node)
            if fac_input and not fac_input.is_linked:
                fac = float(fac_input.default_value)
                if fac < 0.01:
                    tint_color = None

        return (tex_node.image, tint_color)

    def _find_mix_color_inputs(self, mix_node):
        """
        Find the two Color-type inputs (A and B) on a MixRGB or ShaderNodeMix node.

        Blender 4.x ShaderNodeMix has multiple inputs named "A" and "B" for
        different data types (Float, Vector, Color, Rotation).  We need the
        RGBA/COLOR ones, which have default_value with 4 components.
        """
        # Legacy MixRGB — straightforward names.
        c1 = mix_node.inputs.get("Color1")
        c2 = mix_node.inputs.get("Color2")
        if c1 and c2:
            return c1, c2

        # ShaderNodeMix (Blender 3.4+ / 4.x) — find RGBA sockets named A and B.
        color_a = None
        color_b = None
        for inp in mix_node.inputs:
            # Identify Color sockets: they have a default_value with 4 components (RGBA).
            dv = getattr(inp, "default_value", None)
            if dv is None:
                continue
            try:
                length = len(dv)
            except TypeError:
                continue

            if length == 4:
                name = inp.name.strip()
                if name == "A" and color_a is None:
                    color_a = inp
                elif name == "B" and color_b is None:
                    color_b = inp

        return color_a, color_b

    def _find_mix_factor_input(self, mix_node):
        """Find the scalar Factor/Fac input on a Mix node."""
        for name in ("Fac", "Factor"):
            inp = mix_node.inputs.get(name)
            if inp:
                # Make sure it's a scalar (not vector) factor.
                dv = getattr(inp, "default_value", None)
                if dv is not None:
                    try:
                        float(dv)
                        return inp
                    except (TypeError, ValueError):
                        continue
        # Fallback: first input with a scalar default.
        for inp in mix_node.inputs:
            dv = getattr(inp, "default_value", None)
            if dv is None:
                continue
            try:
                float(dv)
                if inp.name.lower() in ("fac", "factor"):
                    return inp
            except (TypeError, ValueError):
                continue
        return None

    def _read_socket_color(self, socket):
        """Read an RGBA socket's default_value as a linear (R, G, B) tuple."""
        dv = getattr(socket, "default_value", None)
        if dv is None:
            return None
        try:
            r = float(dv[0])
            g = float(dv[1])
            b = float(dv[2])
            return (r, g, b)
        except (TypeError, IndexError):
            return None

    def _extract_normal_image_and_strength(self, input_socket):
        if not input_socket.is_linked:
            return None

        from_node = input_socket.links[0].from_node
        if not from_node:
            return None

        if from_node.type == "NORMAL_MAP":
            color_input = from_node.inputs.get("Color")
            if not color_input or not color_input.is_linked:
                return None
            tex_node = self._trace_to_tex_image(color_input)
            if not tex_node:
                return None
            strength = from_node.inputs.get("Strength")
            strength_val = strength.default_value if strength else 1.0
            return tex_node.image, strength_val

        if from_node.type == "TEX_IMAGE" and from_node.image:
            return from_node.image, 1.0

        tex_node = self._trace_to_tex_image(input_socket)
        if tex_node:
            return tex_node.image, 1.0
        return None

    def _extract_scalar_or_texture_source(self, input_socket):
        if not input_socket.is_linked:
            return ChannelSource(mode="SCALAR", scalar=float(input_socket.default_value))

        link = input_socket.links[0]
        from_node = link.from_node
        from_socket = link.from_socket

        if from_node and from_node.type == "TEX_IMAGE" and from_node.image:
            channel = 3 if from_socket.name == "Alpha" else 0
            return ChannelSource(mode="IMAGE", image=from_node.image, channel=channel)

        if from_node and from_node.type in {"SEPARATE_RGB", "SEPARATE_COLOR"}:
            channel = self._channel_from_socket_name(from_socket.name)
            color_input = from_node.inputs.get("Image") or from_node.inputs.get("Color")
            if color_input and color_input.is_linked:
                tex_node = self._trace_to_tex_image(color_input)
                if tex_node and tex_node.image:
                    return ChannelSource(mode="IMAGE", image=tex_node.image, channel=channel)

        tex_node = self._trace_to_tex_image(input_socket)
        if tex_node and tex_node.image:
            return ChannelSource(mode="IMAGE", image=tex_node.image, channel=0)

        return ChannelSource(mode="SCALAR", scalar=float(input_socket.default_value))

    def _trace_to_tex_image(self, input_socket, depth=0, visited=None):
        if depth > 16 or not input_socket.is_linked:
            return None

        from_node = input_socket.links[0].from_node
        if not from_node:
            return None

        if visited is None:
            visited = set()
        node_key = (from_node.name, from_node.type)
        if node_key in visited:
            return None
        visited.add(node_key)

        if from_node.type == "TEX_IMAGE" and from_node.image:
            return from_node

        if from_node.type in {"SEPARATE_RGB", "SEPARATE_COLOR"}:
            upstream = from_node.inputs.get("Image") or from_node.inputs.get("Color")
            if upstream:
                return self._trace_to_tex_image(upstream, depth + 1, visited)

        for inp in from_node.inputs:
            if inp.is_linked:
                result = self._trace_to_tex_image(inp, depth + 1, visited)
                if result:
                    return result
        return None

    def _channel_from_socket_name(self, name):
        lowered = (name or "").lower()
        if lowered in {"r", "red"}:
            return 0
        if lowered in {"g", "green"}:
            return 1
        if lowered in {"b", "blue"}:
            return 2
        if lowered in {"a", "alpha"}:
            return 3
        return 0

    # -------------------------------------------------------------------
    # Image pixel reading — robust for packed, file, and generated images
    # -------------------------------------------------------------------

    def _force_image_pixels_available(self, image):
        """
        Guarantee the image pixel buffer is populated and readable.

        Blender stores packed / file images in compressed form internally.
        The .pixels property may return all-zeros until the buffer is
        explicitly inflated.  ``image.scale(w, h)`` (even to the same size)
        forces Blender to decompress and allocate the float buffer.
        """
        if not image:
            return

        w = max(1, int(image.size[0]))
        h = max(1, int(image.size[1]))

        # Step 1 — reload from source (packed data or file path).
        try:
            image.reload()
        except Exception:
            pass

        # Step 2 — scale to same size.  This is the most reliable way to
        # force the pixel buffer to be allocated on every Blender version.
        try:
            image.scale(w, h)
        except Exception:
            pass

        # Step 3 — update (flushes internal caches).
        try:
            image.update()
        except Exception:
            pass

    def _image_pixels(self, image):
        """Read RGBA pixel data as a flat list.  Cached per image name."""
        cache_key = image.name
        cached = self.pixel_cache.get(cache_key)
        if cached is not None:
            return cached

        self._force_image_pixels_available(image)

        w = max(1, int(image.size[0]))
        h = max(1, int(image.size[1]))
        expected = w * h * 4

        try:
            pixel_data = list(image.pixels[:])
        except Exception:
            pixel_data = []

        if len(pixel_data) != expected:
            pixel_data = [0.0] * expected
            for i in range(3, expected, 4):
                pixel_data[i] = 1.0

        # If still all-zero after the first read, try one more aggressive reload.
        sample = pixel_data[: min(128, expected)]
        if expected > 0 and all(v == 0.0 for v in sample):
            try:
                image.reload()
                image.scale(w, h)
                pixel_data = list(image.pixels[:])
                if len(pixel_data) != expected:
                    pixel_data = [0.0] * expected
                    for i in range(3, expected, 4):
                        pixel_data[i] = 1.0
            except Exception:
                pass

        self.pixel_cache[cache_key] = pixel_data
        return pixel_data

    # -------------------------------------------------------------------
    # Atlas texture building (pixel blitting)
    # -------------------------------------------------------------------

    def _build_atlas_material(self, group_index, group, layout):
        atlas_w = layout["width"]
        atlas_h = layout["height"]
        group_name = f"DCLAtlas_{group_index + 1}"
        size_label = f"{atlas_w}x{atlas_h}"

        base_img = self._new_image(f"{group_name}_BaseColor_{size_label}", "sRGB", atlas_w, atlas_h)
        orm_img = self._new_image(f"{group_name}_ORM_{size_label}", "Non-Color", atlas_w, atlas_h)
        normal_img = self._new_image(f"{group_name}_Normal_{size_label}", "Non-Color", atlas_w, atlas_h)

        # Only create emissive atlas if at least one material in the group has one.
        group_has_emissive = any(item.emissive_image is not None for item in group)
        emissive_img = None
        # Pre-compute the unified emission strength (the maximum in the group).
        # Individual tile brightnesses are scaled relative to this so each
        # tile keeps its original perceived intensity.
        emissive_max_strength = 1.0
        if group_has_emissive:
            emissive_max_strength = max(
                (item.emissive_strength for item in group if item.emissive_image),
                default=1.0,
            )
            emissive_max_strength = max(emissive_max_strength, 0.001)  # avoid /0
            emissive_img = self._new_image(f"{group_name}_Emissive_{size_label}", "sRGB", atlas_w, atlas_h)

        total_px = atlas_w * atlas_h * 4
        base_pixels = [0.0] * total_px
        orm_pixels = [0.0] * total_px
        normal_pixels = [0.0] * total_px
        emissive_pixels = [0.0] * total_px if group_has_emissive else None

        # Fill defaults: BaseColor = black opaque, ORM = (1,0.5,0,1), Normal = flat (0.5,0.5,1,1)
        for i in range(0, total_px, 4):
            base_pixels[i + 3] = 1.0

            orm_pixels[i + 0] = 1.0  # AO = white
            orm_pixels[i + 1] = 0.5  # Roughness = 0.5
            orm_pixels[i + 2] = 0.0  # Metallic = 0
            orm_pixels[i + 3] = 1.0

            normal_pixels[i + 0] = 0.5
            normal_pixels[i + 1] = 0.5
            normal_pixels[i + 2] = 1.0
            normal_pixels[i + 3] = 1.0

            # Emissive default: black (no emission)
            if emissive_pixels is not None:
                emissive_pixels[i + 3] = 1.0

        for tile_idx, item in enumerate(group):
            x_off, y_off = layout["tiles"][tile_idx]

            # BaseColor (apply multiply tint if the material had a Color Factor node)
            self._blit_rgba(item.base_image, base_pixels, atlas_w, x_off, y_off, tint=item.base_color_tint)

            # Normal
            if item.normal_image:
                self._blit_rgba(item.normal_image, normal_pixels, atlas_w, x_off, y_off)
            # else: keep the flat-normal default already written

            # ORM (Occlusion=1, Roughness, Metallic)
            self._blit_orm(item.rough_source, item.metal_source, orm_pixels, atlas_w, x_off, y_off)

            # Emissive — bake per-tile strength differences into pixel brightness.
            # ratio = this_material_strength / max_group_strength, applied as a
            # uniform RGB tint so the single Emission Strength on the atlas BSDF
            # produces the correct intensity for every tile.
            if emissive_pixels is not None and item.emissive_image:
                ratio = item.emissive_strength / emissive_max_strength
                emissive_tint = (ratio, ratio, ratio) if ratio < 0.999 else None
                self._blit_rgba(item.emissive_image, emissive_pixels, atlas_w, x_off, y_off, tint=emissive_tint)
            # else: keep black (no emission) for this tile

        # Write pixel data — use slice assignment (most reliable across versions).
        base_img.pixels[:] = base_pixels
        orm_img.pixels[:] = orm_pixels
        normal_img.pixels[:] = normal_pixels
        if emissive_img is not None:
            emissive_img.pixels[:] = emissive_pixels

        # update() flushes internal caches so the data is visible.
        base_img.update()
        orm_img.update()
        normal_img.update()
        if emissive_img is not None:
            emissive_img.update()

        # Pack images into .blend data so the glTF/GLB exporter can embed them.
        # Without this, in-memory-only images may be skipped or exported as black.
        for img in (base_img, orm_img, normal_img, emissive_img):
            if img is None:
                continue
            try:
                img.pack()
            except Exception:
                pass

        # --- Build the atlas material node tree ---
        atlas_mat = bpy.data.materials.new(name=f"{group_name}_Material")
        atlas_mat.use_nodes = True
        ref_mat = group[0].material

        # Copy surface properties from first material in group.
        # Only propagate non-opaque blend mode if any source actually uses alpha.
        group_needs_alpha = any(item.uses_alpha for item in group)
        if hasattr(atlas_mat, "blend_method"):
            if group_needs_alpha:
                atlas_mat.blend_method = getattr(ref_mat, "blend_method", "OPAQUE")
            else:
                atlas_mat.blend_method = "OPAQUE"
        if hasattr(atlas_mat, "shadow_method") and hasattr(ref_mat, "shadow_method"):
            atlas_mat.shadow_method = ref_mat.shadow_method
        atlas_mat.use_backface_culling = ref_mat.use_backface_culling
        if hasattr(atlas_mat, "alpha_threshold"):
            atlas_mat.alpha_threshold = getattr(ref_mat, "alpha_threshold", 0.5)

        nodes = atlas_mat.node_tree.nodes
        links = atlas_mat.node_tree.links
        nodes.clear()

        out = nodes.new(type="ShaderNodeOutputMaterial")
        out.location = (600, 0)
        bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
        bsdf.location = (300, 0)

        tex_base = nodes.new(type="ShaderNodeTexImage")
        tex_base.image = base_img
        tex_base.label = "BaseColor"
        tex_base.location = (-400, 150)

        tex_orm = nodes.new(type="ShaderNodeTexImage")
        tex_orm.image = orm_img
        tex_orm.label = "ORM"
        tex_orm.image.colorspace_settings.name = "Non-Color"
        tex_orm.location = (-400, -30)

        # SeparateColor (Blender 3.3+ / 4.x) preferred — the glTF exporter in
        # modern Blender only detects this node type for metallic-roughness.
        # Fall back to SeparateRGB only for very old versions.
        try:
            sep = nodes.new(type="ShaderNodeSeparateColor")
            sep_green = "Green"
            sep_blue = "Blue"
        except Exception:
            sep = nodes.new(type="ShaderNodeSeparateRGB")
            sep_green = "G"
            sep_blue = "B"
        sep.location = (-150, -40)

        tex_n = nodes.new(type="ShaderNodeTexImage")
        tex_n.image = normal_img
        tex_n.label = "Normal"
        tex_n.image.colorspace_settings.name = "Non-Color"
        tex_n.location = (-400, -220)

        normal_map = nodes.new(type="ShaderNodeNormalMap")
        normal_map.location = (-150, -220)
        normal_map.space = "TANGENT"
        normal_map.inputs["Strength"].default_value = 1.0

        # UV Map node — references the atlas UV layer we'll create on each mesh.
        # We use "UVMap" as the name because after _finalize_uv_layers it will
        # be the only UV layer (renamed to "UVMap" for TEXCOORD_0 alignment).
        uv_map = nodes.new(type="ShaderNodeUVMap")
        uv_map.location = (-650, -40)
        uv_map.uv_map = "UVMap"

        # Wire everything up.
        links.new(uv_map.outputs["UV"], tex_base.inputs["Vector"])
        links.new(uv_map.outputs["UV"], tex_orm.inputs["Vector"])
        links.new(uv_map.outputs["UV"], tex_n.inputs["Vector"])

        links.new(tex_base.outputs["Color"], bsdf.inputs["Base Color"])

        # Only wire alpha if ANY source material in the group actually uses it.
        # Connecting alpha on opaque materials causes unwanted transparency.
        group_uses_alpha = any(item.uses_alpha for item in group)
        if group_uses_alpha and "Alpha" in tex_base.outputs and "Alpha" in bsdf.inputs:
            links.new(tex_base.outputs["Alpha"], bsdf.inputs["Alpha"])

        links.new(tex_orm.outputs["Color"], sep.inputs[0])
        links.new(sep.outputs[sep_green], bsdf.inputs["Roughness"])
        links.new(sep.outputs[sep_blue], bsdf.inputs["Metallic"])

        links.new(tex_n.outputs["Color"], normal_map.inputs["Color"])
        links.new(normal_map.outputs["Normal"], bsdf.inputs["Normal"])

        # Emissive — only add the texture node and wiring when the group uses it.
        if emissive_img is not None:
            tex_emissive = nodes.new(type="ShaderNodeTexImage")
            tex_emissive.image = emissive_img
            tex_emissive.label = "Emissive"
            tex_emissive.location = (-400, -420)

            links.new(uv_map.outputs["UV"], tex_emissive.inputs["Vector"])

            # Blender 4.0+ renamed "Emission" to "Emission Color"
            emission_color_input = self._socket_by_names(bsdf.inputs, ["Emission Color", "Emission"])
            if emission_color_input:
                links.new(tex_emissive.outputs["Color"], emission_color_input)

            # Normalized to 1.0 — all strength differences are already baked
            # into the emissive pixel brightness (ratio = item / max).
            emission_str_input = bsdf.inputs.get("Emission Strength")
            if emission_str_input:
                emission_str_input.default_value = 1.0

        links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

        self.created_materials.append(atlas_mat)
        return atlas_mat

    def _new_image(self, name, colorspace_name, width, height):
        img = bpy.data.images.new(name=name, width=width, height=height, alpha=True)
        img.generated_color = (0.0, 0.0, 0.0, 1.0)
        img.colorspace_settings.name = colorspace_name
        self.created_images.append(img)
        return img

    def _blit_rgba(self, src_image, dst_pixels, atlas_width, x_off, y_off, tint=None):
        """Copy src_image into a TILE_SIZE×TILE_SIZE region of dst_pixels, resampling.

        If *tint* is a (R, G, B) tuple the multiply is performed in **linear**
        space (matching Blender's renderer) and the result is converted back to
        sRGB so the atlas texture stores correct values for glTF export.

        Pipeline when tinting:
          1. Read source pixel (sRGB from file)
          2. Convert to linear
          3. Multiply by tint (already linear – node default_value)
          4. Convert back to sRGB
          5. Write to atlas
        """
        src_pixels = self._image_pixels(src_image)
        src_w = max(1, int(src_image.size[0]))
        src_h = max(1, int(src_image.size[1]))
        if src_w != TILE_SIZE or src_h != TILE_SIZE:
            self.resized_from_sources.add(src_image.name)

        has_tint = tint is not None and tint != (1.0, 1.0, 1.0)
        tr, tg, tb = tint if has_tint else (1.0, 1.0, 1.0)

        for y in range(TILE_SIZE):
            src_y = min(src_h - 1, int((y + 0.5) * src_h / TILE_SIZE))
            dst_row = (y + y_off) * atlas_width
            for x in range(TILE_SIZE):
                src_x = min(src_w - 1, int((x + 0.5) * src_w / TILE_SIZE))
                src_i = (src_y * src_w + src_x) * 4
                dst_i = (dst_row + x + x_off) * 4
                if has_tint:
                    # sRGB → linear, multiply, linear → sRGB
                    r = _srgb_to_linear(src_pixels[src_i + 0]) * tr
                    g = _srgb_to_linear(src_pixels[src_i + 1]) * tg
                    b = _srgb_to_linear(src_pixels[src_i + 2]) * tb
                    dst_pixels[dst_i + 0] = _linear_to_srgb(r)
                    dst_pixels[dst_i + 1] = _linear_to_srgb(g)
                    dst_pixels[dst_i + 2] = _linear_to_srgb(b)
                    dst_pixels[dst_i + 3] = src_pixels[src_i + 3]
                else:
                    dst_pixels[dst_i : dst_i + 4] = src_pixels[src_i : src_i + 4]

    def _blit_orm(self, rough_source, metal_source, dst_pixels, atlas_width, x_off, y_off):
        """Build ORM tile: R=AO(1.0), G=Roughness, B=Metallic."""
        rough_pixels = None
        metal_pixels = None
        rough_w = rough_h = 1
        metal_w = metal_h = 1

        if rough_source.mode == "IMAGE" and rough_source.image:
            rough_pixels = self._image_pixels(rough_source.image)
            rough_w = max(1, int(rough_source.image.size[0]))
            rough_h = max(1, int(rough_source.image.size[1]))
            if rough_w != TILE_SIZE or rough_h != TILE_SIZE:
                self.resized_from_sources.add(rough_source.image.name)

        if metal_source.mode == "IMAGE" and metal_source.image:
            metal_pixels = self._image_pixels(metal_source.image)
            metal_w = max(1, int(metal_source.image.size[0]))
            metal_h = max(1, int(metal_source.image.size[1]))
            if metal_w != TILE_SIZE or metal_h != TILE_SIZE:
                self.resized_from_sources.add(metal_source.image.name)

        for y in range(TILE_SIZE):
            dst_row = (y + y_off) * atlas_width
            rough_y = min(rough_h - 1, int((y + 0.5) * rough_h / TILE_SIZE)) if rough_pixels else 0
            metal_y = min(metal_h - 1, int((y + 0.5) * metal_h / TILE_SIZE)) if metal_pixels else 0

            for x in range(TILE_SIZE):
                dst_i = (dst_row + x + x_off) * 4

                if rough_pixels:
                    rough_x = min(rough_w - 1, int((x + 0.5) * rough_w / TILE_SIZE))
                    rough_val = rough_pixels[(rough_y * rough_w + rough_x) * 4 + rough_source.channel]
                else:
                    rough_val = rough_source.scalar

                if metal_pixels:
                    metal_x = min(metal_w - 1, int((x + 0.5) * metal_w / TILE_SIZE))
                    metal_val = metal_pixels[(metal_y * metal_w + metal_x) * 4 + metal_source.channel]
                else:
                    metal_val = metal_source.scalar

                dst_pixels[dst_i + 0] = 1.0  # AO = white
                dst_pixels[dst_i + 1] = rough_val  # Roughness
                dst_pixels[dst_i + 2] = metal_val  # Metallic
                dst_pixels[dst_i + 3] = 1.0

    # -------------------------------------------------------------------
    # Apply group — remap UVs + replace materials on temp meshes
    # -------------------------------------------------------------------

    def _apply_group(self, mesh_objects, group, layout, atlas_material):
        """
        For each mesh that uses any of the group's source materials:
        1. Copy source UVs → atlas UVs (scale + offset into tile)
        2. Replace material slots in-place (no append+compact dance)
        3. Finalize UV layers so atlas UV = TEXCOORD_0
        """
        group_mat_names = {item.material.name for item in group}
        tile_by_name = {}
        for idx, item in enumerate(group):
            tile_by_name[item.material.name] = idx

        tile_hits = [0] * len(group)

        atlas_w = float(layout["width"])
        atlas_h = float(layout["height"])
        u_scale = TILE_SIZE / atlas_w
        v_scale = TILE_SIZE / atlas_h

        for obj in mesh_objects:
            mesh = obj.data
            if not mesh or not mesh.materials:
                continue

            # Build map: slot_index → tile_index for slots that use group materials.
            slot_map = {}
            for idx in range(len(mesh.materials)):
                mat = mesh.materials[idx]
                if mat and mat.name in tile_by_name:
                    slot_map[idx] = tile_by_name[mat.name]

            if not slot_map:
                continue

            # Ensure mesh internals are up-to-date before touching UV data.
            mesh.update()

            # Skip meshes with no geometry (no loops = no UV data possible).
            if len(mesh.loops) == 0:
                # Still replace materials even without UVs.
                for slot_idx in slot_map:
                    mesh.materials[slot_idx] = atlas_material
                continue

            # --- UV handling ---
            src_uv = self._get_source_uv_layer(mesh)
            if src_uv is None:
                src_uv = mesh.uv_layers.new(name="UVMap")
                mesh.update()  # sync after creating UV layer

            # Read source UVs.
            src_uv_data = self._read_uv_data(src_uv)

            # If read returned empty but mesh has loops, build a zero-filled buffer.
            expected_count = len(mesh.loops) * 2
            if len(src_uv_data) == 0 and expected_count > 0:
                src_uv_data = [0.0] * expected_count

            # Create or get atlas UV layer.
            atlas_uv = mesh.uv_layers.get("DCL_AtlasUV")
            if atlas_uv is None:
                atlas_uv = mesh.uv_layers.new(name="DCL_AtlasUV")
                mesh.update()  # sync after creating UV layer

            # Start with a copy of source UVs.
            atlas_uv_data = list(src_uv_data)

            # Remap UVs for polygons that belong to group materials.
            for poly in mesh.polygons:
                tile_idx = slot_map.get(poly.material_index)
                if tile_idx is None:
                    continue

                tile_hits[tile_idx] += 1

                x_off, y_off = layout["tiles"][tile_idx]
                u_off = x_off / atlas_w
                v_off = y_off / atlas_h

                for li in poly.loop_indices:
                    bi = li * 2
                    atlas_uv_data[bi + 0] = (atlas_uv_data[bi + 0] * u_scale) + u_off
                    atlas_uv_data[bi + 1] = (atlas_uv_data[bi + 1] * v_scale) + v_off

            # Write remapped UVs.
            self._write_uv_data(atlas_uv, atlas_uv_data)

            # --- Material slot replacement (in-place, no pop/compact) ---
            # Replace each group-material slot directly with the atlas material.
            # Track which slot index becomes the "canonical" atlas slot.
            first_atlas_slot = None
            for slot_idx in sorted(slot_map.keys()):
                mesh.materials[slot_idx] = atlas_material
                if first_atlas_slot is None:
                    first_atlas_slot = slot_idx

            # Merge duplicate atlas slots: remap all atlas polys to first_atlas_slot.
            if first_atlas_slot is not None and len(slot_map) > 1:
                atlas_slots = set(slot_map.keys())
                for poly in mesh.polygons:
                    if poly.material_index in atlas_slots:
                        poly.material_index = first_atlas_slot

            # --- Finalize UV layers for clean glTF export ---
            self._finalize_uv_layers(mesh, atlas_material, atlas_uv)

            # Force mesh data update to sync internal state.
            mesh.update()

        # Note: some tiles may have zero polygon hits if a material exists in a
        # slot but no faces reference it, or if it's only used by a non-mesh object.
        # This is harmless — the atlas tile is still filled, just unused.

    # -------------------------------------------------------------------
    # UV layer helpers (use foreach_get/foreach_set to avoid collection bugs)
    # -------------------------------------------------------------------

    def _get_source_uv_layer(self, mesh):
        uv_layers = mesh.uv_layers
        if not uv_layers:
            return None

        # Prefer active render layer.
        for layer in uv_layers:
            if hasattr(layer, "active_render") and layer.active_render:
                return layer

        if uv_layers.active:
            return uv_layers.active

        return uv_layers[0]

    def _read_uv_data(self, uv_layer):
        """Read UV data as flat [u0, v0, u1, v1, ...] list.

        Uses foreach_get for speed, falls back to per-element access
        if the internal collection is out of sync after mesh duplication.
        """
        n = len(uv_layer.data)
        if n == 0:
            return []
        count = n * 2
        data = [0.0] * count
        try:
            uv_layer.data.foreach_get("uv", data)
        except (RuntimeError, SystemError):
            # foreach_get failed (stale internal size) — read element by element.
            data = []
            for loop_uv in uv_layer.data:
                data.extend(loop_uv.uv[:])
        return data

    def _write_uv_data(self, uv_layer, data):
        """Write UV data from flat list.

        Uses foreach_set for speed, falls back to per-element access
        if the internal collection is out of sync.
        """
        n = len(uv_layer.data)
        if n == 0:
            return
        target_count = n * 2
        if len(data) != target_count:
            if len(data) > target_count:
                payload = data[:target_count]
            else:
                payload = data + [0.0] * (target_count - len(data))
        else:
            payload = data
        try:
            uv_layer.data.foreach_set("uv", payload)
        except (RuntimeError, SystemError):
            # foreach_set failed — write element by element.
            for i, loop_uv in enumerate(uv_layer.data):
                bi = i * 2
                if bi + 1 < len(payload):
                    loop_uv.uv = (payload[bi], payload[bi + 1])

    def _finalize_uv_layers(self, mesh, atlas_material, atlas_uv):
        """
        Ensure the atlas UV layer is exported as TEXCOORD_0.

        For fully-atlased meshes (only the atlas material remains used),
        remove all other UV layers and rename atlas UV to "UVMap".

        For mixed meshes (some original + atlas), copy atlas UVs into
        all layers so that any TEXCOORD the exporter picks will work.
        """
        # Check if this mesh is fully atlased (all polys use atlas material).
        all_atlas = True
        for poly in mesh.polygons:
            idx = poly.material_index
            if idx < 0 or idx >= len(mesh.materials):
                all_atlas = False
                break
            mat = mesh.materials[idx]
            if mat != atlas_material:
                all_atlas = False
                break

        if all_atlas:
            # Remove all UV layers except atlas, then rename it to "UVMap"
            # so the glTF exporter maps it to TEXCOORD_0.
            atlas_data = self._read_uv_data(atlas_uv)

            layers_to_remove = [layer for layer in mesh.uv_layers if layer.name != atlas_uv.name]
            for layer in layers_to_remove:
                mesh.uv_layers.remove(layer)

            # Re-fetch atlas_uv (reference may have changed after removes).
            remaining = mesh.uv_layers.get("DCL_AtlasUV")
            if remaining is None and len(mesh.uv_layers) > 0:
                remaining = mesh.uv_layers[0]
            if remaining:
                remaining.name = "UVMap"
                self._write_uv_data(remaining, atlas_data)
                try:
                    mesh.uv_layers.active = remaining
                except Exception:
                    pass
                if hasattr(remaining, "active_render"):
                    try:
                        remaining.active_render = True
                    except Exception:
                        pass
        else:
            # Mixed mesh: broadcast atlas UVs to all layers as a safety net.
            atlas_data = self._read_uv_data(atlas_uv)
            for layer in mesh.uv_layers:
                if layer.name != atlas_uv.name:
                    self._write_uv_data(layer, atlas_data)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def run_material_atlas_optimization(context, export_objects, resize_mode="AGGRESSIVE", debug_report=True):
    optimizer = MaterialAtlasOptimizer(context, export_objects, resize_mode=resize_mode, debug_report=debug_report)
    return optimizer.run()
