from __future__ import annotations

import asyncio
import json
import logging
import re
import uuid
from typing import Any

from interfaces.context import ContextStore
from prompts.summary import ChapterSummaryPrompt, MergeSummaryPrompt, StorySummarizePrompt
from prompts.extraction import ExtractionPrompt
from services.cache_service import CacheService
from services.cost_logger import CostLogger
from services.model_router.router import ModelRouter

logger = logging.getLogger(__name__)

CHAPTER_PATTERNS = [
    re.compile(r"第[一二三四五六七八九十百千万\d]+章"),
    re.compile(r"Chapter\s+\d+", re.IGNORECASE),
    re.compile(r"CHAPTER\s+\d+"),
    re.compile(r"^\d+[\.\、]\s*", re.MULTILINE),
]


class StoryAgent:
    """Orchestrates story-level understanding from chapter data.

    All LLM calls route through ModelRouter — no direct SDK usage.
    """

    def __init__(
        self,
        router: ModelRouter,
        cache: CacheService,
        context_store: ContextStore,
    ) -> None:
        self._router = router
        self._cache = cache
        self._context_store = context_store

    async def _call_llm(
        self,
        task: str,
        system_prompt: str,
        user_prompt: str,
        project_id: str,
        provider_override: str | None = None,
    ) -> tuple[str, dict]:
        """Route a single LLM call through ModelRouter. Returns (text, metadata)."""
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

    @staticmethod
    def _detect_chapters(chunks: list[dict]) -> list[dict]:
        """Group chunks into chapters by detecting chapter boundary patterns."""
        chapters: list[dict] = []
        current_chapter: dict | None = None

        for chunk in chunks:
            text = chunk.get("text", "")
            matched = False
            for pattern in CHAPTER_PATTERNS:
                if pattern.search(text[:200]):
                    matched = True
                    break

            if matched and current_chapter is not None:
                chapters.append(current_chapter)
                current_chapter = None

            if current_chapter is None:
                chapter_idx = len(chapters) + 1
                current_chapter = {
                    "chapter_index": chapter_idx,
                    "text_parts": [text],
                }
            else:
                current_chapter["text_parts"].append(text)

        if current_chapter is not None:
            chapters.append(current_chapter)

        # If no chapter boundaries detected, treat entire text as one chapter
        if not chapters and chunks:
            chapters = [{"chapter_index": 1, "text_parts": [c["text"] for c in chunks]}]

        return chapters

    async def _summarize_chapter(
        self,
        chapter: dict,
        project_id: str,
    ) -> dict:
        """Summarize a single chapter. Cached per chapter content hash."""
        chapter_index = chapter["chapter_index"]
        full_text = "\n\n".join(chapter["text_parts"])
        content_hash = CacheService.hash_content(full_text)
        cache_key = self._cache.build_key("chapter_summary", project_id, content_hash)

        cached = await self._cache.get(cache_key)
        if cached:
            logger.info("cache hit for chapter %d", chapter_index)
            return cached

        prompt = ChapterSummaryPrompt().render(chapter_index, full_text)
        text, meta = await self._call_llm(
            task="summary",
            system_prompt=prompt["system"],
            user_prompt=prompt["user"],
            project_id=project_id,
        )

        result = StoryAgent._parse_json_response(text, {"chapter_summary": text, "key_events": []})
        result["_meta"] = meta
        await self._cache.set(cache_key, result, ttl=0)  # permanent
        return result

    async def _merge_summaries(
        self,
        summaries: list[str],
        project_id: str,
    ) -> str:
        """Hierarchically merge chapter summaries into a story-level summary."""
        content_hash = CacheService.hash_content("".join(summaries))
        cache_key = self._cache.build_key("story_summary", project_id, content_hash)

        cached = await self._cache.get(cache_key)
        if cached:
            logger.info("cache hit for story summary")
            return cached["narrative_summary"]

        # Merge in batches of 6
        batch_size = 6
        current = summaries[:]
        while len(current) > 1:
            next_level = []
            for i in range(0, len(current), batch_size):
                batch = current[i : i + batch_size]
                if len(batch) == 1:
                    next_level.append(batch[0])
                    continue
                prompt = MergeSummaryPrompt().render("\n---\n".join(batch))
                text, _ = await self._call_llm(
                    task="summary",
                    system_prompt=prompt["system"],
                    user_prompt=prompt["user"],
                    project_id=project_id,
                )
                parsed = StoryAgent._parse_json_response(text, {"merged_summary": text})
                next_level.append(parsed.get("merged_summary", text))
            current = next_level

        result = current[0] if current else ""
        await self._cache.set(
            cache_key, {"narrative_summary": result}, ttl=86400,
        )
        return result

    async def summarize(
        self,
        project_id: str,
        chapter_chunks: list[dict],
        summary_stub: dict | None = None,
    ) -> dict:
        """Map-reduce: chapter summaries → story summary.

        Returns:
            {"story_summary": str, "chapter_summaries": list[dict], "meta": dict}
        """
        chapters = self._detect_chapters(chapter_chunks)

        # MAP: summarize each chapter (with concurrency limit of 5)
        semaphore = asyncio.Semaphore(5)

        async def _summarize_one(ch: dict) -> dict:
            async with semaphore:
                return await self._summarize_chapter(ch, project_id)

        chapter_summaries = await asyncio.gather(
            *[_summarize_one(ch) for ch in chapters],
        )

        # REDUCE: merge into story summary
        summary_texts = [cs.get("chapter_summary", "") for cs in chapter_summaries]
        story_summary = await self._merge_summaries(summary_texts, project_id)

        # Final polish: produce structured story summary
        entities_str = json.dumps(summary_stub, ensure_ascii=False) if summary_stub else ""
        prompt = StorySummarizePrompt().render(
            chapters="\n---\n".join(summary_texts),
            entities=entities_str,
        )
        text, meta = await self._call_llm(
            task="summary",
            system_prompt=prompt["system"],
            user_prompt=prompt["user"],
            project_id=project_id,
        )
        structured = StoryAgent._parse_json_response(text, {"narrative_summary": story_summary})

        return {
            "story_summary": structured.get("narrative_summary", story_summary),
            "protagonist_arc": structured.get("protagonist_arc", ""),
            "central_conflict": structured.get("central_conflict", ""),
            "turning_points": structured.get("turning_points", []),
            "chapter_summaries": chapter_summaries,
            "chapter_count": len(chapters),
            "meta": meta,
        }

    async def extract(
        self,
        story_summary: str,
        entities_stub: dict | None = None,
        chapter_chunks: list[dict] | None = None,
        project_id: str = "",
    ) -> dict:
        """Extract timeline, conflicts, relationships, and world setting.

        Returns:
            {"timeline": [], "conflicts": [], "relationships": [], "world_setting": {}}
        """
        content_hash = CacheService.hash_content(story_summary)
        cache_key = self._cache.build_key("extraction", project_id, content_hash)

        cached = await self._cache.get(cache_key)
        if cached:
            logger.info("cache hit for extraction")
            return cached

        entities_str = json.dumps(entities_stub, ensure_ascii=False) if entities_stub else ""
        prompt = ExtractionPrompt().render(story_summary, entities_str)
        text, meta = await self._call_llm(
            task="summary",
            system_prompt=prompt["system"],
            user_prompt=prompt["user"],
            project_id=project_id,
        )

        result = StoryAgent._parse_json_response(text, {
            "timeline": [],
            "conflicts": [],
            "relationships": [],
            "world_setting": {},
        })
        result["_meta"] = meta
        await self._cache.set(cache_key, result, ttl=86400)
        return result

    @staticmethod
    def _parse_json_response(text: str, default: dict) -> dict:
        """Extract JSON from LLM response text. Returns default on failure."""
        text = text.strip()
        # Try direct parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # Try to extract JSON block from markdown code fences
        json_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if json_match:
            try:
                return json.loads(json_match.group(1).strip())
            except json.JSONDecodeError:
                pass

        # Try to find JSON object in text
        json_match = re.search(r"\{[\s\S]*\}", text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        logger.warning("failed to parse JSON from response: %.200s...", text)
        return default
