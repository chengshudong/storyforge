from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass, field

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)

PHASE_INIT = "init"
PHASE_SUBMIT = "submit"
PHASE_POLL = "poll"
PHASE_COMPOSITE = "composite"
PHASE_SAVE = "save"


@dataclass
class VideoGenerationState:
    project_id: str

    # Input data
    scenes: list[dict] = field(default_factory=list)
    character_assets: dict[str, dict] = field(default_factory=dict)
    voice_assets: dict[str, list[dict]] = field(default_factory=dict)

    # Config
    phases: list[str] = field(default_factory=lambda: [
        PHASE_INIT, PHASE_SUBMIT, PHASE_POLL, PHASE_COMPOSITE, PHASE_SAVE,
    ])
    variant_count: int = 1
    regenerate: bool = False

    # Generation tracking
    batch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    submissions: list[dict] = field(default_factory=list)
    retry_count: int = 0
    max_retries: int = 1

    # Outputs
    generated_videos: list[dict] = field(default_factory=list)
    saved_video_ids: list[str] = field(default_factory=list)
    errors: list[dict] = field(default_factory=list)

    # Tracking
    job_id: str = ""
    progress: int = 0
    status: str = "pending"


# ── Node Functions ───────────────────────────────────────────────────

async def _init_node(state: VideoGenerationState, video_agent) -> dict:
    if PHASE_INIT not in state.phases:
        return {"status": "init_skipped"}

    try:
        if not state.scenes:
            logger.warning("no scenes with storyboards loaded")
            return {"status": "no_scenes"}

        valid_scenes = []
        for s in state.scenes:
            if s.get("storyboard"):
                valid_scenes.append(s)

        if not valid_scenes:
            return {"status": "no_scenes"}

        logger.info("init phase: %d valid scenes", len(valid_scenes))
        return {
            "scenes": valid_scenes,
            "status": "init_done",
        }
    except Exception as e:
        logger.exception("init node failed")
        return {"status": "failed", "error": str(e)}


async def _submit_node(state: VideoGenerationState, video_agent) -> dict:
    if PHASE_SUBMIT not in state.phases:
        return {"status": "submit_skipped"}

    try:
        submissions: list[dict] = []
        errors: list[dict] = []

        for scene in state.scenes:
            scene_id = scene.get("id", "")
            storyboard = scene.get("storyboard", {})

            # Find characters present in this scene
            characters_present = storyboard.get("characters_present", []) or []
            for char_name in characters_present:
                if char_name not in state.character_assets:
                    continue

                char_data = state.character_assets[char_name]
                char_profile = char_data.get("profile", {})
                char_image = char_data.get("image_data")

                if not char_image:
                    continue

                try:
                    prompt_id = await video_agent.submit_scene_video(
                        project_id=uuid.UUID(state.project_id),
                        scene_id=uuid.UUID(scene_id),
                        character_name=char_name,
                        character_profile=char_profile,
                        character_image_data=char_image,
                        storyboard=storyboard,
                        seed=hash(f"{state.project_id}:{scene_id}:{char_name}") & 0x7FFFFFFF,
                    )
                    submissions.append({
                        "prompt_id": prompt_id,
                        "scene_id": scene_id,
                        "character_name": char_name,
                    })
                    logger.info("submitted for %s in scene %s: %s", char_name, scene_id, prompt_id)
                except Exception as e:
                    logger.warning("submit failed for %s in scene %s: %s", char_name, scene_id, e)
                    errors.append({
                        "scene_id": scene_id,
                        "character_name": char_name,
                        "error": str(e),
                    })

        if not submissions:
            return {"status": "failed", "error": "no videos could be submitted", "errors": errors}

        logger.info("submit phase complete: %d submissions", len(submissions))
        return {
            "submissions": submissions,
            "errors": errors,
            "status": "submit_done",
        }
    except Exception as e:
        logger.exception("submit node failed")
        return {"status": "failed", "error": str(e)}


async def _poll_node(state: VideoGenerationState, video_agent) -> dict:
    if PHASE_POLL not in state.phases:
        return {"status": "poll_skipped"}

    try:
        generated: list[dict] = []
        failed: list[dict] = []
        errors: list[dict] = []

        for sub in state.submissions:
            prompt_id = sub["prompt_id"]
            try:
                result = await video_agent.poll_scene_video(prompt_id)
                if result.status.value == "done" and result.video:
                    scene_id = sub["scene_id"]
                    char_name = sub["character_name"]

                    audio_data = None
                    scene_voices = state.voice_assets.get(scene_id, [])
                    for v in scene_voices:
                        if v.get("character_name") == char_name:
                            audio_data = v.get("audio_data")
                            break

                    generated.append({
                        "prompt_id": prompt_id,
                        "scene_id": scene_id,
                        "character_name": char_name,
                        "video_data": result.video,
                        "audio_data": audio_data,
                        "duration_s": result.duration_s,
                    })
                    logger.info("poll success: %s for %s", prompt_id, char_name)
                else:
                    failed.append({
                        "prompt_id": prompt_id,
                        "scene_id": sub["scene_id"],
                        "character_name": sub.get("character_name", ""),
                        "error": result.error or "unknown",
                    })
                    errors.append({
                        "prompt_id": prompt_id,
                        "error": result.error or "unknown",
                    })
            except Exception as e:
                logger.warning("poll failed for %s: %s", prompt_id, e)
                errors.append({"prompt_id": prompt_id, "error": str(e)})

        if not generated:
            if state.retry_count < state.max_retries:
                logger.info("no videos generated, retry %d/%d", state.retry_count + 1, state.max_retries)
                return {
                    "retry_count": state.retry_count + 1,
                    "status": "retry",
                }
            return {"status": "failed", "error": "all video polls failed", "errors": errors}

        logger.info("poll phase complete: %d done, %d failed", len(generated), len(failed))
        return {
            "generated_videos": generated,
            "errors": state.errors + errors,
            "status": "poll_done",
        }
    except Exception as e:
        logger.exception("poll node failed")
        return {"status": "failed", "error": str(e)}


