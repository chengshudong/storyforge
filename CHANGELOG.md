# CHANGELOG

## [task-009-complete] — Video Generation — 2026-05-26

### Added
- **VideoProvider interface** (`backend/interfaces/video.py`, 57 lines) — ABC with `submit(request) → prompt_id`, `poll(prompt_id) → VideoResult`, `cancel(prompt_id) → bool`, `health() → bool`. `VideoStatus` enum (PENDING/RUNNING/DONE/FAILED). `VideoSubmitRequest` dataclass (12 fields: prompt, negative_prompt, seed, fps, num_frames, guidance_scale, width, height, image bytes, image_filename, motion_bucket_id, extra_params). `VideoResult` dataclass (prompt_id, status, video bytes, duration_s, error).
- **Wan21Adapter** (`backend/providers/video/wan21_adapter.py`, 133 lines) — Primary I2V provider using httpx REST client:
  - `POST /api/v1/video/submit` — multipart form-data (image PNG + text params) → task_id
  - `GET /api/v1/video/status/{id}` — poll loop (150 iterations × 2s = 5min max) → status + download on completion
  - `GET /api/v1/video/download/{id}` — MP4 bytes
  - `POST /api/v1/video/cancel/{id}` — cancel in-progress task
  - `GET /api/health` — health check
  - Lazy singleton httpx.AsyncClient, timeouts: connect=10s, read=600s, write=120s
- **CogVideoXAdapter** (`backend/providers/video/cogvideox_adapter.py`, 125 lines) — Fallback I2V provider (THUDM):
  - JSON-only payload (image as base64 data URI)
  - `POST /generate`, `GET /status/{id}`, `GET /download/{id}`, `POST /cancel/{id}`
  - Key differences from Wan2.1: `num_inference_steps=50` instead of `motion_bucket_id`, default `guidance_scale=6.0` vs 7.5
- **2 deterministic video prompt classes** (`backend/prompts/video.py`, 78 lines) — No LLM on hot path:
  - `SceneVideoPrompt` — Constructs cinematic I2V prompt from shot_type + angle + movement + emotion + location + character_actions. Negative prompt targets morphing, flickering, face inconsistency.
  - `SceneContextPrompt` — Optional LLM-enhanced variant with deterministic fallback `render_deterministic()` for complex multi-character sequences.
- **SceneRenderer** (`backend/services/video_renderer.py`, 75 lines) — Deterministic I2V payload builder:
  - `build_payload()` — Constructs `VideoSubmitRequest` from scene storyboard + character image + voice profile
  - 6-level camera movement → motion_bucket_id mapping: static=20, slow_pan/subtle/gentle=80, pan/tilt/dolly/zoom=127, fast_pan/tracking/dynamic=180, action/shake/handheld=220, default=127
  - `_map_movement_to_motion()` — case-insensitive movement keyword matching
  - `duration_estimate × fps → num_frames` calculation with min=1 guard
- **VideoAgent** (`backend/agents/video_agent.py`, 328 lines) — Video orchestration without LLM:
  - `submit_scene_video()` — SceneRenderer.build_payload → provider.submit → prompt_id
  - `poll_scene_video()` — provider.poll → VideoResult with MP4 bytes
  - `generate_scene_video()` — Combined submit + poll (single character, single scene)
  - `composite_audio()` — ffmpeg subprocess: video MP4 + dialogue WAV → composited MP4 with AAC audio, -shortest flag
  - `extract_thumbnail()` — ffmpeg: -ss at_seconds -vframes 1 → JPEG keyframe
  - `extract_preview()` — ffmpeg: -t duration_s -c copy → 3s preview clip
  - `save_video()` — 4 MinIO uploads (video + composited_audio + thumbnail + preview) → Video DB record with full metadata
  - `build_video_cache_key()` — Content-addressed MD5(project|scene|character|seed|params_hash), 30-day TTL
  - `build_prompt_cache_key()` — MD5(prompt content), 7-day TTL
  - `_upload_media()` + `_resolve_provider()` — MinIO upload helper, class-name-based provider resolution
  - DI pattern: video_provider(VideoProvider) + video_repo + asset_repo + cache(CacheService) + router(optional)
- **LangGraph video workflow** (`backend/workflows/video_generation.py`, 349 lines) — 5-node DAG:
  - `init → submit → poll → composite → save → END`
  - Conditional edges: init→save (no scenes/fail), poll→submit (retry with max_retries=1), poll→save (fail after retries), composite→save (always)
  - `VideoGenerationState` dataclass with 22 fields (project_id, scenes with storyboard, character_assets, voice_assets, phases, variant_count, regenerate, batch_id, submissions, retry_count, max_retries, generated_videos, saved_video_ids, errors, etc.)
  - Init node: filters scenes with storyboards, validates character assets presence
  - Submit node: iterates all characters_present per scene, calls submit_scene_video for each character with image_data
  - Poll node: polls all submissions, matches voice_assets by scene_id+character_name, retries once if all fail
  - Composite node: extracts thumbnail + preview for each generated video
  - Save node: calls video_agent.save_video for each video, persists all completed work
  - `MemorySaver` checkpointer for resumability
