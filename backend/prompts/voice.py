from __future__ import annotations


class ReferenceTextPrompt:
    """Build reference text for voice cloning from character profile.
    Deterministic — no LLM call."""

    def render(self, name: str, voice_profile: dict | None = None) -> str:
        profile = voice_profile or {}
        pitch = profile.get("pitch", "medium")
        accent = profile.get("accent", "neutral")
        tone = profile.get("tone_quality", "clear")
        patterns = profile.get("speech_patterns", [])

        sentences = [
            f"My name is {name}.",
            f"I speak with a {pitch}-pitched, {tone} voice, carrying a {accent} accent.",
        ]
        if patterns:
            sentences.append(f"People say I tend to {patterns[0]}.")
        else:
            sentences.append("It is a pleasure to make your acquaintance.")

        return " ".join(sentences)


class EmotionResolver:
    """Map storyboard emotion to CosyVoice emotion tag + vector.
    Deterministic — no LLM call.

    Returns (emotion_tag, emotion_vector) or (None, None) if unmappable.
    """

    EMOTION_MAP: dict[str, tuple[str, dict]] = {
        "happy": ("happy", {"pitch": 1.15, "rhythm": 1.05, "timbre": 0.55}),
        "joyful": ("happy", {"pitch": 1.15, "rhythm": 1.05, "timbre": 0.55}),
        "sad": ("sad", {"pitch": 0.85, "rhythm": 0.90, "timbre": 0.40}),
        "sorrowful": ("sad", {"pitch": 0.85, "rhythm": 0.90, "timbre": 0.40}),
        "angry": ("angry", {"pitch": 1.10, "rhythm": 1.10, "timbre": 0.75}),
        "furious": ("angry", {"pitch": 1.10, "rhythm": 1.10, "timbre": 0.75}),
        "enraged": ("angry", {"pitch": 1.10, "rhythm": 1.10, "timbre": 0.75}),
        "calm": ("soothing", {"pitch": 0.95, "rhythm": 0.90, "timbre": 0.45}),
        "peaceful": ("soothing", {"pitch": 0.95, "rhythm": 0.90, "timbre": 0.45}),
        "gentle": ("soothing", {"pitch": 0.95, "rhythm": 0.90, "timbre": 0.45}),
        "mysterious": ("mysterious", {"pitch": 0.90, "rhythm": 0.85, "timbre": 0.35}),
        "eerie": ("mysterious", {"pitch": 0.90, "rhythm": 0.85, "timbre": 0.35}),
        "suspenseful": ("mysterious", {"pitch": 0.90, "rhythm": 0.85, "timbre": 0.35}),
        "determined": ("determined", {"pitch": 1.05, "rhythm": 1.00, "timbre": 0.65}),
        "resolute": ("determined", {"pitch": 1.05, "rhythm": 1.00, "timbre": 0.65}),
        "firm": ("determined", {"pitch": 1.05, "rhythm": 1.00, "timbre": 0.65}),
        "afraid": ("sad", {"pitch": 0.80, "rhythm": 1.15, "timbre": 0.30}),
        "terrified": ("sad", {"pitch": 0.80, "rhythm": 1.15, "timbre": 0.30}),
        "surprised": ("happy", {"pitch": 1.20, "rhythm": 1.20, "timbre": 0.55}),
        "shocked": ("happy", {"pitch": 1.20, "rhythm": 1.20, "timbre": 0.55}),
        "neutral": ("neutral", {"pitch": 1.00, "rhythm": 1.00, "timbre": 0.50}),
        "cold": ("angry", {"pitch": 0.90, "rhythm": 0.85, "timbre": 0.70}),
        "icy": ("angry", {"pitch": 0.90, "rhythm": 0.85, "timbre": 0.70}),
        "menacing": ("angry", {"pitch": 0.90, "rhythm": 0.85, "timbre": 0.70}),
        "warm": ("soothing", {"pitch": 1.05, "rhythm": 0.95, "timbre": 0.50}),
        "affectionate": ("soothing", {"pitch": 1.05, "rhythm": 0.95, "timbre": 0.50}),
        "loving": ("soothing", {"pitch": 1.05, "rhythm": 0.95, "timbre": 0.50}),
        "sarcastic": ("happy", {"pitch": 1.10, "rhythm": 1.15, "timbre": 0.60}),
        "mocking": ("happy", {"pitch": 1.10, "rhythm": 1.15, "timbre": 0.60}),
        "desperate": ("sad", {"pitch": 0.90, "rhythm": 1.10, "timbre": 0.45}),
        "pleading": ("sad", {"pitch": 0.90, "rhythm": 1.10, "timbre": 0.45}),
        "stoic": ("neutral", {"pitch": 0.95, "rhythm": 0.90, "timbre": 0.55}),
        "emotionless": ("neutral", {"pitch": 0.95, "rhythm": 0.90, "timbre": 0.55}),
    }

    @classmethod
    def map(cls, emotion_text: str) -> tuple[str | None, dict | None]:
        if not emotion_text:
            return "neutral", {"pitch": 1.00, "rhythm": 1.00, "timbre": 0.50}
        key = emotion_text.strip().lower().rstrip(".!?,")
        if key in cls.EMOTION_MAP:
            return cls.EMOTION_MAP[key]
        return None, None

    @classmethod
    def needs_llm(cls, emotion_text: str) -> bool:
        _, vector = cls.map(emotion_text)
        return vector is None


