from __future__ import annotations

import pytest

from interfaces.video import VideoSubmitRequest
from services.video_renderer import SceneRenderer


class TestSceneRendererBuildPayload:
    def test_basic_payload_construction(self):
        scene = {"id": "abc", "title": "Test Scene"}
        storyboard = {
            "camera": {
                "shot_type": "medium shot",
                "angle": "eye level",
                "movement": "pan",
            },
            "emotion": "happy",
            "location": "meadow",
            "duration_estimate": 3.0,
        }
        req = SceneRenderer.build_payload(
            scene=scene,
            storyboard=storyboard,
            character_image=b"\x89PNG keyframe",
            character_name="Alice",
            seed=42,
        )
        assert isinstance(req, VideoSubmitRequest)
        assert "Alice" in req.prompt
        assert "meadow" in req.prompt
        assert req.seed == 42
        assert req.fps == 24
        assert req.image == b"\x89PNG keyframe"
        assert req.image_filename == "Alice_keyframe.png"

    def test_duration_to_frames_calculation(self):
        storyboard = {"duration_estimate": 5.0}
        req = SceneRenderer.build_payload(
            scene={}, storyboard=storyboard,
            character_image=None, character_name="X", seed=0,
        )
        assert req.num_frames == 120  # 5 * 24

    def test_short_duration_minimum_one_frame(self):
        storyboard = {"duration_estimate": 0.01}
        req = SceneRenderer.build_payload(
            scene={}, storyboard=storyboard,
            character_image=None, character_name="X", seed=0,
        )
        assert req.num_frames == 1

    def test_default_duration_when_missing(self):
        storyboard = {}
        req = SceneRenderer.build_payload(
            scene={}, storyboard=storyboard,
            character_image=None, character_name="X", seed=0,
        )
        assert req.num_frames == 120  # 5 * 24 default

    def test_none_storyboard_safe(self):
        req = SceneRenderer.build_payload(
            scene={}, storyboard=None,
            character_image=None, character_name="Safe", seed=0,
        )
        assert "Safe" in req.prompt
        assert req.fps == 24


class TestMovementMapping:
    def test_static_movement(self):
        assert SceneRenderer._map_movement_to_motion("static") == 20
        assert SceneRenderer._map_movement_to_motion("still") == 20
        assert SceneRenderer._map_movement_to_motion("") == 20

    def test_slow_movement(self):
        assert SceneRenderer._map_movement_to_motion("slow_pan") == 80
        assert SceneRenderer._map_movement_to_motion("subtle") == 80
        assert SceneRenderer._map_movement_to_motion("gentle") == 80

    def test_normal_movement(self):
        assert SceneRenderer._map_movement_to_motion("pan") == 127
        assert SceneRenderer._map_movement_to_motion("tilt") == 127
        assert SceneRenderer._map_movement_to_motion("dolly") == 127
        assert SceneRenderer._map_movement_to_motion("track") == 127

    def test_fast_movement(self):
        assert SceneRenderer._map_movement_to_motion("fast_pan") == 180
        assert SceneRenderer._map_movement_to_motion("tracking") == 180
        assert SceneRenderer._map_movement_to_motion("dynamic") == 180

    def test_action_movement(self):
        assert SceneRenderer._map_movement_to_motion("action") == 220
        assert SceneRenderer._map_movement_to_motion("shake") == 220
        assert SceneRenderer._map_movement_to_motion("handheld") == 220

    def test_unknown_movement_defaults_to_127(self):
        assert SceneRenderer._map_movement_to_motion("spiral_crazy") == 127
        assert SceneRenderer._map_movement_to_motion("whatever") == 127

    def test_case_insensitive(self):
        assert SceneRenderer._map_movement_to_motion("PAN") == 127
        assert SceneRenderer._map_movement_to_motion("Fast_Pan") == 180
