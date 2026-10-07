"""Tests for the Builder Live Preview bridge, its payloads and its wiring."""

import json
import os
import re
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from tests._helpers import SRC_DIR, read_source

ROOT_DIR = os.path.dirname(SRC_DIR)

sys.path.insert(0, os.path.join(SRC_DIR, "ops"))

import bridge_utils  # noqa: E402


class TestStatePayload:
    def test_wearable_payload_round_trips(self):
        state = json.loads(bridge_utils.build_state_payload(version=3, is_emote=False, name="Hat", category="hat"))
        assert state == {"version": 3, "type": "wearable", "name": "Hat", "category": "hat"}

    def test_emote_payload_drops_the_wearable_category(self):
        # The Builder page decides "is emote" from type, and an emote's category
        # comes from its own dropdown there.
        state = json.loads(bridge_utils.build_state_payload(version=1, is_emote=True, name="Wave", category="hat"))
        assert state["type"] == "emote"
        assert state["category"] == ""

    def test_version_is_always_an_int(self):
        state = json.loads(bridge_utils.build_state_payload(version="7", is_emote=False, name="x"))
        assert state["version"] == 7

    def test_name_falls_back_when_the_file_is_unsaved(self):
        state = json.loads(bridge_utils.build_state_payload(version=1, is_emote=False, name=""))
        assert state["name"] == "Blender Preview"


class TestPreviewerURL:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("decentraland.zone/builder/live-preview", "https://decentraland.zone/builder/live-preview"),
            ("https://decentraland.org/builder/live-preview/", "https://decentraland.org/builder/live-preview"),
            ("https://decentraland.org/builder/live-preview?tab=x", "https://decentraland.org/builder/live-preview"),
            ("  https://decentraland.org/builder/live-preview#top  ", "https://decentraland.org/builder/live-preview"),
            ("http://localhost:3000/live-preview", "http://localhost:3000/live-preview"),
            ("", ""),
            (None, ""),
        ],
    )
    def test_normalization(self, raw, expected):
        assert bridge_utils.normalize_previewer_url(raw) == expected

    def test_live_preview_url_is_used_as_is(self):
        # The field holds the full page URL; nothing is appended to it.
        assert (
            bridge_utils.live_preview_url("http://localhost:3000/live-preview/") == "http://localhost:3000/live-preview"
        )

    def test_live_preview_url_carries_the_bridge_as_a_query_param(self):
        url = bridge_utils.live_preview_url("http://localhost:3000/live-preview", "http://127.0.0.1:54321")
        assert url == "http://localhost:3000/live-preview?bridge=http%3A%2F%2F127.0.0.1%3A54321"

    def test_empty_previewer_url_raises(self):
        with pytest.raises(ValueError):
            bridge_utils.live_preview_url("   ")

    @pytest.mark.parametrize(
        "raw",
        ["file:///etc/passwd", "ms-settings://display", "javascript://x", "https://"],
    )
    def test_only_http_pages_are_opened(self, raw):
        assert bridge_utils.normalize_previewer_url(raw) == ""

    def test_default_is_the_production_page(self):
        assert bridge_utils.DEFAULT_PREVIEWER_URL == "https://decentraland.org/create/live-preview"


class TestLoopbackHost:
    @pytest.mark.parametrize("host", ["127.0.0.1:8081", "localhost:8081", "LOCALHOST:8081"])
    def test_loopback_names_are_accepted(self, host):
        assert bridge_utils.is_loopback_host(host, 8081)

    @pytest.mark.parametrize("host", ["attacker.example:8081", "127.0.0.1:9999", "", None])
    def test_other_hosts_are_rejected(self, host):
        assert not bridge_utils.is_loopback_host(host, 8081)


class TestReadableCategory:
    def test_labels_match_the_builder(self):
        assert bridge_utils.readable_category("upper_body") == "Upper Body"
        assert bridge_utils.readable_category("hands_wear") == "Hands Wear"


