"""Live preview of the current wearable or emote in the Builder.

Previewing means three things: export the selection to a GLB, serve it from a
short-lived local bridge, and open the Builder's ``/live-preview`` page, which
polls the bridge and hot-swaps the model on a live avatar:

    GET /<token>/state           -> {"version", "type", "name", "category"}
    GET /<token>/state?since=N   -> same, answered once version != N (or after 25 seconds)
    GET /<token>/model.glb       -> the latest export

The token is generated per session, so only the page opened with the bridge
URL can read the export; other sites reaching 127.0.0.1 get a 404.

Overrides, body shape and emote playback are all chosen on the Builder page;
the add-on only exports and serves. Refresh is always live: saving the .blend
re-exports immediately, scene edits re-export after a quiet period, and each
re-export bumps ``version`` so the page picks it up on its next poll. The
user's mode is never touched: the export runs with no active object (the glTF
exporter would otherwise force Object Mode) and edit-mode meshes are exported
from a throwaway copy. The
bridge binds to 127.0.0.1 (OS-assigned port unless one is set in the add-on preferences),
its URL is passed to the page as the ``bridge`` query param, and it is torn
down on Stop Live Preview, when another file is opened or when the add-on is
unregistered.
"""

import os
import time
import webbrowser

import bpy
from bpy.app.handlers import persistent

from .bridge_utils import (
    DEFAULT_PREVIEWER_URL,
    MODEL_FILE,
    REFERENCE_AVATAR_COLLECTIONS,
    WEARABLE_CATEGORIES,
    BridgeServer,
    RefreshScheduler,
    bound_armatures,
    build_state_payload,
    emote_export_error,
    emote_validation_error,
    is_emote_validation_failure,
    live_preview_url,
    normalize_previewer_url,
    readable_category,
    report_lines,
    wearable_export_error,
)
from .validate_emote import run_emote_validation

# Re-export only once the scene has been quiet for this long, so dragging a
# vertex or scrubbing a slider does not export on every mouse move.
DEBOUNCE_SECONDS = 0.5
# The refresh itself dirties the depsgraph (the emote exporter toggles
# visibility and scrubs frames). _refresh flushes that while the handler is
# muted; anything still landing this close after a refresh goes through
# RefreshScheduler so an edit is never lost and a side effect cannot loop.
_POST_REFRESH_GRACE = 0.75
_TIMER_INTERVAL = 0.2
# A modal operator (transform drag, stroke) holds re-exports back, but some
# add-ons keep one running permanently, so the hold is capped.
_MODAL_HOLD_SECONDS = 5.0


_server = BridgeServer()


# ---------------------------------------------------------------------------
# Live session: re-export on save or scene changes and bump the version
# ---------------------------------------------------------------------------


class _LiveSession:
    def __init__(self):
        self.export = None
        self.is_emote = False
        self.name = ""
        self.category = ""
        self.dirty_at = None
        self.exporting = False
        self.scheduler = RefreshScheduler(_POST_REFRESH_GRACE)

    @property
    def active(self):
        return self.export is not None


_session = _LiveSession()
# Monotonic across session restarts, so a page that is already polling always
# sees a change when a new preview starts.
_version = 0


def _publish_state():
    _server.publish(
        build_state_payload(
            version=_version,
            is_emote=_session.is_emote,
            name=_session.name,
            category=_session.category,
        )
    )


def start_live_session(export_callback, *, is_emote, name, category=""):
    """Begin streaming to the Builder.

    ``export_callback`` re-exports the GLB in place and returns an error string,
    or None on success. It runs on the main thread, from a save handler or a
    timer.
    """
    global _version
    stop_live_session()
    _session.export = export_callback
    _session.is_emote = is_emote
    _session.name = name
    _session.category = category
    # The operator's initial export just ran: treat it as a refresh so its side
    # effects get the same grace window, and nothing leaks from a previous session.
    _session.exporting = False
    _session.scheduler = RefreshScheduler(_POST_REFRESH_GRACE)
    _session.scheduler.refreshed(time.monotonic())
    _version += 1
    _publish_state()
    _install_handlers()


def stop_live_session():
    _session.export = None
    _session.dirty_at = None
    _remove_handlers()


def stop_live_preview():
    """Tear the bridge down."""
    stop_live_session()
    _server.stop()


def register_live_preview():
    # Installed once for the add-on's lifetime: a handler that removes itself from
    # load_pre while Blender iterates that list makes the next add-on's handler skip.
    if _on_load_pre not in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.append(_on_load_pre)


def unregister_live_preview():
    stop_live_preview()
    if _on_load_pre in bpy.app.handlers.load_pre:
        bpy.app.handlers.load_pre.remove(_on_load_pre)


