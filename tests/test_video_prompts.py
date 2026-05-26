from __future__ import annotations

from prompts.video import SceneVideoPrompt, SceneContextPrompt


class TestSceneVideoPrompt:
    def test_basic_render(self):
        prompt = SceneVideoPrompt()
        result = prompt.render(
            name="Alice",
            storyboard={
                "camera": {"shot_type": "close-up", "angle": "low angle", "movement": "slow_pan"},
                "emotion": "sad",
                "location": "rainy alley",
                "character_actions": {"Alice": "wiping tears"},
            },
        )
        assert "Alice" in result["positive"]
        assert "close-up" in result["positive"]
        assert "low angle" in result["positive"]
        assert "sad" in result["positive"]
        assert "rainy alley" in result["positive"]
        assert "wiping tears" in result["positive"]
        assert "slow_pan camera movement" in result["positive"]
        assert "negative" in result

    def test_static_movement_no_camera_fragment(self):
        prompt = SceneVideoPrompt()
        result = prompt.render(
            name="Bob",
            storyboard={
                "camera": {"shot_type": "wide shot", "movement": "static"},
                "emotion": "neutral",
                "location": "desert",
            },
        )
        assert "camera movement" not in result["positive"]

    def test_empty_storyboard_defaults(self):
        prompt = SceneVideoPrompt()
        result = prompt.render(name="Eve", storyboard={})
        assert "cinematic video of Eve" in result["positive"]
        assert "medium shot" in result["positive"]
        assert "eye level" in result["positive"]
        assert "neutral" in result["positive"]

    def test_no_character_actions(self):
        prompt = SceneVideoPrompt()
        result = prompt.render(
            name="Dan",
            storyboard={"emotion": "happy", "character_actions": {}},
        )
        assert "Dan" in result["positive"]

    def test_none_camera_safe(self):
        prompt = SceneVideoPrompt()
        result = prompt.render(
            name="Frank",
            storyboard={"camera": None, "emotion": "angry", "location": "castle"},
        )
        assert "medium shot" in result["positive"]
        assert "eye level" in result["positive"]

    def test_negative_prompt_content(self):
        prompt = SceneVideoPrompt()
        result = prompt.render(name="A", storyboard={})
        assert "blurry" in result["negative"]
        assert "morphing" in result["negative"]
        assert "flickering" in result["negative"]

    def test_movement_fragment_appended(self):
        prompt = SceneVideoPrompt()
        result = prompt.render(
            name="Grace",
            storyboard={"camera": {"movement": "dolly"}},
        )
        assert "dolly camera movement" in result["positive"]

    def test_complex_storyboard(self):
        prompt = SceneVideoPrompt()
        storyboard = {
            "camera": {
                "shot_type": "medium shot",
                "angle": "dutch angle",
                "movement": "handheld",
            },
            "emotion": "determined",
            "location": "burning forest",
            "character_actions": {"Luke": "drawing sword, advancing"},
        }
        result = prompt.render(name="Luke", storyboard=storyboard)
        assert "dutch angle" in result["positive"]
        assert "determined" in result["positive"]
        assert "burning forest" in result["positive"]
        assert "drawing sword" in result["positive"]


class TestSceneContextPrompt:
    def test_deterministic_fallback(self):
        storyboard = {
            "camera": {"shot_type": "wide shot", "movement": "pan"},
            "emotion": "mysterious",
            "location": "ancient tomb",
        }
        result = SceneContextPrompt.render_deterministic(
            storyboard=storyboard,
            character_names=["Jade", "Quinn"],
        )
        assert "Jade, Quinn" in result["positive"]
        assert "ancient tomb" in result["positive"]
        assert "mysterious" in result["positive"]
        assert "pan" in result["positive"]
