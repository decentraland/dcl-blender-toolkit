import bpy


class OBJECT_OT_batch_rename(bpy.types.Operator):
    bl_idname = "object.batch_rename"
    bl_label = "Batch Rename"
    bl_description = "Rename multiple selected objects using prefix, suffix, or find-and-replace"
    bl_options = {"REGISTER", "UNDO"}

    mode: bpy.props.EnumProperty(
        name="Mode",
        description="Rename mode",
        items=[
            ("PREFIX", "Add Prefix", "Prepend a string to each object name"),
            ("SUFFIX", "Add Suffix", "Append a string to each object name"),
            ("FIND_REPLACE", "Find & Replace", "Replace a substring in object names"),
        ],
        default="SUFFIX",
    )

    prefix: bpy.props.StringProperty(
        name="Prefix",
        description="String to prepend",
        default="",
    )

    suffix: bpy.props.StringProperty(
        name="Suffix",
        description="String to append",
        default="",
    )

    find_str: bpy.props.StringProperty(
        name="Find",
        description="Substring to find",
        default="",
    )

    replace_str: bpy.props.StringProperty(
        name="Replace",
        description="Substring to replace with",
        default="",
    )

    def execute(self, context):
        objects = context.selected_objects
        if not objects:
            self.report({"WARNING"}, "No objects selected")
            return {"CANCELLED"}

        renamed = 0

        for obj in objects:
            old_name = obj.name

            if self.mode == "PREFIX":
                if not self.prefix:
                    continue
                obj.name = self.prefix + old_name
                renamed += 1

            elif self.mode == "SUFFIX":
                if not self.suffix:
                    continue
                obj.name = old_name + self.suffix
                renamed += 1

            elif self.mode == "FIND_REPLACE":
                if not self.find_str:
                    continue
                if self.find_str in old_name:
                    obj.name = old_name.replace(self.find_str, self.replace_str)
                    renamed += 1

        if renamed > 0:
            self.report({"INFO"}, f"Renamed {renamed} object(s)")
        else:
            self.report({"INFO"}, "No objects were renamed")
        return {"FINISHED"}

    def draw(self, context):
        layout = self.layout

        layout.prop(self, "mode", expand=True)
        layout.separator()

        if self.mode == "PREFIX":
            layout.prop(self, "prefix")
        elif self.mode == "SUFFIX":
            layout.prop(self, "suffix")
        elif self.mode == "FIND_REPLACE":
            layout.prop(self, "find_str")
            layout.prop(self, "replace_str")

        layout.separator()
        count = len(context.selected_objects)
        layout.label(text=f"{count} object(s) selected", icon="INFO")

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self, width=350)