def _refresh():
    global _version
    _session.exporting = True
    try:
        error = _session.export()
    except Exception as exc:
        error = str(exc)
    finally:
        # Evaluate the depsgraph now, while the handler is still muted, so the
        # exporter's restore work (visibility, frame) is not taken for an edit.
        view_layer = getattr(bpy.context, "view_layer", None)
        if view_layer is not None:
            try:
                view_layer.update()
            except Exception:
                pass
        _session.exporting = False
        _session.scheduler.refreshed(time.monotonic())

    if error:
        print("DCL live preview: refresh skipped — " + error.replace("\n", " | "))
        return
    _version += 1
    _publish_state()


def _is_relevant(update):
    """Ignore updates that cannot change the exported GLB, like selection."""
    data = update.id
    if isinstance(data, bpy.types.Object):
        return update.is_updated_geometry or update.is_updated_transform
    return isinstance(
        data,
        (
            bpy.types.Mesh,
            bpy.types.Curve,
            bpy.types.Armature,
            bpy.types.Material,
            bpy.types.Image,
            bpy.types.Action,
            bpy.types.NodeTree,
        ),
    )


@persistent
def _on_save_post(*_args):
    if _session.active:
        _session.dirty_at = None
        _refresh()


@persistent
def _on_load_pre(*_args):
    # The session belongs to the file it was started from; keeping the bridge up
    # would serve the previous file's model to the open page.
    if _server.running:
        stop_live_preview()


@persistent
def _on_depsgraph_update(scene, depsgraph):
    if not _session.active or _session.exporting:
        return
    screen = getattr(bpy.context, "screen", None)
    if screen and screen.is_animation_playing:
        return
    if not any(_is_relevant(update) for update in depsgraph.updates):
        return
    dirty_at = _session.scheduler.change(time.monotonic())
    if dirty_at is not None:
        _session.dirty_at = dirty_at


def _modal_operator_running():
    """True during a transform drag, knife cut or sculpt stroke (Blender 4.2+ lists them)."""
    return any(
        getattr(window, "modal_operators", ()) for manager in bpy.data.window_managers for window in manager.windows
    )


def _timer():
    if not _session.active:
        return None
    if _session.dirty_at is None:
        return _TIMER_INTERVAL
    waited = time.monotonic() - _session.dirty_at
    if waited >= DEBOUNCE_SECONDS:
        # Exporting under a running modal operator would fight it: stay dirty and retry,
        # unless the hold has gone on long enough that the operator is a permanent one.
        if waited < _MODAL_HOLD_SECONDS and _modal_operator_running():
            return _TIMER_INTERVAL
        _session.dirty_at = None
        _refresh()
    return _TIMER_INTERVAL


def _install_handlers():
    handlers = bpy.app.handlers
    if _on_save_post not in handlers.save_post:
        handlers.save_post.append(_on_save_post)
    if _on_depsgraph_update not in handlers.depsgraph_update_post:
        handlers.depsgraph_update_post.append(_on_depsgraph_update)
    if not bpy.app.timers.is_registered(_timer):
        bpy.app.timers.register(_timer, first_interval=_TIMER_INTERVAL)


def _remove_handlers():
    handlers = bpy.app.handlers
    for collection, fn in (
        (handlers.save_post, _on_save_post),
        (handlers.depsgraph_update_post, _on_depsgraph_update),
    ):
        if fn in collection:
            collection.remove(fn)
    if bpy.app.timers.is_registered(_timer):
        bpy.app.timers.unregister(_timer)


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------


def _addon_package():
    """Root add-on package name, from either an extension or a legacy install."""
    return __package__.rsplit(".", 1)[0] if "." in __package__ else __package__


def get_addon_preferences(context):
    addon = context.preferences.addons.get(_addon_package())
    return addon.preferences if addon else None


def _bound_meshes(armatures):
    """Meshes bound to the given armatures, minus the reference avatar's body."""
    if not armatures:
        return set()
    meshes = set()
    for obj in bpy.context.view_layer.objects:
        if obj.type != "MESH":
            continue
        if any(coll.name in REFERENCE_AVATAR_COLLECTIONS for coll in obj.users_collection):
            continue
        if obj.parent in armatures or any(mod.type == "ARMATURE" and mod.object in armatures for mod in obj.modifiers):
            meshes.add(obj)
    return meshes


