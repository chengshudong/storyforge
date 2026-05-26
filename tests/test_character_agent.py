import asyncio
import json

import pytest

from agents.character_agent import CharacterAgent
from services.model_router.router import ModelRouter


class MockLLMAdapter:
    def __init__(self, responses: list[str] | None = None):
        self.responses = responses or []
        self.calls: list[dict] = []

    async def generate(self, prompt, model, **kwargs):
        self.calls.append({"prompt": prompt, "model": model})
        text = self.responses.pop(0) if self.responses else "{}"
        from interfaces.llm import ModelResponse
        return ModelResponse(
            text=text, model=model, provider="mock",
            tokens_input=10, tokens_output=20, duration_ms=100,
        )

    async def stream(self, prompt, model, **kwargs):
        yield ""
    async def embedding(self, texts, model):
        return []
    async def health(self):
        return {"status": "healthy"}


class MockCacheService:
    def __init__(self):
        self.store: dict = {}

    def build_key(self, entity, project_id, content_hash):
        return f"cache:model:{entity}:{project_id}:{content_hash}"

    @staticmethod
    def hash_content(content):
        import hashlib
        return hashlib.md5(content.encode()).hexdigest()[:16]

    async def get(self, key):
        return self.store.get(key)

    async def set(self, key, value, ttl):
        self.store[key] = value

    async def invalidate_project(self, project_id):
        return 0


class MockVectorStore:
    def __init__(self):
        self.points: dict = {}

    async def upsert(self, collection, points):
        for p in points:
            self.points[p["id"]] = p
        return True

    async def query(self, collection, vector, top_k=10):
        return []

    async def delete(self, collection, point_ids):
        return True


def make_agent(responses: list[str] | None = None):
    adapter = MockLLMAdapter(responses)
    registry = {
        "tasks": {"character": {"provider": "mock", "model": "mock-model"}},
        "fallback": ["mock", "local"],
        "degrade": {"character": {"provider": "mock", "model": "local-model"}},
    }
    router = ModelRouter({"mock": adapter, "local": adapter}, registry)
    cache = MockCacheService()
    vector = MockVectorStore()
    agent = CharacterAgent(router, cache, vector)
    return agent, adapter


EXTRACT_JSON = json.dumps({
    "characters": [
        {"name": "Alice", "aliases": ["Ally"], "role": "protagonist",
         "importance": "primary", "first_appearance": "Chapter 1",
         "scene_count": 12, "relationship_to_protagonist": "self",
         "narrative_function": "Drives the story", "is_protagonist": True},
        {"name": "Bob", "aliases": [], "role": "antagonist",
         "importance": "primary", "first_appearance": "Chapter 2",
         "scene_count": 8, "relationship_to_protagonist": "rival",
         "narrative_function": "Opposes Alice", "is_protagonist": False},
    ]
})

PROFILE_JSON_1 = json.dumps({
    "appearance": {"age_estimate": "mid 20s", "height": "average", "build": "athletic",
                   "hair": "short brown", "eyes": "green", "distinguishing_features": "none",
                   "typical_expression": "determined"},
    "voice_profile": {"pitch": "medium", "tempo": "measured", "accent": "standard",
                      "tone_quality": "warm", "speech_patterns": ["speaks clearly"]},
    "personality": {"traits": ["brave", "curious", "stubborn"],
                    "motivation": "find the truth", "fears": ["failure"],
                    "quirks": ["taps fingers when thinking"],
                    "moral_alignment": "neutral good"},
    "emotion_range": {"dominant": "determined", "secondary": ["curious", "frustrated"],
                      "rarely_shows": ["fear"], "trigger_situations": ["injustice → anger"]},
    "costume_style": {"era": "modern", "style": "casual practical",
                      "signature_items": ["red scarf"], "color_palette": ["red", "blue"],
                      "notes": ""},
    "backstory": "Alice grew up in a small town.",
})

