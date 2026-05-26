from __future__ import annotations

import json
import logging
import re
import uuid
from typing import Any

from prompts.episode import EpisodePlanPrompt, EpisodeRegeneratePrompt
from services.cache_service import CacheService
from services.cost_logger import CostLogger
from services.model_router.router import ModelRouter

logger = logging.getLogger(__name__)


class EpisodeAgent:
    """Converts story summary + timeline into episode breakdown.

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
        provider_override: str | None = None,
    ) -> tuple[str, dict]:
        request_id = str(uuid.uuid4())
        full_prompt = f"{system_prompt}\n\n{user_prompt}"
        response = await self._router.generate(
            task=task,
            prompt=full_prompt,
            project_id=project_id,
            provider_override=provider_override,
        )
        CostLogger.from_response(request_id, project_id, task, response)
        return response.text, {
            "provider": response.provider,
            "model": response.model,
            "tokens_input": response.tokens_input,
            "tokens_output": response.tokens_output,
            "duration_ms": response.duration_ms,
        }

    async def plan(
        self,
        project_id: str,
        story_summary: str,
        timeline: list[dict],
        chapter_count: int,
    ) -> list[dict]:
        """Generate episode plan covering all chapters.

        Returns list of episode dicts with: episode_number, title, summary,
        chapter_range, cliffhanger, key_scenes.
        """
        content_hash = CacheService.hash_content(f"{story_summary}{chapter_count}")
        cache_key = self._cache.build_key("episode_plan", project_id, content_hash)

        cached = await self._cache.get(cache_key)
        if cached:
            logger.info("cache hit for episode plan")
            return cached["episodes"]

        timeline_str = json.dumps(timeline, ensure_ascii=False)
        prompt = EpisodePlanPrompt().render(story_summary, timeline_str, chapter_count)
        text, meta = await self._call_llm(
            task="episode",
            system_prompt=prompt["system"],
            user_prompt=prompt["user"],
            project_id=project_id,
        )

        episodes = self._parse_episodes(text, chapter_count)

        # Validate: every chapter covered exactly once
        covered: set[int] = set()
        for ep in episodes:
            start, end = ep.get("chapter_range", [1, 1])
            for ch in range(start, end + 1):
                covered.add(ch)
        expected = set(range(1, chapter_count + 1))
        if covered != expected:
            missing = expected - covered
            extra = covered - expected
            logger.warning(
                "episode plan validation: missing chapters=%s, extra chapters=%s",
                sorted(missing), sorted(extra),
            )

        await self._cache.set(cache_key, {"episodes": episodes}, ttl=86400)
        return episodes

    async def regenerate_episode(
        self,
        project_id: str,
        episode: dict,
        adjacent_episodes: list[dict],
        feedback: str,
    ) -> dict:
        """Regenerate a single episode based on human feedback."""
        adjacent_str = json.dumps(adjacent_episodes, ensure_ascii=False)
        prompt = EpisodeRegeneratePrompt().render(episode, adjacent_str, feedback)
        text, meta = await self._call_llm(
            task="episode",
            system_prompt=prompt["system"],
            user_prompt=prompt["user"],
            project_id=project_id,
        )

        result = self._parse_json(text)
        result["episode_number"] = episode.get("episode_number")
        result["chapter_range"] = episode.get("chapter_range")
        result["_meta"] = meta
        return result

    @staticmethod
    def _parse_episodes(text: str, chapter_count: int) -> list[dict]:
        """Parse LLM response into episode list."""
        parsed = EpisodeAgent._parse_json(text)
        episodes = parsed.get("episodes", [])
        if not episodes:
            # Fallback: single episode covering everything
            return [{
                "episode_number": 1,
                "title": "Full Story",
                "summary": text[:500],
                "chapter_range": [1, chapter_count],
                "cliffhanger": None,
                "key_scenes": [],
            }]
        return episodes

    @staticmethod
    def _parse_json(text: str) -> dict:
        """Extract JSON from LLM response text."""
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
        logger.warning("failed to parse JSON from episode response: %.200s...", text)
        return {}