def _export_wearable_glb(out_path, selected_only):
    """Export the wearable to GLB, returning the error (or None)."""
    # hide_set/select_set raise for objects outside the view layer (excluded collections).
    in_view_layer = bpy.context.view_layer.objects
    if selected_only:
        base = list(bpy.context.selected_objects)
        # Complete the selection in both directions: a mesh pulls in the rig
        # it is bound to, and an armature pulls in the wearable meshes bound
        # to it (never the reference body — that is the full-scene footgun).
        selected_armatures = {obj for obj in base if obj.type == "ARMATURE"}
        extras = [mesh for mesh in _bound_meshes(selected_armatures) if mesh not in base]
    else:
        # What the user hid on purpose (helpers, colliders, alternates) stays out of the preview.
        base = [obj for obj in in_view_layer if obj.visible_get()]
        extras = []
    # A mesh always needs the rig it is skinned to, even one hidden while modelling;
    # the hide/restore below unhides it for the export only.
    extras += [arm for arm in bound_armatures(base) if arm not in base]
    scope_objects = base + [obj for obj in extras if obj.name in in_view_layer]

    scope = [(obj.type, [coll.name for coll in obj.users_collection]) for obj in scope_objects]
    error = wearable_export_error(scope, selected_only=selected_only)
    if error:
        return error

    view_layer = bpy.context.view_layer
    active = view_layer.objects.active
    restore = []
    snapshots = []
    try:
        # The glTF exporter forces Object Mode on the active object and never
        # restores it; with none active it leaves the user's mode alone.
        view_layer.objects.active = None
        for obj in scope_objects:
            restore.append((obj, obj.hide_get(), obj.select_get()))
            if obj.type == "MESH" and obj.mode == "EDIT":
                obj.select_set(False)
                obj = _snapshot_edit_mesh(obj, snapshots)
            obj.hide_set(False)
            obj.select_set(True)
        bpy.ops.export_scene.gltf(
            filepath=out_path,
            export_format="GLB",
            use_selection=True,
            export_apply=True,
            export_animations=False,
            export_cameras=False,
            export_lights=False,
        )
    except Exception as exc:
        return str(exc)
    finally:
        # Snapshots first: a failed restore below must not leave a mesh renamed.
        for obj, copy, name in snapshots:
            mesh = copy.data
            bpy.data.objects.remove(copy)
            bpy.data.meshes.remove(mesh)
            obj.name = name
        for obj, was_hidden, was_selected in reversed(restore):
            try:
                obj.select_set(was_selected)
                obj.hide_set(was_hidden)
            except RuntimeError:
                pass
        view_layer.objects.active = active
    return None


def _snapshot_edit_mesh(obj, snapshots):
    """A plain copy exported in place of a mesh being edited: the glTF exporter
    cannot read edit-mode meshes. Takes the original's name so the GLB matches."""
    obj.update_from_editmode()
    copy = obj.copy()
    copy.data = obj.data.copy()
    collection = obj.users_collection[0] if obj.users_collection else bpy.context.scene.collection
    collection.objects.link(copy)
    name = obj.name
    obj.name = name + ".live"
    copy.name = name
    snapshots.append((obj, copy, name))
    return copy


def _emote_export_failure(message):
    """The user-facing reason an emote export failed, listing the validation problems when that was the gate."""
    if is_emote_validation_failure(message):
        validation = run_emote_validation(bpy.context)
        strict = bool(bpy.context.scene.dcl_tools.emote_strict_validation)
        error = emote_validation_error(validation["errors"], validation["warnings"], strict=strict)
        if error:
            return error
    return emote_export_error(message)


def _show_error_details(context, title, lines):
    """A popup listing ``lines``: the status-bar report only fits a single line."""

    def draw(menu, _context):
        for line in lines:
            menu.layout.label(text=line)

    context.window_manager.popup_menu(draw, title=title, icon="ERROR")


def _make_exporter(directory, is_emote, selected_only):
    """A callback that re-exports into the served folder.

    Exports land in a scratch file first and are swapped in with os.replace, so
    the Builder never fetches a half-written model.
    """
    model_path = os.path.join(directory, MODEL_FILE)
    scratch_path = os.path.join(directory, f"next_{MODEL_FILE}")

    def _export():
        if is_emote:
            # Reuses the emote exporter so validation, frame range and prop
            # armatures behave exactly like a normal emote export.
            try:
                result = bpy.ops.object.export_emote_glb(filepath=scratch_path)
            except RuntimeError as exc:
                # bpy re-raises the operator's ERROR report; its text is meant
                # for the export dialog, not for someone who only hit Preview.
                return _emote_export_failure(str(exc))
            if "FINISHED" not in result:
                return emote_export_error("")
        else:
            error = _export_wearable_glb(scratch_path, selected_only)
            if error:
                return str(error)
        if not os.path.isfile(scratch_path):
            return "export produced no file"
        os.replace(scratch_path, model_path)
        return None

    return _export


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------


