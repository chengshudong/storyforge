from __future__ import annotations

import pytest

from prompts.image import (
    BackgroundPrompt,
    CharacterRefPrompt,
    CharacterScenePrompt,
    CoverPrompt,
    PropPrompt,
    _build_physique,
    _build_outfit,
)


class TestBuildPhysique:
    def test_full_profile(self):
        appearance = {
            "age_estimate": "mid-30s",
            "height": "tall",
            "build": "slender",
            "hair": "sandy blonde, short",
            "eyes": "pale blue",
            "distinguishing_features": "thin scar across nose",
        }
        result = _build_physique(appearance)
        assert "mid-30s" in result
        assert "tall stature" in result
        assert "slender build" in result
        assert "sandy blonde, short hair" in result
        assert "pale blue eyes" in result
        assert "thin scar across nose" in result

    def test_empty_dict(self):
        assert _build_physique({}) == "adult person"

    def test_partial_profile(self):
        result = _build_physique({"age_estimate": "young", "build": "stocky"})
        assert "young" in result
        assert "stocky build" in result
        assert "hair" not in result


class TestBuildOutfit:
    def test_full_costume(self):
        costume = {
            "era": "Ming Dynasty",
            "style": "silk hanfu",
            "color_palette": ["crimson", "gold"],
            "signature_items": ["jade hairpin", "embroidered sash"],
            "notes": "formal court attire",
        }
        result = _build_outfit(costume)
        assert "Ming Dynasty silk hanfu" in result
        assert "crimson, gold color palette" in result
        assert "wearing jade hairpin, embroidered sash" in result
        assert "formal court attire" in result

    def test_empty_dict(self):
        assert _build_outfit({}) == "appropriate period attire"

    def test_minimal_costume(self):
        result = _build_outfit({"era": "modern"})
        assert result == "modern"


class TestCharacterRefPrompt:
    def test_full_profile(self):
        cr = CharacterRefPrompt()
        profile = {
            "appearance": {
                "age_estimate": "late 20s",
                "height": "tall",
                "build": "athletic",
                "hair": "black, shoulder-length",
                "eyes": "deep brown",
                "typical_expression": "stoic, guarded",
                "distinguishing_features": "small scar on left cheek",
            },
            "costume_style": {
                "era": "Victorian",
                "style": "military greatcoat",
                "color_palette": ["navy", "brass"],
                "signature_items": ["ornamental sword"],
                "notes": "high collar, epaulettes",
            },
        }
        result = cr.render("Captain Alistair", profile)
        assert "professional portrait photograph of Captain Alistair" in result["positive"]
        assert "stoic, guarded" in result["positive"]
        assert "Victorian military greatcoat" in result["positive"]
        assert "looking at camera" in result["positive"]
        assert "nsfw" in result["negative"]
        assert "low quality" in result["negative"]

    def test_none_profile(self):
        cr = CharacterRefPrompt()
        result = cr.render("Jane", None)
        assert "professional portrait photograph of Jane" in result["positive"]
        assert "adult person" in result["positive"]
        assert "neutral expression" in result["positive"]
        assert "appropriate period attire" in result["positive"]

    def test_empty_profile(self):
        cr = CharacterRefPrompt()
        result = cr.render("Jane", {})
        assert "Jane" in result["positive"]
        assert "chest-up portrait" in result["positive"]


class TestCharacterScenePrompt:
    def test_full_context(self):
        cs = CharacterScenePrompt()
        profile = {
            "appearance": {"age_estimate": "elderly", "build": "frail"},
            "costume_style": {"era": "ancient", "style": "robes"},
        }
        storyboard = {
            "camera": "close-up",
            "emotion": "fearful",
            "location": "dimly lit stone corridor",
            "props": ["flickering lantern"],
        }
        result = cs.render("Wise Man", profile, storyboard, action="gripping a staff")
        assert "close-up of Wise Man" in result["positive"]
        assert "fearful expression" in result["positive"]
        assert "gripping a staff" in result["positive"]
        assert "dimly lit stone corridor" in result["positive"]
        assert "cinematic lighting" in result["positive"]

    def test_minimal_inputs(self):
        cs = CharacterScenePrompt()
        result = cs.render("Jane")
        assert "medium of Jane" in result["positive"]
        assert "adult person" in result["positive"]
        assert "cinematic setting" in result["positive"]

    def test_no_action(self):
        cs = CharacterScenePrompt()
        result = cs.render("Jane", {}, {}, action="")
        assert ", in" in result["positive"]  # no stray action comma


class TestBackgroundPrompt:
    def test_full_storyboard(self):
        bg = BackgroundPrompt()
        storyboard = {
            "location": "abandoned Victorian greenhouse",
            "camera": "wide shot",
            "emotion": "eerie",
            "props": ["broken pots", "overgrown vines", "rusted watering can"],
        }
        result = bg.render(storyboard)
        assert "wide shot of abandoned Victorian greenhouse" in result["positive"]
        assert "eerie atmosphere" in result["positive"]
        assert "broken pots" in result["positive"]
        assert "people, person" in result["negative"]  # no characters allowed

    def test_none_storyboard(self):
        bg = BackgroundPrompt()
        result = bg.render(None)
        assert "wide shot of cinematic environment" in result["positive"]
        assert "neutral atmosphere" in result["positive"]

    def test_no_props(self):
        bg = BackgroundPrompt()
        result = bg.render({"location": "desert at sunset"})
        assert "desert at sunset" in result["positive"]
        assert "featuring" not in result["positive"]


class TestPropPrompt:
    def test_full(self):
        pp = PropPrompt()
        result = pp.render("Ancient Scroll", "Yellowed parchment with arcane script", "document")
        assert "isolated product shot of Yellowed parchment with arcane script" in result["positive"]
        assert "(document)" in result["positive"]
        assert "white background" in result["positive"]
        assert "logo" in result["negative"]

    def test_no_description_falls_back_to_name(self):
        pp = PropPrompt()
        result = pp.render("Ancient Scroll")
        assert "isolated product shot of Ancient Scroll" in result["positive"]

    def test_no_prop_type(self):
        pp = PropPrompt()
        result = pp.render("Crown", "Golden crown with rubies")
        assert "(document)" not in result["positive"]


class TestCoverPrompt:
    def test_full(self):
        cp = CoverPrompt()
        result = cp.render(
            "Shadows of Empire",
            description="A tale of betrayal and redemption",
            world_setting="Victorian London",
            key_characters="Captain Alistair and Lady Eleanor",
            mood="dark mysterious romantic",
        )
        assert "cinematic poster art for Shadows of Empire" in result["positive"]
        assert "A tale of betrayal and redemption" in result["positive"]
        assert "set in Victorian London" in result["positive"]
        assert "featuring Captain Alistair and Lady Eleanor" in result["positive"]
        assert "dark mysterious romantic mood" in result["positive"]

    def test_minimal(self):
        cp = CoverPrompt()
        result = cp.render("Untitled")
        assert "cinematic poster art for Untitled" in result["positive"]
        assert "epic cinematic dramatic mood" in result["positive"]
        assert "set in" not in result["positive"]
