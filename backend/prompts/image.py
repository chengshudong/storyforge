from __future__ import annotations


def _build_physique(appearance: dict) -> str:
    parts = []
    if appearance.get("age_estimate"):
        parts.append(appearance["age_estimate"])
    if appearance.get("height"):
        parts.append(f"{appearance['height']} stature")
    if appearance.get("build"):
        parts.append(f"{appearance['build']} build")
    if appearance.get("hair"):
        parts.append(f"{appearance['hair']} hair")
    if appearance.get("eyes"):
        parts.append(f"{appearance['eyes']} eyes")
    if appearance.get("distinguishing_features"):
        parts.append(appearance["distinguishing_features"])
    return ", ".join(parts) if parts else "adult person"


def _build_outfit(costume: dict) -> str:
    parts = []
    era = costume.get("era", "")
    style = costume.get("style", "")
    if era or style:
        parts.append(f"{era} {style}".strip())
    colors = costume.get("color_palette", [])
    if colors:
        parts.append(f"{', '.join(colors)} color palette")
    items = costume.get("signature_items", [])
    if items:
        parts.append(f"wearing {', '.join(items)}")
    notes = costume.get("notes", "")
    if notes:
        parts.append(notes)
    return ", ".join(parts) if parts else "appropriate period attire"


class CharacterRefPrompt:
    """Deterministic SDXL prompt builder for character reference portraits.

    Phase: char_ref — generates the reference portrait used as InstantID face input.
    No LLM involved; all text is constructed from structured profile data.
    """

    negative: str = (
        "low quality, blurry, distorted face, bad anatomy, extra limbs, "
        "missing limbs, floating limbs, disconnected limbs, mutation, "
        "mutated, ugly, disgusting, poorly drawn face, cloned face, "
        "double face, long neck, bad hands, signature, watermark, text, "
        "nsfw, nude, naked"
    )

    def render(self, name: str, profile: dict | None = None) -> dict:
        profile = profile or {}
        appearance = profile.get("appearance", {}) or {}
        costume = profile.get("costume_style", {}) or {}
        expression = appearance.get("typical_expression", "neutral expression")

        physique = _build_physique(appearance)
        outfit = _build_outfit(costume)

        positive = (
            f"masterpiece, best quality, highly detailed, "
            f"professional portrait photograph of {name}, "
            f"{physique}, {outfit}, "
            f"{expression}, "
            f"looking at camera, chest-up portrait, "
            f"professional studio lighting, soft diffused light, "
            f"plain gray background, "
            f"8k, high resolution, sharp focus, skin texture"
        )
        return {"positive": positive, "negative": self.negative}


class CharacterScenePrompt:
    """Deterministic SDXL prompt builder for character-in-scene images.

    Phase: char_scene — character posed in a storyboard-described scene.
    Used with InstantID IP-Adapter for face consistency. The face itself
    is driven by the reference image, so the prompt focuses on body pose,
    action, costume, and environment.
    """

    negative: str = (
        "low quality, blurry, distorted face, bad anatomy, extra limbs, "
        "missing limbs, floating limbs, disconnected limbs, mutation, "
        "mutated, ugly, disgusting, poorly drawn face, cloned face, "
        "double face, long neck, bad hands, body horror, distorted body, "
        "signature, watermark, text, nsfw, nude, naked"
    )

    def render(
        self,
        name: str,
        profile: dict | None = None,
        storyboard: dict | None = None,
        action: str = "",
    ) -> dict:
        profile = profile or {}
        storyboard = storyboard or {}
        appearance = profile.get("appearance", {}) or {}
        costume = profile.get("costume_style", {}) or {}

        physique = _build_physique(appearance)
        outfit = _build_outfit(costume)
        camera = storyboard.get("camera", "medium")
        emotion = storyboard.get("emotion", "neutral")
        location = storyboard.get("location", "cinematic setting")

        action_text = f", {action}" if action else ""
        positive = (
            f"masterpiece, best quality, highly detailed, "
            f"{camera} of {name}, "
            f"{physique}, {outfit}, "
            f"{emotion} expression{action_text}, "
            f"in {location}, "
            f"cinematic lighting, dramatic shadows, "
            f"production still, film grain, 8k"
        )
        return {"positive": positive, "negative": self.negative}


class BackgroundPrompt:
    """Deterministic SDXL prompt builder for environment backgrounds.

    Phase: bg — environment-only shots for scene settings. No characters.
    """

    negative: str = (
        "people, person, character, face, portrait, low quality, blurry, "
        "distorted, signature, watermark, text, frame, border"
    )

    def render(self, storyboard: dict | None = None) -> dict:
        storyboard = storyboard or {}
        location = storyboard.get("location", "cinematic environment")
        camera = storyboard.get("camera", "wide shot")
        emotion = storyboard.get("emotion", "neutral")
        props = storyboard.get("props", [])

        props_text = ""
        if props:
            props_text = f", featuring {', '.join(props)}"

        positive = (
            f"masterpiece, best quality, highly detailed, "
            f"{camera} of {location}, "
            f"{emotion} atmosphere{props_text}, "
            f"cinematic composition, atmospheric lighting, depth of field, "
            f"production still, film grade, 8k, photorealistic"
        )
        return {"positive": positive, "negative": self.negative}


class PropPrompt:
    """Deterministic SDXL prompt builder for individual prop/item images.

    Phase: prop — isolated object renders for key scene props.
    """

    negative: str = (
        "people, person, character, face, portrait, low quality, blurry, "
        "distorted, text, watermark, signature, label, logo, background clutter"
    )

    def render(self, name: str, description: str = "", prop_type: str = "") -> dict:
        desc = description or name
        type_hint = f" ({prop_type})" if prop_type else ""
        positive = (
            f"masterpiece, best quality, highly detailed, "
            f"isolated product shot of {desc}{type_hint}, "
            f"white background, studio lighting, "
            f"sharp focus, 8k, photorealistic, centered composition"
        )
        return {"positive": positive, "negative": self.negative}


class CoverPrompt:
    """Deterministic SDXL prompt builder for project/episode cover images.

    Phase: cover — poster-style key art for the project or episode.
    """

    negative: str = (
        "low quality, blurry, distorted, bad anatomy, signature, watermark, "
        "text, lettering, title, logo, frame, border, nsfw, nude"
    )

    def render(
        self,
        title: str,
        description: str = "",
        world_setting: str = "",
        key_characters: str = "",
        mood: str = "epic cinematic dramatic",
    ) -> dict:
        desc_part = f", {description}" if description else ""
        setting_part = f", set in {world_setting}" if world_setting else ""
        chars_part = f", featuring {key_characters}" if key_characters else ""

        positive = (
            f"masterpiece, best quality, highly detailed, "
            f"cinematic poster art for {title}{desc_part}, "
            f"{mood} mood{setting_part}{chars_part}, "
            f"dramatic composition, movie poster style, professional lighting, "
            f"8k, sharp focus, film grade color grading"
        )
        return {"positive": positive, "negative": self.negative}
