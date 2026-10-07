"""The Builder Live Preview bridge: a tiny local HTTP server and its payloads.

The Builder's ``/live-preview`` page connects to the bridge exposed by this
add-on: ``GET /<token>/state`` returns the JSON metadata built here and
``GET /<token>/model.glb`` returns the latest export. The page polls ``state``
and re-fetches the model whenever ``version`` moves, then hot-swaps it on the
avatar without reloading. Everything in this module is plain Python so it can
be exercised without Blender.
"""

import hmac
import json
import os
import secrets
import shutil
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlsplit

DEFAULT_PREVIEWER_URL = "https://decentraland.org/create/live-preview"
MODEL_FILE = "model.glb"

# Wearable categories accepted by the Builder (WearableCategory in @dcl/schemas).
WEARABLE_CATEGORIES = (
    "upper_body",
    "lower_body",
    "hands_wear",
    "feet",
    "hat",
    "helmet",
    "top_head",
    "tiara",
    "mask",
    "eyewear",
    "earring",
    "hair",
    "facial_hair",
    "eyes",
    "eyebrows",
    "mouth",
    "skin",
    "body_shape",
)


def normalize_previewer_url(raw):
    """Turn whatever was pasted into a usable previewer page URL.

    Accepts a bare host, a full URL, and URLs that still carry a query or
    fragment. The path is kept: the value is the page itself.
    """
    value = (raw or "").strip()
    if not value:
        return ""

    if "://" not in value:
        value = f"https://{value.lstrip('/')}"

    value = value.split("?", 1)[0].split("#", 1)[0].rstrip("/")
    # webbrowser.open hands anything else (file://, custom handlers) to the OS.
    parts = urlsplit(value)
    if parts.scheme.lower() not in ("http", "https") or not parts.netloc:
        return ""
    return value


def is_loopback_host(host_header, port):
    """True when a request's Host header names the bridge on loopback."""
    return (host_header or "").lower() in (f"127.0.0.1:{port}", f"localhost:{port}")


def strip_session_token(path, token):
    """``/<token>/state`` -> ``/state``, or None unless the first segment is this session's token."""
    segment, slash, rest = path.lstrip("/").partition("/")
    if not token or not slash or not hmac.compare_digest(segment.encode("utf-8"), token.encode("utf-8")):
        return None
    return "/" + rest


def live_preview_url(page_url, bridge_url=""):
    """The previewer page to open.

    ``bridge_url`` is handed over as the ``bridge`` query param so the page
    connects to the local bridge without the user pasting anything.
    """
    url = normalize_previewer_url(page_url)
    if not url:
        raise ValueError("Previewer URL is empty")
    if bridge_url:
        url += f"?bridge={quote(bridge_url, safe='')}"
    return url


# Body-mesh collections created by Import DCL Rig. Meshes in them are only a
# problem for full-scene exports: an explicit selection of them is a
# deliberate body_shape/skin wearable.
REFERENCE_AVATAR_COLLECTIONS = frozenset({"Avatar_ShapeA", "Avatar_ShapeB"})


def wearable_export_error(objects, *, selected_only):
    """Why exporting ``objects`` would show a broken wearable preview, or None.

    ``objects`` describes everything the GLB export would include, as
    ``(object_type, collection_names)`` pairs. An explicit selection is
    trusted beyond being non-empty and containing a mesh; only full-scene
    exports are checked for content that cannot belong to a wearable.
    """
    objects = list(objects)

    if not objects:
        return (
            "nothing is selected — select the wearable mesh" if selected_only else "the scene has no exportable objects"
        )

    if not any(obj_type == "MESH" for obj_type, _ in objects):
        return (
            "the selection contains no meshes and nothing is bound to the selected armature — select the wearable mesh"
            if selected_only
            else "the scene contains no meshes"
        )

    if selected_only:
        return None

    hint = 'enable "Selected Only" and select the wearable mesh'

    if any(REFERENCE_AVATAR_COLLECTIONS.intersection(colls) for obj_type, colls in objects if obj_type == "MESH"):
        return f"the export would include the reference avatar's body — {hint}"

    armature_count = sum(1 for obj_type, _ in objects if obj_type == "ARMATURE")
    if armature_count > 1:
        return f"the export would include {armature_count} armatures, but a wearable uses at most one — {hint}"

    return None


def emote_validation_error(errors, warnings, *, strict):
    """Why the emote cannot be previewed: a headline, then one problem per line. None when it can.

    Mirrors the Export Emote GLB rule: errors always block, warnings block only
    with Strict Validation on.
    """
    problems = list(errors)
    if strict:
        problems += list(warnings)
    if not problems:
        return None

    if errors:
        count = len(errors)
        headline = f"the emote has {count} validation error{'s' if count != 1 else ''} — fix them and preview again"
    else:
        headline = (
            "Strict Validation is on and the emote has warnings — "
            "fix them, or turn Strict Validation off in the Emote settings"
        )
    return "\n".join([headline, *problems])


