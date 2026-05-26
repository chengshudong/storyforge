from __future__ import annotations

import pytest

from prompts.voice import (
    EmotionLLMPrompt,
    EmotionResolver,
    ReferenceTextPrompt,
    VoiceProfileMapper,
)


class TestReferenceTextPrompt:
    def test_standard_profile(self):
        prompt = ReferenceTextPrompt()
        voice_profile = {
            "pitch": "medium-low",
            "accent": "Victorian English",
            "tone_quality": "authoritative",
            "speech_patterns": ["pause before responding"],
        }
        result = prompt.render("Captain Alistair", voice_profile)
        assert "Captain Alistair" in result
        assert "medium-low-pitched" in result
        assert "authoritative" in result
        assert "Victorian English" in result
        assert "pause before responding" in result

    def test_minimal_profile(self):
        prompt = ReferenceTextPrompt()
        result = prompt.render("Jane", {})
        assert "Jane" in result
        assert "medium-pitched" in result
        assert "clear" in result
        assert "neutral" in result

    def test_empty_patterns_list(self):
        prompt = ReferenceTextPrompt()
        voice_profile = {"pitch": "high", "speech_patterns": []}
        result = prompt.render("Test", voice_profile)
        assert "pleasure to make your acquaintance" in result


class TestEmotionResolver:
    def test_happy(self):
        tag, vector = EmotionResolver.map("happy")
        assert tag == "happy"
        assert vector["pitch"] == 1.15

    def test_sad(self):
        tag, vector = EmotionResolver.map("sad")
        assert tag == "sad"
        assert vector["pitch"] == 0.85

    def test_angry_variants(self):
        for e in ("angry", "furious", "enraged"):
            tag, _ = EmotionResolver.map(e)
            assert tag == "angry"

    def test_neutral(self):
        tag, vector = EmotionResolver.map("neutral")
        assert tag == "neutral"
        assert vector["pitch"] == 1.0

    def test_case_insensitive(self):
        tag, _ = EmotionResolver.map("HAPPY")
        assert tag == "happy"

    def test_with_punctuation(self):
        tag, _ = EmotionResolver.map("angry!")
        assert tag == "angry"

    def test_unknown_emotion(self):
        tag, vector = EmotionResolver.map("bittersweet nostalgia")
        assert tag is None
        assert vector is None

    def test_empty_emotion_defaults_to_neutral(self):
        tag, vector = EmotionResolver.map("")
        assert tag == "neutral"

    def test_none_emotion_defaults_to_neutral(self):
        tag, vector = EmotionResolver.map(None)
        assert tag == "neutral"

    def test_needs_llm(self):
        assert EmotionResolver.needs_llm("happy") is False
        assert EmotionResolver.needs_llm("complex mixed emotion") is True

    def test_stoic_maps_to_neutral(self):
        tag, vector = EmotionResolver.map("stoic")
        assert tag == "neutral"

    def test_all_mapped_emotions_have_valid_tags(self):
        valid = {"happy", "sad", "angry", "soothing", "mysterious", "determined", "neutral"}
        for emotion in EmotionResolver.EMOTION_MAP:
            tag, _ = EmotionResolver.map(emotion)
            assert tag in valid, f"{emotion} -> {tag}"


class TestVoiceProfileMapper:
    def test_map_speed_medium(self):
        speed = VoiceProfileMapper.map_speed({"pitch": "medium", "tempo": "measured"})
        assert speed == 1.0

    def test_map_speed_high_fast(self):
        speed = VoiceProfileMapper.map_speed({"pitch": "high", "tempo": "fast"})
        assert speed == pytest.approx(1.2 * 1.15)

    def test_map_speed_low_slow(self):
        speed = VoiceProfileMapper.map_speed({"pitch": "low", "tempo": "slow"})
        assert speed == pytest.approx(0.8 * 0.9)

    def test_map_pitch_offset_high(self):
        offset = VoiceProfileMapper.map_pitch_offset({"pitch": "high", "tone_quality": "clear"})
        assert offset > 0

    def test_map_pitch_offset_low(self):
        offset = VoiceProfileMapper.map_pitch_offset({"pitch": "low", "tone_quality": "clear"})
        assert offset < 0

    def test_map_timbre_warm(self):
        timbre = VoiceProfileMapper.map_timbre({"tone_quality": "warm"})
        assert timbre == 0.7

    def test_map_timbre_unknown_defaults_to_clear(self):
        timbre = VoiceProfileMapper.map_timbre({})
        assert timbre == 0.5

    def test_apply_character_baseline_stoic(self):
        vector = {"pitch": 1.0, "rhythm": 1.0, "timbre": 0.5}
        voice_profile = {"tone_quality": "warm"}
        emotion_range = {"dominant": "stoic determination"}
        result = VoiceProfileMapper.apply_character_baseline(vector, voice_profile, emotion_range)
        assert result["rhythm"] < 1.0
        assert result["timbre"] == 0.7

    def test_apply_character_baseline_no_range(self):
        vector = {"pitch": 1.0, "rhythm": 1.0, "timbre": 0.5}
        voice_profile = {"tone_quality": "smooth"}
        result = VoiceProfileMapper.apply_character_baseline(vector, voice_profile, None)
        assert result["timbre"] == 0.5


class TestEmotionLLMPrompt:
    def test_render(self):
        prompt = EmotionLLMPrompt()
        result = prompt.render("Alistair", "stoic", "seething rage barely contained")
        assert "Alistair" in result["user"]
        assert "stoic" in result["user"]
        assert "seething rage barely contained" in result["user"]
        assert "happy" in result["system"]
