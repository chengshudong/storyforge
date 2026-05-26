from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Any

from prompts.scene import (
    SceneSplitPrompt,
    SceneStoryboardPrompt,
    SceneValidatePrompt,
    SceneEditPrompt,
)
from services.cache_service import CacheService
from services.cost_logger import CostLogger
from services.model_router.router import ModelRouter

logger = logging.getLogger(__name__)


class SceneAgent:
    """Converts episode data into full scene storyboards.

    All LLM calls route through ModelRouter — no direct SDK usage.
    """

    def __init__(
        self,
        router: ModelRouter,
        cache: CacheService,
    ) -> None:
        self._router = router
        self._cache = cache

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

    async def _split_episode(
        self,
        project_id: str,
        episode: dict,
        characters: list[dict],
        timeline: list[dict],
    ) -> list[dict]:
        """Split episode summary into scene beat boundaries."""
        content = f"{episode.get('title','')}{episode.get('summary','')}"
        content_hash = CacheService.hash_content(content)
        cache_key = self._cache.build_key("scene_split", episode.get("id", project_id), content_hash)

        cached = await self._cache.get(cache_key)
        if cached:
            logger.info("cache hit for scene split")
            return cached["scenes"]

        characters_str = json.dumps(
            [{"name": c.get("name", ""), "role": c.get("role", ""),
              "traits": c.get("traits", [])} for c in characters],
            ensure_ascii=False,
        )
        timeline_str = json.dumps(timeline, ensure_ascii=False) if timeline else "[]"

        prompt = SceneSplitPrompt().render(
            title=episode.get("title", ""),
            summary=episode.get("summary", ""),
            key_scenes=episode.get("key_scenes", []),
            characters=characters_str,
            timeline=timeline_str,
        )

        text, meta = await self._call_llm(
            task="scene",
            system_prompt=prompt["system"],
            user_prompt=prompt["user"],
            project_id=project_id,
        )

        result = self._parse_json(text, {"scenes": []})
        scenes = result.get("scenes", [])
        await self._cache.set(cache_key, {"scenes": scenes, "_meta": meta}, ttl=86400)
        return scenes

    async def _storyboard_scene(
        self,
        project_id: str,
        scene_beat: dict,
        episode_summary: str,
        world_setting: dict,
        previous_scene: str,
        next_scene: str,
    ) -> dict:
        """Generate full storyboard for a single scene beat."""
        content_hash = CacheService.hash_content(
            f"{episode_summary}{scene_beat.get('scene_beat','')}{scene_beat.get('scene_number',0)}"
        )
        cache_key = self._cache.build_key("scene", project_id, content_hash)

        cached = await self._cache.get(cache_key)
        if cached:
            logger.info("cache hit for scene %d", scene_beat.get("scene_number", 0))
            return cached

        world_str = json.dumps(world_setting, ensure_ascii=False) if world_setting else "{}"
        prompt = SceneStoryboardPrompt().render(
            episode_summary=episode_summary,
            world_setting=world_str,
            scene_beat=scene_beat.get("scene_beat", ""),
            characters_present=json.dumps(scene_beat.get("characters_present", [])),
            previous_scene=previous_scene,
            next_scene=next_scene,
        )

        text, meta = await self._call_llm(
            task="scene",
            system_prompt=prompt["system"],
            user_prompt=prompt["user"],
            project_id=project_id,
        )

        result = self._parse_json(text, {
            "scene_title": scene_beat.get("scene_title", ""),
            "description": scene_beat.get("scene_beat", ""),
            "camera": "medium shot",
            "emotion": "neutral",
            "location": "",
            "dialogue": [],
            "props": [],
            "transition": "cut",
            "character_actions": {},
            "asset_refs": [],
        })
        result["scene_number"] = scene_beat.get("scene_number", 0)
        result["estimated_duration"] = scene_beat.get("estimated_duration", 30)
        result["characters_present"] = scene_beat.get("characters_present", [])
        result["_meta"] = meta
        await self._cache.set(cache_key, result, ttl=3600)
        return result

    async def _validate_continuity(
        self,
        project_id: str,
        scenes: list[dict],
    ) -> dict:
        """Validate scene continuity across the episode."""
        content_hash = CacheService.hash_content(json.dumps(scenes, ensure_ascii=False))
        cache_key = self._cache.build_key("scene_validate", project_id, content_hash)

        cached = await self._cache.get(cache_key)
        if cached:
            return cached

        scenes_json = json.dumps(
            [{"scene_number": s.get("scene_number"), "scene_title": s.get("scene_title"),
              "location": s.get("location"), "emotion": s.get("emotion"),
              "characters_present": s.get("characters_present"),
              "props": s.get("props"), "transition": s.get("transition")} for s in scenes],
            ensure_ascii=False,
        )
        prompt = SceneValidatePrompt().render(scenes_json)
        text, meta = await self._call_llm(
            task="scene",
            system_prompt=prompt["system"],
            user_prompt=prompt["user"],
            project_id=project_id,
        )

        result = self._parse_json(text, {"valid": True, "issues": []})
        result["_meta"] = meta
        await self._cache.set(cache_key, result, ttl=86400)
        return result

    async def storyboard(
        self,
        project_id: str,
        episode: dict,
        characters: list[dict],
        timeline: list[dict] | None = None,
        world_setting: dict | None = None,
        previous_scenes: list[dict] | None = None,
    ) -> list[dict]:
        """Full pipeline: split → storyboard each scene → validate.

        Returns list of scene dicts with full storyboard data.
        """
        # Step 1: Split episode into scene beats
        scene_beats = await self._split_episode(
            project_id, episode, characters, timeline or [],
        )

        if not scene_beats:
            return []

        episode_summary = episode.get("summary", "")
        world = world_setting or {}
        prev_scenes = previous_scenes or []

        # Build previous/next context for each scene
        semaphore = asyncio.Semaphore(3)

        async def _storyboard_one(idx: int) -> dict:
            beat = scene_beats[idx]
            prev_summary = ""
            if idx > 0:
                prev_summary = scene_beats[idx - 1].get("scene_beat", "")
            elif prev_scenes:
                prev_summary = prev_scenes[-1].get("description", "")

            next_beat = ""
            if idx + 1 < len(scene_beats):
                next_beat = scene_beats[idx + 1].get("scene_beat", "")

            async with semaphore:
                return await self._storyboard_scene(
                    project_id, beat, episode_summary, world,
                    prev_summary, next_beat,
                )

        scenes = await asyncio.gather(*[_storyboard_one(i) for i in range(len(scene_beats))])

        # Step 3: Validate continuity
        validation = await self._validate_continuity(project_id, scenes)
        if not validation.get("valid", True):
            issues = validation.get("issues", [])
            logger.warning("continuity validation found %d issues for episode %s",
                           len(issues), episode.get("id", "unknown"))
            for issue in issues:
                logger.warning("  scenes %s: %s", issue.get("scene_pair", []), issue.get("problem", ""))

        return list(scenes)

    async def regenerate_scene(
        self,
        project_id: str,
        scene: dict,
        adjacent: list[dict],
        feedback: str,
    ) -> dict:
        """Regenerate a single scene based on director feedback."""
        prompt = SceneEditPrompt().render(
            current_scene=json.dumps(scene, ensure_ascii=False),
            adjacent=json.dumps(adjacent, ensure_ascii=False),
            feedback=feedback,
        )

        text, meta = await self._call_llm(
            task="scene",
            system_prompt=prompt["system"],
            user_prompt=prompt["user"],
            project_id=project_id,
        )

        result = self._parse_json(text, scene)
        result["scene_number"] = scene.get("scene_number")
        result["estimated_duration"] = scene.get("estimated_duration", 30)
        result["characters_present"] = scene.get("characters_present", [])
        result["_meta"] = meta
        return result

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
        logger.warning("failed to parse JSON from scene response: %.200s...", text)
        return default