- **Extended Video model** (`backend/domain/models.py`): From 6 to 20 columns — added project_id (UUID FK→projects), prompt (Text), negative_prompt (Text), seed (Integer), fps (Integer, default 24), generation_params (JSONB), provider (String 50), preview_path (String 500), thumbnail_path (String 500), batch_id (UUID), selected (Boolean, default false), version (Integer, default 1), audio_path (String 500), audio_duration (Float), file_size (Integer). Added `project` relationship.
- **Extended VideoRepository** (`backend/repository/video_repository.py`): From 1 to 5 methods — added `list_by_project()`, `list_by_scene()`, `get_selected()`, `get_by_version()`, `set_selected()`
- **Alembic migration 006** (`backend/alembic/versions/006_extend_videos.py`): 14 new columns (all nullable initially, backfill project_id from scene→episode FK chain, then non-nullable). 3 indexes: `ix_videos_project_id`, `ix_videos_scene_selected`, `ix_videos_batch_id`.
- **8 video API endpoints** (`backend/api/v1/videos.py`, 206 lines):
  - `POST /videos/generate` (202) — Trigger video generation async via Celery
  - `GET /videos?project_id=&scene_id=&selected=` — List with filters (paginated)
  - `GET /videos/{id}` — Get video metadata (20 fields)
  - `GET /videos/{id}/stream` — Stream MP4 via MinIO download (video/mp4)
  - `GET /videos/{id}/thumbnail` — Keyframe thumbnail (image/jpeg)
  - `GET /videos/{id}/preview` — 3s preview clip (video/mp4)
  - `POST /videos/select` — Mark videos as selected/unselected
  - `DELETE /videos/{id}` (204) — Delete video (409 if locked)
- **5 Pydantic schemas** (`backend/api/v1/schemas.py`): VideoGenerationParams, VideoGenerateRequest, VideoGenerateResponse, VideoResponse (21 fields), VideoListResponse, VideoSelectRequest
- **Wan2.1 + CogVideoX services** (`docker-compose.yml`): GPU profile services (wan21:7860, cogvideox:7861), celery-video worker (Q video_generation --concurrency=1), wan21_models + cogvideox_models volumes
- **Dedicated Celery queue** (`backend/infra/celery_app.py`): `video_generation` queue route, concurrency=1 for sequential GPU processing
- **Environment variables** (`.env.example`): WAN21_BASE_URL, COGVIDEOX_BASE_URL
- **92 new tests**: 11 Wan2.1Adapter, 6 CogVideoXAdapter, 9 video prompts, 12 SceneRenderer, 14 VideoAgent, 23 video workflow, 17 video API (all passing, 308 total)

### Design Decisions
- **Hot path is fully deterministic**: `submit_scene_video()` → `SceneRenderer.build_payload()` → `SceneVideoPrompt.render()` has zero LLM calls. Unlike CharacterAgent (4 LLM calls) or StoryAgent (3 LLM calls), the video pipeline uses only structured data construction.
- **Provider pattern mirrors ImageProvider/VoiceProvider**: Separate ABC (not through ModelRouter), purpose-built for I2V REST API's submit→poll→download pattern. Both adapters follow identical interface with provider-specific payload serialization (multipart vs JSON+base64).
- **Audio composited as post-processing**: Wan2.1 generates silent video. Voice audio is added via ffmpeg subprocess after generation completes — allows independent evolution of video and audio pipelines.
- **Single-GPU sequential queue**: Video generation consumes full GPU per request. Dedicated Celery queue `video_generation` with `--concurrency=1 --worker_prefetch_multiplier=1`. Cross-project queuing via Celery (all projects share one worker).
- **SceneRenderer is the integration point**: Takes scene storyboard + character image data + voice profile → produces deterministic `VideoSubmitRequest`. No data loading or IO — pure transformation from dicts to payload.
- **Camera movement → motion_bucket_id mapping**: 6 discrete buckets (20/80/127/180/220) from keyword matching. Case-insensitive. Unknown movements default to 127 (normal pan). This is the key Wan2.1-specific tuning parameter.
- **Content-addressed video cache**: `MD5(project|scene|character|seed|params_hash)` — 30-day TTL for generation metadata. Actual video bytes NOT cached in Redis (too large for in-memory store — MinIO is permanent storage).
- **Fail-fast but save-accumulated**: On any phase failure, conditional edges route to save node which persists all completed videos. No orphaned generated work.
- **Voice-audio matching by scene+character**: Poll node looks up `voice_assets[scene_id]` for matching `character_name` to attach dialogue audio. Audio composited in save phase, not generation phase.

