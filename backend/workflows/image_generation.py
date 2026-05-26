from __future__ import annotations

import asyncio
import json
import logging
import random
import uuid
from dataclasses import dataclass, field

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from api.v1.schemas import AssetGenerationParams
from domain.models import AssetType

logger = logging.getLogger(__name__)

PHASE_CHAR_REF = "char_ref"
PHASE_UPLOAD = "upload_refs"
PHASE_CHAR_SCENE = "char_scene"
PHASE_BG = "bg"
PHASE_PROP = "prop"
PHASE_COVER = "cover"


@dataclass
class ImageGenerationState:
    project_id: str
    # Input data
    characters: list[dict] = field(default_factory=list)  # profiles with id, name, profile
    scenes: list[dict] = field(default_factory=list)       # storyboard + id
    props: list[dict] = field(default_factory=list)        # name, description, prop_type
    project_meta: dict = field(default_factory=dict)       # title, description, world_setting

    # Config
    phases: list[str] = field(default_factory=lambda: [PHASE_CHAR_REF, PHASE_CHAR_SCENE, PHASE_BG, PHASE_PROP])
    variant_count: int = 4
    params: AssetGenerationParams = field(default_factory=AssetGenerationParams)

    # Generation outputs
    char_ref_assets: list[dict] = field(default_factory=list)
    # {character_id, name, ref_comfyui_filename, asset_ids: [...]}
    face_ref_map: dict[str, str] = field(default_factory=dict)  # character_id → comfyui filename
    scene_assets: list[dict] = field(default_factory=list)
    bg_assets: list[dict] = field(default_factory=list)
    prop_assets: list[dict] = field(default_factory=list)
    cover_assets: list[dict] = field(default_factory=list)

    # Batch tracking
    batch_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    total_generated: int = 0
    current_phase: str = "pending"

    # Control
    status: str = "pending"
    error: str | None = None


def _seeds_for_variants(count: int, base_seed: int = 0) -> list[int]:
    if base_seed == 0:
        base_seed = random.randint(1, 2_147_483_647)
    return [base_seed + i * 1000 for i in range(count)]


async def _char_ref_node(state: ImageGenerationState, image_agent) -> dict:
    if PHASE_CHAR_REF not in state.phases:
        return {"current_phase": PHASE_CHAR_REF, "status": "char_ref_skipped"}
    try:
        results: list[dict] = []
        for char in state.characters:
            name = char.get("name", "unknown")
            profile = char.get("profile", {})
            seeds = _seeds_for_variants(state.variant_count)
            char_assets: list[dict] = []

            for i, seed in enumerate(seeds):
                prompt_id = await image_agent.generate_char_ref(name, profile, seed, state.params)
                poll_result = await image_agent.poll(prompt_id)
                if poll_result.status.value == "done" and poll_result.images:
                    for img_idx, img_data in enumerate(poll_result.images):
                        fn = poll_result.filenames[img_idx] if poll_result.filenames and img_idx < len(poll_result.filenames) else f"{name}_ref_v{i}_{img_idx}.png"
                        rendered_prompt = await _get_rendered_prompt(image_agent, "char_ref", name, profile, seed, state.params)
                        char_assets.append({
                            "image_data": img_data,
                            "filename": fn,
                            "seed": seed,
                            "variant": i,
                            "prompt": rendered_prompt.get("positive", ""),
                            "negative_prompt": rendered_prompt.get("negative", ""),
                        })

            if char_assets:
                results.append({
                    "character_id": char.get("id"),
                    "name": name,
                    "ref_comfyui_filename": char_assets[0]["filename"],  # Use first variant as face ref
                    "assets": char_assets,
                })

        return {
            "char_ref_assets": results,
            "current_phase": PHASE_CHAR_REF,
            "status": "char_ref_done",
        }
    except Exception as e:
        logger.exception("char_ref phase failed")
        return {"status": "failed", "error": str(e)}


