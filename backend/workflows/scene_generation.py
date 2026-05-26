from __future__ import annotations

import logging
from dataclasses import dataclass, field

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)


@dataclass
class SceneGenerationState:
    project_id: str
    episode_id: str
    # Input
    episode: dict | None = None
    episode_number: int = 0
    characters: list[dict] = field(default_factory=list)
    timeline: list[dict] | None = None
    world_setting: dict | None = None
    relationships: list[dict] | None = None
    previous_episode_scenes: list[dict] = field(default_factory=list)
    # Node 1 output: split
    scene_beats: list[dict] | None = None
    # Node 2 output: storyboard
    scenes: list[dict] | None = None
    # Node 3 output: validate
    validation: dict | None = None
    validation_passed: bool = True
    # Node 4 output: save
    saved_scene_ids: list[str] = field(default_factory=list)
    # Control
    status: str = "pending"
    error: str | None = None


async def _split_node(state: SceneGenerationState, scene_agent) -> dict:
    try:
        beats = await scene_agent._split_episode(
            project_id=state.project_id,
            episode=state.episode or {},
            characters=state.characters,
            timeline=state.timeline or [],
        )
        return {
            "scene_beats": beats,
            "status": "split",
            "error": None,
        }
    except Exception as e:
        logger.exception("split node failed")
        return {"status": "failed", "error": str(e)}


async def _storyboard_node(state: SceneGenerationState, scene_agent) -> dict:
    try:
        scenes = await scene_agent.storyboard(
            project_id=state.project_id,
            episode=state.episode or {},
            characters=state.characters,
            timeline=state.timeline,
            world_setting=state.world_setting,
            previous_scenes=state.previous_episode_scenes,
        )
        return {
            "scenes": scenes,
            "status": "storyboarded",
            "error": None,
        }
    except Exception as e:
        logger.exception("storyboard node failed")
        return {"status": "failed", "error": str(e)}


async def _validate_node(state: SceneGenerationState, scene_agent) -> dict:
    try:
        validation = await scene_agent._validate_continuity(
            project_id=state.project_id,
            scenes=state.scenes or [],
        )
        valid = validation.get("valid", True)
        issues = validation.get("issues", [])
        if not valid:
            logger.warning("scene validation: %d issues found", len(issues))
        return {
            "validation": validation,
            "validation_passed": valid,
            "status": "validated",
            "error": None,
        }
    except Exception as e:
        logger.exception("validate node failed")
        # Validation failure is non-blocking — proceed to save
        return {
            "validation_passed": True,
            "status": "validated",
            "error": None,
        }


async def _save_node(
    state: SceneGenerationState,
    scene_repository,
    episode_repository,
    db_session,
) -> dict:
    try:
        from domain.models import Scene, ProjectStatus

        saved_ids = []
        for sc in state.scenes or []:
            # Build storyboard dict for the JSONB column
            storyboard_data = {
                "camera": sc.get("camera"),
                "duration": sc.get("estimated_duration", 30),
                "emotion": sc.get("emotion"),
                "location": sc.get("location"),
                "props": sc.get("props", []),
                "transition": sc.get("transition", "cut"),
                "asset_refs": sc.get("asset_refs", []),
                "character_actions": sc.get("character_actions", {}),
                "characters_present": sc.get("characters_present", []),
                "locked": False,
            }

            scene = Scene(
                episode_id=state.episode_id,
                scene_number=sc.get("scene_number", len(saved_ids) + 1),
                title=sc.get("scene_title", ""),
                description=sc.get("description", ""),
                dialogue=sc.get("dialogue", []),
                storyboard=storyboard_data,
                status=ProjectStatus.PENDING,
            )
            await scene_repository.create(scene)
            saved_ids.append(str(scene.id))

        # Update episode status
        episode = await episode_repository.get(state.episode_id)
        if episode:
            episode.status = ProjectStatus.SCENES
            await db_session.flush()

        return {
            "saved_scene_ids": saved_ids,
            "status": "done",
            "error": None,
        }
    except Exception as e:
        logger.exception("save node failed")
        return {"status": "failed", "error": str(e)}


def build_scene_workflow(
    scene_agent,
    scene_repository,
    episode_repository,
    db_session,
) -> StateGraph:
    """Build the scene generation DAG: split → storyboard → validate → save."""
    graph = StateGraph(SceneGenerationState)

    async def _split(state: SceneGenerationState) -> dict:
        return await _split_node(state, scene_agent)

    async def _storyboard(state: SceneGenerationState) -> dict:
        return await _storyboard_node(state, scene_agent)

    async def _validate(state: SceneGenerationState) -> dict:
        return await _validate_node(state, scene_agent)

    async def _save(state: SceneGenerationState) -> dict:
        return await _save_node(state, scene_repository, episode_repository, db_session)

    graph.add_node("split", _split)
    graph.add_node("storyboard", _storyboard)
    graph.add_node("validate", _validate)
    graph.add_node("save", _save)

    graph.set_entry_point("split")

    def _after_split(state: SceneGenerationState) -> str:
        if state.status == "failed":
            return END
        return "storyboard"

    def _after_storyboard(state: SceneGenerationState) -> str:
        if state.status == "failed":
            return END
        return "validate"

    def _after_validate(state: SceneGenerationState) -> str:
        if state.status == "failed":
            return END
        return "save"

    graph.add_conditional_edges("split", _after_split, {"storyboard": "storyboard", END: END})
    graph.add_conditional_edges("storyboard", _after_storyboard, {"validate": "validate", END: END})
    graph.add_conditional_edges("validate", _after_validate, {"save": "save", END: END})
    graph.add_edge("save", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