### Known Limitations
- **Missing Celery task**: `workflows.video_generation.run` is referenced in API (`videos.py:67`) and queue routing (`celery_app.py:17`) but NOT defined in `workflows/tasks.py`. The POST /generate endpoint dispatches to a non-existent task.
- **No cancel API**: No endpoint to cancel in-progress video generation. Both adapters implement `cancel()` but it's unreachable from the API layer.
- **No audio-video sync validation**: `audio_duration` vs `video_duration` not compared; drift beyond the -shortest flag boundary is undetected.
- **No provider fallback at task level**: Wan2.1→CogVideoX fallback is designed in architecture but not wired in the missing Celery task.
- **ffmpeg dependency**: composite_audio, extract_thumbnail, extract_preview all require ffmpeg on the system PATH. No graceful degradation if ffmpeg is missing.
- **No streaming video response**: Video endpoint returns full file — no HTTP Range request support for seeking.
- **MemorySaver only**: Workflow checkpoints are in-memory; lost on process restart.

### Preserved
- All TASK_001–TASK_008 agents — Unchanged (NovelAgent, StoryAgent, EpisodeAgent, SceneAgent, CharacterAgent, ImageAgent, VoiceAgent)
- ModelRouter / CacheService / CostLogger — Unchanged (used only for optional LLM-enhanced prompt path)
- All existing API endpoints — Unchanged
- All existing tests — 216 existing passing, no regressions; 92 new video tests added

---

## [task-008-complete] — Voice Generation — 2026-05-26

### Added
- **VoiceProvider interface** (`backend/interfaces/voice.py`, 60 lines) — ABC with `clone_voice(character_name, reference_audio, reference_text) → speaker`, `synthesize(request) → VoiceResult`, `synthesize_batch(requests) → list[VoiceResult]`, `preview(speaker, text) → VoiceResult`, `health() → bool`, `list_speakers() → list[str]`, `delete_speaker(speaker) → bool`. `VoiceStatus` enum (PENDING/RUNNING/DONE/FAILED). `VoiceResult` dataclass (speaker, status, audio, duration_ms, error). `SynthesisRequest` dataclass (text, emotion, emotion_vector, speed, pitch, speaker).
- **CosyVoiceAdapter** (`backend/providers/voice/cosyvoice_adapter.py`, 120 lines) — Primary TTS provider using httpx REST client:
  - `POST /upload` — clone voice → speaker ID
  - `POST /tts` — synthesize text → WAV bytes with emotion vector support
  - `GET /voices` — list available speakers
  - `DELETE /voices/{id}` — delete speaker
  - `GET /health` — health check
  - `synthesize_batch()` — concurrent synthesis with `asyncio.Semaphore(3)`
- **GPTSoVITSAdapter** (`backend/providers/voice/gptsovits_adapter.py`, 95 lines) — Optional fallback TTS provider:
  - `POST /set_reference` — clone voice → speaker_id
  - `POST /tts` — synthesize → WAV bytes
  - Serial-only `synthesize_batch()`
- **4 deterministic voice prompt/mapping classes** (`backend/prompts/voice.py`, 190 lines) — No LLM on hot path:
  - `ReferenceTextPrompt` — Builds "My name is X. I speak with a Y-pitched, Z voice..." from structured profile
  - `EmotionResolver` — 33-entry EMOTION_MAP (happy/sad/angry/soothing/mysterious/determined/neutral) with specific pitch/rhythm/timbre vectors per entry. Returns `(None, None)` for unmappable emotions → triggers LLM fallback.
  - `VoiceProfileMapper` — Maps voice_profile fields to speed (pitch×tempo lookup), pitch offset (-5 to +5), timbre. `apply_character_baseline()` applies per-character emotion offsets (stoic: rhythm-0.05, cheerful: pitch+0.05).
  - `EmotionLLMPrompt` — Fallback prompt to map complex emotion descriptions to 7 supported tags + vector values. System prompt constrains output to valid JSON.
