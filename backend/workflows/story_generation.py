from __future__ import annotations

import logging
from dataclasses import dataclass, field

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)


@dataclass
class StoryGenerationState:
    project_id: str
    # Input
    chapter_chunks: list[dict] = field(default_factory=list)
    summary_stub: dict | None = None
    entities_stub: dict | None = None
    # Node 1 output: summarize
    story_summary: str | None = None
    protagonist_arc: str | None = None
    central_conflict: str | None = None
    turning_points: list[str] | None = None
    chapter_summaries: list[dict] | None = None
    chapter_count: int = 0
    # Node 2 output: extract
    timeline: list[dict] | None = None
    conflicts: list[dict] | None = None
    relationships: list[dict] | None = None
    world_setting: dict | None = None
    # Node 3 output: plan
    episode_plan: list[dict] | None = None
    # Node 4 output: save
    saved_episodes: list[str] = field(default_factory=list)
    # Control
    status: str = "pending"
    error: str | None = None
    meta: dict = field(default_factory=dict)


async def _summarize_node(
    state: StoryGenerationState,
    story_agent,
) -> dict:
    try:
        result = await story_agent.summarize(
            project_id=state.project_id,
            chapter_chunks=state.chapter_chunks,
            summary_stub=state.summary_stub,
        )
        return {
            "story_summary": result["story_summary"],
            "protagonist_arc": result.get("protagonist_arc", ""),
            "central_conflict": result.get("central_conflict", ""),
            "turning_points": result.get("turning_points", []),
            "chapter_summaries": result.get("chapter_summaries", []),
            "chapter_count": result.get("chapter_count", 0),
            "meta": result.get("meta", {}),
            "status": "summarized",
            "error": None,
        }
    except Exception as e:
        logger.exception("summarize node failed")
        return {"status": "failed", "error": str(e)}


async def _extract_node(
    state: StoryGenerationState,
    story_agent,
) -> dict:
    try:
        result = await story_agent.extract(
            story_summary=state.story_summary or "",
            entities_stub=state.entities_stub,
            chapter_chunks=state.chapter_chunks,
            project_id=state.project_id,
        )
        return {
            "timeline": result.get("timeline", []),
            "conflicts": result.get("conflicts", []),
            "relationships": result.get("relationships", []),
            "world_setting": result.get("world_setting", {}),
            "status": "extracted",
            "error": None,
        }
    except Exception as e:
        logger.exception("extract node failed")
        return {"status": "failed", "error": str(e)}


async def _plan_node(
    state: StoryGenerationState,
    episode_agent,
) -> dict:
    try:
        episodes = await episode_agent.plan(
            project_id=state.project_id,
            story_summary=state.story_summary or "",
            timeline=state.timeline or [],
            chapter_count=state.chapter_count,
        )
        return {
            "episode_plan": episodes,
            "status": "planned",
            "error": None,
        }
    except Exception as e:
        logger.exception("plan node failed")
        return {"status": "failed", "error": str(e)}


async def _save_node(
    state: StoryGenerationState,
    episode_repository,
    project_repository,
    db_session,
) -> dict:
    try:
        from domain.models import Episode, ProjectStatus

        saved_ids = []
        for ep in state.episode_plan or []:
            episode = Episode(
                project_id=state.project_id,
                episode_number=ep.get("episode_number", len(saved_ids) + 1),
                title=ep.get("title", f"Episode {len(saved_ids) + 1}"),
                summary=ep.get("summary", ""),
                status=ProjectStatus.PENDING,
            )
            await episode_repository.create(episode)
            saved_ids.append(str(episode.id))

        # Update project status and store extraction results in meta
        project = await project_repository.get(state.project_id)
        if project:
            from domain.models import ProjectStatus as PS
            project.status = PS.EPISODES
            project.meta = {
                **(project.meta or {}),
                "story_summary": state.story_summary,
                "protagonist_arc": state.protagonist_arc,
                "central_conflict": state.central_conflict,
                "turning_points": state.turning_points,
                "timeline": state.timeline,
                "conflicts": state.conflicts,
                "relationships": state.relationships,
                "world_setting": state.world_setting,
            }
            await db_session.flush()

        return {
            "saved_episodes": saved_ids,
            "status": "done",
            "error": None,
        }
    except Exception as e:
        logger.exception("save node failed")
        return {"status": "failed", "error": str(e)}


def build_story_workflow(
    story_agent,
    episode_agent,
    episode_repository,
    project_repository,
    db_session,
) -> StateGraph:
    """Build the story generation DAG: summarize → extract → plan → save."""
    graph = StateGraph(StoryGenerationState)

    async def _summarize(state: StoryGenerationState) -> dict:
        return await _summarize_node(state, story_agent)

    async def _extract(state: StoryGenerationState) -> dict:
        return await _extract_node(state, story_agent)

    async def _plan(state: StoryGenerationState) -> dict:
        return await _plan_node(state, episode_agent)

    async def _save(state: StoryGenerationState) -> dict:
        return await _save_node(state, episode_repository, project_repository, db_session)

    graph.add_node("summarize", _summarize)
    graph.add_node("extract", _extract)
    graph.add_node("plan", _plan)
    graph.add_node("save", _save)

    graph.set_entry_point("summarize")

    # Conditional routing: if status="failed", stop
    def _after_summarize(state: StoryGenerationState) -> str:
        if state.status == "failed":
            return END
        return "extract"

    def _after_extract(state: StoryGenerationState) -> str:
        if state.status == "failed":
            return END
        return "plan"

    def _after_plan(state: StoryGenerationState) -> str:
        if state.status == "failed":
            return END
        return "save"

    graph.add_conditional_edges("summarize", _after_summarize, {"extract": "extract", END: END})
    graph.add_conditional_edges("extract", _after_extract, {"plan": "plan", END: END})
    graph.add_conditional_edges("plan", _after_plan, {"save": "save", END: END})
    graph.add_edge("save", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
