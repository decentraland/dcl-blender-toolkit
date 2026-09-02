"""Live preview of the current wearable or emote in the Builder.

Previewing means three things: export the selection to a GLB, serve it from a
short-lived local bridge, and open the Builder's ``/live-preview`` page, which
polls the bridge and hot-swaps the model on a live avatar:

    GET /state                 -> {"version", "type", "name", "category"}
    GET /state?since=N         -> same, answered once version != N (or after 25 seconds)
    GET /model.glb             -> the latest export

Overrides, body shape and emote playback are all chosen on the Builder page;
the add-on only exports and serves. Refresh is always live: saving the .blend
re-exports immediately, scene edits re-export after a quiet period, and each
re-export bumps ``version`` so the page picks it up on its next poll. The
bridge binds to 127.0.0.1 (OS-assigned port unless one is set under Advanced),
its URL is passed to the page as the ``bridge`` query param, and it is torn
down on Stop Live Preview or when the add-on is unregistered.
"""

import os
import shutil
import tempfile
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs

import bpy
from bpy.app.handlers import persistent

from .bridge_utils import (
    DEFAULT_PREVIEWER_URL,
    REFERENCE_AVATAR_COLLECTIONS,
    WEARABLE_CATEGORIES,
    LiveState,
    build_state_payload,
    live_preview_url,
    normalize_previewer_url,
    previewer_origin,
    readable_category,
    schedule_dirty,
    wearable_export_error,
)

MODEL_FILE = "model.glb"

# Re-export only once the scene has been quiet for this long, so dragging a
# vertex or scrubbing a slider does not export on every mouse move.
DEBOUNCE_SECONDS = 0.5
# The refresh itself dirties the depsgraph (the emote exporter toggles
# visibility and scrubs frames). _refresh flushes that while the handler is
# muted; anything still landing this close after a refresh is handled by
# schedule_dirty so the session can neither lose an edit nor loop forever.
_POST_REFRESH_GRACE = 0.75
_TIMER_INTERVAL = 0.2


# ---------------------------------------------------------------------------
# Bridge server
# ---------------------------------------------------------------------------


class _BridgeRequestHandler(BaseHTTPRequestHandler):
    """Serves /state and /model.glb, with CORS scoped to the previewer page's origin."""

    def _send(self, code, content_type, body):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", _server.allowed_origin or "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):  # noqa: N802 — http.server naming
        self._send(204, "text/plain", b"")

    def do_GET(self):  # noqa: N802 — http.server naming
        path, _, query = self.path.partition("?")
        state, model_path = _server.snapshot()
        if path == "/state" and state:
            since = parse_qs(query).get("since", [None])[0]
            if since is not None:
                state = _server.live.wait_for_change(since) or state
            self._send(200, "application/json", state.encode("utf-8"))
        elif path == f"/{MODEL_FILE}" and model_path:
            try:
                with open(model_path, "rb") as f:
                    body = f.read()
            except OSError:
                # stop() may delete the directory between the snapshot and the read.
                self._send(404, "text/plain", b"not found")
            else:
                self._send(200, "model/gltf-binary", body)
        else:
            self._send(404, "text/plain", b"not found")

    def log_message(self, fmt, *args):
        # Silence per-request logging; Blender's console is not a web server log.
        pass


class _BridgeServer:
    """Threaded HTTP server over a temporary export directory."""

    def __init__(self):
        self._httpd = None
        self._thread = None
        self._lock = threading.Lock()
        self.live = LiveState()
        self.directory = None
        self.allowed_origin = ""

    @property
    def running(self):
        return self._httpd is not None

    @property
    def port(self):
        return self._httpd.server_address[1] if self._httpd else None

    def start(self, port=0, allowed_origin=""):
        self.allowed_origin = allowed_origin
        if self.running:
            if port and port != self.port:
                # An explicitly requested port beats the one already bound.
                self.stop()
            else:
                return self.directory

        self.directory = tempfile.mkdtemp(prefix="dcl_live_preview_")
        self._httpd = ThreadingHTTPServer(("127.0.0.1", port), _BridgeRequestHandler)
        self._httpd.daemon_threads = True
        self._thread = threading.Thread(target=self._httpd.serve_forever, name="dcl-live-preview", daemon=True)
        self._thread.start()
        return self.directory

    def publish(self, state_payload):
        self.live.publish(state_payload)

    def snapshot(self):
        """Read by the server thread; the state payload and model path move together."""
        with self._lock:
            model_path = os.path.join(self.directory, MODEL_FILE) if self.directory else None
        return self.live.snapshot(), model_path

    def stop(self):
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread:
            self._thread.join(timeout=5)
        if self.directory and os.path.isdir(self.directory):
            shutil.rmtree(self.directory, ignore_errors=True)

        self._httpd = None
        self._thread = None
        self.allowed_origin = ""
        # Also releases any long-poll still waiting on a version change.
        self.live.publish("")
        with self._lock:
            self.directory = None


