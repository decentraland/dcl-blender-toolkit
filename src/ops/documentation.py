import webbrowser

import bpy


class OBJECT_OT_open_documentation(bpy.types.Operator):
    bl_idname = "object.open_documentation"
    bl_label = "Open Documentation"
    bl_description = "Open Decentraland documentation in your web browser"
    bl_options = {"REGISTER"}

    doc_type: bpy.props.EnumProperty(
        name="Documentation",
        description="Choose which documentation to open",
        items=[
            ("MAIN", "Main Documentation", "Open docs.decentraland.org"),
            ("SDK", "SDK7 Guide", "Open SDK7 documentation"),
            ("SCENES", "Scene Development", "Open scene development guide"),
            ("WEARABLES", "Wearables", "Open wearables documentation"),
            ("ASSETS", "3D Models", "Open 3D modeling guide"),
            ("WEBSITE", "Decentraland Website", "Open decentraland.org"),
        ],
        default="MAIN",
    )

    def execute(self, context):
        # Documentation URLs (Updated 2024)
        urls = {
            "MAIN": "https://docs.decentraland.org/",
            "SDK": "https://docs.decentraland.org/creator/development-guide/sdk7/sdk-101/",
            "SCENES": "https://docs.decentraland.org/creator/development-guide/sdk7/dev-workflow/",
            "WEARABLES": "https://docs.decentraland.org/creator/wearables/wearables-overview/",
            "ASSETS": "https://docs.decentraland.org/creator/3d-modeling/3d-models/",
            "WEBSITE": "https://decentraland.org/",
        }

        url = urls.get(self.doc_type, urls["MAIN"])

        try:
            webbrowser.open(url)
            self.report({"INFO"}, f"Opening {self.doc_type} documentation in browser")
        except Exception as e:
            self.report({"ERROR"}, f"Could not open browser: {str(e)}")
            return {"CANCELLED"}

        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "doc_type", expand=True)
        layout.separator()
        layout.label(text="This will open the selected documentation")
        layout.label(text="in your default web browser.")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)


class OBJECT_OT_scene_limits_guide(bpy.types.Operator):
    bl_idname = "object.scene_limits_guide"
    bl_label = "Scene Limits Guide"
    bl_description = "Open the scene limits documentation"
    bl_options = {"REGISTER"}

    def execute(self, context):
        url = "https://docs.decentraland.org/creator/design-experience/scene-limitations/"

        try:
            webbrowser.open(url)
            self.report({"INFO"}, "Opening scene limits documentation")
        except Exception as e:
            self.report({"ERROR"}, f"Could not open browser: {str(e)}")
            return {"CANCELLED"}

        return {"FINISHED"}


class OBJECT_OT_asset_guidelines(bpy.types.Operator):
    bl_idname = "object.asset_guidelines"
    bl_label = "Asset Guidelines"
    bl_description = "Open the asset creation guidelines"
    bl_options = {"REGISTER"}

    def execute(self, context):
        url = "https://docs.decentraland.org/creator/3d-modeling/3d-models/"

        try:
            webbrowser.open(url)
            self.report({"INFO"}, "Opening asset guidelines")
        except Exception as e:
            self.report({"ERROR"}, f"Could not open browser: {str(e)}")
            return {"CANCELLED"}

        return {"FINISHED"}