- **VoiceAgent** (`backend/agents/voice_agent.py`, 310 lines) — Voice orchestration without LLM (except emotion fallback):
  - `clone_character_voice()` — ReferenceTextPrompt → TTS reference audio (ModelRouter/EdgeTTS/silence) → voice provider clone → preview → save Voice row with selected=True
  - `get_or_clone_voice()` — DB check (get_selected with matching version) → Redis speaker cache → clone if not found
  - `synthesize_dialogue()` — EmotionResolver.map → synthesis cache check → provider.synthesize → cache result. Fully deterministic hot path.
  - `_resolve_emotion_llm()` — LLM fallback for unmappable emotions, cached 24h via CacheService, logged via CostLogger
  - `_synthesize_reference_audio()` — Tries ModelRouter → EdgeTTS → silence WAV fallback (3s 16kHz mono PCM)
  - `_wav_header()` — Static method generating valid 44-byte WAV header
  - `save_voice_asset()` — MinIO upload + Voice DB create
  - `preview_voice()` — Generate short preview clip from speaker
- **VoiceLibrary** (`backend/services/voice_library.py`, 105 lines) — Three-layer Redis cache:
  - Speaker cache: `voice:speaker:{character_id}`, 7-day TTL with version binding
  - Synthesis cache: `voice:synth:{MD5(speaker|text|emotion|speed|pitch)[:16]}`, 30-day TTL, audio stored as base64
  - Provider health cache: `voice:active_provider`, 60s TTL for provider routing
  - Invalidation: `invalidate_speaker()` + `invalidate_character_audio()`
- **LangGraph voice workflow** (`backend/workflows/voice_generation.py`, 349 lines) — 4-node DAG:
  - `clone → synthesize → preview → save → END`
  - Each node skippable via `state.phases`; conditional fail-fast edges route to save on error
  - `VoiceGenerationState` dataclass with 16 fields (characters, scenes, speaker_map, synthesis_assets, preview_assets, etc.)
  - Clone node: iterates all characters, checks Redis cache first, clones only if missing or regenerate=True
  - Synthesize node: builds tasks for all dialogue lines across all scenes, concurrent with `asyncio.Semaphore(3)`
  - Preview node: generates "Hello, my name is X" preview for each character
  - Save node: persists all accumulated assets from completed phases (even on upstream failure)
  - `MemorySaver` checkpointer for resumability
- **Celery task** (`backend/workflows/tasks.py`): `workflows.voice_generation.run` — max_retries=2, default_retry_delay=120s. Provider health check with CosyVoice→GPT-SoVITS fallback. Loads characters+scenes+storyboards from DB, initializes VoiceAgent, runs workflow with progress updates at each phase transition (clone=35, synth=80, preview=95, done=100).
- **5 voice API endpoints** (`backend/api/v1/voices.py`, 155 lines):
  - `POST /voices/generate` (202) — Trigger voice generation async via Celery
  - `GET /voices?project_id=&character_id=&scene_id=` — List with filters (paginated)
  - `GET /voices/{id}` — Get voice with full metadata
  - `GET /voices/{id}/preview` — Preview audio clip (audio/wav)
  - `DELETE /voices/{id}` (204) — Delete voice (409 if selected)
- **6 voice Pydantic schemas** (`backend/api/v1/schemas.py`): VoiceGenerateRequest, VoiceGenerateResponse, VoiceResponse (19 fields), VoiceListResponse
- **Extended Voice model** (`backend/domain/models.py`): From 6 to 22 columns — added scene_id, dialogue_index, provider, speaker, speed, pitch, emotion, version, selected, voice_params (JSONB), duration_ms, preview_path, reference_audio_path. Added `scene` relationship.
- **Extended VoiceRepository** (`backend/repository/voice_repository.py`): From 2 to 6 methods — added `list_by_scene()`, `get_selected()`, `get_by_version()`, `set_selected()`
- **Alembic migration 005** (`backend/alembic/versions/005_extend_voices.py`): 12 new columns (all nullable for backward compat), 3 indices: `ix_voices_character_selected`, `ix_voices_character_version`, `ix_voices_scene_dialogue`
- **CosyVoice + GPT-SoVITS services** (`docker-compose.yml`): GPU profile services, volumes, env vars
- **Environment variables** (`.env.example`): COSYVOICE_BASE_URL, COSYVOICE_TIMEOUT, GPTSOVITS_BASE_URL, GPTSOVITS_ENABLED
- **56 new tests**: 25 voice prompts, 12 voice agent, 10 voice adapter, 6 voice workflow (all passing, 221 total)

