from __future__ import annotations


class SceneVideoPrompt:
    """Deterministic prompt builder for I2V generation.

    The IMAGE provides character identity via the keyframe.
    The prompt describes the MOTION and SCENE CONTEXT — character action,
    camera movement, and emotional atmosphere for the video model.
    """

    negative: str = (
        "low quality, blurry, distorted, bad anatomy, extra limbs, "
        "morphing, warping, flickering, jitter, jump cut, static noise, "
        "watermark, text, subtitles, nsfw, nude, naked, "
        "multiple faces, face morphing, inconsistent face"
    )

    def render(
        self,
        name: str,
        profile: dict | None = None,
        storyboard: dict | None = None,
    ) -> dict:
        storyboard = storyboard or {}

        camera = storyboard.get("camera", {}) or {}
        shot_type = camera.get("shot_type", "medium shot")
        angle = camera.get("angle", "eye level")
        movement = camera.get("movement", "static")

        emotion = storyboard.get("emotion", "neutral")
        location = storyboard.get("location", "cinematic setting")
        character_actions = storyboard.get("character_actions", {}) or {}
        action = character_actions.get(name, "")

        action_fragment = f", {action}" if action else ""
        movement_fragment = f", {movement} camera movement" if movement not in ("static", "still", "none", "") else ""

        positive = (
            f"masterpiece, best quality, highly detailed, "
            f"cinematic video of {name}, "
            f"{shot_type}, {angle} angle{action_fragment}, "
            f"{emotion} expression, "
            f"in {location}"
            f"{movement_fragment}, "
            f"cinematic lighting, smooth motion, consistent face, "
            f"film grain, 24fps, photorealistic, high quality video"
        )
        return {"positive": positive, "negative": self.negative}


class SceneContextPrompt:
    """Optional LLM-enhanced prompt for complex action sequences.

    Only used when ModelRouter is available AND storyboard complexity
    exceeds a threshold. Deterministic fallback provided via SceneVideoPrompt.
    """

    negative: str = SceneVideoPrompt.negative

    @staticmethod
    def render_deterministic(
        storyboard: dict,
        character_names: list[str],
    ) -> dict:
        camera = storyboard.get("camera", {}) or {}
        emotion = storyboard.get("emotion", "neutral")
        location = storyboard.get("location", "")

        positive = (
            f"cinematic video, {camera.get('shot_type', 'medium shot')}, "
            f"{', '.join(character_names)} in {location}, "
            f"{emotion} atmosphere, "
            f"smooth camera {camera.get('movement', 'static')}"
        )
        return {"positive": positive, "negative": SceneContextPrompt.negative}
