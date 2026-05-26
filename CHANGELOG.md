# CHANGELOG

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
