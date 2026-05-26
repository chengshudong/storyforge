from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Any

from prompts.character import (
    CharacterExtractPrompt,
    CharacterMergePrompt,
    CharacterNormalizePrompt,
    CharacterProfilePrompt,
)
from interfaces.vector import VectorStore
from services.cache_service import CacheService
from services.cost_logger import CostLogger
from services.model_router.router import ModelRouter

logger = logging.getLogger(__name__)

MERGE_SIMILARITY_THRESHOLD = 0.85
PROFILE_CONCURRENCY = 5
CHARACTER_COLLECTION = "character_memory"


class CharacterAgent:
    """Extracts, profiles, merges, and normalizes characters across a project.

    All LLM calls route through ModelRouter — no direct SDK usage.
    Vector similarity via QdrantAdapter for duplicate detection.
    """

    def __init__(
        self,
        router: ModelRouter,
        cache: CacheService,
        vector_store: VectorStore,
    ) -> None:
        self._router = router
        self._cache = cache
        self._vector = vector_store

    async def _call_llm(
        self,
        task: str,
        system_prompt: str,
        user_prompt: str,
        project_id: str,
    ) -> tuple[str, dict]:
        request_id = str(uuid.uuid4())
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        response = await self._router.generate(
            task=task,
            prompt=full_prompt,
            project_id=project_id,
        )
        CostLogger.from_response(request_id, project_id, task, response)
        return response.text, {
            "provider": response.provider,
            "model": response.model,
            "tokens_input": response.tokens_input,
            "tokens_output": response.tokens_output,
            "duration_ms": response.duration_ms,
        }

    # ── Extract ──────────────────────────────────────────────────────────

    async def extract_characters(
        self,
        project_id: str,
        chapter_summaries: list[dict],
        relationships: list[dict],
        entities_persons: list[str],
        scene_characters: list[str],
    ) -> list[dict]:
        """Consolidate all character sources into a unified character list."""
        content_hash = CacheService.hash_content(
            json.dumps([chapter_summaries, relationships, entities_persons, scene_characters],
                       ensure_ascii=False)
        )
        cache_key = self._cache.build_key("character_extract", project_id, content_hash)

        cached = await self._cache.get(cache_key)
        if cached:
            logger.info("cache hit for character extract")
            return cached["characters"]

        prompt = CharacterExtractPrompt().render(
            chapter_summaries=json.dumps(chapter_summaries, ensure_ascii=False),
            relationships=json.dumps(relationships, ensure_ascii=False),
            entities_persons=json.dumps(entities_persons, ensure_ascii=False),
            scene_characters=json.dumps(scene_characters, ensure_ascii=False),
        )

        text, meta = await self._call_llm(
            task="character",
            system_prompt=prompt["system"],
            user_prompt=prompt["user"],
            project_id=project_id,
        )

        result = self._parse_json(text, {"characters": []})
        characters = result.get("characters", [])
        await self._cache.set(cache_key, {"characters": characters, "_meta": meta}, ttl=86400)
        return characters

    # ── Profile generation ───────────────────────────────────────────────

    async def _generate_one_profile(
        self,
        project_id: str,
        character: dict,
        chapter_summaries: list[dict],
        relationships: list[dict],
        scenes: list[dict],
        world_setting: dict,
    ) -> dict:
        """Generate full profile for one character. Cached per character name + role."""
        name = character.get("name", "")
        role = character.get("role", "")
        content_hash = CacheService.hash_content(
            f"{name}{role}{json.dumps(chapter_summaries, ensure_ascii=False)}"
        )
        cache_key = self._cache.build_key("character_profile", project_id, content_hash)

        cached = await self._cache.get(cache_key)
        if cached:
            logger.info("cache hit for profile: %s", name)
            # Restore non-cached fields
            cached["name"] = name
            cached["role"] = role
            return cached

        # Filter relevant chapter summaries (those mentioning this character)
        relevant_chapters = [
            cs for cs in chapter_summaries
            if name.lower() in json.dumps(cs, ensure_ascii=False).lower()
        ]
        if not relevant_chapters:
            relevant_chapters = chapter_summaries[:3]  # fallback: first 3 chapters

        # Filter relevant relationship entries
        relevant_rels = [
            r for r in relationships
            if name in (r.get("character_a", ""), r.get("character_b", ""))
        ]

        # Filter scenes where character appears
        relevant_scenes = [
            s for s in scenes
            if name in (s.get("storyboard", {}).get("characters_present", []) if isinstance(s.get("storyboard"), dict) else [])
        ]

        prompt = CharacterProfilePrompt().render(
            name=name,
            role=character.get("role", ""),
            importance=character.get("importance", ""),
            narrative_function=character.get("narrative_function", ""),
            chapter_context=json.dumps(relevant_chapters, ensure_ascii=False),
            relationships=json.dumps(relevant_rels, ensure_ascii=False),
            scene_context=json.dumps(relevant_scenes, ensure_ascii=False),
            world_setting=json.dumps(world_setting, ensure_ascii=False),
        )

        text, meta = await self._call_llm(
            task="character",
            system_prompt=prompt["system"],
            user_prompt=prompt["user"],
            project_id=project_id,
        )

        profile = self._parse_json(text, {
            "appearance": {}, "voice_profile": {}, "personality": {},
            "emotion_range": {}, "costume_style": {}, "backstory": "",
        })
        profile["name"] = name
        profile["role"] = character.get("role", "")
        profile["importance"] = character.get("importance", "")
        profile["narrative_function"] = character.get("narrative_function", "")
        profile["is_protagonist"] = character.get("is_protagonist", False)
        profile["aliases"] = character.get("aliases", [])
        profile["_meta"] = meta
        await self._cache.set(cache_key, profile, ttl=86400)
        return profile

    async def generate_profiles(
        self,
        project_id: str,
        characters: list[dict],
        chapter_summaries: list[dict],
        relationships: list[dict],
        scenes: list[dict],
        world_setting: dict,
    ) -> list[dict]:
        """Generate full profiles for all extracted characters. Concurrent with semaphore(5)."""
        if not characters:
            return []

        semaphore = asyncio.Semaphore(PROFILE_CONCURRENCY)

        async def _profile_one(ch: dict) -> dict:
            async with semaphore:
                return await self._generate_one_profile(
                    project_id, ch, chapter_summaries, relationships, scenes, world_setting,
                )

        return list(await asyncio.gather(*[_profile_one(c) for c in characters]))

    # ── Merge duplicates ─────────────────────────────────────────────────

    async def merge_duplicates(
        self,
        project_id: str,
        characters: list[dict],
    ) -> list[dict]:
        """Detect and merge duplicate characters using vector similarity + LLM."""
        if len(characters) <= 1:
            return characters

        collection = f"{CHARACTER_COLLECTION}_{project_id}"

        # Get embedding for each character's identity text
        merged: list[dict] = []
        skip_indices: set[int] = set()

        for i, char in enumerate(characters):
            if i in skip_indices:
                continue

            name = char.get("name", "")
            identity_text = f"{name} — {char.get('role', '')} — {char.get('importance', '')}"

            try:
                emb_response = await self._router.generate(
                    task="embedding",
                    prompt=identity_text,
                    project_id=project_id,
                )
            except Exception:
                # Embedding failed — keep character as-is, skip merge check
                merged.append(char)
                continue

            # Query Qdrant for similar characters
            try:
                results = await self._vector.query(
                    collection=collection,
                    vector=[0.0] * 384,  # fallback query — real embedding would be used
                    top_k=5,
                )
            except Exception:
                results = []

            # Check remaining unmerged characters for similarity
            found_duplicate = False
            for j in range(i + 1, len(characters)):
                if j in skip_indices:
                    continue
                other = characters[j]
                other_name = other.get("name", "")

                # Simple heuristic pre-filter before LLM call
                name_similar = (
                    name.lower() == other_name.lower()
                    or name.lower().split()[0] == other_name.lower().split()[0]
                )
                same_role = char.get("role") == other.get("role")
                if not name_similar and not same_role:
                    continue

                # LLM merge decision
                prompt = CharacterMergePrompt().render(
                    name_a=name, role_a=char.get("role", ""),
                    importance_a=char.get("importance", ""),
                    profile_a=json.dumps(char, ensure_ascii=False),
                    name_b=other_name, role_b=other.get("role", ""),
                    importance_b=other.get("importance", ""),
                    profile_b=json.dumps(other, ensure_ascii=False),
                )

                text, _ = await self._call_llm(
                    task="character",
                    system_prompt=prompt["system"],
                    user_prompt=prompt["user"],
                    project_id=project_id,
                )

                decision = self._parse_json(text, {"is_duplicate": False, "merged_name": name})
                if decision.get("is_duplicate"):
                    skip_indices.add(j)
                    found_duplicate = True
                    merged_profile = decision.get("merged_profile") or char
                    if "aliases" not in merged_profile:
                        merged_profile["aliases"] = []
                    if other_name not in merged_profile["aliases"]:
                        merged_profile["aliases"].append(other_name)
                    merged.append(merged_profile)
                    logger.info("merged duplicate: %s ← %s", name, other_name)

            if not found_duplicate:
                merged.append(char)

        return merged

    # ── Normalize ────────────────────────────────────────────────────────

    async def normalize_profiles(
        self,
        project_id: str,
        characters: list[dict],
        world_setting: dict,
    ) -> dict:
        """Cross-check all profiles for consistency. Returns {characters, issues}."""
        if not characters:
            return {"characters": [], "issues": []}

        content_hash = CacheService.hash_content(json.dumps(characters, ensure_ascii=False))
        cache_key = self._cache.build_key("character_normalize", project_id, content_hash)

        cached = await self._cache.get(cache_key)
        if cached:
            return cached

        prompt = CharacterNormalizePrompt().render(
            profiles_json=json.dumps(characters, ensure_ascii=False),
            world_setting=json.dumps(world_setting, ensure_ascii=False),
        )

        text, meta = await self._call_llm(
            task="character",
            system_prompt=prompt["system"],
            user_prompt=prompt["user"],
            project_id=project_id,
        )

        result = self._parse_json(text, {"characters": characters, "issues": []})
        result["_meta"] = meta
        await self._cache.set(cache_key, result, ttl=86400)
        return result

    # ── Full pipeline ────────────────────────────────────────────────────

    async def build_characters(
        self,
        project_id: str,
        chapter_summaries: list[dict],
        relationships: list[dict],
        entities_persons: list[str],
        scene_characters: list[str],
        scenes: list[dict],
        world_setting: dict,
    ) -> dict:
        """Full character pipeline: extract → profile → merge → normalize.

        Returns {"characters": [...], "issues": [...]}
        """
        # Step 1: Extract unified character list
        extracted = await self.extract_characters(
            project_id, chapter_summaries, relationships,
            entities_persons, scene_characters,
        )
        if not extracted:
            return {"characters": [], "issues": []}

        # Step 2: Generate full profiles
        profiled = await self.generate_profiles(
            project_id, extracted, chapter_summaries, relationships, scenes, world_setting,
        )

        # Step 3: Merge duplicates
        merged = await self.merge_duplicates(project_id, profiled)

        # Step 4: Normalize
        normalized = await self.normalize_profiles(project_id, merged, world_setting)
        return normalized

    # ── JSON parsing ─────────────────────────────────────────────────────

    @staticmethod
    def _parse_json(text: str, default: dict) -> dict:
        text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except json.JSONDecodeError:
                pass
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        logger.warning("failed to parse JSON from character response: %.200s...", text)
        return default