_server = _BridgeServer()


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
        self.last_refresh = 0.0
        self.deferred_after_refresh = False

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
    _version += 1
    _publish_state()
    _install_handlers()


def stop_live_session():
    _session.export = None
    _session.dirty_at = None
    _remove_handlers()


def stop_live_preview():
    """Tear the bridge down. Called from the add-on's unregister()."""
    stop_live_session()
    _server.stop()


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
        _session.last_refresh = time.monotonic()

    if error:
        print(f"DCL live preview: refresh skipped — {error}")
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
    # The session belongs to the file it was started from.
    stop_live_session()


@persistent
def _on_depsgraph_update(scene, depsgraph):
    if not _session.active or _session.exporting:
        return
    screen = getattr(bpy.context, "screen", None)
    if screen and screen.is_animation_playing:
        return
    if not any(_is_relevant(update) for update in depsgraph.updates):
        return
    dirty_at, _session.deferred_after_refresh = schedule_dirty(
        time.monotonic(), _session.last_refresh, _POST_REFRESH_GRACE, _session.deferred_after_refresh
    )
    if dirty_at is not None:
        _session.dirty_at = dirty_at


def _timer():
    if not _session.active:
        return None
    if _session.dirty_at is not None and time.monotonic() - _session.dirty_at >= DEBOUNCE_SECONDS:
        _session.dirty_at = None
        _refresh()
    return _TIMER_INTERVAL


def _install_handlers():
    handlers = bpy.app.handlers
    if _on_save_post not in handlers.save_post:
        handlers.save_post.append(_on_save_post)
    if _on_depsgraph_update not in handlers.depsgraph_update_post:
        handlers.depsgraph_update_post.append(_on_depsgraph_update)
    if _on_load_pre not in handlers.load_pre:
        handlers.load_pre.append(_on_load_pre)
    if not bpy.app.timers.is_registered(_timer):
        bpy.app.timers.register(_timer, first_interval=_TIMER_INTERVAL)


