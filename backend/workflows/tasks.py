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