def is_emote_validation_failure(message):
    """Whether an Export Emote GLB failure was its validation gate (details come from re-validating)."""
    return "validation" in message.lower()


def emote_export_error(message):
    """Rewrite an Export Emote GLB failure into something the user can act on."""
    message = message.strip()
    if message.startswith("Error: "):
        message = message[len("Error: ") :]
    message = message.rstrip(".")

    if message.startswith("No armature found"):
        return "no avatar rig found — use Import DCL Rig in the Emote tab and animate it before previewing"

    view_layer_prefix = "Cannot export, not in the current view layer:"
    if message.startswith(view_layer_prefix):
        names = message[len(view_layer_prefix) :].strip()
        return (
            f"these objects are excluded from the current view layer and cannot be exported: {names} — "
            "enable their collections in the Outliner"
        )

    gltf_prefix = "Export failed:"
    if message.startswith(gltf_prefix):
        return f"Blender's glTF exporter failed: {message[len(gltf_prefix) :].strip()}"

    if is_emote_validation_failure(message):
        return "the emote does not pass validation — run Validate Emote in the Emote tab to see why"

    return message or "the emote export was cancelled"


def report_lines(message):
    """Split an exporter error into the headline for the status bar and the detail lines for a popup."""
    headline, *details = message.split("\n")
    return headline, [line for line in details if line.strip()]


def readable_category(name):
    """ "upper_body" -> "Upper Body", matching the Builder's labels."""
    return name.replace("_", " ").title()


def build_state_payload(*, version, is_emote, name, category=""):
    """The ``/state`` body. The Builder treats a changed ``version`` as "re-fetch the model"."""
    return json.dumps(
        {
            "version": int(version),
            "type": "emote" if is_emote else "wearable",
            "name": name or "Blender Preview",
            "category": "" if is_emote else category,
        },
        separators=(",", ":"),
    )


# How long a ``/state?since=`` request may be held open before answering with the unchanged state.
LONG_POLL_SECONDS = 25.0


class LiveState:
    """The ``/state`` payload, publishable from Blender's thread and waitable from the server's.

    The Builder long-polls ``/state?since=<version>``: the request is answered as
    soon as the published version differs from ``since``, or after LONG_POLL_SECONDS.
    """

    def __init__(self):
        self._cond = threading.Condition()
        self._payload = ""
        self._version = None

    def publish(self, payload):
        with self._cond:
            self._payload = payload
            self._version = json.loads(payload)["version"] if payload else None
            self._cond.notify_all()

    def snapshot(self):
        with self._cond:
            return self._payload

    def wait_for_change(self, since):
        with self._cond:
            self._cond.wait_for(lambda: self._version is None or str(self._version) != since, LONG_POLL_SECONDS)
            return self._payload


def bound_armatures(objects):
    """The armatures the given objects are skinned or parented to."""
    armatures = set()
    for obj in objects:
        for mod in getattr(obj, "modifiers", ()):
            if mod.type == "ARMATURE" and mod.object is not None:
                armatures.add(mod.object)
        if obj.parent is not None and obj.parent.type == "ARMATURE":
            armatures.add(obj.parent)
    return armatures


class RefreshScheduler:
    """Decides when a scene change marks the live session dirty.

    Changes landing within ``grace`` seconds of a refresh may be the exporter's
    own restore work rather than an edit. The first one in a window is deferred
    to the window's end so a real edit is not lost, and later ones in the same
    window share that deferral. Refreshes that came only from deferrals are
    counted, and after MAX_CHAINED_DEFERRALS in a row the next in-window change
    is dropped, so a side effect that survives the depsgraph flush cannot
    re-export forever. A change outside the window is a fresh edit and resets
    the count.
    """

    MAX_CHAINED_DEFERRALS = 2

    def __init__(self, grace):
        self.grace = grace
        self.last_refresh = 0.0
        self.deferred = False
        self.pending_is_deferred = False
        self.chained = 0

    def refreshed(self, now):
        self.last_refresh = now
        self.deferred = False
        self.chained = self.chained + 1 if self.pending_is_deferred else 0
        self.pending_is_deferred = False

    def change(self, now):
        """When the session should go dirty for a change at ``now``, or None to ignore it."""
        if now - self.last_refresh >= self.grace:
            self.chained = 0
            self.pending_is_deferred = False
            return now
        if self.deferred or self.chained >= self.MAX_CHAINED_DEFERRALS:
            return None
        self.deferred = True
        self.pending_is_deferred = True
        return self.last_refresh + self.grace


