"""Tests for the Builder Live Preview bridge payload and its wiring."""

import json
import os
import sys

import pytest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_DIR = os.path.join(ROOT_DIR, "src")
sys.path.insert(0, os.path.join(SRC_DIR, "ops"))

import bridge_utils  # noqa: E402


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


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

    def test_default_is_the_production_page(self):
        assert bridge_utils.DEFAULT_PREVIEWER_URL == "https://decentraland.org/builder/live-preview"


class TestPreviewerOrigin:
    @pytest.mark.parametrize(
        "url,expected",
        [
            ("https://decentraland.org/builder/live-preview", "https://decentraland.org"),
            ("http://localhost:3000/live-preview", "http://localhost:3000"),
            ("decentraland.zone/builder/live-preview", "https://decentraland.zone"),
            ("", ""),
            (None, ""),
        ],
    )
    def test_origin_is_scheme_and_host(self, url, expected):
        assert bridge_utils.previewer_origin(url) == expected


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


class TestWiring:
    def test_server_binds_to_loopback_only(self):
        # Security tripwire: the bridge serves the local export to the browser,
        # so it must never listen on anything but loopback.
        live_src = _read(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        assert '("127.0.0.1", port)' in live_src
        assert '"0.0.0.0"' not in live_src

    def test_cors_is_scoped_to_the_previewer_origin(self):
        live_src = _read(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        assert '_server.allowed_origin or "*"' in live_src
        assert "_server.start(self.bridge_port, previewer_origin(previewer_url))" in live_src

    def test_wearable_exports_are_validated_before_running(self):
        # Both the initial export and live re-exports go through the scope
        # check, so a broken scene cancels the preview instead of streaming.
        live_src = _read(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        assert "error = wearable_export_error(scope, selected_only=selected_only)" in live_src

    def test_the_selection_is_completed_in_both_directions(self):
        # Selecting just the wearable mesh pulls in its rig, selecting just
        # the armature pulls in the wearable meshes bound to it, and the
        # borrowed selection is restored afterwards.
        live_src = _read(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        assert "_bound_armatures(selected)" in live_src
        assert "_bound_meshes(selected_armatures)" in live_src
        assert "extra.select_set(True)" in live_src
        assert "extra.select_set(False)" in live_src

    def test_selected_only_defaults_to_on(self):
        live_src = _read(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        prop = live_src.split("selected_only: bpy.props.BoolProperty(", 1)[1].split("show_advanced:", 1)[0]
        assert "default=True" in prop

    def test_previewer_url_can_be_reset_to_the_default(self):
        live_src = _read(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        assert "op.previewer_url = DEFAULT_PREVIEWER_URL" in live_src
        assert 'sub.prop(self, "reset_previewer_url"' in live_src


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

    def test_the_handler_long_polls_state(self):
        live_src = _read(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        assert 'parse_qs(query).get("since", [None])[0]' in live_src
        assert "_server.live.wait_for_change(since)" in live_src


class TestDirtyScheduling:
    GRACE = 0.75

    def test_an_edit_outside_the_grace_window_is_dirty_now(self):
        assert bridge_utils.schedule_dirty(10.0, 5.0, self.GRACE, already_deferred=True) == (10.0, False)

    def test_the_first_edit_inside_the_window_is_deferred_to_its_end(self):
        assert bridge_utils.schedule_dirty(5.2, 5.0, self.GRACE, already_deferred=False) == (5.75, True)

    def test_a_second_edit_inside_the_window_is_dropped(self):
        # The exporter's own side effects land here after a deferred refresh; without this the
        # session would re-export forever.
        assert bridge_utils.schedule_dirty(5.3, 5.0, self.GRACE, already_deferred=True) == (None, True)

    def test_refresh_flushes_the_depsgraph_while_muted(self):
        live_src = _read(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        flush = live_src.index("view_layer.update()")
        assert flush < live_src.index("_session.exporting = False\n        _session.last_refresh")

    def test_latency_constants(self):
        live_src = _read(os.path.join(SRC_DIR, "ops", "live_preview.py"))
        assert "DEBOUNCE_SECONDS = 0.5" in live_src
        assert "_TIMER_INTERVAL = 0.2" in live_src