class OBJECT_OT_preview_in_builder(bpy.types.Operator):
    bl_idname = "object.preview_in_builder"
    bl_label = "Live Preview in Builder"
    bl_description = (
        "Export the current wearable or emote and stream it to the Builder's Live Preview page, "
        "re-exporting whenever the scene changes or the file is saved"
    )
    bl_options = {"REGISTER"}

    # Preset by the Preview Wearable / Preview Emote buttons; not shown in the dialog.
    content_type: bpy.props.EnumProperty(
        name="Preview",
        items=[
            ("WEARABLE", "Wearable", "Export the model and equip it on the avatar"),
            ("EMOTE", "Emote", "Export the animation and play it on the avatar"),
        ],
        default="WEARABLE",
        options={"HIDDEN"},
    )

    category: bpy.props.EnumProperty(
        name="Category",
        description="Wearable category the Builder page starts with (changeable there)",
        items=[(cat, readable_category(cat), f"Preview as a {cat} wearable") for cat in WEARABLE_CATEGORIES],
        default="upper_body",
    )

    selected_only: bpy.props.BoolProperty(
        name="Selected Only",
        description=(
            "Export only the selected objects. Selecting the wearable mesh includes its armature "
            "automatically, and selecting the armature includes the wearable meshes bound to it"
        ),
        default=True,
    )

    def invoke(self, context, event):
        # Emotes have nothing left to configure here; the previewer URL and
        # bridge port live in the add-on preferences.
        if self.content_type == "EMOTE":
            return self.execute(context)
        return context.window_manager.invoke_props_dialog(self, width=380)

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "category")
        layout.prop(self, "selected_only")

    def execute(self, context):
        prefs = get_addon_preferences(context)
        previewer_url = normalize_previewer_url(
            (getattr(prefs, "previewer_url", "") if prefs else "") or DEFAULT_PREVIEWER_URL
        )
        if not previewer_url:
            self.report({"ERROR"}, "Set the Previewer URL first (Preferences > Add-ons > Decentraland Tools).")
            return {"CANCELLED"}
        bridge_port = getattr(prefs, "bridge_port", 0) if prefs else 0

        is_emote = self.content_type == "EMOTE"

        if _server.running and bridge_port and bridge_port != _server.port:
            # Rebinding deletes the folder the running session exports into.
            stop_live_session()
        try:
            directory = _server.start(bridge_port)
        except OSError as exc:
            self.report({"ERROR"}, f"Could not start the local bridge: {exc}")
            return {"CANCELLED"}

        export = _make_exporter(directory, is_emote, self.selected_only)
        error = export()
        if error:
            if not _session.active:
                _server.stop()
            headline, details = report_lines(error)
            self.report({"ERROR"}, f"Cannot preview: {headline}")
            if details:
                _show_error_details(context, f"Cannot preview: {headline}", details)
            return {"CANCELLED"}

        start_live_session(
            export,
            is_emote=is_emote,
            name=bpy.path.display_name_from_filepath(bpy.data.filepath) or "Blender Preview",
            category=self.category,
        )

        bridge_url = _server.url
        try:
            webbrowser.open(live_preview_url(previewer_url, bridge_url))
        except Exception as exc:
            # Don't leave handlers and the timer re-exporting for a page nobody opened.
            stop_live_session()
            self.report({"ERROR"}, f"Could not open the browser: {exc}")
            return {"CANCELLED"}

        self.report({"INFO"}, f"Streaming to the Builder Live Preview page (bridge on 127.0.0.1:{_server.port}).")
        return {"FINISHED"}


class OBJECT_OT_reset_previewer_url(bpy.types.Operator):
    bl_idname = "object.reset_previewer_url"
    bl_label = "Reset Previewer URL"
    bl_description = "Restore the default previewer URL"
    bl_options = {"REGISTER", "INTERNAL"}

    def execute(self, context):
        prefs = get_addon_preferences(context)
        if prefs is None:
            return {"CANCELLED"}
        prefs.previewer_url = DEFAULT_PREVIEWER_URL
        return {"FINISHED"}


class OBJECT_OT_stop_live_preview(bpy.types.Operator):
    bl_idname = "object.stop_live_preview"
    bl_label = "Stop Live Preview"
    bl_description = "Stop the local bridge that streams exports to the Builder and delete the exported files"
    bl_options = {"REGISTER"}

    @classmethod
    def poll(cls, context):
        return _server.running

    def execute(self, context):
        stop_live_preview()
        self.report({"INFO"}, "Live preview stopped.")
        return {"FINISHED"}
