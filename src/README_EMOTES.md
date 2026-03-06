# Decentraland Emotes Workflow

This add-on includes a full Decentraland emote pipeline in the `Emotes` section.

## Included Rig Asset

- Bundled rig file: `assets/Avatar_File.blend`
- Source: <https://raw.githubusercontent.com/decentraland/docs/main/creator/images/emotes/Avatar_File.blend>
- Documentation: <https://docs.decentraland.org/creator/wearables-and-emotes/emotes/creating-emotes/>

## Recommended Workflow

1. Open `Decentraland Tools > Emotes`.
2. Run `Import DCL Rig`.
3. Animate in Pose Mode on your target action.
4. Run `Validate Emote`.
5. Run `Export Emote GLB`.

## Emote Settings

- `Start Frame`: First frame of animation clip.
- `End Frame`: Last frame of animation clip (`<= 300`).
- `Sampling Rate`: Export bake step (`2` recommended, `3` if you need smaller output).
- `Strict Validation`: If enabled, warnings block export.

## What Validator Checks

- Frame rate is `30 fps`.
- Clip length is `<= 300` frames.
- There is only one armature action prepared for export.
- Deform channels are keyed at first and last frame.
- Approximate horizontal and vertical displacement stays within 1m guidance.

## Manual QA Checklist

- Import rig in an empty scene and confirm armature appears.
- Confirm scene fps switches to `30` and timeline range to `1..300`.
- Create or select your emote action in the Dope Sheet Action Editor.
- Add a simple animation and set keyframes on first and last frame.
- Run `Validate Emote` and check both pass and warning scenarios.
- Export `.glb` and verify file size and animation count externally before upload.