async def _upload_refs_node(state: ImageGenerationState, image_agent) -> dict:
    if PHASE_UPLOAD not in state.phases and PHASE_CHAR_SCENE not in state.phases:
        return {"current_phase": PHASE_UPLOAD, "status": "upload_skipped"}
    try:
        face_ref_map: dict[str, str] = {}
        for entry in state.char_ref_assets:
            char_id = entry.get("character_id")
            name = entry.get("name", "unknown")
            # Upload the first (best) variant as the face reference for InstantID
            assets = entry.get("assets", [])
            if not assets:
                continue
            first_asset = assets[0]
            comfyui_name = await image_agent.upload_face_ref(
                f"{name}_face_ref.png", first_asset["image_data"],
            )
            face_ref_map[str(char_id)] = comfyui_name
            entry["ref_comfyui_filename"] = comfyui_name

        return {
            "face_ref_map": face_ref_map,
            "current_phase": PHASE_UPLOAD,
            "status": "upload_done",
        }
    except Exception as e:
        logger.exception("upload_refs phase failed")
        return {"status": "failed", "error": str(e)}


async def _char_scene_node(state: ImageGenerationState, image_agent) -> dict:
    if PHASE_CHAR_SCENE not in state.phases:
        return {"current_phase": PHASE_CHAR_SCENE, "status": "char_scene_skipped"}
    try:
        results: list[dict] = []
        face_map = state.face_ref_map
        for scene in state.scenes:
            storyboard = scene.get("storyboard", {}) or {}
            char_present = storyboard.get("characters_present", [])
            char_actions = storyboard.get("character_actions", {})

            for char_name in char_present:
                # Find matching character profile
                char = next((c for c in state.characters if c.get("name") == char_name), None)
                if char is None:
                    continue
                char_id = str(char.get("id", ""))
                face_ref = face_map.get(char_id)
                if not face_ref:
                    continue  # No face ref uploaded — skip this character

                profile = char.get("profile", {})
                action = char_actions.get(char_name, "")
                seeds = _seeds_for_variants(max(1, state.variant_count // 2))  # Fewer variants for scene

                for i, seed in enumerate(seeds):
                    prompt_id = await image_agent.generate_char_scene(
                        char_name, profile, storyboard, face_ref, seed, state.params, action,
                    )
                    poll_result = await image_agent.poll(prompt_id)
                    if poll_result.status.value == "done" and poll_result.images:
                        for img_idx, img_data in enumerate(poll_result.images):
                            fn = poll_result.filenames[img_idx] if poll_result.filenames and img_idx < len(poll_result.filenames) else f"{char_name}_scene_v{i}_{img_idx}.png"
                            results.append({
                                "character_id": char.get("id"),
                                "scene_id": scene.get("id"),
                                "image_data": img_data,
                                "filename": fn,
                                "seed": seed,
                                "variant": i,
                            })

        return {
            "scene_assets": results,
            "current_phase": PHASE_CHAR_SCENE,
            "status": "char_scene_done",
        }
    except Exception as e:
        logger.exception("char_scene phase failed")
        return {"status": "failed", "error": str(e)}


async def _bg_node(state: ImageGenerationState, image_agent) -> dict:
    if PHASE_BG not in state.phases:
        return {"current_phase": PHASE_BG, "status": "bg_skipped"}
    try:
        results: list[dict] = []
        for scene in state.scenes:
            storyboard = scene.get("storyboard", {}) or {}
            seeds = _seeds_for_variants(state.variant_count)
            for i, seed in enumerate(seeds):
                prompt_id = await image_agent.generate_background(storyboard, seed, state.params)
                poll_result = await image_agent.poll(prompt_id)
                if poll_result.status.value == "done" and poll_result.images:
                    for img_idx, img_data in enumerate(poll_result.images):
                        fn = poll_result.filenames[img_idx] if poll_result.filenames and img_idx < len(poll_result.filenames) else f"bg_scene_{scene.get('id', 'unknown')}_v{i}_{img_idx}.png"
                        results.append({
                            "scene_id": scene.get("id"),
                            "image_data": img_data,
                            "filename": fn,
                            "seed": seed,
                            "variant": i,
                        })
        return {
            "bg_assets": results,
            "current_phase": PHASE_BG,
            "status": "bg_done",
        }
    except Exception as e:
        logger.exception("bg phase failed")
        return {"status": "failed", "error": str(e)}


async def _prop_node(state: ImageGenerationState, image_agent) -> dict:
    if PHASE_PROP not in state.phases:
        return {"current_phase": PHASE_PROP, "status": "prop_skipped"}
    try:
        results: list[dict] = []
        for prop in state.props:
            name = prop.get("name", "unknown")
            description = prop.get("description", "")
            prop_type = prop.get("prop_type", "")
            seeds = _seeds_for_variants(state.variant_count)
            for i, seed in enumerate(seeds):
                prompt_id = await image_agent.generate_prop(name, description, prop_type, seed, state.params)
                poll_result = await image_agent.poll(prompt_id)
                if poll_result.status.value == "done" and poll_result.images:
                    for img_idx, img_data in enumerate(poll_result.images):
                        fn = poll_result.filenames[img_idx] if poll_result.filenames and img_idx < len(poll_result.filenames) else f"prop_{name}_v{i}_{img_idx}.png"
                        results.append({
                            "prop_name": name,
                            "image_data": img_data,
                            "filename": fn,
                            "seed": seed,
                            "variant": i,
                        })
        return {
            "prop_assets": results,
            "current_phase": PHASE_PROP,
            "status": "prop_done",
        }
    except Exception as e:
        logger.exception("prop phase failed")
        return {"status": "failed", "error": str(e)}


async def _cover_node(state: ImageGenerationState, image_agent) -> dict:
    if PHASE_COVER not in state.phases:
        return {"current_phase": PHASE_COVER, "status": "cover_skipped"}
    try:
        meta = state.project_meta
        title = meta.get("title", meta.get("name", "Untitled"))
        description = meta.get("description", "")
        world_setting = json.dumps(meta.get("world_setting", {}))
        key_characters = ", ".join(c.get("name", "") for c in state.characters[:3])
        seeds = _seeds_for_variants(state.variant_count)
        results: list[dict] = []
        for i, seed in enumerate(seeds):
            prompt_id = await image_agent.generate_cover(
                title=title,
                description=description,
                world_setting=world_setting,
                key_characters=key_characters,
                seed=seed,
                params=state.params,
            )
            poll_result = await image_agent.poll(prompt_id)
            if poll_result.status.value == "done" and poll_result.images:
                for img_idx, img_data in enumerate(poll_result.images):
                    fn = poll_result.filenames[img_idx] if poll_result.filenames and img_idx < len(poll_result.filenames) else f"cover_v{i}_{img_idx}.png"
                    results.append({
                        "image_data": img_data,
                        "filename": fn,
                        "seed": seed,
                        "variant": i,
                    })
        return {
            "cover_assets": results,
            "current_phase": PHASE_COVER,
            "status": "cover_done",
        }
    except Exception as e:
        logger.exception("cover phase failed")
        return {"status": "failed", "error": str(e)}


async def _save_node(state: ImageGenerationState, image_agent, asset_repo) -> dict:
    try:
        batch_id = uuid.UUID(state.batch_id)
        project_id = uuid.UUID(state.project_id)
        saved_ids: list[str] = []
        total = 0

        # Save char_ref assets
        for entry in state.char_ref_assets:
            char_id = uuid.UUID(entry["character_id"]) if entry.get("character_id") else None
            for asset_data in entry.get("assets", []):
                saved = await image_agent.save_asset(
                    project_id=project_id,
                    asset_type=AssetType.CHARACTER_IMAGE,
                    image_data=asset_data["image_data"],
                    filename=asset_data["filename"],
                    prompt=asset_data.get("prompt", ""),
                    negative_prompt=asset_data.get("negative_prompt", ""),
                    seed=asset_data["seed"],
                    params_dict=state.params.model_dump(),
                    character_id=char_id,
                    batch_id=batch_id,
                )
                saved_ids.append(str(saved.id))
                total += 1

        # Save scene assets
        for asset_data in state.scene_assets:
            char_id = uuid.UUID(asset_data["character_id"]) if asset_data.get("character_id") else None
            scene_id = uuid.UUID(asset_data["scene_id"]) if asset_data.get("scene_id") else None
            saved = await image_agent.save_asset(
                project_id=project_id,
                asset_type=AssetType.CHARACTER_IMAGE,
                image_data=asset_data["image_data"],
                filename=asset_data["filename"],
                prompt="",
                negative_prompt="",
                seed=asset_data["seed"],
                params_dict=state.params.model_dump(),
                character_id=char_id,
                scene_id=scene_id,
                batch_id=batch_id,
            )
            saved_ids.append(str(saved.id))
            total += 1

        # Save bg assets
        for asset_data in state.bg_assets:
            scene_id = uuid.UUID(asset_data["scene_id"]) if asset_data.get("scene_id") else None
            saved = await image_agent.save_asset(
                project_id=project_id,
                asset_type=AssetType.STORYBOARD,
                image_data=asset_data["image_data"],
                filename=asset_data["filename"],
                prompt="",
                negative_prompt="",
                seed=asset_data["seed"],
                params_dict=state.params.model_dump(),
                scene_id=scene_id,
                batch_id=batch_id,
            )
            saved_ids.append(str(saved.id))
            total += 1

        # Save prop assets
        for asset_data in state.prop_assets:
            saved = await image_agent.save_asset(
                project_id=project_id,
                asset_type=AssetType.IMAGE,
                image_data=asset_data["image_data"],
                filename=asset_data["filename"],
                prompt="",
                negative_prompt="",
                seed=asset_data["seed"],
                params_dict=state.params.model_dump(),
                batch_id=batch_id,
            )
            saved_ids.append(str(saved.id))
            total += 1

        # Save cover assets
        for asset_data in state.cover_assets:
            saved = await image_agent.save_asset(
                project_id=project_id,
                asset_type=AssetType.COVER,
                image_data=asset_data["image_data"],
                filename=asset_data["filename"],
                prompt="",
                negative_prompt="",
                seed=asset_data["seed"],
                params_dict=state.params.model_dump(),
                batch_id=batch_id,
            )
            saved_ids.append(str(saved.id))
            total += 1

        return {
            "total_generated": total,
            "status": "done",
            "error": None,
        }
    except Exception as e:
        logger.exception("save node failed")
        return {"status": "failed", "error": str(e)}


async def _get_rendered_prompt(agent, phase: str, name: str, profile: dict, seed: int, params: AssetGenerationParams) -> dict:
    """Helper to re-render the prompt text for saving in asset metadata."""
    from prompts.image import CharacterRefPrompt
    return CharacterRefPrompt().render(name, profile)


def build_image_workflow(image_agent, asset_repo) -> StateGraph:
    graph = StateGraph(ImageGenerationState)

    async def char_ref(state: ImageGenerationState) -> dict:
        return await _char_ref_node(state, image_agent)

    async def upload_refs(state: ImageGenerationState) -> dict:
        return await _upload_refs_node(state, image_agent)

    async def char_scene(state: ImageGenerationState) -> dict:
        return await _char_scene_node(state, image_agent)

    async def bg(state: ImageGenerationState) -> dict:
        return await _bg_node(state, image_agent)

    async def prop(state: ImageGenerationState) -> dict:
        return await _prop_node(state, image_agent)

    async def cover(state: ImageGenerationState) -> dict:
        return await _cover_node(state, image_agent)

    async def save(state: ImageGenerationState) -> dict:
        return await _save_node(state, image_agent, asset_repo)

    graph.add_node(PHASE_CHAR_REF, char_ref)
    graph.add_node(PHASE_UPLOAD, upload_refs)
    graph.add_node(PHASE_CHAR_SCENE, char_scene)
    graph.add_node(PHASE_BG, bg)
    graph.add_node(PHASE_PROP, prop)
    graph.add_node(PHASE_COVER, cover)
    graph.add_node("save", save)

    graph.set_entry_point(PHASE_CHAR_REF)

    def _after_phase(state: ImageGenerationState, next_key: str) -> str:
        if state.status == "failed":
            return "save"
        return next_key

    graph.add_conditional_edges(PHASE_CHAR_REF, lambda s: _after_phase(s, PHASE_UPLOAD),
                                {PHASE_UPLOAD: PHASE_UPLOAD, "save": "save"})
    graph.add_conditional_edges(PHASE_UPLOAD, lambda s: _after_phase(s, PHASE_CHAR_SCENE),
                                {PHASE_CHAR_SCENE: PHASE_CHAR_SCENE, "save": "save"})
    graph.add_conditional_edges(PHASE_CHAR_SCENE, lambda s: _after_phase(s, PHASE_BG),
                                {PHASE_BG: PHASE_BG, "save": "save"})
    graph.add_conditional_edges(PHASE_BG, lambda s: _after_phase(s, PHASE_PROP),
                                {PHASE_PROP: PHASE_PROP, "save": "save"})
    graph.add_conditional_edges(PHASE_PROP, lambda s: _after_phase(s, PHASE_COVER),
                                {PHASE_COVER: PHASE_COVER, "save": "save"})
    graph.add_conditional_edges(PHASE_COVER, lambda s: _after_phase(s, "save"),
                                {"save": "save"})
    graph.add_edge("save", END)

    checkpointer = MemorySaver()
    return graph.compile(checkpointer=checkpointer)
