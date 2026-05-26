from __future__ import annotations

import asyncio
import json
import logging
import uuid
from dataclasses import dataclass, field

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

logger = logging.getLogger(__name__)

PHASE_CLONE = "clone"
PHASE_SYNTHESIZE = "synthesize"
PHASE_PREVIEW = "preview"


@dataclass
class VoiceGenerationState:
    project_id: str
    # Input data
    characters: list[dict] = field(default_factory=list)  # {id, name, profile: {voice_profile, emotion_range}}
    scenes: list[dict] = field(default_factory=list)       # {id, dialogue: [...], storyboard: {emotion, ...}}
    scene_storyboards: dict[str, dict] = field(default_factory=dict)  # scene_id -> storyboard

    # Config
    phases: list[str] = field(default_factory=lambda: [PHASE_CLONE, PHASE_SYNTHESIZE, PHASE_PREVIEW])
    regenerate: bool = False

    # Outputs
    speaker_map: dict[str, str] = field(default_factory=dict)         # character_id -> speaker
    selected_voice_ids: dict[str, str] = field(default_factory=dict)   # character_id -> Voice.id
    clone_voice_assets: list[dict] = field(default_factory=list)
    synthesis_voice_assets: list[dict] = field(default_factory=list)
    preview_voice_assets: list[dict] = field(default_factory=list)

    # Tracking
    batch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    job_id: str = ""
    progress: int = 0
    errors: list[str] = field(default_factory=list)
    status: str = "pending"


async def _clone_node(state: VoiceGenerationState, voice_agent) -> dict:
    if PHASE_CLONE not in state.phases:
        return {"status": "clone_skipped"}

    try:
        speaker_map: dict[str, str] = {}
        voice_ids: dict[str, str] = {}
        clone_assets: list[dict] = []

        for char in state.characters:
            char_id = char.get("id", "")
            name = char.get("name", "unknown")
            profile = char.get("profile", {})
            voice_profile = profile.get("voice_profile", {})
            char_version = char.get("version", 1)

            # Check if already cloned
            cached = await voice_agent._library.get_speaker(char_id)
            if cached and cached.get("version") == char_version and not state.regenerate:
                speaker_map[char_id] = cached["speaker"]
                logger.info("using cached speaker for %s: %s", name, cached["speaker"])
                continue

            # Clone voice
            voice_id = await voice_agent.clone_character_voice(
                project_id=state.project_id,
                character_id=char_id,
                voice_profile=voice_profile,
                character_name=name,
                character_version=char_version,
            )

            saved = await voice_agent._voices.get(uuid.UUID(voice_id))
            if saved:
                speaker_map[char_id] = saved.speaker or ""
                voice_ids[char_id] = voice_id
                clone_assets.append({
                    "voice_id": voice_id,
                    "character_id": char_id,
                    "character_name": name,
                    "speaker": saved.speaker,
                    "version": char_version,
                })

        total = len(clone_assets)
        logger.info("clone phase complete: %d voices cloned", total)
        return {
            "speaker_map": speaker_map,
            "selected_voice_ids": voice_ids,
            "clone_voice_assets": clone_assets,
            "status": "clone_done",
        }
    except Exception as e:
        logger.exception("clone node failed")
        return {"status": "failed", "error": str(e)}


async def _synthesize_node(state: VoiceGenerationState, voice_agent) -> dict:
    if PHASE_SYNTHESIZE not in state.phases:
        return {"status": "synthesize_skipped"}

    try:
        synthesis_assets: list[dict] = []
        semaphore = asyncio.Semaphore(3)

        async def _synth_one_line(
            line: dict, character_name: str, char_id: str,
            voice_profile: dict, emotion_range: dict, speaker: str,
        ) -> dict | None:
            async with semaphore:
                text = line.get("text", "")
                if not text.strip():
                    return None

                # Resolve emotion from line or storyboard
                emotion = line.get("emotion", "neutral")
                speed = voice_agent._provider.__class__.__name__.replace("Adapter", "").lower()
                default_speed = 1.0
                default_pitch = 0

                result = await voice_agent.synthesize_dialogue(
                    speaker=speaker,
                    text=text,
                    emotion=emotion,
                    emotion_range=emotion_range,
                    voice_profile=voice_profile,
                    speed=default_speed,
                    pitch=default_pitch,
                )

                if result.status.value == "done" and result.audio:
                    return {
                        "character_id": char_id,
                        "character_name": character_name,
                        "speaker": speaker,
                        "text": text[:200],
                        "emotion": emotion,
                        "audio": result.audio,
                        "duration_ms": result.duration_ms,
                    }
                return None

        # Build tasks for all scenes
        tasks = []
        for scene in state.scenes:
            scene_id = scene.get("id", "")
            dialogue = scene.get("dialogue", []) or []
            storyboard = state.scene_storyboards.get(scene_id, {})
            scene_emotion = storyboard.get("emotion", "neutral")

            for i, line in enumerate(dialogue):
                char_name = line.get("character", "")
                # Find character
                char_id = ""
                voice_profile = {}
                emotion_range = {}
                for c in state.characters:
                    if c.get("name") == char_name:
                        char_id = c.get("id", "")
                        profile = c.get("profile", {})
                        voice_profile = profile.get("voice_profile", {})
                        emotion_range = profile.get("emotion_range", {})
                        break

                speaker = state.speaker_map.get(char_id, "")
                if not speaker:
                    continue

                line_with_emotion = dict(line)
                if not line_with_emotion.get("emotion"):
                    line_with_emotion["emotion"] = scene_emotion
                line_with_emotion["dialogue_index"] = i
                line_with_emotion["scene_id"] = scene_id

                tasks.append(
                    _synth_one_line(line_with_emotion, char_name, char_id,
                                    voice_profile, emotion_range, speaker)
                )

        results = await asyncio.gather(*tasks)
        synthesis_assets = [r for r in results if r is not None]

        logger.info("synthesize phase complete: %d audio clips", len(synthesis_assets))
        return {
            "synthesis_voice_assets": synthesis_assets,
            "status": "synthesize_done",
        }
    except Exception as e:
        logger.exception("synthesize node failed")
        return {"status": "failed", "error": str(e)}