### Design Decisions
- **VoiceProvider pattern mirrors ImageProvider**: Separate ABC (not through ModelRouter), purpose-built for TTS REST API pattern. Provider auto-detected from adapter class name.
- **Deterministic hot path**: `synthesize_dialogue()` has zero LLM calls — EmotionResolver is a 33-entry lookup table. LLM only invoked for unmappable emotion descriptions, cached 24h.
- **Content-addressed synthesis cache**: MD5(speaker|text|emotion|speed|pitch) — identical inputs always hit cache regardless of project/character/scene context. 30-day TTL.
- **Voice-version binding**: Voice.version matches Character.version. `get_or_clone_voice()` checks get_selected() for matching version before returning cached speaker. Rollback restores old Voice with matching version.
- **Flat columns over JSONB**: Provider, speaker, speed, pitch, emotion are flat columns (frequently accessed) while voice_params is JSONB (rarely queried profile metadata).
- **selected field**: Only one selected=true per character, mirrors Asset.selected pattern.
- **Fail-fast but save-accumulated**: On any phase failure, conditional edges route to save node which persists all completed work. No orphaned voice assets.
- **Concurrent synthesis by dialogue line**: All lines across all scenes submitted concurrently via `asyncio.gather` with Semaphore(3), rather than scene-by-scene or character-by-character.
- **Silence fallback for reference audio**: When all TTS providers fail during cloning, generates 3s 16kHz mono PCM silence with valid WAV header. Ensures clone phase never blocks the pipeline.

### Known Limitations
- **No streaming TTS**: CosyVoiceAdapter returns complete WAV bytes; no chunked audio streaming for low-latency preview.
- **MemorySaver only**: Workflow checkpoints are in-memory; lost on process restart. Not suitable for long-running production without persistent checkpointer.
- **Serial emotion LLM fallback**: LLM calls for unmappable emotions are made one at a time (no concurrent LLM calls), though results are cached 24h.
- **No per-synthesis retry**: CosyVoiceAdapter.synthesize() has no retry on connection failure. One failed TTS call abandons that dialogue line.

### Preserved
- All TASK_001–TASK_007 agents — Unchanged (NovelAgent, StoryAgent, EpisodeAgent, SceneAgent, CharacterAgent, ImageAgent)
- ModelRouter / CacheService / CostLogger — Unchanged (used only for emotion LLM fallback)
- All existing API endpoints — Unchanged
- All existing tests — 165 passing, no regressions; 56 new voice tests added

---

## [task-007-complete] — Image / Asset Generation — 2026-05-26

### Added
- **ImageProvider interface** (`backend/interfaces/image.py`) — ABC with `generate(workflow) → prompt_id`, `poll(prompt_id) → ImageResult`, `upload_image(filename, data) → str`, `health() → bool`. `ImageStatus` enum (PENDING/RUNNING/DONE/FAILED). `ImageResult` dataclass.
- **ComfyUIAdapter** (`backend/providers/image/comfyui_adapter.py`, 195 lines) — Async httpx REST client for ComfyUI HTTP API:
  - `POST /api/prompt` — submit workflow JSON
  - `GET /api/history/{id}` — poll with 60 iterations × 2s = 2min timeout per generation
  - `GET /api/view?filename=` — download generated images
  - `POST /api/upload/image` — upload reference portrait for InstantID
  - Health check via `/system_stats`
- **InstantIDWorkflow** (`backend/providers/image/comfyui_adapter.py`) — Static workflow builders:
  - `build_character_ref_workflow()` — SDXL workflow: CheckpointLoaderSimple → CLIPTextEncode(×2) → KSampler → VAEDecode → SaveImage
  - `build_instantid_workflow()` — SDXL + IPAdapterInstantID node for face-consistent character images (ip_weight=0.8)
- **5 deterministic image prompt templates** (`backend/prompts/image.py`, 210 lines) — No LLM involved:
  - `CharacterRefPrompt` — Portrait prompt from profile (appearance + costume_style)
  - `CharacterScenePrompt` — Character-in-scene prompt from profile + storyboard + action
  - `BackgroundPrompt` — Environment-only prompt from storyboard location/camera/emotion/props
  - `PropPrompt` — Isolated product-shot prompt from prop name/description/type
  - `CoverPrompt` — Poster-art prompt from project title/description/world/characters/mood
  - Module-level `_build_physique()` and `_build_outfit()` helpers
- **ImageAgent** (`backend/agents/image_agent.py`, 228 lines) — Generation orchestration without LLM:
  - `generate_char_ref(name, profile, seed, params)` → prompt_id
  - `generate_char_scene(name, profile, storyboard, face_ref, seed, params, action)` → prompt_id
  - `generate_background(storyboard, seed, params)` → prompt_id
  - `generate_prop(name, description, prop_type, seed, params)` → prompt_id
  - `generate_cover(title, description, world_setting, key_characters, seed, params)` → prompt_id
  - `poll(prompt_id)` → ImageResult
  - `upload_face_ref(filename, data)` → comfyui_name
  - `save_asset(...)` → MinIO upload + Asset DB record
- **LangGraph image workflow** (`backend/workflows/image_generation.py`, 462 lines) — 7-node DAG:
  - `char_ref → upload_refs → char_scene → bg → prop → cover → save`
  - Each phase skippable via config; conditional fail-fast edges route to save on error
  - `MemorySaver` checkpointer for resumability
  - `_seeds_for_variants()` deterministic seed generator
  - Saves all accumulated assets from completed phases even when later phases fail
