from __future__ import annotations

import logging
import uuid

from infra.celery_app import app as celery_app

logger = logging.getLogger(__name__)


@celery_app.task(name="workflows.story_generation.run", bind=True, max_retries=3, default_retry_delay=60)
def run_story_generation(self, project_id: str, job_id: str, regenerate: bool = False):
    """Celery task: run the story generation workflow.

    This task is deliberately synchronous in its Celery binding because the
    LangGraph workflow is itself async and will be driven by an asyncio event
    loop inside the task.
    """
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from infra.config import settings
    from infra.redis import get_redis
    from services.model_router.router import ModelRouter
    from services.model_router.secret_loader import SecretLoader
    from services.cache_service import CacheService
    from providers.llm.deepseek import DeepSeekAdapter
    from providers.llm.openai import OpenAIAdapter
    from providers.llm.anthropic import AnthropicAdapter
    from providers.llm.gemini import GeminiAdapter
    from providers.llm.openrouter import OpenRouterAdapter
    from providers.llm.local import LocalAdapter
    from providers.context.llamaindex_adapter import LlamaIndexAdapter
    from providers.vector.qdrant_adapter import QdrantAdapter
    from agents.story_agent import StoryAgent
    from agents.episode_agent import EpisodeAgent
    from workflows.story_generation import build_story_workflow, StoryGenerationState
    from repository.episode_repository import EpisodeRepository
    from repository.project_repository import ProjectRepository
    from domain.models import ProjectStatus, JobStatus
    from infra.queue import complete_job, fail_job, update_job_progress

    async def _run():
        engine = create_async_engine(settings.database_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        provider_map = {
            "deepseek": DeepSeekAdapter(),
            "openai": OpenAIAdapter(),
            "anthropic": AnthropicAdapter(),
            "gemini": GeminiAdapter(),
            "openrouter": OpenRouterAdapter(),
            "local": LocalAdapter(),
        }

        registry = _load_registry()
        router = ModelRouter(provider_map, registry)
        cache = CacheService()

        # Initialize context store for vector search
        vector_store = QdrantAdapter()
        context_store = LlamaIndexAdapter(vector_store)

        story_agent = StoryAgent(router, cache, context_store)
        episode_agent = EpisodeAgent(router, cache)

        async with async_session() as session:
            try:
                await update_job_progress(session, uuid.UUID(job_id), 5, "Starting story generation")

                project_repo = ProjectRepository(session)
                project = await project_repo.get(uuid.UUID(project_id))
                if project is None:
                    await fail_job(session, uuid.UUID(job_id), "Project not found")
                    return

                collection = (project.meta or {}).get("collection", f"novel_{project_id}")
                entities_stub = (project.meta or {}).get("entities", {})

                # Fetch chapter chunks from Qdrant
                chapter_chunks: list[dict] = []
                try:
                    search_results = await vector_store.query(
                        collection=collection,
                        vector=[0.0] * 384,  # dummy vector to get all points
                        top_k=500,
                    )
                    chapter_chunks = [
                        {"text": r.get("text", ""), "index": r.get("chunk_index", i)}
                        for i, r in enumerate(search_results)
                    ]
                except Exception as e:
                    logger.warning("vector fetch failed, using empty chunks: %s", e)

                await update_job_progress(session, uuid.UUID(job_id), 10, f"Fetched {len(chapter_chunks)} chunks")

                episode_repo = EpisodeRepository(session)
                workflow = build_story_workflow(
                    story_agent, episode_agent,
                    episode_repo, project_repo, session,
                )

                initial_state = StoryGenerationState(
                    project_id=project_id,
                    chapter_chunks=chapter_chunks,
                    entities_stub=entities_stub,
                    summary_stub=project.meta,
                )

                config = {"configurable": {"thread_id": project_id}}
                await update_job_progress(session, uuid.UUID(job_id), 15, "Running summarize node")

                final_state = None
                async for event in workflow.astream(initial_state, config):
                    for node_name, node_output in event.items():
                        if isinstance(node_output, dict):
                            status = node_output.get("status", "")
                            if status == "summarized":
                                await update_job_progress(session, uuid.UUID(job_id), 40,
                                                          "Summarize complete")
                            elif status == "extracted":
                                await update_job_progress(session, uuid.UUID(job_id), 60,
                                                          "Extraction complete")
                            elif status == "planned":
                                await update_job_progress(session, uuid.UUID(job_id), 80,
                                                          "Episode plan complete")
                            elif status == "done":
                                await update_job_progress(session, uuid.UUID(job_id), 95,
                                                          "Saving complete")
                            elif status == "failed":
                                error_msg = node_output.get("error", "Unknown error")
                                await fail_job(session, uuid.UUID(job_id), error_msg)
                                return
                            final_state = node_output

                await complete_job(
                    session,
                    uuid.UUID(job_id),
                    result={
                        "episodes_saved": final_state.get("saved_episodes", []) if final_state else [],
                        "chapter_count": final_state.get("chapter_count", 0) if final_state else 0,
                    },
                )

            except Exception as e:
                logger.exception("story generation workflow failed")
                await fail_job(session, uuid.UUID(job_id), str(e))

    asyncio.run(_run())


def _load_registry() -> dict:
    import yaml
    from pathlib import Path

    config_path = Path(__file__).parent.parent / "config" / "models.yaml"
    if not config_path.exists():
        return {}
    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


@celery_app.task(name="workflows.scene_generation.run", bind=True, max_retries=3, default_retry_delay=60)
def run_scene_generation(self, project_id: str, episode_id: str, job_id: str, regenerate: bool = False):
    """Celery task: run the scene generation workflow for one episode."""
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from infra.config import settings
    from providers.llm.deepseek import DeepSeekAdapter
    from providers.llm.openai import OpenAIAdapter
    from providers.llm.anthropic import AnthropicAdapter
    from providers.llm.gemini import GeminiAdapter
    from providers.llm.openrouter import OpenRouterAdapter
    from providers.llm.local import LocalAdapter
    from agents.scene_agent import SceneAgent
    from workflows.scene_generation import build_scene_workflow, SceneGenerationState
    from repository.episode_repository import EpisodeRepository
    from repository.project_repository import ProjectRepository
    from repository.scene_repository import SceneRepository
    from services.model_router.router import ModelRouter
    from services.cache_service import CacheService
    from infra.queue import complete_job, fail_job, update_job_progress

    async def _run():
        engine = create_async_engine(settings.database_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        provider_map = {
            "deepseek": DeepSeekAdapter(), "openai": OpenAIAdapter(),
            "anthropic": AnthropicAdapter(), "gemini": GeminiAdapter(),
            "openrouter": OpenRouterAdapter(), "local": LocalAdapter(),
        }
        registry = _load_registry()
        router = ModelRouter(provider_map, registry)
        cache = CacheService()
        scene_agent = SceneAgent(router, cache)

        async with async_session() as session:
            try:
                await update_job_progress(session, uuid.UUID(job_id), 5, "Starting scene generation")

                episode_repo = EpisodeRepository(session)
                project_repo = ProjectRepository(session)
                scene_repo = SceneRepository(session)

                episode = await episode_repo.get(uuid.UUID(episode_id))
                if episode is None:
                    await fail_job(session, uuid.UUID(job_id), "Episode not found")
                    return

                project = await project_repo.get(uuid.UUID(project_id))
                if project is None:
                    await fail_job(session, uuid.UUID(job_id), "Project not found")
                    return

                meta = project.meta or {}

                # Build character list from project meta
                characters: list[dict] = []
                for rel in meta.get("relationships", []):
                    for role_name in ("character_a", "character_b"):
                        name = rel.get(role_name, "")
                        if name and not any(c.get("name") == name for c in characters):
                            characters.append({
                                "name": name,
                                "role": rel.get("relation_type", ""),
                                "traits": [],
                            })
                # Also include persons from entities stub
                for person in meta.get("entities", {}).get("persons", []):
                    if not any(c.get("name") == person for c in characters):
                        characters.append({"name": person, "role": "", "traits": []})

                episode_data = {
                    "id": episode_id,
                    "title": episode.title or "",
                    "summary": episode.summary or "",
                    "key_scenes": [],
                }
                # Try to get key_scenes from project meta episode_plan
                for plan_ep in meta.get("episode_plan", []):
                    if plan_ep.get("episode_number") == episode.episode_number:
                        episode_data["key_scenes"] = plan_ep.get("key_scenes", [])
                        break

                # Get previous episode scenes for context
                previous_scenes: list[dict] = []
                if episode.episode_number > 1:
                    prev_ep = await episode_repo.get_by_number(
                        uuid.UUID(project_id), episode.episode_number - 1,
                    )
                    if prev_ep:
                        prev_scenes = await scene_repo.list_by_episode(prev_ep.id)
                        previous_scenes = [
                            {"description": s.description, "scene_number": s.scene_number}
                            for s in prev_scenes
                        ]

                await update_job_progress(session, uuid.UUID(job_id), 10, f"Episode {episode.episode_number}: building workflow")

                workflow = build_scene_workflow(scene_agent, scene_repo, episode_repo, session)

                initial_state = SceneGenerationState(
                    project_id=project_id,
                    episode_id=episode_id,
                    episode=episode_data,
                    episode_number=episode.episode_number,
                    characters=characters,
                    timeline=meta.get("timeline", []),
                    world_setting=meta.get("world_setting", {}),
                    relationships=meta.get("relationships", []),
                    previous_episode_scenes=previous_scenes,
                )

                config = {"configurable": {"thread_id": f"{project_id}_scenes_{episode_id}"}}
                await update_job_progress(session, uuid.UUID(job_id), 15, "Running split node")

                final_state = None
                async for event in workflow.astream(initial_state, config):
                    for node_name, node_output in event.items():
                        if isinstance(node_output, dict):
                            status = node_output.get("status", "")
                            if status == "split":
                                beat_count = len(node_output.get("scene_beats", []))
                                await update_job_progress(
                                    session, uuid.UUID(job_id), 30,
                                    f"Split complete: {beat_count} scene beats",
                                )
                            elif status == "storyboarded":
                                scene_count = len(node_output.get("scenes", []))
                                await update_job_progress(
                                    session, uuid.UUID(job_id), 60,
                                    f"Storyboard complete: {scene_count} scenes",
                                )
                            elif status == "validated":
                                await update_job_progress(session, uuid.UUID(job_id), 80, "Validation complete")
                            elif status == "done":
                                await update_job_progress(
                                    session, uuid.UUID(job_id), 95,
                                    f"Saved {len(node_output.get('saved_scene_ids', []))} scenes",
                                )
                            elif status == "failed":
                                await fail_job(session, uuid.UUID(job_id), node_output.get("error", "Unknown error"))
                                return
                            final_state = node_output

                await complete_job(session, uuid.UUID(job_id), result={
                    "scenes_saved": final_state.get("saved_scene_ids", []) if final_state else [],
                    "episode_number": episode.episode_number,
                })

            except Exception as e:
                logger.exception("scene generation workflow failed")
                await fail_job(session, uuid.UUID(job_id), str(e))

    asyncio.run(_run())


@celery_app.task(name="workflows.character_generation.run", bind=True, max_retries=3, default_retry_delay=60)
def run_character_generation(self, project_id: str, job_id: str, regenerate: bool = False):
    """Celery task: run the character generation workflow for a project."""
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from infra.config import settings
    from providers.llm.deepseek import DeepSeekAdapter
    from providers.llm.openai import OpenAIAdapter
    from providers.llm.anthropic import AnthropicAdapter
    from providers.llm.gemini import GeminiAdapter
    from providers.llm.openrouter import OpenRouterAdapter
    from providers.llm.local import LocalAdapter
    from providers.vector.qdrant_adapter import QdrantAdapter
    from agents.character_agent import CharacterAgent
    from workflows.character_generation import build_character_workflow, CharacterGenerationState
    from repository.character_repository import CharacterRepository
    from repository.project_repository import ProjectRepository
    from repository.episode_repository import EpisodeRepository
    from repository.scene_repository import SceneRepository
    from services.model_router.router import ModelRouter
    from services.cache_service import CacheService
    from infra.queue import complete_job, fail_job, update_job_progress

    async def _run():
        engine = create_async_engine(settings.database_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        provider_map = {
            "deepseek": DeepSeekAdapter(), "openai": OpenAIAdapter(),
            "anthropic": AnthropicAdapter(), "gemini": GeminiAdapter(),
            "openrouter": OpenRouterAdapter(), "local": LocalAdapter(),
        }
        registry = _load_registry()
        router = ModelRouter(provider_map, registry)
        cache = CacheService()
        vector_store = QdrantAdapter()
        character_agent = CharacterAgent(router, cache, vector_store)

        async with async_session() as session:
            try:
                await update_job_progress(session, uuid.UUID(job_id), 5, "Starting character generation")

                project_repo = ProjectRepository(session)
                project = await project_repo.get(uuid.UUID(project_id))
                if project is None:
                    await fail_job(session, uuid.UUID(job_id), "Project not found")
                    return

                meta = project.meta or {}
                relationships = meta.get("relationships", [])
                entities_persons = meta.get("entities", {}).get("persons", [])
                world_setting = meta.get("world_setting", {})

                # Load chapter summaries from project meta
                chapter_summaries: list[dict] = meta.get("chapter_summaries", [])
                if not chapter_summaries:
                    # Fallback: synthesize from story_summary
                    story = meta.get("story_summary", "")
                    if story:
                        chapter_summaries = [{"chapter_index": 1, "chapter_summary": story}]

                # Collect scene characters_present
                scene_repo = SceneRepository(session)
                episode_repo = EpisodeRepository(session)
                episodes = await episode_repo.list_by_project(uuid.UUID(project_id))
                all_scenes: list[dict] = []
                scene_characters: list[str] = []
                for ep in episodes:
                    ep_scenes = await scene_repo.list_by_episode(ep.id)
                    for sc in ep_scenes:
                        sc_dict = {
                            "id": str(sc.id),
                            "scene_number": sc.scene_number,
                            "title": sc.title,
                            "description": sc.description,
                            "storyboard": sc.storyboard,
                        }
                        all_scenes.append(sc_dict)
                        chars = (sc.storyboard or {}).get("characters_present", [])
                        for c in chars:
                            if c not in scene_characters:
                                scene_characters.append(c)

                await update_job_progress(session, uuid.UUID(job_id), 10,
                                          f"Found {len(entities_persons)} entities, "
                                          f"{len(relationships)} relationships, "
                                          f"{len(all_scenes)} scenes")

                char_repo = CharacterRepository(session)
                workflow = build_character_workflow(character_agent, char_repo, session)

                initial_state = CharacterGenerationState(
                    project_id=project_id,
                    chapter_summaries=chapter_summaries,
                    relationships=relationships,
                    entities_persons=entities_persons,
                    scene_characters=scene_characters,
                    scenes=all_scenes,
                    world_setting=world_setting,
                )

                config = {"configurable": {"thread_id": f"{project_id}_characters"}}
                await update_job_progress(session, uuid.UUID(job_id), 15, "Running extract node")

                final_state = None
                async for event in workflow.astream(initial_state, config):
                    for node_name, node_output in event.items():
                        if isinstance(node_output, dict):
                            status = node_output.get("status", "")
                            if status == "extracted":
                                count = len(node_output.get("extracted_characters", []))
                                await update_job_progress(session, uuid.UUID(job_id), 30,
                                                          f"Extracted {count} characters")
                            elif status == "profiled":
                                count = len(node_output.get("profiled_characters", []))
                                await update_job_progress(session, uuid.UUID(job_id), 55,
                                                          f"Profiled {count} characters")
                            elif status == "merged":
                                count = len(node_output.get("merged_characters", []))
                                await update_job_progress(session, uuid.UUID(job_id), 70,
                                                          f"Merged to {count} characters")
                            elif status == "normalized":
                                issues = len(node_output.get("issues", []))
                                await update_job_progress(session, uuid.UUID(job_id), 85,
                                                          f"Normalized ({issues} issues)")
                            elif status == "done":
                                await update_job_progress(
                                    session, uuid.UUID(job_id), 95,
                                    f"Saved {len(node_output.get('saved_character_ids', []))} characters",
                                )
                            elif status == "failed":
                                await fail_job(session, uuid.UUID(job_id),
                                               node_output.get("error", "Unknown error"))
                                return
                            final_state = node_output

                await complete_job(session, uuid.UUID(job_id), result={
                    "characters_saved": final_state.get("saved_character_ids", []) if final_state else [],
                    "issues": final_state.get("issues", []) if final_state else [],
                })

            except Exception as e:
                logger.exception("character generation workflow failed")
                await fail_job(session, uuid.UUID(job_id), str(e))

    asyncio.run(_run())


@celery_app.task(name="workflows.image_generation.run", bind=True, max_retries=2, default_retry_delay=120)
def run_image_generation(self, project_id: str, job_id: str, phases: list[str] | None = None,
                         variant_count: int = 4, regenerate: bool = False):
    """Celery task: run the image generation workflow for a project.

    Orchestrates ComfyUI image generation across multiple phases:
    char_ref → upload_refs → char_scene → bg → prop → cover.

    Does NOT use LLM — all prompts are deterministic from profile data.
    """
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from infra.config import settings
    from providers.image.comfyui_adapter import ComfyUIAdapter
    from agents.image_agent import ImageAgent
    from workflows.image_generation import build_image_workflow, ImageGenerationState
    from repository.asset_repository import AssetRepository
    from repository.character_repository import CharacterRepository
    from repository.scene_repository import SceneRepository
    from repository.project_repository import ProjectRepository
    from repository.prop_repository import PropRepository
    from api.v1.schemas import AssetGenerationParams
    from infra.queue import complete_job, fail_job, update_job_progress

    async def _run():
        engine = create_async_engine(settings.database_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            try:
                await update_job_progress(session, uuid.UUID(job_id), 5, "Starting image generation")

                project_repo = ProjectRepository(session)
                project = await project_repo.get(uuid.UUID(project_id))
                if project is None:
                    await fail_job(session, uuid.UUID(job_id), "Project not found")
                    return

                # Load characters with profiles
                char_repo = CharacterRepository(session)
                characters = await char_repo.list_by_project(uuid.UUID(project_id))
                char_data = [
                    {
                        "id": str(c.id),
                        "name": c.name,
                        "profile": c.profile or {},
                        "description": c.description or "",
                        "role": c.role or "",
                    }
                    for c in characters
                ]

                # Load scenes with storyboards
                scene_repo = SceneRepository(session)
                from repository.episode_repository import EpisodeRepository
                ep_repo = EpisodeRepository(session)
                episodes = await ep_repo.list_by_project(uuid.UUID(project_id))
                all_scenes: list[dict] = []
                for ep in episodes:
                    ep_scenes = await scene_repo.list_by_episode(ep.id)
                    for sc in ep_scenes:
                        all_scenes.append({
                            "id": str(sc.id),
                            "title": sc.title,
                            "storyboard": sc.storyboard or {},
                        })

                # Load props
                prop_repo = PropRepository(session)
                props = await prop_repo.list_by_project(uuid.UUID(project_id))
                prop_data = [
                    {"name": p.name, "description": p.description or "", "prop_type": p.prop_type or ""}
                    for p in props
                ]

                meta = project.meta or {}
                project_meta = {
                    "title": project.name,
                    "description": project.description or "",
                    "world_setting": meta.get("world_setting", {}),
                }

                active_phases = phases or ["char_ref", "char_scene", "bg", "prop"]

                await update_job_progress(
                    session, uuid.UUID(job_id), 10,
                    f"Loaded {len(char_data)} characters, {len(all_scenes)} scenes, "
                    f"{len(prop_data)} props. Phases: {active_phases}",
                )

                # Initialize image provider and agent (no LLM needed)
                image_provider = ComfyUIAdapter()
                asset_repo = AssetRepository(session)
                image_agent = ImageAgent(image_provider, asset_repo)

                workflow = build_image_workflow(image_agent, asset_repo)

                initial_state = ImageGenerationState(
                    project_id=project_id,
                    characters=char_data,
                    scenes=all_scenes,
                    props=prop_data,
                    project_meta=project_meta,
                    phases=active_phases,
                    variant_count=variant_count,
                    params=AssetGenerationParams(),
                )

                config = {"configurable": {"thread_id": f"{project_id}_images"}}
                await update_job_progress(session, uuid.UUID(job_id), 15, "Running image generation phases")

                final_state = None
                async for event in workflow.astream(initial_state, config):
                    for node_name, node_output in event.items():
                        if isinstance(node_output, dict):
                            status = node_output.get("status", "")
                            progress_map = {
                                "char_ref_done": (25, "Character references generated"),
                                "char_ref_skipped": (25, "Char ref skipped"),
                                "upload_done": (35, "Face references uploaded"),
                                "upload_skipped": (30, "Upload skipped"),
                                "char_scene_done": (55, "Character scene images generated"),
                                "char_scene_skipped": (45, "Char scene skipped"),
                                "bg_done": (70, "Backgrounds generated"),
                                "bg_skipped": (60, "BG skipped"),
                                "prop_done": (85, "Props generated"),
                                "prop_skipped": (75, "Prop skipped"),
                                "cover_done": (95, "Cover generated"),
                                "cover_skipped": (85, "Cover skipped"),
                                "done": (100, "All phases complete"),
                            }
                            if status in progress_map:
                                pct, msg = progress_map[status]
                                await update_job_progress(session, uuid.UUID(job_id), pct, msg)
                            elif status == "failed":
                                await fail_job(session, uuid.UUID(job_id),
                                               node_output.get("error", "Unknown error"))
                                return
                            final_state = node_output

                await complete_job(
                    session,
                    uuid.UUID(job_id),
                    result={
                        "total_generated": final_state.get("total_generated", 0) if final_state else 0,
                        "batch_id": initial_state.batch_id,
                        "phases_completed": active_phases,
                    },
                )

            except Exception as e:
                logger.exception("image generation workflow failed")
                await fail_job(session, uuid.UUID(job_id), str(e))

    asyncio.run(_run())


@celery_app.task(name="workflows.voice_generation.run", bind=True, max_retries=2, default_retry_delay=120)
def run_voice_generation(self, project_id: str, job_id: str,
                         phases: list[str] | None = None,
                         regenerate: bool = False):
    """Celery task: run the voice generation workflow for a project.

    Orchestrates CosyVoice voice cloning and dialogue synthesis:
    clone -> synthesize -> preview -> save.

    Uses ModelRouter only for emotion LLM fallback.
    Hot synthesis path is deterministic (no LLM calls).
    """
    import asyncio
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.orm import sessionmaker

    from infra.config import settings
    from providers.llm.deepseek import DeepSeekAdapter
    from providers.llm.openai import OpenAIAdapter
    from providers.llm.anthropic import AnthropicAdapter
    from providers.llm.gemini import GeminiAdapter
    from providers.llm.openrouter import OpenRouterAdapter
    from providers.llm.local import LocalAdapter
    from providers.voice.cosyvoice_adapter import CosyVoiceAdapter
    from providers.voice.gptsovits_adapter import GPTSoVITSAdapter
    from agents.voice_agent import VoiceAgent
    from services.voice_library import VoiceLibrary
    from workflows.voice_generation import build_voice_workflow, VoiceGenerationState
    from repository.voice_repository import VoiceRepository
    from repository.character_repository import CharacterRepository
    from repository.scene_repository import SceneRepository
    from repository.episode_repository import EpisodeRepository
    from repository.project_repository import ProjectRepository
    from services.model_router.router import ModelRouter
    from services.cache_service import CacheService
    from infra.queue import complete_job, fail_job, update_job_progress

    async def _run():
        engine = create_async_engine(settings.database_url)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        provider_map = {
            "deepseek": DeepSeekAdapter(), "openai": OpenAIAdapter(),
            "anthropic": AnthropicAdapter(), "gemini": GeminiAdapter(),
            "openrouter": OpenRouterAdapter(), "local": LocalAdapter(),
        }
        registry = _load_registry()
        router = ModelRouter(provider_map, registry)
        cache = CacheService()

        async with async_session() as session:
            try:
                await update_job_progress(session, uuid.UUID(job_id), 5, "Starting voice generation")

                project_repo = ProjectRepository(session)
                project = await project_repo.get(uuid.UUID(project_id))
                if project is None:
                    await fail_job(session, uuid.UUID(job_id), "Project not found")
                    return

                # Load characters with voice profiles
                char_repo = CharacterRepository(session)
                characters = await char_repo.list_by_project(uuid.UUID(project_id))
                char_data = [
                    {
                        "id": str(c.id),
                        "name": c.name,
                        "profile": c.profile or {},
                        "version": c.version or 1,
                    }
                    for c in characters
                ]

                # Load scenes with dialogue
                scene_repo = SceneRepository(session)
                ep_repo = EpisodeRepository(session)
                episodes = await ep_repo.list_by_project(uuid.UUID(project_id))
                all_scenes: list[dict] = []
                scene_storyboards: dict[str, dict] = {}
                for ep in episodes:
                    ep_scenes = await scene_repo.list_by_episode(ep.id)
                    for sc in ep_scenes:
                        scene_dict = {
                            "id": str(sc.id),
                            "title": sc.title,
                            "dialogue": sc.dialogue or [],
                            "storyboard": sc.storyboard or {},
                        }
                        all_scenes.append(scene_dict)
                        if sc.storyboard:
                            scene_storyboards[str(sc.id)] = sc.storyboard

                active_phases = phases or ["clone", "synthesize", "preview"]

                await update_job_progress(
                    session, uuid.UUID(job_id), 10,
                    f"Loaded {len(char_data)} characters, {len(all_scenes)} scenes. "
                    f"Phases: {active_phases}",
                )

                # Initialize voice provider
                cosyvoice = CosyVoiceAdapter()
                cosy_healthy = await cosyvoice.health()
                if cosy_healthy:
                    voice_provider = cosyvoice
                else:
                    logger.warning("CosyVoice unhealthy, checking GPT-SoVITS")
                    gptsovits = GPTSoVITSAdapter()
                    if await gptsovits.health():
                        voice_provider = gptsovits
                    else:
                        voice_provider = cosyvoice

                voice_repo = VoiceRepository(session)
                voice_library = VoiceLibrary(cache)
                voice_agent = VoiceAgent(voice_provider, voice_repo, voice_library, cache, router)

                workflow = build_voice_workflow(voice_agent)

                initial_state = VoiceGenerationState(
                    project_id=project_id,
                    characters=char_data,
                    scenes=all_scenes,
                    scene_storyboards=scene_storyboards,
                    phases=active_phases,
                    job_id=job_id,
                    regenerate=regenerate,
                )

                config = {"configurable": {"thread_id": f"{project_id}_voices"}}
                await update_job_progress(session, uuid.UUID(job_id), 15, "Running clone phase")

                final_state = None
                async for event in workflow.astream(initial_state, config):
                    for node_name, node_output in event.items():
                        if isinstance(node_output, dict):
                            status = node_output.get("status", "")
                            progress_map = {
                                "clone_done": (35, "Voice cloning complete"),
                                "clone_skipped": (30, "Clone skipped"),
                                "synthesize_done": (80, "Dialogue synthesis complete"),
                                "synthesize_skipped": (70, "Synthesis skipped"),
                                "preview_done": (95, "Previews generated"),
                                "preview_skipped": (85, "Preview skipped"),
                                "done": (100, "All phases complete"),
                            }
                            if status in progress_map:
                                pct, msg = progress_map[status]
                                await update_job_progress(session, uuid.UUID(job_id), pct, msg)
                            elif status == "failed":
                                await fail_job(session, uuid.UUID(job_id),
                                               node_output.get("error", "Unknown error"))
                                return
                            final_state = node_output

                saved = final_state.get("saved_voice_ids", []) if final_state else []
                speakers = final_state.get("speaker_map", {}) if final_state else {}
                await complete_job(
                    session,
                    uuid.UUID(job_id),
                    result={
                        "voices_saved": len(saved),
                        "voice_ids": saved,
                        "characters_cloned": len(speakers),
                        "phases_completed": active_phases,
                    },
                )

            except Exception as e:
                logger.exception("voice generation workflow failed")
                await fail_job(session, uuid.UUID(job_id), str(e))

    asyncio.run(_run())
