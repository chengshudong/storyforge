from __future__ import annotations

from interfaces.video import VideoSubmitRequest
from prompts.video import SceneVideoPrompt


class SceneRenderer:
    """Constructs Wan2.1 / CogVideoX payloads from scene + assets + voice data.

    Analogous to InstantIDWorkflow in image/comfyui_adapter.py — builds
    the payload that gets submitted to the video provider. The keyframe
    image is the composite input for I2V generation.

    Deterministic — NO LLM calls. All prompt text is constructed from
    structured storyboard + character profile data using SceneVideoPrompt.
    """

    @staticmethod
    def build_payload(
        scene: dict,
        storyboard: dict,
        character_image: bytes | None,
        character_name: str,
        character_profile: dict | None = None,
        seed: int = 0,
        cfg: float = 7.5,
        width: int = 768,
        height: int = 1152,
    ) -> VideoSubmitRequest:
        storyboard = storyboard or {}

        renderer = SceneVideoPrompt()
        prompt = renderer.render(
            name=character_name,
            profile=character_profile,
            storyboard=storyboard,
        )

        duration_s = storyboard.get("duration_estimate", 5.0)
        fps = 24
        num_frames = max(1, int(float(duration_s) * fps))

        camera = storyboard.get("camera", {}) or {}
        movement = camera.get("movement", "static")
        motion_id = SceneRenderer._map_movement_to_motion(movement)

        return VideoSubmitRequest(
            prompt=prompt["positive"],
            negative_prompt=prompt["negative"],
            seed=seed,
            fps=fps,
            num_frames=num_frames,
            guidance_scale=cfg,
            width=width,
            height=height,
            image=character_image,
            image_filename=f"{character_name}_keyframe.png",
            motion_bucket_id=motion_id,
        )

    @staticmethod
    def _map_movement_to_motion(movement: str) -> int:
        movement_lower = movement.strip().lower()
        if movement_lower in ("static", "still", "none", ""):
            return 20
        if movement_lower in ("slow_pan", "subtle", "gentle", "slow zoom", "creep"):
            return 80
        if movement_lower in ("pan", "tilt", "dolly", "zoom", "track"):
            return 127
        if movement_lower in ("fast_pan", "tracking", "dynamic", "whip"):
            return 180
        if movement_lower in ("action", "shake", "handheld", "chaotic"):
            return 220
        return 127