async def _preview_node(state: VoiceGenerationState, voice_agent) -> dict:
    if PHASE_PREVIEW not in state.phases:
        return {"status": "preview_skipped"}

    try:
        preview_assets: list[dict] = []

        for char in state.characters:
            char_id = char.get("id", "")
            name = char.get("name", "unknown")
            speaker = state.speaker_map.get(char_id, "")
            if not speaker:
                continue

            preview_text = f"Hello, my name is {name}."
            try:
                audio = await voice_agent.preview_voice(speaker, preview_text)
                preview_assets.append({
                    "character_id": char_id,
                    "character_name": name,
                    "speaker": speaker,
                    "preview_text": preview_text,
                    "audio": audio,
                })
            except Exception as e:
                logger.warning("preview failed for %s: %s", name, e)

        logger.info("preview phase complete: %d previews", len(preview_assets))
        return {
            "preview_voice_assets": preview_assets,
            "status": "preview_done",
        }
    except Exception as e:
        logger.exception("preview node failed")
        return {"status": "failed", "error": str(e)}


async def _save_node(state: VoiceGenerationState, voice_agent) -> dict:
    try:
        saved_ids: list[str] = []

        # Save clone voice assets
        for asset in state.clone_voice_assets:
            try:
                saved = await voice_agent._voices.get(uuid.UUID(asset["voice_id"]))
                if saved:
                    saved_ids.append(str(saved.id))
            except Exception as e:
                logger.warning("save clone asset failed: %s", e)

        # Save synthesis assets
        for synth in state.synthesis_voice_assets:
            try:
                char_id = synth.get("character_id", "")
                audio = synth.get("audio")
                if not audio:
                    continue
                saved = await voice_agent.save_voice_asset(
                    project_id=state.project_id,
                    character_id=char_id,
                    audio_data=audio,
                    filename=f"{char_id}_synth_{uuid.uuid4().hex[:8]}.wav",
                    provider="cosyvoice",
                    speaker=synth.get("speaker", ""),
                    emotion=synth.get("emotion", "neutral"),
                    speed=1.0,
                    pitch=0,
                    version=1,
                    scene_id=None,
                    dialogue_index=None,
                )
                saved_ids.append(str(saved.id))
            except Exception as e:
                logger.warning("save synthesis asset failed: %s", e)

        # Save preview assets
        for prev in state.preview_voice_assets:
            try:
                char_id = prev.get("character_id", "")
                audio = prev.get("audio")
                if not audio:
                    continue
                await voice_agent._upload_audio(
                    f"projects/{state.project_id}/voices/{char_id}_preview.wav",
                    audio,
                )
            except Exception as e:
                logger.warning("save preview asset failed: %s", e)

        logger.info("save phase complete: %d assets saved", len(saved_ids))
        return {"status": "done", "saved_voice_ids": saved_ids}

    except Exception as e:
        logger.exception("save node failed")
        return {"status": "failed", "error": str(e)}


def build_voice_workflow(voice_agent):
    """Build the voice generation LangGraph workflow.

    DAG: clone -> synthesize -> preview -> save -> END
    Each node can be skipped by omitting its phase key from state.phases.
    On failure, routes to save to persist completed work.
    """
    workflow = StateGraph(VoiceGenerationState)

    async def clone_wrapper(state: VoiceGenerationState) -> dict:
        return await _clone_node(state, voice_agent)

    async def synth_wrapper(state: VoiceGenerationState) -> dict:
        return await _synthesize_node(state, voice_agent)

    async def preview_wrapper(state: VoiceGenerationState) -> dict:
        return await _preview_node(state, voice_agent)

    async def save_wrapper(state: VoiceGenerationState) -> dict:
        return await _save_node(state, voice_agent)

    workflow.add_node("clone", clone_wrapper)
    workflow.add_node("synthesize", synth_wrapper)
    workflow.add_node("preview", preview_wrapper)
    workflow.add_node("save", save_wrapper)

    workflow.set_entry_point("clone")

    def _route_after_clone(state: VoiceGenerationState) -> str:
        if state.status == "failed":
            return "save"
        return "synthesize"

    def _route_after_synth(state: VoiceGenerationState) -> str:
        if state.status == "failed":
            return "save"
        return "preview"

    def _route_after_preview(state: VoiceGenerationState) -> str:
        return "save"

    workflow.add_conditional_edges("clone", _route_after_clone, {
        "save": "save", "synthesize": "synthesize",
    })
    workflow.add_conditional_edges("synthesize", _route_after_synth, {
        "save": "save", "preview": "preview",
    })
    workflow.add_conditional_edges("preview", _route_after_preview, {
        "save": "save",
    })

    workflow.add_edge("save", END)

    return workflow.compile(checkpointer=MemorySaver())
