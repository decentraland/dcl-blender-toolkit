# dcl-blender-toolkit

Blender extension (Python, `src/` → `decentraland_tools` package) for Decentraland scenes, wearables and emotes. Operators live one per file in `src/ops/`; the panel and property group in `src/__init__.py`. Same zip installs as a 4.2+ extension (`blender_manifest.toml`) and a legacy add-on (`bl_info`).

## Commands

- `make check` — ruff lint + format check + syntax
- `make test` — pytest; Blender-only suites are skipped without `bpy` (`tests/conftest.py`)
- `make build` — the installable zip into `dist/`
- `make sync-rules` / `make check-rules` — vendor the rule book, or report whether npm's copy differs (below)

## Validation rules come from the Builder's rule book

Every wearable and emote limit (triangles, materials, textures, fps, frames, file sizes, root motion) is read from `src/rules/manifest.json` through `src/rules/__init__.py`. That file is a vendored copy of `manifest.json` from the npm package `@dcl-regenesislabs/wearable-validator`, the same rule book the Builder (`wemotes-builder`) and the curation job run. `src/rules/manifest.lock` records the package version, rules version and sha256 of the copy.

- Never type a limit into a validator; read it from `manifest()`. `tests/test_rules.py` fails on known literals and on a hand-edited manifest.
- To update: `make sync-rules`, commit `src/rules/manifest.json` and `manifest.lock` together. CI runs `check-rules` as an informational job: it prints a warning naming the changed blocks when the published manifest differs, and never fails. Run it before touching a validator; if it warns, sync first.
- A rule the toolkit cannot measure the same way as the rule book (it measures the Blender scene, the rule book measures the exported GLB) stays an approximation: say so in the message, keep the number from the manifest.
- Changing a number is done in `decentraland/wearable-validator` (`packages/wearable-validator/src/manifest/manifest.json`), never here.

## Style

ruff (`pyproject.toml`), 120 columns, double quotes. Tests that need no Blender load modules standalone (`tests/_helpers.py`) so plain pytest runs without `bpy`. Comments say why, not what.