class TestWearableExportError:
    WEARABLE = ("MESH", ["Hat"])
    RIG_ARMATURE = ("ARMATURE", ["Avatar"])
    BODY_MESH = ("MESH", ["Avatar_ShapeA"])

    def test_a_clean_wearable_with_its_armature_passes(self):
        objects = [self.WEARABLE, self.RIG_ARMATURE]
        assert bridge_utils.wearable_export_error(objects, selected_only=True) is None
        assert bridge_utils.wearable_export_error(objects, selected_only=False) is None

    def test_a_full_scene_with_the_reference_avatar_body_is_rejected(self):
        # The footgun: the imported DCL rig's body meshes would be baked into
        # the wearable and the Builder shows a deformed mess.
        error = bridge_utils.wearable_export_error(
            [self.WEARABLE, self.RIG_ARMATURE, self.BODY_MESH], selected_only=False
        )
        assert "reference avatar" in error
        assert "Selected Only" in error

    def test_an_explicit_selection_is_trusted(self):
        # body_shape and skin wearables legitimately export the body meshes,
        # and wearable meshes often live inside the Avatar collection.
        for objects in (
            [self.BODY_MESH, self.RIG_ARMATURE],
            [("MESH", ["Avatar"]), self.RIG_ARMATURE],
            [self.WEARABLE, self.RIG_ARMATURE, ("ARMATURE", ["Prop"])],
        ):
            assert bridge_utils.wearable_export_error(objects, selected_only=True) is None

    def test_a_wearable_parented_inside_the_avatar_collection_passes(self):
        # Only the ShapeA/ShapeB body collections mark reference meshes; the
        # top-level Avatar collection also holds the user's wearable.
        objects = [("MESH", ["Avatar"]), self.RIG_ARMATURE]
        assert bridge_utils.wearable_export_error(objects, selected_only=False) is None

    def test_a_full_scene_with_multiple_armatures_is_rejected(self):
        error = bridge_utils.wearable_export_error(
            [self.WEARABLE, self.RIG_ARMATURE, ("ARMATURE", ["Prop"])], selected_only=False
        )
        assert "2 armatures" in error

    def test_an_empty_selection_is_rejected(self):
        error = bridge_utils.wearable_export_error([], selected_only=True)
        assert "nothing is selected" in error

    def test_an_empty_scene_is_rejected(self):
        error = bridge_utils.wearable_export_error([], selected_only=False)
        assert "no exportable objects" in error

    def test_a_scope_without_meshes_is_rejected(self):
        assert "no meshes" in bridge_utils.wearable_export_error([self.RIG_ARMATURE], selected_only=True)
        assert "no meshes" in bridge_utils.wearable_export_error([self.RIG_ARMATURE], selected_only=False)


class TestSessionToken:
    def test_the_token_segment_is_stripped(self):
        assert bridge_utils.strip_session_token("/abc/state", "abc") == "/state"
        assert bridge_utils.strip_session_token("/abc/model.glb", "abc") == "/model.glb"

    @pytest.mark.parametrize("path", ["/state", "/abc", "/abd/state", "/abc?x=1", "//state", ""])
    def test_anything_else_is_refused(self, path):
        assert bridge_utils.strip_session_token(path, "abc") is None

    def test_a_stopped_bridge_has_no_token_and_refuses_everything(self):
        assert bridge_utils.strip_session_token("//state", "") is None


@pytest.fixture
def bridge():
    server = bridge_utils.BridgeServer()
    directory = server.start()
    server.publish(bridge_utils.build_state_payload(version=1, is_emote=False, name="Hat", category="hat"))
    with open(os.path.join(directory, bridge_utils.MODEL_FILE), "wb") as f:
        f.write(b"glTF-bytes")
    yield server
    server.stop()


def _get(url, **headers):
    return urlopen(Request(url, headers=headers), timeout=5)


