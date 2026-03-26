# Decentraland Tools

[![CI Status](https://github.com/decentraland/dcl-blender-toolkit/workflows/CI/badge.svg)](https://github.com/decentraland/dcl-blender-toolkit/actions/workflows/ci.yml) [![License: GPL-3.0 / Apache-2.0](https://img.shields.io/badge/License-GPL--3.0%20%2F%20Apache--2.0-blue.svg)](LICENSE) [![Blender](https://img.shields.io/badge/Blender-2.80--5.0+-orange.svg)](https://www.blender.org/) [![Made for Decentraland](https://img.shields.io/badge/Made%20for-Decentraland-ff0099.svg)](https://decentraland.org/)

A comprehensive Blender extension for Decentraland scene, wearable, and emote creation. Provides tools for scene setup, material management, texture optimization, avatar development, emote pipeline, collider workflow, LOD generation, and glTF export with atlas optimization.

## Table of Contents

- [Installation](#installation)
- [Features](#features)
  - [Scene Creation](#scene-creation)
  - [Avatars](#avatars)
  - [Emotes](#emotes)
  - [Materials & Textures](#materials--textures)
  - [Generate Thumbnail](#generate-thumbnail)
  - [LOD Generator](#lod-generator)
  - [Viewer](#viewer)
  - [CleanUp](#cleanup)
  - [Collider Management](#collider-management)
  - [Export](#export)
  - [Documentation](#documentation)
  - [Experimental](#experimental)
- [Development](#development)
  - [Prerequisites](#prerequisites)
  - [Quick Start](#quick-start)
  - [Makefile Commands](#makefile-commands)
  - [Project Structure](#project-structure)
- [CI/CD](#cicd)
  - [Pull Request Workflow](#pull-request-workflow)
  - [Release Workflow](#release-workflow)
  - [Release Process](#release-process)
  - [Blender Extensions Platform Publishing](#blender-extensions-platform-publishing)
- [Architecture](#architecture)
  - [Operator Pattern](#operator-pattern)
  - [Dual Install Support](#dual-install-support)
  - [Key Modules](#key-modules)
- [Troubleshooting](#troubleshooting)
- [Contributing](#contributing)
- [License](#license)

## Installation

### Blender 4.2+ (Extensions Platform)

1. Download `decentraland_tools-X.Y.Z.zip` from the [Releases](https://github.com/decentraland/dcl-blender-toolkit/releases) page
2. In Blender: **Edit > Preferences > Get Extensions > Install from Disk...**
3. Select the downloaded zip file
4. The extension will appear in **3D Viewport > Sidebar (N) > Decentraland Tools**

### Blender 2.80 - 4.1 (Legacy Add-on)

1. Download `decentraland_tools-X.Y.Z.zip` from the [Releases](https://github.com/decentraland/dcl-blender-toolkit/releases) page
2. In Blender: **Edit > Preferences > Add-ons > Install...**
3. Select the downloaded zip file
4. Enable **"Decentraland Tools"** in the add-ons list
5. Open the panel in **3D Viewport > Sidebar (N) > Decentraland Tools**

> The same zip file works for both install methods. Blender 4.2+ reads `blender_manifest.toml`, while older versions read `bl_info` from `__init__.py`.

## Features

The panel is organized into collapsible sections in the **3D Viewport Sidebar (N key)**. Every tool supports undo (Ctrl+Z), scope selection, configurable dialog options, and status feedback in the Blender info bar.

### Scene Creation

| Tool | Description |
|------|-------------|
| **Create Parcels** | Generate a parcel grid with customizable X/Y dimensions (16m per parcel) |
| **Scene Limitations Calculator** | Analyze current scene usage against Decentraland limits (triangles, entities, bodies, materials, textures, height) |
| **Scene Validator (Pre-flight)** | One-click pre-flight check with green/yellow/red status for all DCL limits, transforms, materials, and textures |

### Avatars

| Tool | Description |
|------|-------------|
| **Avatar Shapes** | Import editable Decentraland avatar base meshes (Shape A, Shape B, or both) for wearable development |
| **Wearable Limits** | Check selected objects against wearable triangle/material/texture limits per category |

### Emotes

| Tool | Description |
|------|-------------|
| **Import DCL Rig** | Append the official Decentraland avatar rig into the scene (30 fps, 1-300 frame range) |
| **Add Prop** | Import the Prop collection for emotes with hand-held objects |
| **Limit Area Reference** | Import the animation area reference (ground plane, boundary circles, area box) |
| **Create Emote Action** | Create a new action on the avatar armature for emote animation |
| **Set Boundary Keyframes** | Automatically set deform-bone boundary keyframes at start/end frames |
| **Validate Emote** | Pre-flight check: fps, frame length, action count, boundary keyframes, root displacement |
| **Export Emote GLB** | Export emote animation to GLB with DCL settings and validation preflight |

### Materials & Textures

| Tool | Description |
|------|-------------|
| **Replace Materials** | Replace one or more materials with another across the scene |
| **Resize Textures** | Batch resize textures to target resolutions (64-1024px) with optional backup |
| **Validate Textures** | Check all textures for glTF/DCL compatibility (power-of-two, size, format) |
| **Enable Backface Culling** | Enable backface culling on all materials in the scene |
| **Remove Specular** | Remove specular tint textures and set specular values to 0 on Principled BSDF materials to reduce file size |
| **Compress Images** | Compress textures to JPEG or PNG with configurable quality. Auto mode uses JPEG for opaque images and PNG for transparent, with an option to force JPEG when no alpha is present |

### Generate Thumbnail

| Tool | Description |
|------|-------------|
| **Add Camera** | Add a camera aimed at the active object for thumbnail shots |
| **Camera Controls** | Adjust zoom, side, height, and angle for the thumbnail camera |
| **Add Lighting** | Add thumbnail lighting around the active object with simple controls |
| **Transparent Background** | Render the thumbnail with or without a transparent background |
| **Output Size** | Choose a preset thumbnail size or set a custom width and height |
| **Render Image** | Render and save a PNG thumbnail using Eevee or Cycles |

### LOD Generator

| Tool | Description |
|------|-------------|
| **Generate LODs** | Create Level of Detail copies using decimation (1-4 levels with configurable ratios) |

### CleanUp

| Tool | Description |
|------|-------------|
| **Remove Empty Objects** | Remove empty objects, meshes with no geometry, or meshes without materials |
| **Rename Textures** | Auto-rename textures based on PBR node usage (baseColor, hrm, normal, emissive) |

### Collider Management

| Tool | Description |
|------|-------------|
| **Add _collider Suffix** | Rename selected objects to append `_collider` |
| **Remove UVs from Colliders** | Strip UV data from collider objects |
| **Strip Materials from Colliders** | Remove all material slots from collider objects |
| **Simplify Colliders** | Apply decimation to reduce polygon count on collider meshes |
| **Clean Up Colliders** | Remove doubles and dissolve degenerate geometry on collider meshes |

### Export

| Tool | Description |
|------|-------------|
| **Export glTF (.glb)** | One-click GLB export with DCL-optimized defaults. Automatically realizes collection instances. Includes browsable export path picker |
| **Atlas Optimizer** | Non-destructive PBR atlas pass at export time. Merges 2-4 compatible materials into a single atlas (BaseColor + ORM + Normal + Emissive) to reduce draw calls. Conservative and Aggressive modes |

### Documentation

| Tool | Description |
|------|-------------|
| **Documentation** | Links to Decentraland creator documentation |
| **Limits Guide** | Links to the official scene limitations reference |
| **Asset Guide** | Links to 3D asset optimization guidelines |

### Experimental

| Tool | Description |
|------|-------------|
| **Export Lights** | Export lights to JSON formatted for the Decentraland SDK |
| **Particle to Armature** | Convert particle systems into armature-driven animations |

## Development

### Prerequisites

Before starting, ensure you have the following installed:

- **Python** 3.10 or higher ([Download](https://www.python.org/downloads/))
- **make** (included on macOS/Linux; on Windows use [WSL](https://learn.microsoft.com/en-us/windows/wsl/) or [Git Bash](https://gitforwindows.org/))
- **Git** ([Download](https://git-scm.com/downloads))

### Quick Start

1. **Clone the repository:**

   ```bash
   git clone https://github.com/decentraland/dcl-blender-toolkit.git
   cd dcl-blender-toolkit
   ```

2. **Install dev dependencies:**

   ```bash
   make setup
   ```

   This installs `ruff` (linter/formatter) and `pytest` (test framework).

3. **Verify everything works:**

   ```bash
   make check
   make test
   ```

4. **Build the distributable zip:**

   ```bash
   make build
   ```

   Output: `dist/decentraland_tools-X.Y.Z.zip`

### Makefile Commands

| Command | Description |
|---------|-------------|
| `make setup` | Install dev dependencies (ruff, pytest) |
| `make lint` | Run linter on all Python files |
| `make format` | Auto-format all Python files |
| `make check` | Lint + format check + syntax validation (mirrors CI) |
| `make test` | Run test suite |
| `make build` | Build distributable zip from source |
| `make build VERSION=X.Y.Z` | Build with explicit version (used by CI) |
| `make clean` | Remove build artifacts and caches |

### Project Structure

```
dcl-blender-toolkit/
├── src/                          # All Python source code
│   ├── __init__.py               # Plugin entry point, panel UI, registration
│   ├── icon_loader.py            # Custom PNG icon loading via bpy.utils.previews
│   ├── dcl_rig_metadata.py       # Paths/URLs for bundled avatar files
│   ├── icons/                    # Tabler Icons PNGs (MIT license)
│   └── ops/                      # All operator modules (one class per file)
│       ├── scene_utils.py        # Shared: DCL limit calculations, usage counting
│       ├── emote_utils.py        # Shared: armature/action helpers
│       ├── create_parcels.py     # Generate parcel grid
│       ├── scene_limitations.py  # Scene limits calculator
│       ├── validate_scene.py     # Scene pre-flight validator
│       ├── link_avatar_wearables.py  # Import avatar shapes
│       ├── avatar_limitations.py     # Wearable limits checker
│       ├── emote_actions.py      # Create emote action, set boundary keys
│       ├── import_dcl_rig.py     # Import avatar rig/prop/limit area
│       ├── validate_emote.py     # Emote validation checks
│       ├── export_emote_glb.py   # Emote GLB export
│       ├── replace_materials.py  # Material replacement with UI list
│       ├── clean_unused_materials.py  # Remove unused/orphan materials
│       ├── resize_textures.py    # Batch texture resize
│       ├── validate_textures.py  # Texture compatibility checks
│       ├── quick_export_gltf.py  # GLB export with collection instances
│       ├── export_material_atlas.py  # PBR atlas optimizer (1400 lines)
│       └── ...                   # Additional operators
├── assets/                       # Bundled .blend files
│   ├── AvatarShape_A.blend       # Male avatar base mesh
│   ├── AvatarShape_B.blend       # Female avatar base mesh
│   └── Avatar_File.blend         # Official DCL avatar rig
├── scripts/
│   ├── build.py                  # Build distributable zip
│   └── check_syntax.py           # Syntax validation for CI
├── tests/
│   └── test_build.py             # Structure, version, build, and syntax tests
├── .github/workflows/
│   ├── ci.yml                    # PR workflow: lint, test, build
│   └── release.yml               # Release workflow: build + publish
├── blender_manifest.toml         # Blender Extensions Platform manifest (4.2+)
├── pyproject.toml                # Ruff linting/formatting config
├── Makefile                      # Dev task runner
└── LICENSE                       # Apache 2.0
```

## CI/CD

The project uses GitHub Actions for continuous integration and release management.

### Pull Request Workflow (`ci.yml`)

Runs on every pull request and push to `main`:

1. **Check** - Lint (ruff), format verification, syntax validation
2. **Test** - Full test suite via pytest
3. **Build** - Assemble distributable zip and upload as artifact

The `check` and `test` jobs run in parallel. `build` only runs after both pass.

### Release Workflow (`release.yml`)

Triggered when a GitHub Release is published:

1. **Setup** - Install dev dependencies
2. **Check** - Lint and syntax validation
3. **Test** - Full test suite
4. **Extract version** - Parse version from release tag (e.g., `v1.3.0` -> `1.3.0`)
5. **Build** - Build zip with the release version (patches `bl_info` and `blender_manifest.toml`)
6. **Verify** - Confirm the build artifact exists
7. **Upload to GitHub** - Attach the zip to the GitHub Release
8. **Publish to Blender Extensions** - Upload to the [Blender Extensions Platform](https://extensions.blender.org/) (if enabled)

### Release Process

1. Create a new **Release** on GitHub with a tag like `v1.3.0`
2. The release workflow runs automatically
3. The built `decentraland_tools-1.3.0.zip` is attached to the release
4. If Blender Extensions publishing is enabled, the zip is also uploaded to [extensions.blender.org](https://extensions.blender.org/)
5. Users can download from GitHub Releases or install directly from within Blender

> Version is driven entirely by the git tag. The build script patches the version into both `bl_info` (for legacy Blender) and `blender_manifest.toml` (for Extensions Platform) at build time.

### Blender Extensions Platform Publishing

Automated publishing to the Blender Extensions Platform is gated behind two settings:

1. **Repository variable** `BLENDER_EXTENSIONS_ENABLED` must be set to `true`
   - Go to **Settings > Secrets and variables > Actions > Variables**
   - Create a variable named `BLENDER_EXTENSIONS_ENABLED` with value `true`

2. **Repository secret** `BLENDER_EXTENSIONS_TOKEN` must contain a valid API token
   - Generate a token at [extensions.blender.org/settings/tokens/](https://extensions.blender.org/settings/tokens/)
   - Go to **Settings > Secrets and variables > Actions > Secrets**
   - Create a secret named `BLENDER_EXTENSIONS_TOKEN` with the token value

> The first extension submission must be done manually through the Blender Extensions Platform web UI. Once approved, enable automated publishing by adding the variable and secret above.

## Architecture

### Operator Pattern

All tools are implemented as `bpy.types.Operator` subclasses following Blender conventions:

- `bl_options = {'REGISTER', 'UNDO'}` for undo support
- `invoke_props_dialog` for configuration dialogs before execution
- Selection and active object state is saved and restored
- Results reported via `self.report()` to Blender's info bar

### Dual Install Support

A single zip supports both install methods:

- **Blender 4.2+** reads `blender_manifest.toml` at the package root
- **Blender 2.80-4.1** reads `bl_info` dict in `__init__.py`

Both are kept in sync by the build script's version patching.

### Key Modules

| Module | Purpose |
|--------|---------|
| `__init__.py` | Entry point: `bl_info`, panel UI (`VIEW3D_PT_dcl_tools`), operator registration |
| `scene_utils.py` | Shared DCL limit calculations and scene usage counting |
| `emote_utils.py` | Shared armature/action helpers (supports Blender 5 slotted actions) |
| `export_material_atlas.py` | Non-destructive PBR atlas optimizer with sRGB/linear conversion |
| `quick_export_gltf.py` | GLB export with collection instance realization and atlas integration |
| `icon_loader.py` | Custom icon loading with lazy `bpy.utils.previews` initialization |
| `dcl_rig_metadata.py` | Path resolution for bundled `.blend` assets |

## Troubleshooting

### Extension Not Appearing After Install

- **Blender 4.2+**: Check **Edit > Preferences > Get Extensions** and search for "Decentraland"
- **Blender 2.80-4.1**: Check **Edit > Preferences > Add-ons**, search for "Decentraland", and ensure it's enabled
- Restart Blender after installing

### Panel Not Visible

- Open the **3D Viewport** (not another editor like the UV Editor)
- Press **N** to open the sidebar
- Look for the **Decentraland Tools** tab

### Build Failures

```bash
make clean     # Remove cached artifacts
make setup     # Reinstall dev dependencies
make check     # Verify lint and syntax
make test      # Run tests
make build     # Rebuild
```

### Python Version Issues

The project requires Python 3.10+. Check your version:

```bash
python --version
```

Use [pyenv](https://github.com/pyenv/pyenv) to manage Python versions if needed.

### Getting Help

1. **Search existing issues**: [GitHub Issues](https://github.com/decentraland/dcl-blender-toolkit/issues)
2. **Ask the community**: [Decentraland Discord](https://dcl.gg/discord)
3. **Create a new issue**: [Report a bug](https://github.com/decentraland/dcl-blender-toolkit/issues/new)

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/my-feature`)
3. Set up your dev environment (`make setup`)
4. Make your changes
5. Verify locally (`make check && make test`)
6. Submit a pull request

The CI pipeline will automatically lint, test, and build your changes.

## License

Dual-licensed under [GPL-3.0-or-later](LICENSE-GPL) and [Apache-2.0](LICENSE-APACHE) at your option. The GPL-3.0 license applies when distributed through the Blender Extensions Platform. See [LICENSE](LICENSE) for details.

---

Made with care by the [Decentraland](https://decentraland.org/) community
