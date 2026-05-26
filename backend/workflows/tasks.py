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