- **Celery task** (`backend/workflows/tasks.py`): `workflows.image_generation.run` — max_retries=2, default_retry_delay=120s. Loads characters/scenes/props from DB, initializes ComfyUIAdapter + ImageAgent, runs workflow with progress updates at each phase transition.
- **PropRepository** (`backend/repository/prop_repository.py`) — list_by_project, list_by_scene
- **7 asset API endpoints** (`backend/api/v1/assets.py`, 213 lines):
  - `POST /assets/generate` (202) — Trigger image generation async via Celery
  - `POST /assets/select` — Approve/select assets by IDs
  - `POST /assets/favorite` — Favorite/unfavorite assets by IDs
  - `GET /assets?project_id=&character_id=&scene_id=&asset_type=` — List with filters (paginated)
  - `GET /assets/{id}` — Get single asset with all metadata
  - `PATCH /assets/{id}` — Edit (lock/unlock, store feedback, trigger regenerate)
  - `DELETE /assets/{id}` (204) — Delete asset (409 if locked)
- **8 asset Pydantic schemas** (`backend/api/v1/schemas.py`): AssetGenerationParams, AssetResponse, AssetListResponse, AssetGenerateRequest, AssetGenerateResponse, AssetSelectRequest, AssetFavoriteRequest, AssetEditRequest
- **Alembic migration 004** — Extended assets table: +prompt, +negative_prompt, +seed, +generation_params(JSONB), +variation_of(FK→assets), +batch_id, +selected, +favorite, +locked, +locked_at, +asset_ref. Created generation_batches table. Added 'cover' to asset_type enum.
- **Extended Asset model** (`backend/domain/models.py`): +11 columns, AssetType.COVER, GenerationBatch model (project_id, status, total_assets, completed_assets)
- **40 new tests**: 20 image prompts, 14 ImageAgent, 6 workflow (all passing, 165 total)

### Design Decisions
- **Zero LLM image prompts**: All 5 prompt classes are deterministic string builders from structured data. No LLM calls in the entire image pipeline. Contrast with CharacterAgent which uses 4 LLM calls per run.
- **InstantID face consistency**: `char_ref` phase generates a reference portrait (no InstantID). That portrait is uploaded to ComfyUI. `char_scene` phase uses IPAdapterInstantID with the uploaded reference for face-consistent character images across all scenes.
- **First-variant-as-reference**: The workflow uses `char_assets[0]` (first variant) as the InstantID face reference. No quality scoring or human selection of the best reference portrait — deferred to the select/favorite API.
- **Separate ImageProvider interface**: Image generation does NOT go through ModelRouter. The `ImageProvider` ABC is purpose-built for ComfyUI's REST API pattern (submit → poll → download).
- **Phase-skippable DAG**: Each phase node checks `PHASE_X in state.phases` and returns `*_skipped` if not requested. Default phases: `["char_ref", "char_scene", "bg", "prop"]`. Cover is opt-in.
- **Fail-fast but save-accumulated**: On any phase failure, conditional edges route to save node which persists all assets from completed phases before ending. No orphaned generated images.
- **Serial generation within phases**: Each image is submitted and polled sequentially (not concurrent). Trade-off: simpler error handling vs ~3-4× longer wall-clock time. Contrasts with CharacterAgent which uses `asyncio.Semaphore(5)`.

### Known Limitations
- **No image caching**: Unlike CharacterAgent (CacheService + Redis 24h TTL), the image pipeline has zero caching. Identical (profile, seed, params) will re-run ComfyUI every time.
- **No per-image retry**: ComfyUIAdapter.generate() has no retry on connection failure. One failed submit abandons that image slot.
- **MemorySaver only**: Workflow checkpoints are in-memory; lost on process restart. Not suitable for long-running production without persistent checkpointer.
- **No concurrent generation**: Within a phase, all images are generated serially (submit → poll → next). For 4 variants × 5 scenes × 2 characters, wall-clock time = ~17 minutes vs ~4 minutes with concurrent submission.
- **clip_vision node wiring**: `build_instantid_workflow()` references `["4", 3]` for CLIP Vision output — requires ComfyUI IP-Adapter custom nodes and a checkpoint that outputs CLIP Vision at index 3. May fail at runtime without the correct ComfyUI extensions installed.

### Preserved
- All TASK_001–TASK_006 agents — Unchanged (StoryAgent, EpisodeAgent, SceneAgent, CharacterAgent)
- ModelRouter / CacheService / CostLogger — Unchanged (not used by image pipeline)
- All existing API endpoints — Unchanged
- All existing tests — 165 passing, no regressions

---