async def _composite_node(state: VideoGenerationState, video_agent) -> dict:
    if PHASE_COMPOSITE not in state.phases:
        return {"status": "composite_skipped"}

    try:
        composited: list[dict] = []
        for video in state.generated_videos:
            try:
                vdata = video.get("video_data")
                adata = video.get("audio_data")

                thumb = await video_agent.extract_thumbnail(vdata)
                preview = await video_agent.extract_preview(vdata)

                composited.append({
                    "scene_id": video["scene_id"],
                    "character_name": video["character_name"],
                    "video_data": vdata,
                    "audio_data": adata,
                    "thumbnail_data": thumb,
                    "preview_data": preview,
                    "duration_s": video.get("duration_s"),
                })
            except Exception as e:
                logger.warning("composite failed for %s: %s", video.get("prompt_id"), e)

        if not composited:
            return {"status": "composite_partial"}

        logger.info("composite phase complete: %d processed", len(composited))
        return {
            "generated_videos": composited,
            "status": "composite_done",
        }
    except Exception as e:
        logger.exception("composite node failed")
        return {"status": "failed", "error": str(e)}


async def _save_node(state: VideoGenerationState, video_agent) -> dict:
    try:
        saved_ids: list[str] = []
        scene = state.scenes[0] if state.scenes else {}
        storyboard = scene.get("storyboard", {})
        prompt_text = ""

        for video in state.generated_videos:
            try:
                vdata = video.get("video_data")
                adata = video.get("audio_data")
                if not vdata:
                    continue

                saved = await video_agent.save_video(
                    project_id=uuid.UUID(state.project_id),
                    scene_id=uuid.UUID(video["scene_id"]),
                    video_data=vdata,
                    audio_data=adata,
                    prompt=prompt_text or "video generation",
                    negative_prompt="",
                    seed=0,
                    fps=24,
                    params_dict={"width": 768, "height": 1152},
                    provider=await video_agent._resolve_provider(),
                    batch_id=uuid.UUID(state.batch_id) if state.batch_id else None,
                )
                saved_ids.append(str(saved.id))
            except Exception as e:
                logger.warning("save video failed for %s: %s", video.get("character_name"), e)

        logger.info("save phase complete: %d videos saved", len(saved_ids))
        return {"status": "done", "saved_video_ids": saved_ids}
    except Exception as e:
        logger.exception("save node failed")
        return {"status": "failed", "error": str(e)}


# ── Graph Construction ────────────────────────────────────────────────

def build_video_workflow(video_agent):
    workflow = StateGraph(VideoGenerationState)

    async def init_wrapper(state: VideoGenerationState) -> dict:
        return await _init_node(state, video_agent)

    async def submit_wrapper(state: VideoGenerationState) -> dict:
        return await _submit_node(state, video_agent)

    async def poll_wrapper(state: VideoGenerationState) -> dict:
        return await _poll_node(state, video_agent)

    async def composite_wrapper(state: VideoGenerationState) -> dict:
        return await _composite_node(state, video_agent)

    async def save_wrapper(state: VideoGenerationState) -> dict:
        return await _save_node(state, video_agent)

    workflow.add_node(PHASE_INIT, init_wrapper)
    workflow.add_node(PHASE_SUBMIT, submit_wrapper)
    workflow.add_node(PHASE_POLL, poll_wrapper)
    workflow.add_node(PHASE_COMPOSITE, composite_wrapper)
    workflow.add_node(PHASE_SAVE, save_wrapper)

    workflow.set_entry_point(PHASE_INIT)

    def _init_route(state: VideoGenerationState) -> str:
        if state.status == "no_scenes" or state.status == "failed":
            return PHASE_SAVE
        return PHASE_SUBMIT

    def _poll_route(state: VideoGenerationState) -> str:
        if state.status == "retry":
            return PHASE_SUBMIT
        if state.status == "failed":
            return PHASE_SAVE
        return PHASE_COMPOSITE

    def _composite_route(state: VideoGenerationState) -> str:
        return PHASE_SAVE

    workflow.add_conditional_edges(PHASE_INIT, _init_route, {
        PHASE_SUBMIT: PHASE_SUBMIT,
        PHASE_SAVE: PHASE_SAVE,
    })
    workflow.add_edge(PHASE_SUBMIT, PHASE_POLL)
    workflow.add_conditional_edges(PHASE_POLL, _poll_route, {
        PHASE_SUBMIT: PHASE_SUBMIT,
        PHASE_COMPOSITE: PHASE_COMPOSITE,
        PHASE_SAVE: PHASE_SAVE,
    })
    workflow.add_conditional_edges(PHASE_COMPOSITE, _composite_route, {
        PHASE_SAVE: PHASE_SAVE,
    })
    workflow.add_edge(PHASE_SAVE, END)

    return workflow.compile(checkpointer=MemorySaver())