class VoiceProfileMapper:
    """Map character voice_profile to synthesis parameters.
    Deterministic — no LLM call."""

    PITCH_SPEED_MAP = {
        "high": 1.2, "medium-high": 1.1, "medium": 1.0,
        "medium-low": 0.9, "low": 0.8,
    }

    TEMPO_SPEED_MOD = {
        "fast": 1.15, "measured": 1.0, "slow": 0.9, "deliberate": 0.85,
    }

    TONE_TIMBRE_MAP = {
        "warm": 0.7, "cool": 0.3, "rough": 0.8, "smooth": 0.5,
        "authoritative": 0.6, "soft": 0.4, "harsh": 0.75, "clear": 0.5,
    }

    @classmethod
    def map_speed(cls, voice_profile: dict) -> float:
        pitch = voice_profile.get("pitch", "medium")
        tempo = voice_profile.get("tempo", "measured")
        base = cls.PITCH_SPEED_MAP.get(pitch, 1.0)
        mod = cls.TEMPO_SPEED_MOD.get(tempo, 1.0)
        return round(base * mod, 2)

    @classmethod
    def map_pitch_offset(cls, voice_profile: dict) -> int:
        pitch = voice_profile.get("pitch", "medium")
        tone = voice_profile.get("tone_quality", "clear")
        offset = 0
        if pitch in ("high", "medium-high"):
            offset += 2
        elif pitch in ("low", "medium-low"):
            offset -= 2
        if tone in ("rough", "harsh"):
            offset += 1
        elif tone in ("soft", "warm"):
            offset -= 1
        return max(-5, min(5, offset))

    @classmethod
    def map_timbre(cls, voice_profile: dict) -> float:
        tone = voice_profile.get("tone_quality", "clear")
        return cls.TONE_TIMBRE_MAP.get(tone, 0.5)

    @classmethod
    def apply_character_baseline(cls, emotion_vector: dict,
                                 voice_profile: dict,
                                 emotion_range: dict | None = None) -> dict:
        """Apply per-character emotion baseline offset to the emotion vector."""
        result = dict(emotion_vector)
        result["timbre"] = cls.map_timbre(voice_profile)

        if emotion_range:
            dominant = (emotion_range.get("dominant") or "").lower()
            if "stoic" in dominant:
                result["rhythm"] = max(0.7, result.get("rhythm", 1.0) - 0.05)
            elif "bright" in dominant or "cheerful" in dominant:
                result["pitch"] = min(1.3, result.get("pitch", 1.0) + 0.05)

        return result


class EmotionLLMPrompt:
    """LLM fallback for complex emotion descriptions.
    Only invoked when EmotionResolver cannot map.
    Cached per (emotion_description + character_id) — 24h TTL."""

    system: str = (
        "Map a complex emotional description to ONE of these tags: "
        "happy, sad, angry, soothing, mysterious, determined, neutral.\n\n"
        "Return valid JSON:\n"
        '{\n'
        '  "emotion": "happy|sad|angry|soothing|mysterious|determined|neutral",\n'
        '  "pitch": 0.0,\n'
        '  "rhythm": 0.0,\n'
        '  "timbre": 0.0,\n'
        '  "reasoning": "brief explanation"\n'
        '}\n\n'
        "Rules:\n"
        "- pitch: 0.7 (very low) to 1.3 (very high), 1.0 neutral\n"
        "- rhythm: 0.7 (very slow) to 1.3 (very fast), 1.0 neutral\n"
        "- timbre: 0.2 (very dark) to 0.8 (very bright), 0.5 neutral\n"
        "- Match the closest emotion tag even if imperfect.\n"
        "- Set vector values to reflect the intensity and quality described."
    )

    user_template: str = (
        "Character: {character_name}\n"
        "Character's typical emotional state: {dominant_emotion}\n"
        "Emotion to express in this line: {target_emotion}\n\n"
        "Map this to a supported emotion tag with appropriate vector values."
    )

    def render(self, character_name: str, dominant_emotion: str,
               target_emotion: str) -> dict:
        return {
            "system": self.system,
            "user": self.user_template.format(
                character_name=character_name,
                dominant_emotion=dominant_emotion or "neutral",
                target_emotion=target_emotion,
            ),
        }