def _remove_handlers():
    handlers = bpy.app.handlers
    for collection, fn in (
        (handlers.save_post, _on_save_post),
        (handlers.depsgraph_update_post, _on_depsgraph_update),
        (handlers.load_pre, _on_load_pre),
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


def _bound_armatures(objects):
    """The armatures the given objects are skinned or parented to."""
    armatures = set()
    for obj in objects:
        for mod in getattr(obj, "modifiers", ()):
            if mod.type == "ARMATURE" and mod.object is not None:
                armatures.add(mod.object)
        if obj.parent is not None and obj.parent.type == "ARMATURE":
            armatures.add(obj.parent)
    return armatures


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
    extras = []
    if selected_only:
        selected = list(bpy.context.selected_objects)
        # Complete the selection in both directions: a mesh pulls in the rig
        # it is bound to, and an armature pulls in the wearable meshes bound
        # to it (never the reference body — that is the full-scene footgun).
        extras = [arm for arm in _bound_armatures(selected) if arm not in selected]
        selected_armatures = {obj for obj in selected if obj.type == "ARMATURE"}
        extras += [mesh for mesh in _bound_meshes(selected_armatures) if mesh not in selected]
        scope_objects = selected + extras
    else:
        scope_objects = bpy.context.view_layer.objects

    scope = [(obj.type, [coll.name for coll in obj.users_collection]) for obj in scope_objects]
    error = wearable_export_error(scope, selected_only=selected_only)
    if error:
        return error

    restore = []
    try:
        for extra in extras:
            restore.append((extra, extra.hide_get()))
            extra.hide_set(False)
            extra.select_set(True)
        bpy.ops.export_scene.gltf(
            filepath=out_path,
            export_format="GLB",
            use_selection=selected_only,
            export_apply=True,
            export_animations=False,
            export_cameras=False,
            export_lights=False,
        )
    except Exception as exc:
        return str(exc)
    finally:
        for extra, was_hidden in restore:
            extra.select_set(False)
            extra.hide_set(was_hidden)
    return None


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
            result = bpy.ops.object.export_emote_glb(filepath=scratch_path)
            if "FINISHED" not in result:
                return "emote export cancelled (check validation)"
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


def _apply_previewer_url_reset(op, _context):
    # A dialog cannot host a real button that edits its own properties, so the
    # reset icon is a self-clearing toggle whose update does the work.
    if op.reset_previewer_url:
        op.reset_previewer_url = False
        op.previewer_url = DEFAULT_PREVIEWER_URL


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

    show_advanced: bpy.props.BoolProperty(
        name="Advanced",
        default=False,
        options={"HIDDEN"},
    )

    previewer_url: bpy.props.StringProperty(
        name="Previewer URL",
        description=(
            "Live Preview page to open. A locally served one "
            "(http://localhost:3000/live-preview) works too. Saved to the add-on preferences"
        ),
        default=DEFAULT_PREVIEWER_URL,
    )

    reset_previewer_url: bpy.props.BoolProperty(
        name="Reset Previewer URL",
        description="Restore the default previewer URL",
        default=False,
        update=_apply_previewer_url_reset,
        options={"HIDDEN", "SKIP_SAVE"},
    )

    bridge_port: bpy.props.IntProperty(
        name="Blender Port",
        description="Port the local bridge listens on. 0 picks a free port automatically",
        default=0,
        min=0,
        max=65535,
    )

    def invoke(self, context, event):
        prefs = get_addon_preferences(context)
        saved = getattr(prefs, "previewer_url", "") if prefs else ""
        self.previewer_url = saved or DEFAULT_PREVIEWER_URL
        return context.window_manager.invoke_props_dialog(self, width=380)

    def draw(self, context):
        layout = self.layout

        if self.content_type == "WEARABLE":
            layout.prop(self, "category")
            layout.prop(self, "selected_only")

        row = layout.row()
        row.alignment = "LEFT"
        row.prop(
            self,
            "show_advanced",
            icon="TRIA_DOWN" if self.show_advanced else "TRIA_RIGHT",
            emboss=False,
        )
        if self.show_advanced:
            box = layout.box()
            box.use_property_split = True
            box.use_property_decorate = False
            row = box.row(align=True)
            row.prop(self, "previewer_url")
            sub = row.row(align=True)
            sub.use_property_split = False
            sub.prop(self, "reset_previewer_url", text="", icon="LOOP_BACK", emboss=False)
            box.prop(self, "bridge_port")

    def execute(self, context):
        previewer_url = normalize_previewer_url(self.previewer_url)
        if not previewer_url:
            self.report({"ERROR"}, "Set the Previewer URL first (Preferences > Add-ons > Decentraland Tools).")
            return {"CANCELLED"}

        prefs = get_addon_preferences(context)
        if prefs and prefs.previewer_url != previewer_url:
            prefs.previewer_url = previewer_url

        is_emote = self.content_type == "EMOTE"

        try:
            directory = _server.start(self.bridge_port, previewer_origin(previewer_url))
        except OSError as exc:
            self.report({"ERROR"}, f"Could not start the local bridge: {exc}")
            return {"CANCELLED"}

        export = _make_exporter(directory, is_emote, self.selected_only)
        error = export()
        if error:
            self.report({"ERROR"}, f"Export failed: {error}")
            return {"CANCELLED"}

        start_live_session(
            export,
            is_emote=is_emote,
            name=bpy.path.display_name_from_filepath(bpy.data.filepath) or "Blender Preview",
            category=self.category,
        )

        bridge_url = f"http://127.0.0.1:{_server.port}"
        try:
            webbrowser.open(live_preview_url(previewer_url, bridge_url))
        except Exception as exc:
            # Don't leave handlers and the timer re-exporting for a page nobody opened.
            stop_live_session()
            self.report({"ERROR"}, f"Could not open the browser: {exc}")
            return {"CANCELLED"}

        self.report({"INFO"}, f"Streaming to the Builder Live Preview page (bridge on {bridge_url}).")
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
