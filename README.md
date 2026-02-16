# Decentraland Blender Tools

A comprehensive Blender add-on for Decentraland scene and wearable creation. Provides tools for scene setup, material management, texture optimization, avatar development, emote creation, collider workflow, and more.

Compatible with **Blender 2.80 through 5.0+**.

---

## Installation

1. Download the `DCLBlender_toolkit.zip` file from the [Releases](https://github.com/decentraland/DCLTools/releases) page
2. In Blender: **Edit > Preferences > Add-ons > Install...**
3. Select the `DCLBlender_toolkit.zip` file
4. Enable **"Decentraland Tools"** in the add-ons list
5. Open the panel in **3D Viewport > Sidebar (N) > Decentraland Tools**

---

## Panel Section Order

1. Scene Creation
2. Avatars
3. Emotes
4. Materials & Textures
5. LOD Generator
6. Viewer
7. CleanUp
8. Collider Management
9. Export
10. Documentation
11. Experimental

---

## Features

### Scene Creation

| Tool | Description |
|------|-------------|
| **Create Parcels** | Generate a parcel grid with customizable X/Y dimensions (16m per parcel, Decentraland standard) |
| **Scene Limitations Calculator** | Analyze current scene usage against Decentraland limits (triangles, entities, bodies, materials, textures, height) |
| **Scene Validator (Pre-flight)** | One-click pre-flight check: validates triangle count, entities, bodies, materials, textures, height, non-applied transforms, missing materials, and non-power-of-two textures against DCL limits with green/yellow/red status |

### Avatars

| Tool | Description |
|------|-------------|
| **Avatar Shapes** | Import editable Decentraland avatar base meshes (Shape A, Shape B, or both) for wearable development |
| **Wearable Limits** | Check selected objects against wearable triangle/material/texture limits per category (upper body, hat, helmet, etc.) |

### Emotes

| Tool | Description |
|------|-------------|
| **Import DCL Rig** | Append the official Decentraland avatar rig (Avatar_File.blend) into the scene. Sets scene to 30 fps and 1-300 frame range. Defaults to Avatar_ShapeA visible, Avatar_ShapeB hidden |
| **Add Prop** | Import the Prop collection (Armature_Prop) for emotes that use hand-held objects |
| **Limit Area Reference** | Import the Animation_Area_Reference collection (ground plane, boundary circles, animation area box) |
| **Validate Emote** | Pre-flight check: validates fps (30), frame length (<= 300), active action count, deform-bone boundary keyframes, and root displacement guidance (<= 1m) |
| **Emote Settings** | Configurable start/end frame, sampling rate (2 recommended), and strict validation toggle |

### Materials & Textures

| Tool | Description |
|------|-------------|
| **Replace Materials** | Replace one or more materials with another across the scene. Supports multi-source selection with search, and scope to selected objects |
| **Clean Unused Materials** | Remove unused material slots from objects (slots not referenced by any face) and/or globally orphan materials with zero users |
| **Resize Textures** | Batch resize textures to target resolutions (64 - 1024px) with optional backup |
| **Validate Textures** | Check all textures for glTF/DCL compatibility: non-power-of-two dimensions, oversized textures, non-square textures, and unsupported formats |
| **Enable Backface Culling** | Enable backface culling on all materials in the scene |

### LOD Generator

| Tool | Description |
|------|-------------|
| **Generate LODs** | Create Level of Detail copies of selected meshes using decimation. Configurable LOD levels (1-4) with per-level ratio sliders. Defaults: LOD 1 at 50%, LOD 2 at 15%, LOD 3 at 5%. Optionally places LODs in a dedicated collection |

### Viewer

| Tool | Description |
|------|-------------|
| **Toggle Display Mode** | Switch viewport display for objects between Bounds, Wire, Textured, and Solid |

### CleanUp

| Tool | Description |
|------|-------------|
| **Remove Empty Objects** | Remove empty objects, meshes with no geometry, or meshes without materials |
| **Apply Transforms** | Apply location, rotation, and scale transforms to selected or all objects |
| **Rename Mesh Data** | Sync mesh data block names with their parent object names |
| **Rename Textures** | Automatically rename textures based on their material node usage (baseColor, hrm, normal, emissive) |
| **Batch Rename Objects** | Rename multiple selected objects with three modes: Add Prefix, Add Suffix, or Find & Replace |

### Collider Management

| Tool | Description |
|------|-------------|
| **Add _collider Suffix** | Rename selected objects to append the `_collider` suffix |
| **Remove UVs from Colliders** | Strip UV mapping data from all objects containing `_collider` in their name |
| **Strip Materials from Colliders** | Remove all material slots from collider objects |
| **Simplify Colliders** | Apply decimation to reduce polygon count on collider meshes with adjustable ratio |

### Export

| Tool | Description |
|------|-------------|
| **Export glTF (.glb)** | One-click glTF/GLB export with DCL-optimized defaults: binary format, apply modifiers, no cameras/lights. Includes a browsable **Export Path** picker to choose any output folder. Automatically realizes **collection instances** into real geometry so instanced objects (including nested instances) are properly included in the GLB without manual "Make Instances Real". Reports file size after export |
| **Export Emote GLB** | Export emote animation to GLB with DCL settings: deformation bones only, configurable sampling rate, validation preflight. Warns if file exceeds 1 MB |
| **Atlas Optimizer** | Non-destructive material/texture atlas pass that runs at export time. Merges 2 or 4 compatible PBR materials into a single atlas material (**BaseColor + ORM + Normal + Emissive**) to reduce draw calls. Two modes: **Conservative** (only merges 512px textures, leaves 1024px intact for quality) and **Aggressive** (downscales 1024→512 for maximum optimization). Handles tinted materials (MixRGB/Multiply nodes), emissive textures with per-tile strength normalization (baked to Emission Strength 1.0), tiled UV detection, alpha materials, and proper sRGB↔Linear color space conversion. Operates on temporary duplicates — original scene is never modified |

### Documentation

| Tool | Description |
|------|-------------|
| **Documentation** | Links to Decentraland creator documentation |
| **Limits Guide** | Links to the official scene limitations reference |
| **Asset Guide** | Links to 3D asset optimization guidelines |

### Experimental

| Tool | Description |
|------|-------------|
| **Export Lights** | Export lights from a collection to a JSON file formatted for the Decentraland SDK (position, color, intensity, range) |
| **Particle to Armature** | Convert particle systems into armature-driven animations for Decentraland compatibility |

---

## UI Overview

The panel is organized into collapsible sections in the **3D Viewport Sidebar (N key)**. Each section can be expanded or collapsed to keep the workspace clean. The Experimental section is collapsed by default.

Every tool supports:
- **Undo** (Ctrl+Z) for all operations
- **Scope selection** - apply to selected objects or the entire scene
- **Dialog options** - configurable parameters before execution
- **Status feedback** - results reported in the Blender info bar

---

## Version

Current version: **1.2.0**
Compatible with Blender 2.80 - 5.0+