class _BridgeHTTPServer(ThreadingHTTPServer):
    daemon_threads = True
    # Never join handler threads on close: the page always holds a long-poll open.
    block_on_close = False

    def __init__(self, address, handler, bridge):
        super().__init__(address, handler)
        self.bridge = bridge


class BridgeRequestHandler(BaseHTTPRequestHandler):
    """Serves ``/<token>/state`` and ``/<token>/model.glb`` to any page that knows the token."""

    # Longer than the long-poll, so idle connections cannot pin threads.
    timeout = LONG_POLL_SECONDS + 5

    def _send(self, code, content_type, body, cors=True):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        if cors:
            # Any origin: the page may come from any environment or a local dev server. The
            # per-session token in the path is what keeps other sites out.
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "*")
            # Chromium's private-network preflight for a public page reaching localhost.
            self.send_header("Access-Control-Allow-Private-Network", "true")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _refuse(self, code, body):
        # No CORS headers: a page without the token cannot even tell the bridge is here.
        self._send(code, "text/plain", body, cors=False)

    def _authorised_path(self):
        """The route under the session token, or None after refusing the request."""
        # Blocks DNS rebinding: a page whose own host resolves to 127.0.0.1 still sends its name.
        if not is_loopback_host(self.headers.get("Host"), self.server.server_address[1]):
            self._refuse(403, b"forbidden")
            return None
        path = self.path.partition("?")[0]
        # Only the page opened with this session's bridge URL knows the token; any other
        # site fetching 127.0.0.1 directly gets a 404 for every path.
        path = strip_session_token(path, self.server.bridge.token)
        if path is None:
            self._refuse(404, b"not found")
        return path

    def do_OPTIONS(self):  # noqa: N802 — http.server naming
        if self._authorised_path() is not None:
            self._send(204, "text/plain", b"")

    def do_GET(self):  # noqa: N802 — http.server naming
        bridge = self.server.bridge
        path = self._authorised_path()
        if path is None:
            return
        query = self.path.partition("?")[2]
        state, model_path = bridge.snapshot()
        if path == "/state" and state:
            since = parse_qs(query).get("since", [None])[0]
            if since is not None:
                state = bridge.live.wait_for_change(since) or state
            self._send(200, "application/json", state.encode("utf-8"))
        elif path == f"/{MODEL_FILE}" and model_path:
            try:
                with open(model_path, "rb") as f:
                    body = f.read()
            except OSError:
                # stop() may delete the directory between the snapshot and the read.
                self._refuse(404, b"not found")
            else:
                self._send(200, "model/gltf-binary", body)
        else:
            self._refuse(404, b"not found")

    def log_message(self, fmt, *args):
        # Silence per-request logging; Blender's console is not a web server log.
        pass


class BridgeServer:
    """Threaded HTTP server over a temporary export directory, bound to loopback."""

    def __init__(self):
        self._httpd = None
        self._thread = None
        self._lock = threading.Lock()
        self.live = LiveState()
        self.directory = None
        self.token = ""

    @property
    def running(self):
        return self._httpd is not None

    @property
    def port(self):
        return self._httpd.server_address[1] if self._httpd else None

    @property
    def url(self):
        """The bridge URL handed to the page; the token is part of the path."""
        return f"http://127.0.0.1:{self.port}/{self.token}" if self._httpd else None

    def start(self, port=0):
        """Bind and serve, returning the export directory. Rebinds when ``port`` changes.

        Every call is a new preview, so the token rotates each time: the URL a
        previous tab, link or analytics hit may have kept stops working.
        """
        if self.running:
            if port and port != self.port:
                self.stop()
            else:
                self.token = secrets.token_urlsafe(24)
                return self.directory

        self.directory = tempfile.mkdtemp(prefix="dcl_live_preview_")
        try:
            self._httpd = _BridgeHTTPServer(("127.0.0.1", port), BridgeRequestHandler, self)
        except OSError:
            shutil.rmtree(self.directory, ignore_errors=True)
            self.directory = None
            raise
        self.token = secrets.token_urlsafe(24)
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
        # Release any long-poll first, or shutting down would wait on it.
        self.live.publish("")
        if self._httpd:
            self._httpd.shutdown()
            self._httpd.server_close()
        if self._thread:
            self._thread.join(timeout=5)
        if self.directory and os.path.isdir(self.directory):
            shutil.rmtree(self.directory, ignore_errors=True)

        self._httpd = None
        self._thread = None
        self.token = ""
        with self._lock:
            self.directory = None
