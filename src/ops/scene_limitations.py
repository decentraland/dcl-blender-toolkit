import bpy

from .scene_utils import calculate_limits, count_current_usage, status_icon, usage_percentage


class OBJECT_OT_scene_limitations(bpy.types.Operator):
    bl_idname = "object.scene_limitations"
    bl_label = "Scene Limitations Calculator"
    bl_description = "Calculate Decentraland scene limitations based on parcel count"
    bl_options = {"REGISTER", "UNDO"}

    parcel_count: bpy.props.IntProperty(
        name="Parcel Count",
        description="Number of parcels in your scene (e.g., 2x2 = 4 parcels)",
        default=4,
        min=1,
        max=100,
    )

    def execute(self, context):
        limitations = calculate_limits(self.parcel_count)
        current_usage = count_current_usage()

        # Check for warnings
        warnings = []
        for key in ("triangles", "entities", "bodies", "materials", "textures", "height"):
            if current_usage[key] > limitations[key]:
                diff = current_usage[key] - limitations[key]
                unit = "m" if key == "height" else ""
                warnings.append(f"{key.upper()}: Exceeding limit by {diff:,}{unit}")

        if warnings:
            self.report(
                {"WARNING"}, f"Scene analysis complete - {len(warnings)} warnings found. Check console for details."
            )
        else:
            self.report({"INFO"}, "Scene analysis complete - All limits within bounds.")

        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout

        col = layout.column(align=True)
        col.label(text="Enter your scene size:")
        col.prop(self, "parcel_count")

        if self.parcel_count > 0:
            limitations = calculate_limits(self.parcel_count)
            current_usage = count_current_usage()

            layout.separator()
            layout.label(text="Current Usage vs Limits:", icon="INFO")

            box = layout.box()
            col = box.column(align=True)

            for key, label in [
                ("triangles", "Triangles"),
                ("entities", "Entities"),
                ("bodies", "Bodies"),
                ("materials", "Materials"),
                ("textures", "Textures"),
                ("height", "Height (m)"),
            ]:
                pct = usage_percentage(current_usage[key], limitations[key])
                icon = status_icon(pct)
                col.label(
                    text=f"{label}: {current_usage[key]:,} / {limitations[key]:,} ({pct}%)",
                    icon=icon,
                )

            layout.separator()
            layout.label(text="File Limits:", icon="FILE")
            box2 = layout.box()
            col2 = box2.column(align=True)
            col2.label(text=f"File Size: {limitations['total_file_size_mb']} MB")
            col2.label(text=f"Files: {limitations['file_count']:,}")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)