class TestBridgeServer:
    def test_the_bridge_url_carries_a_per_session_token(self, bridge):
        assert bridge.url == f"http://127.0.0.1:{bridge.port}/{bridge.token}"
        assert len(bridge.token) >= 32

    def test_the_page_reads_state_and_model_through_the_token(self, bridge):
        with _get(f"{bridge.url}/state") as response:
            assert json.loads(response.read())["version"] == 1
            # Any origin may read: the token, not the origin, is the gate.
            assert response.headers["Access-Control-Allow-Origin"] == "*"
        with _get(f"{bridge.url}/model.glb") as response:
            assert response.read() == b"glTF-bytes"

    @pytest.mark.parametrize("path", ["/state", "/model.glb", "/nope/state", "/nope/model.glb"])
    def test_other_sites_fetching_loopback_directly_get_nothing(self, bridge, path):
        with pytest.raises(HTTPError) as excinfo:
            _get(f"http://127.0.0.1:{bridge.port}{path}")
        assert excinfo.value.code == 404

    def test_a_non_loopback_host_header_is_rejected(self, bridge):
        with pytest.raises(HTTPError) as excinfo:
            _get(f"{bridge.url}/state", Host="evil.example:80")
        assert excinfo.value.code == 403

    def test_refusals_carry_no_cors_headers(self, bridge):
        # A page without the token cannot even learn that the bridge is listening.
        for url, headers in ((f"http://127.0.0.1:{bridge.port}/state", {}), (f"{bridge.url}/state", {"Host": "x:1"})):
            with pytest.raises(HTTPError) as excinfo:
                _get(url, **headers)
            assert "Access-Control-Allow-Origin" not in excinfo.value.headers
            assert "Access-Control-Allow-Private-Network" not in excinfo.value.headers

    def test_preflight_is_gated_like_every_other_request(self, bridge):
        with urlopen(Request(f"{bridge.url}/state", method="OPTIONS"), timeout=5) as response:
            assert response.status == 204
            assert response.headers["Access-Control-Allow-Private-Network"] == "true"
        with pytest.raises(HTTPError) as excinfo:
            urlopen(Request(f"http://127.0.0.1:{bridge.port}/state", method="OPTIONS"), timeout=5)
        assert excinfo.value.code == 404
        assert "Access-Control-Allow-Origin" not in excinfo.value.headers
        with pytest.raises(HTTPError) as excinfo:
            urlopen(Request(f"{bridge.url}/state", method="OPTIONS", headers={"Host": "evil.example:80"}), timeout=5)
        assert excinfo.value.code == 403

    def test_starting_a_running_bridge_keeps_the_page_connected(self, bridge):
        # A re-preview calls start() before its export; if that export fails, the
        # page streaming the previous session must still reach the bridge.
        first = bridge.url
        assert bridge.start() == bridge.directory
        assert bridge.url == first
        with _get(f"{first}/state") as response:
            assert json.loads(response.read())["version"] == 1

    def test_a_new_session_rotates_the_token(self, bridge):
        # A URL kept by an old tab, a shared link or analytics stops working on the next session.
        first = bridge.url
        bridge.rotate_token()
        assert bridge.url != first
        with pytest.raises(HTTPError) as excinfo:
            _get(f"{first}/state")
        assert excinfo.value.code == 404
        with _get(f"{bridge.url}/state") as response:
            assert json.loads(response.read())["version"] == 1

    def test_the_operator_rotates_the_token_only_after_the_export_succeeded(self):
        live_src = read_source(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        execute = live_src.split("        export = _make_exporter(directory", 1)[1]
        assert execute.count("_server.rotate_token()") == 1
        assert execute.index('return {"CANCELLED"}') < execute.index("_server.rotate_token()")
        assert execute.index("_server.rotate_token()") < execute.index("start_live_session(")
        assert execute.index("start_live_session(") < execute.index("bridge_url = _server.url")

    def test_stop_returns_at_once_while_a_long_poll_is_open(self, bridge):
        # The page always holds /state?since=<current> open; stopping must not wait for it.
        poll = threading.Thread(target=lambda: _get(f"{bridge.url}/state?since=1").read(), daemon=True)
        poll.start()
        time.sleep(0.2)
        started = time.monotonic()
        bridge.stop()
        assert time.monotonic() - started < 1
        poll.join(timeout=2)
        assert not poll.is_alive()

    def test_stop_forgets_the_token_and_directory(self, bridge):
        directory = bridge.directory
        bridge.stop()
        assert bridge.token == ""
        assert bridge.directory is None
        assert not os.path.isdir(directory)

    def test_a_new_session_gets_a_new_token(self, bridge):
        first = bridge.token
        bridge.stop()
        bridge.start()
        assert bridge.token and bridge.token != first


class TestWiring:
    def test_server_binds_to_loopback_only(self):
        # Security tripwire: the bridge serves the local export to the browser,
        # so it must never listen on anything but loopback.
        bridge_src = read_source(os.path.join(SRC_DIR, "ops", "bridge_utils.py"))
        assert '("127.0.0.1", port)' in bridge_src
        assert '"0.0.0.0"' not in bridge_src

    def test_handler_threads_are_not_joined_on_close(self):
        bridge_src = read_source(os.path.join(SRC_DIR, "ops", "bridge_utils.py"))
        assert "block_on_close = False" in bridge_src

    def test_the_operator_hands_the_tokenised_url_to_the_page(self):
        live_src = read_source(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        assert "bridge_url = _server.url" in live_src
        assert 'f"http://127.0.0.1:{_server.port}"' not in live_src

    def test_the_manifest_permission_fits_blenders_limit(self):
        # Blender's extension validator caps permission texts at 64 characters.
        manifest = read_source(os.path.join(ROOT_DIR, "blender_manifest.toml"))
        for key, text in re.findall(r'^(\w+) = "([^"]*)"', manifest.split("[permissions]", 1)[1], re.M):
            assert len(text) <= 64, f"{key} permission is {len(text)} characters"

    def test_wearable_exports_are_validated_before_running(self):
        # Both the initial export and live re-exports go through the scope
        # check, so a broken scene cancels the preview instead of streaming.
        live_src = read_source(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        assert "error = wearable_export_error(scope, selected_only=selected_only)" in live_src

    def test_the_selection_is_completed_in_both_directions(self):
        # Selecting just the wearable mesh pulls in its rig, selecting just
        # the armature pulls in the wearable meshes bound to it, and the
        # borrowed selection is restored afterwards.
        live_src = read_source(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        assert "missing_bound_armatures(base)" in live_src
        assert "_bound_meshes(selected_armatures)" in live_src
        assert "obj.select_set(True)" in live_src
        assert "obj.select_set(was_selected)" in live_src

    def test_selected_only_defaults_to_on(self):
        live_src = read_source(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        prop = live_src.split("selected_only: bpy.props.BoolProperty(", 1)[1].split("def invoke", 1)[0]
        assert "default=True" in prop

    def test_edit_mode_meshes_export_from_a_copy(self):
        # The glTF exporter cannot read a mesh that is being edited.
        live_src = read_source(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        emote_src = read_source(os.path.join(SRC_DIR, "ops", "export_emote_glb.py"))
        assert 'if obj.type == "MESH" and obj.mode == "EDIT":' in live_src
        assert "obj.update_from_editmode()" in live_src
        assert "objects.active = armature" not in emote_src

    def test_a_failed_bind_removes_the_temp_directory(self):
        bridge_src = read_source(os.path.join(SRC_DIR, "ops", "bridge_utils.py"))
        start = bridge_src.split("    def start(self, port=0):", 1)[1].split("    def publish", 1)[0]
        assert "except OSError:" in start
        assert "shutil.rmtree(self.directory, ignore_errors=True)" in start

    def test_a_rebind_ends_the_session_exporting_into_the_old_folder(self):
        live_src = read_source(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        execute = live_src.split("    def execute(self, context):\n        prefs = get_addon_preferences", 1)[1]
        assert execute.index("stop_live_session()") < execute.index("_server.start(bridge_port)")

    def test_a_new_session_resets_the_refresh_timing(self):
        live_src = read_source(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        start = live_src.split("def start_live_session(", 1)[1].split("def stop_live_session", 1)[0]
        assert "_session.scheduler = RefreshScheduler(_POST_REFRESH_GRACE)" in start
        assert "_session.scheduler.refreshed(time.monotonic())" in start

    def test_opening_another_file_stops_the_bridge(self):
        live_src = read_source(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        load_pre = live_src.split("def _on_load_pre(", 1)[1].split("@persistent", 1)[0]
        assert "stop_live_preview()" in load_pre

    def test_the_load_handler_lives_for_the_whole_addon(self):
        # Removing a load_pre handler from inside load_pre makes Blender skip the next one.
        live_src = read_source(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        init_src = read_source(os.path.join(SRC_DIR, "__init__.py"))
        remove = live_src.split("def _remove_handlers(", 1)[1].split("\n\n\n", 1)[0]
        assert "load_pre" not in remove
        assert "load_pre" not in live_src.split("def _install_handlers(", 1)[1].split("\n\n\n", 1)[0]
        assert "handlers.load_pre.append(_on_load_pre)" in live_src.split("def register_live_preview(", 1)[1]
        assert "register_live_preview()" in init_src.split("def register():", 1)[1].split("def unregister", 1)[0]
        assert "unregister_live_preview()" in init_src.split("def unregister():", 1)[1]

    def test_refreshes_wait_for_modal_operators_to_finish(self):
        live_src = read_source(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        timer = live_src.split("def _timer(", 1)[1].split("def _install_handlers", 1)[0]
        # ...but not forever: an add-on with a permanent modal operator must not stall refreshes.
        assert "if waited < _MODAL_HOLD_SECONDS and _modal_operator_running():" in timer
        assert timer.index("_modal_operator_running()") < timer.index("_session.dirty_at = None")
        assert "_MODAL_HOLD_SECONDS = 5.0" in live_src
        assert 'getattr(window, "modal_operators", ())' in live_src

    def test_full_scene_exports_keep_hidden_objects_hidden_but_pull_in_hidden_rigs(self):
        live_src = read_source(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        scope = live_src.split("def _export_wearable_glb(", 1)[1].split("scope = [", 1)[0]
        assert "base = [obj for obj in in_view_layer if obj.visible_get()]" in scope
        assert "extras += list(missing_bound_armatures(base))" in scope
        assert "list(bpy.context.view_layer.objects)" not in live_src

    def test_the_panel_has_a_stop_button(self):
        init_src = read_source(os.path.join(SRC_DIR, "__init__.py"))
        assert init_src.count('row.operator(OBJECT_OT_stop_live_preview.bl_idname, text="", icon="X")') == 2

    def test_both_exporters_clear_the_active_object_around_the_gltf_export(self):
        live_src = read_source(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        emote_src = read_source(os.path.join(SRC_DIR, "ops", "export_emote_glb.py"))
        wearable = live_src.split("def _export_wearable_glb(", 1)[1].split("def _snapshot_edit_mesh", 1)[0]
        assert "view_layer.objects.active = None" in wearable
        assert "view_layer.objects.active = active" in wearable
        assert "context.view_layer.objects.active = None" in emote_src

    def test_the_dialog_has_no_advanced_settings(self):
        # Previewer URL and bridge port are add-on preferences, not dialog options.
        live_src = read_source(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        init_src = read_source(os.path.join(SRC_DIR, "__init__.py"))
        assert "show_advanced" not in live_src
        assert "previewer_url: bpy.props" not in live_src
        assert "bridge_port: bpy.props" not in live_src
        assert "bridge_port: bpy.props.IntProperty(" in init_src
        assert 'getattr(prefs, "bridge_port", 0)' in live_src

    def test_the_previewer_url_preference_can_be_reset_to_the_default(self):
        live_src = read_source(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        init_src = read_source(os.path.join(SRC_DIR, "__init__.py"))
        assert "prefs.previewer_url = DEFAULT_PREVIEWER_URL" in live_src
        assert "default=DEFAULT_PREVIEWER_URL" in init_src
        assert "row.operator(OBJECT_OT_reset_previewer_url.bl_idname" in init_src


class TestLongPoll:
    def test_a_stale_since_is_answered_at_once(self):
        live = bridge_utils.LiveState()
        live.publish(bridge_utils.build_state_payload(version=2, is_emote=False, name="x"))
        assert json.loads(live.wait_for_change("1"))["version"] == 2

    def test_a_current_since_waits_until_the_version_moves(self):
        import threading
        import time

        live = bridge_utils.LiveState()
        live.publish(bridge_utils.build_state_payload(version=1, is_emote=False, name="x"))
        threading.Timer(
            0.05, live.publish, [bridge_utils.build_state_payload(version=2, is_emote=False, name="x")]
        ).start()
        started = time.monotonic()
        assert json.loads(live.wait_for_change("1"))["version"] == 2
        assert time.monotonic() - started < 2

    def test_clearing_releases_waiters(self):
        import threading

        live = bridge_utils.LiveState()
        live.publish(bridge_utils.build_state_payload(version=1, is_emote=False, name="x"))
        threading.Timer(0.05, live.publish, [""]).start()
        assert live.wait_for_change("1") == ""

    def test_the_handler_long_polls_state(self, bridge):
        bridge.publish(bridge_utils.build_state_payload(version=1, is_emote=False, name="Hat"))
        threading.Timer(
            0.1, bridge.publish, [bridge_utils.build_state_payload(version=2, is_emote=False, name="Hat")]
        ).start()
        started = time.monotonic()
        with _get(f"{bridge.url}/state?since=1") as response:
            assert json.loads(response.read())["version"] == 2
        assert 0.05 < time.monotonic() - started < 2


class FakeArmature:
    type = "ARMATURE"
    parent = None
    modifiers = ()

    def __init__(self, name):
        self.name = name


class FakeMesh:
    type = "MESH"

    def __init__(self, name, parent=None, skinned_to=(), disabled=()):
        self.name = name
        self.parent = parent
        self.modifiers = [
            type("Mod", (), {"type": "ARMATURE", "object": rig, "show_viewport": rig not in disabled})()
            for rig in skinned_to
        ]


class TestBoundArmatures:
    def test_a_visible_mesh_pulls_in_the_hidden_rig_it_is_skinned_to(self):
        # Full-scene scope: hiding the rig while modelling must not export the mesh unskinned.
        rig = FakeArmature("Armature")
        visible = [FakeMesh("Jacket", skinned_to=[rig]), FakeMesh("Prop")]
        assert bridge_utils.missing_bound_armatures(visible) == {rig}

    def test_parenting_counts_too(self):
        rig = FakeArmature("Armature")
        assert bridge_utils.missing_bound_armatures([FakeMesh("Hat", parent=rig)]) == {rig}

    def test_unbound_meshes_pull_in_nothing(self):
        assert bridge_utils.missing_bound_armatures([FakeMesh("Rock"), FakeArmature("Other")]) == set()

    def test_a_mesh_with_its_rig_in_scope_leaves_hidden_stale_rigs_out(self):
        # After retargeting, a stale modifier to a hidden mocap rig must not be dragged in.
        rig, mocap = FakeArmature("Armature"), FakeArmature("Mocap")
        visible = [FakeMesh("Jacket", skinned_to=[rig, mocap]), rig]
        assert bridge_utils.missing_bound_armatures(visible) == set()

    def test_disabled_modifiers_do_not_bind(self):
        rig, mocap = FakeArmature("Armature"), FakeArmature("Mocap")
        mesh = FakeMesh("Jacket", skinned_to=[rig, mocap], disabled=[mocap])
        assert bridge_utils.bound_armatures([mesh]) == {rig}
        assert bridge_utils.missing_bound_armatures([mesh]) == {rig}

    def test_a_mesh_bound_only_to_hidden_rigs_pulls_them_all_in(self):
        # Timing cannot tell the real one from a stale one; the scope check then explains.
        rig, mocap = FakeArmature("Armature"), FakeArmature("Mocap")
        assert bridge_utils.missing_bound_armatures([FakeMesh("Jacket", skinned_to=[rig, mocap])]) == {rig, mocap}


class TestRefreshScheduling:
    GRACE = 0.75

    def scheduler(self, refreshed_at=5.0):
        scheduler = bridge_utils.RefreshScheduler(self.GRACE)
        scheduler.refreshed(refreshed_at)
        return scheduler

    def test_an_edit_outside_the_grace_window_is_dirty_now(self):
        assert self.scheduler().change(10.0) == 10.0

    def test_the_first_edit_inside_the_window_is_deferred_to_its_end(self):
        assert self.scheduler().change(5.2) == 5.75

    def test_later_edits_inside_the_window_share_the_deferral(self):
        scheduler = self.scheduler()
        assert scheduler.change(5.2) == 5.75
        assert scheduler.change(5.3) is None

    def test_an_edit_right_after_a_deferred_refresh_is_kept(self):
        # Refresh at 5.0, a change at 5.2 is deferred to 5.75, the timer refreshes at ~6.25,
        # and an edit at 6.55 must not be dropped.
        scheduler = self.scheduler()
        assert scheduler.change(5.2) == 5.75
        scheduler.refreshed(6.25)
        assert scheduler.change(6.55) == 7.0

    def test_side_effects_cannot_chain_refreshes_forever(self):
        # A side effect that survives the depsgraph flush lands after every refresh.
        scheduler = self.scheduler(0.0)
        now = 0.0
        refreshes = 0
        for _ in range(10):
            dirty_at = scheduler.change(now + 0.3)
            if dirty_at is None:
                break
            now = dirty_at + 0.5
            scheduler.refreshed(now)
            refreshes += 1
        assert refreshes == bridge_utils.RefreshScheduler.MAX_CHAINED_DEFERRALS

    def test_a_fresh_edit_resets_the_chain(self):
        scheduler = self.scheduler(0.0)
        now = 0.0
        for _ in range(bridge_utils.RefreshScheduler.MAX_CHAINED_DEFERRALS):
            now = scheduler.change(now + 0.3) + 0.5
            scheduler.refreshed(now)
        assert scheduler.change(now + 0.3) is None
        later = now + 10.0
        assert scheduler.change(later) == later
        scheduler.refreshed(later + 0.5)
        assert scheduler.change(later + 0.8) == later + 0.5 + self.GRACE

    def test_a_refresh_from_a_save_does_not_count_as_chained(self):
        scheduler = self.scheduler(0.0)
        scheduler.refreshed(3.0)
        scheduler.refreshed(6.0)
        assert scheduler.chained == 0

    def test_refresh_flushes_the_depsgraph_while_muted(self):
        live_src = read_source(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        flush = live_src.index("view_layer.update()")
        assert flush < live_src.index("_session.exporting = False\n        _session.scheduler.refreshed")

    def test_latency_constants(self):
        live_src = read_source(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        assert "DEBOUNCE_SECONDS = 0.5" in live_src
        assert "_TIMER_INTERVAL = 0.2" in live_src


class TestEmoteExportErrors:
    def test_a_passing_emote_has_no_error(self):
        assert bridge_utils.emote_validation_error([], ["soft"], strict=False) is None
        assert bridge_utils.emote_validation_error([], [], strict=True) is None

    def test_errors_are_listed_one_per_line_after_a_headline(self):
        error = bridge_utils.emote_validation_error(
            [
                "Scene framerate is 24fps; Decentraland emotes must be 30fps.",
                "End frame must be greater than start frame.",
            ],
            ["a warning that does not block"],
            strict=False,
        )
        headline, details = bridge_utils.report_lines(error)
        assert "2 validation errors" in headline
        assert details == [
            "Scene framerate is 24fps; Decentraland emotes must be 30fps.",
            "End frame must be greater than start frame.",
        ]

    def test_a_single_error_is_not_pluralised(self):
        error = bridge_utils.emote_validation_error(["only one"], [], strict=False)
        assert "1 validation error —" in error

    def test_strict_mode_blocks_on_warnings_and_says_how_to_get_out(self):
        error = bridge_utils.emote_validation_error(
            [], ["Missing first/last-frame keys on 3 bone channels."], strict=True
        )
        headline, details = bridge_utils.report_lines(error)
        assert "Strict Validation" in headline
        assert details == ["Missing first/last-frame keys on 3 bone channels."]

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("Error: No armature found for export.", "Import DCL Rig"),
            ("Error: Cannot export, not in the current view layer: Prop, Prop_Mesh", "Prop, Prop_Mesh"),
            ("Error: Export failed: ValueError('boom')", "glTF exporter failed: ValueError('boom')"),
            ("Error: Cannot export: emote validation has blocking errors.", "Validate Emote"),
            ("Error: Strict mode enabled: resolve validation warnings before export.", "Validate Emote"),
            ("", "cancelled"),
        ],
    )
    def test_operator_failures_are_rewritten_for_the_user(self, raw, expected):
        message = bridge_utils.emote_export_error(raw)
        assert expected in message
        assert not message.startswith("Error:")

    def test_validation_failures_are_recognised_so_they_can_be_expanded(self):
        assert bridge_utils.is_emote_validation_failure("Error: Cannot export: emote validation has blocking errors.")
        assert bridge_utils.is_emote_validation_failure(
            "Strict mode enabled: resolve validation warnings before export."
        )
        assert not bridge_utils.is_emote_validation_failure("Error: No armature found for export.")

    def test_the_live_preview_never_leaks_the_operator_traceback(self):
        live_src = read_source(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        assert "except RuntimeError as exc:" in live_src
        assert "_emote_export_failure(str(exc))" in live_src
        assert "run_emote_validation(bpy.context)" in live_src