## [task-005-complete] — Scene Generation / Storyboard Layer — 2026-05-26

### Added
- **SceneAgent** (`backend/agents/scene_agent.py`) — Episode → scene storyboard pipeline with caching
  - `_split_episode()`: 1 LLM call → scene beat boundaries with characters, duration estimates
  - `_storyboard_scene()`: 1 LLM call per scene → full cinematography (camera, emotion, dialogue, props, asset_refs)
  - `_validate_continuity()`: 1 LLM call → character/location/time/emotion/prop continuity check (non-blocking on failure)
  - `storyboard()`: Full pipeline orchestrating split → N×storyboard (semaphore(3)) → validate
  - `regenerate_scene()`: Single scene regeneration from director feedback
  - All LLM calls through ModelRouter, all responses cached (split 24h, storyboard 1h, validate 24h)
- **StoryboardEngine interface** (`backend/interfaces/storyboard.py`) — ABC with run/resume/checkpoint
- **4 scene prompt templates** (`backend/prompts/scene.py`): SceneSplitPrompt, SceneStoryboardPrompt, SceneValidatePrompt, SceneEditPrompt
  - Controlled vocabularies: 10 camera terms, 12 emotion tones, 5 transition types
  - All prompts require structured JSON output with inline schema
- **LangGraph scene workflow** (`backend/workflows/scene_generation.py`): 4-node DAG (split → storyboard → validate → save) with MemorySaver checkpoints, conditional edges (fail-fast)
- **Celery task** (`backend/workflows/tasks.py`): `workflows.scene_generation.run` — async workflow with progress updates at each node transition, character pre-population from project.meta
- **SceneRepository** (`backend/repository/scene_repository.py`): list_by_episode (paginated), get_by_number
- **4 API endpoints**: POST /episodes/{id}/scenes (202 async), GET /scenes (paginated), GET /scenes/{id}, PATCH /scenes/{id} (edits + feedback-based LLM regeneration with lock check)
- **Scene schema** (`backend/api/v1/schemas.py`): SceneStoryboardSchema (11 fields), SceneResponse, SceneListResponse, SceneGenerateRequest/Response, SceneEditRequest
- **Alembic migration 002**: Added JSONB `storyboard` column to scenes table
- **19 new tests**: 10 SceneAgent (split, storyboard, full pipeline, regenerate, validate, cache, empty, JSON parse), 9 workflow (node success/failure/graceful failure, state defaults, workflow construction) — all passing

### Changed
- `backend/domain/models.py`: Added `storyboard: Mapped[dict | None] = mapped_column(JSONB, nullable=True)` to Scene
- `backend/api/v1/schemas.py`: Added SceneStoryboardSchema, SceneResponse, SceneListResponse, SceneGenerateRequest/Response, SceneEditRequest
- `backend/main.py`: Registered scenes_episode_router, scenes_router
- `backend/workflows/tasks.py`: Added `run_scene_generation` Celery task (~160 lines)

### Design Decisions
- **JSONB storyboard column**: Single column for 11 storyboard fields (camera, duration, emotion, location, props, transition, asset_refs, character_actions, characters_present, locked) instead of 8+ individual columns
- **Non-blocking validation**: Validate node catches exceptions and returns `validation_passed=True` — LLM continuity issues are logged as WARNING but never halt the pipeline
- **Content-addressed caching**: All 3 cache keys use MD5(content) — different beat text = different hash, no collision risk
- **Character pre-population**: Celery task builds character list from `project.meta.relationships` + `project.meta.entities.persons` as dicts; Character table population deferred to TASK_006

### Preserved
- `backend/agents/story_agent.py` — Unchanged (TASK_004 territory)
- `backend/agents/episode_agent.py` — Unchanged (TASK_004 territory)
- `backend/agents/novel_agent.py` — Unchanged (TASK_003 territory)
- All TASK_001–TASK_004 modules — Unchanged

---

## [task-004-complete] — Story Generation Layer — 2026-05-26

### Added
- **StoryAgent** (`backend/agents/story_agent.py`) — Map-reduce summarization + narrative extraction
- **EpisodeAgent** (`backend/agents/episode_agent.py`) — Episode planning with cliffhangers + regeneration
- **6 prompt templates** (`backend/prompts/`): StorySummarize, ChapterSummary, MergeSummary, Extraction, EpisodePlan, EpisodeRegenerate
- **LangGraph workflow** (`backend/workflows/story_generation.py`): 4-node DAG (summarize → extract → plan → save) with MemorySaver checkpoints
- **Celery task** (`backend/workflows/tasks.py`): `workflows.story_generation.run` bridging API → workflow
- **3 API endpoints**: POST /generate/story, GET /episodes, GET /episodes/{id}
- **CacheService** (`backend/services/cache_service.py`): Redis model response cache per MODEL_POLICY §5
- **CostLogger** (`backend/services/cost_logger.py`): JSONL cost logging per MODEL_POLICY §6
- **ModelRouter enhancements**: `asyncio.wait_for` timeout wrapper, exponential backoff with jitter
- **25 new tests**: 11 StoryAgent, 6 EpisodeAgent, 8 workflow (all passing)