PROFILE_JSON_2 = json.dumps({
    "appearance": {"age_estimate": "late 30s", "height": "tall", "build": "stocky",
                   "hair": "dark slicked back", "eyes": "cold blue",
                   "distinguishing_features": "scar on jaw",
                   "typical_expression": "smirking"},
    "voice_profile": {"pitch": "medium-low", "tempo": "deliberate", "accent": "refined",
                      "tone_quality": "cool", "speech_patterns": ["drawls on vowels"]},
    "personality": {"traits": ["cunning", "ruthless", "charismatic"],
                    "motivation": "seize power", "fears": ["exposure"],
                    "quirks": ["adjusts cufflinks"], "moral_alignment": "lawful evil"},
    "emotion_range": {"dominant": "smug confidence", "secondary": ["cold anger"],
                      "rarely_shows": ["genuine warmth"], "trigger_situations": ["challenge → aggression"]},
    "costume_style": {"era": "modern", "style": "tailored suits",
                      "signature_items": ["silver cufflinks"], "color_palette": ["black", "grey"],
                      "notes": ""},
    "backstory": "Bob clawed his way to power.",
})

MERGE_JSON_NO = json.dumps({"is_duplicate": False, "reasoning": "different roles"})
MERGE_JSON_YES = json.dumps({"is_duplicate": True, "merged_name": "Alice",
                              "reasoning": "same character",
                              "merged_profile": {"name": "Alice", "role": "protagonist"}})

NORMALIZE_JSON = json.dumps({"characters": [], "issues": []})


# ── Extract tests ────────────────────────────────────────────────────────

def test_extract_characters():
    agent, adapter = make_agent([EXTRACT_JSON])
    chars = asyncio.run(agent.extract_characters(
        project_id="proj-1",
        chapter_summaries=[{"chapter_index": 1, "chapter_summary": "Story begins."}],
        relationships=[{"character_a": "Alice", "character_b": "Bob", "relation_type": "rivalry"}],
        entities_persons=["Alice", "Bob"],
        scene_characters=["Alice", "Bob"],
    ))
    assert len(chars) == 2
    assert chars[0]["name"] == "Alice"
    assert chars[0]["is_protagonist"] is True
    assert chars[1]["name"] == "Bob"
    assert chars[1]["role"] == "antagonist"


def test_extract_cache_hit():
    agent, adapter = make_agent([EXTRACT_JSON, EXTRACT_JSON])
    args = {
        "project_id": "proj-1",
        "chapter_summaries": [{"chapter_index": 1}],
        "relationships": [],
        "entities_persons": [],
        "scene_characters": [],
    }
    r1 = asyncio.run(agent.extract_characters(**args))
    r2 = asyncio.run(agent.extract_characters(**args))
    assert r1 == r2
    assert len(adapter.calls) == 1


def test_extract_empty():
    agent, adapter = make_agent([json.dumps({"characters": []})])
    chars = asyncio.run(agent.extract_characters(
        project_id="p", chapter_summaries=[], relationships=[],
        entities_persons=[], scene_characters=[],
    ))
    assert chars == []


# ── Profile tests ────────────────────────────────────────────────────────

def test_generate_profile():
    agent, adapter = make_agent([PROFILE_JSON_1])
    chars = [{"name": "Alice", "role": "protagonist", "importance": "primary",
              "narrative_function": "Drives story", "is_protagonist": True, "aliases": []}]
    profiles = asyncio.run(agent.generate_profiles(
        project_id="proj-1", characters=chars,
        chapter_summaries=[{"chapter_index": 1, "chapter_summary": "Alice enters."}],
        relationships=[],
        scenes=[],
        world_setting={"time_period": "modern"},
    ))
    assert len(profiles) == 1
    p = profiles[0]
    assert p["appearance"]["age_estimate"] == "mid 20s"
    assert p["personality"]["traits"] == ["brave", "curious", "stubborn"]
    assert p["voice_profile"]["pitch"] == "medium"


def test_profile_cache_hit():
    agent, adapter = make_agent([PROFILE_JSON_1, PROFILE_JSON_1])
    chars = [{"name": "Alice", "role": "protagonist", "importance": "primary",
              "narrative_function": "", "is_protagonist": True, "aliases": []}]
    args = {
        "project_id": "proj-1", "characters": chars,
        "chapter_summaries": [], "relationships": [], "scenes": [],
        "world_setting": {},
    }
    r1 = asyncio.run(agent.generate_profiles(**args))
    r2 = asyncio.run(agent.generate_profiles(**args))
    assert r1[0]["appearance"] == r2[0]["appearance"]
    assert len(adapter.calls) == 1


