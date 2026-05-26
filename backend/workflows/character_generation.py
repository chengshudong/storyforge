from __future__ import annotations

import logging
from dataclasses import dataclass, field

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)


@dataclass
class CharacterGenerationState:
    project_id: str
    # Input
    chapter_summaries: list[dict] = field(default_factory=list)
    relationships: list[dict] = field(default_factory=list)
    entities_persons: list[str] = field(default_factory=list)
    scene_characters: list[str] = field(default_factory=list)
    scenes: list[dict] = field(default_factory=list)
    world_setting: dict = field(default_factory=dict)
    # Node 1 output: extract
    extracted_characters: list[dict] | None = None
    # Node 2 output: profile
    profiled_characters: list[dict] | None = None
    # Node 3 output: merge
    merged_characters: list[dict] | None = None
    # Node 4 output: normalize
    normalized_characters: list[dict] | None = None
    issues: list[dict] = field(default_factory=list)
    # Node 5 output: save
    saved_character_ids: list[str] = field(default_factory=list)
    # Control
    status: str = "pending"
    error: str | None = None


async def _extract_node(state: CharacterGenerationState, character_agent) -> dict:
    try:
        characters = await character_agent.extract_characters(
            project_id=state.project_id,
            chapter_summaries=state.chapter_summaries,
            relationships=state.relationships,
            entities_persons=state.entities_persons,
            scene_characters=state.scene_characters,
        )
        return {
            "extracted_characters": characters,
            "status": "extracted",
            "error": None,
        }
    except Exception as e:
        logger.exception("extract node failed")
        return {"status": "failed", "error": str(e)}


async def _profile_node(state: CharacterGenerationState, character_agent) -> dict:
    try:
        characters = await character_agent.generate_profiles(
            project_id=state.project_id,
            characters=state.extracted_characters or [],
            chapter_summaries=state.chapter_summaries,
            relationships=state.relationships,
            scenes=state.scenes,
            world_setting=state.world_setting,
        )
        return {
            "profiled_characters": characters,
            "status": "profiled",
            "error": None,
        }
    except Exception as e:
        logger.exception("profile node failed")
        return {"status": "failed", "error": str(e)}


async def _merge_node(state: CharacterGenerationState, character_agent) -> dict:
    try:
        characters = await character_agent.merge_duplicates(
            project_id=state.project_id,
            characters=state.profiled_characters or [],
        )
        return {
            "merged_characters": characters,
            "status": "merged",
            "error": None,
        }
    except Exception as e:
        logger.exception("merge node failed")
        return {"status": "failed", "error": str(e)}


async def _normalize_node(state: CharacterGenerationState, character_agent) -> dict:
    try:
        result = await character_agent.normalize_profiles(
            project_id=state.project_id,
            characters=state.merged_characters or [],
            world_setting=state.world_setting,
        )
        chars = result.get("characters", [])
        issues = result.get("issues", [])
        if issues:
            logger.warning("character normalization: %d issues found", len(issues))
        return {
            "normalized_characters": chars,
            "issues": issues,
            "status": "normalized",
            "error": None,
        }
    except Exception as e:
        logger.exception("normalize node failed")
        return {"status": "failed", "error": str(e)}


async def _save_node(
    state: CharacterGenerationState,
    character_repository,
    db_session,
) -> dict:
    try:
        from domain.models import Character, CharacterVersion, ProjectStatus
        from datetime import datetime, timezone

        saved_ids = []
        for ch in state.normalized_characters or []:
            existing = await character_repository.get_by_name(
                state.project_id, ch.get("name", ""),
            ) if hasattr(character_repository, 'get_by_name') else None

            profile_data = {
                "appearance": ch.get("appearance", {}),
                "voice_profile": ch.get("voice_profile", {}),
                "personality": ch.get("personality", {}),
                "emotion_range": ch.get("emotion_range", {}),
                "costume_style": ch.get("costume_style", {}),
                "relationship_graph": ch.get("relationship_graph", {}),
                "backstory": ch.get("backstory", ""),
            }

            character = Character(
                project_id=state.project_id,
                name=ch.get("name", ""),
                description=ch.get("narrative_function", ""),
                role=ch.get("role", ""),
                traits=ch.get("personality", {}).get("traits", []),
                profile=profile_data,
                version=1,
                locked=False,
                status=ProjectStatus.PENDING,
            )
            await character_repository.create(character)
            await db_session.flush()

            # Create initial version record
            from sqlalchemy import insert
            await db_session.execute(
                insert(CharacterVersion).values(
                    id=__import__('uuid').uuid4(),
                    character_id=character.id,
                    version_number=1,
                    profile_snapshot=profile_data,
                    diff=None,
                    created_by="system",
                )
            )

            saved_ids.append(str(character.id))

        return {
            "saved_character_ids": saved_ids,
            "status": "done",
            "error": None,
        }
    except Exception as e:
        logger.exception("save node failed")
        return {"status": "failed", "error": str(e)}


def build_character_workflow(
    character_agent,
    character_repository,
    db_session,
) -> StateGraph:
    """Build the character generation DAG: extract → profile → merge → normalize → save."""
    graph = StateGraph(CharacterGenerationState)

    async def _extract(state: CharacterGenerationState) -> dict:
        return await _extract_node(state, character_agent)

    async def _profile(state: CharacterGenerationState) -> dict:
        return await _profile_node(state, character_agent)

    async def _merge(state: CharacterGenerationState) -> dict:
        return await _merge_node(state, character_agent)

    async def _normalize(state: CharacterGenerationState) -> dict:
        return await _normalize_node(state, character_agent)

    async def _save(state: CharacterGenerationState) -> dict:
        return await _save_node(state, character_repository, db_session)

    graph.add_node("extract", _extract)
    graph.add_node("profile", _profile)
    graph.add_node("merge", _merge)
    graph.add_node("normalize", _normalize)
    graph.add_node("save", _save)

    graph.set_entry_point("extract")

    def _after(state: CharacterGenerationState, next_node: str) -> str:
        if state.status == "failed":
            return END
        return next_node

    def _after_extract(state: CharacterGenerationState) -> str:
        return _after(state, "profile")

    def _after_profile(state: CharacterGenerationState) -> str:
        return _after(state, "merge")

    def _after_merge(state: CharacterGenerationState) -> str:
        return _after(state, "normalize")

    def _after_normalize(state: CharacterGenerationState) -> str:
        return _after(state, "save")

    graph.add_conditional_edges("extract", _after_extract, {"profile": "profile", END: END})
    graph.add_conditional_edges("profile", _after_profile, {"merge": "merge", END: END})
    graph.add_conditional_edges("merge", _after_merge, {"normalize": "normalize", END: END})
    graph.add_conditional_edges("normalize", _after_normalize, {"save": "save", END: END})
    graph.add_edge("save", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