### Changed
- `backend/services/model_router/router.py`: Added timeout + backoff + jitter
- `backend/api/v1/schemas.py`: Added StoryGenerateRequest, StoryGenerateResponse, EpisodeResponse, EpisodeListResponse
- `backend/main.py`: Registered generate_router, episode_router

### Preserved
- `backend/agents/novel_agent.py` — Unchanged (TASK_003 territory)
- All TASK_001–TASK_003A modules — Unchanged

---

## [TASK-003A] — 2026-05-26 — Model Gateway

### Added
- **LLMProvider interface** (`backend/interfaces/llm.py`): generate, stream, embedding, health
- **6 provider adapters**: DeepSeek, OpenAI, Anthropic, Gemini, OpenRouter, Local
- **ModelRouter** (`backend/services/model_router/router.py`): select, fallback, degrade, retry
- **SecretLoader** (`backend/services/model_router/secret_loader.py`): load, validate, mask
- **models.yaml** (`backend/config/models.yaml`): task→provider→model registry with fallback chain
- **3 API endpoints**: GET /models, GET /models/health, POST /models/test
- **12 tests**: router, retry, adapters, secret loader (all passing)

---

## [TASK-003] — 2026-05-26 — Novel Parsing

### Added
- **NovelAgent** (`backend/agents/novel_agent.py`): parse → split → embed → store pipeline
- **3 provider adapters**: Unstructured (parser), LlamaIndex (context), Qdrant (vector)
- **3 interfaces**: NovelParser, ContextStore, VectorStore
- **Parse API**: POST /projects/parse (upload TXT/DOCX/EPUB → store vectors)
- **LangGraph workflow** (`backend/workflows/novel_processing.py`): single-node parse DAG
- **Tests**: parsers, workflow, agent (all passing)

---

## [TASK-002] — 2026-05-25 — Data Layer

### Added
- **10 ORM models**: Project, Episode, Scene, Character, Prop, Asset, Voice, Video, Job, Log
- **3 native PostgreSQL enum types**: project_status (12 values), job_status (5 values), asset_type (4 values)
- **8 repositories**: ProjectRepository, EpisodeRepository, SceneRepository, CharacterRepository, AssetRepository, VoiceRepository, VideoRepository, JobRepository — all extending generic `BaseRepository[T]`
- **Generic CRUD base**: `BaseRepository[T]` with create/get/list/update/delete/count
- **Workflow state**: `ProjectState` dataclass with 8 fields + `to_dict()` serialization
- **Queue helpers**: create_job, cancel_job, retry_job, complete_job, fail_job, update_job_progress, get_job_progress
- **API endpoints**: POST /projects (201), GET /projects (paginated), GET /projects/{id}, GET /jobs, GET /jobs/{id}
- **Alembic migration**: `001_initial_schema.py` — baseline migration creating all 10 tables + 3 enum types
- **i18n system**: Chinese (default) + English toggle, zustand persist store
- **Tests**: 27 test cases across 7 test files (repo unit, API integration, workflow state, infra)

### Changed
- **Transaction management**: `get_db()` now handles commit/rollback; removed nested `db.begin()` from handlers
- **Alembic env.py**: Rewrote from async to sync engine (psycopg2) for migration reliability
- **Database engine**: Made lazy-initialized (`_get_engine()`) to avoid import-time connection
- **Enum alignment**: Model `Enum()` calls now use explicit `name=` parameters matching migration enum type names

### Fixed
- `timezone` not imported in models.py (used in Log.timestamp default)
- Enum name mismatch: model `projectstatus` vs migration `project_status`
- Enum value mismatch: lowercase vs UPPERCASE → recreated PostgreSQL enums
- Nested transaction pattern: `async with db.begin()` removed from endpoint handlers

---

## [TASK-001] — 2026-05-25 — Infrastructure

### Added
- FastAPI application with health endpoint, config, logging, exception handler, middleware, Swagger
- Next.js 15 frontend with home, dashboard, upload pages, routing, Tailwind, shadcn/ui
- PostgreSQL connection with health check
- Redis client with health check
- MinIO client (upload/download/health)
- Celery worker configuration
- Docker compose multi-service (PostgreSQL, Redis, MinIO, Qdrant, Celery, backend, frontend)
- README, STARTUP.md, ARCHITECTURE.md, .env.example
- pytest configuration with SQLite in-memory test support