def test_generate_profiles_empty():
    agent, adapter = make_agent([])
    profiles = asyncio.run(agent.generate_profiles(
        project_id="p", characters=[], chapter_summaries=[],
        relationships=[], scenes=[], world_setting={},
    ))
    assert profiles == []


# ── Merge tests ──────────────────────────────────────────────────────────

def test_merge_no_duplicates():
    agent, adapter = make_agent([MERGE_JSON_NO])
    chars = [
        {"name": "Alice", "role": "protagonist", "importance": "primary"},
        {"name": "Bob", "role": "antagonist", "importance": "primary"},
    ]
    result = asyncio.run(agent.merge_duplicates("proj-1", chars))
    assert len(result) == 2


def test_merge_single_character():
    agent, adapter = make_agent([])
    chars = [{"name": "Alice", "role": "protagonist"}]
    result = asyncio.run(agent.merge_duplicates("proj-1", chars))
    assert len(result) == 1
    assert len(adapter.calls) == 0  # No LLM call needed for single character


# ── Normalize tests ──────────────────────────────────────────────────────

def test_normalize_profiles():
    agent, adapter = make_agent([json.dumps({
        "characters": [
            {"name": "Alice", "role": "protagonist", "appearance": {"age_estimate": "mid 20s"}},
            {"name": "Bob", "role": "antagonist", "appearance": {"age_estimate": "late 30s"}},
        ],
        "issues": [],
    })])
    chars = [
        {"name": "Alice", "role": "protagonist", "appearance": {"age_estimate": "mid 20s"}},
        {"name": "Bob", "role": "antagonist", "appearance": {"age_estimate": "late 30s"}},
    ]
    result = asyncio.run(agent.normalize_profiles("proj-1", chars, {}))
    assert len(result["characters"]) == 2
    assert result["issues"] == []


def test_normalize_finds_issues():
    agent, adapter = make_agent([json.dumps({
        "characters": [
            {"name": "Alice", "role": "protagonist", "appearance": {"age_estimate": "mid 20s"}},
        ],
        "issues": [{"character": "Alice", "field": "age",
                    "problem": "Age contradicts timeline"}],
    })])
    chars = [{"name": "Alice", "role": "protagonist", "appearance": {"age_estimate": "mid 20s"}}]
    result = asyncio.run(agent.normalize_profiles("proj-1", chars, {}))
    assert len(result["issues"]) == 1


def test_normalize_empty():
    agent, adapter = make_agent([])
    result = asyncio.run(agent.normalize_profiles("proj-1", [], {}))
    assert result == {"characters": [], "issues": []}


# ── Full pipeline test ───────────────────────────────────────────────────

def test_full_pipeline():
    normalize_out = json.dumps({
        "characters": [
            {"name": "Alice", "role": "protagonist",
             "appearance": {"age_estimate": "mid 20s"}, "backstory": "..."},
            {"name": "Bob", "role": "antagonist",
             "appearance": {"age_estimate": "late 30s"}, "backstory": "..."},
        ],
        "issues": [],
    })
    # Call order: extract(1), profile Alice(2), profile Bob(3),
    #   embedding Alice(4), embedding Bob(5), normalize(6)
    dummy = "{}"
    agent, adapter = make_agent([
        EXTRACT_JSON, PROFILE_JSON_1, PROFILE_JSON_2,
        dummy, dummy, normalize_out,
    ])
    result = asyncio.run(agent.build_characters(
        project_id="proj-1",
        chapter_summaries=[{"chapter_index": 1, "chapter_summary": "Story."}],
        relationships=[{"character_a": "Alice", "character_b": "Bob", "relation_type": "rivalry"}],
        entities_persons=["Alice", "Bob"],
        scene_characters=["Alice", "Bob"],
        scenes=[],
        world_setting={"time_period": "modern"},
    ))
    assert len(result["characters"]) == 2
    assert result["issues"] == []


# ── JSON parse fallback ──────────────────────────────────────────────────

def test_parse_json_fallback():
    result = CharacterAgent._parse_json('```json\n{"key": "value"}\n```', {"default": True})
    assert result == {"key": "value"}
    result2 = CharacterAgent._parse_json("not json", {"fallback": 1})
    assert result2 == {"fallback": 1}
    result3 = CharacterAgent._parse_json('{"direct": "parse"}', {})
    assert result3 == {"direct": "parse"}
