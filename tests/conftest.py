# Skip Blender-only tests when running under plain pytest (no bpy module).
collect_ignore = ["test_composite_blender.py"]
