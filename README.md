# Novel2Drama Agent

Convert novels into serialized short-form drama videos using AI orchestration.

## Architecture

The platform orchestrates existing open-source capabilities. It does not train models — it coordinates generation.

- **Frontend**: Next.js (TypeScript, Tailwind, shadcn/ui, zustand, react-query)
- **Backend**: FastAPI (Python, SQLAlchemy, Pydantic, Celery)
- **Agents**: LangGraph
- **Database**: PostgreSQL + Redis + Qdrant + MinIO

## Quick Start

```bash
cp .env.example .env
docker compose up
```

Open:
- Frontend: http://localhost:3000
- API Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health
- MinIO Console: http://localhost:9001

## Project Structure

```
backend/            FastAPI application
  agents/           AI agents (NovelAgent, StoryAgent, EpisodeAgent, SceneAgent, CharacterAgent, ImageAgent, VoiceAgent, VideoAgent)
  alembic/          Database migrations
  api/v1/           REST endpoints (health, projects, parse, models, generate, jobs, scenes, characters, assets, voices, videos)
  config/           Model registry (models.yaml)
  domain/           ORM models + shared mixins
  infra/            Infrastructure (DB, Redis, MinIO, Celery)
  interfaces/       Provider interfaces (LLM, parser, context, vector, storyboard, image, voice, video)
  middleware/       Request ID, exception handlers
  prompts/          Prompt templates (LLM: summary, extraction, episode, scene, character; Deterministic: image, voice, video)
  providers/        Provider adapters (llm, novel, context, vector, image, voice, video)
  repository/       Data access layer (9 model repos + base)
  service/          Business logic
  services/         Shared services (model_router, cache, cost_logger, voice_library)
  workflows/        LangGraph workflows (novel_processing, story_generation, scene_generation, image_generation, voice_generation, video_generation)
frontend/           Next.js application
  src/
    app/            Routes (home, dashboard, upload)
    components/     Shared UI (header, providers, shadcn)
    i18n/           Internationalization (zh/en)
    lib/            API client, zustand store, utilities
infra/              Docker compose, nginx, init scripts
tests/              pytest suite (308+ tests)
docs/               Documentation
```

## API

| Method | Endpoint | Status | Description |
|--------|----------|--------|-------------|
| GET | `/health` | 200 | Root health check |
| GET | `/api/v1/health` | 200 | API health check |
| POST | `/api/v1/projects` | 201 | Create project |
| GET | `/api/v1/projects` | 200 | List projects (paginated) |
| GET | `/api/v1/projects/{id}` | 200 | Get project by ID |
| POST | `/api/v1/projects/parse` | 201 | Upload and parse novel (TXT/DOCX/EPUB) |
| POST | `/api/v1/generate/story` | 202 | Generate story summary + episode plan |
| GET | `/api/v1/episodes` | 200 | List episodes for a project |
| GET | `/api/v1/episodes/{id}` | 200 | Get episode detail |
| POST | `/api/v1/episodes/{id}/scenes` | 202 | Generate scene storyboards for episode |
| GET | `/api/v1/scenes?episode_id=` | 200 | List scenes (paginated, by episode) |
| GET | `/api/v1/scenes/{id}` | 200 | Get scene with storyboard detail |
| PATCH | `/api/v1/scenes/{id}` | 200 | Edit scene or regenerate via LLM feedback |
| GET | `/api/v1/models` | 200 | List available models and tasks |
| GET | `/api/v1/models/health` | 200 | Provider health status |
| POST | `/api/v1/models/test` | 200 | Test model generation |
| GET | `/api/v1/jobs` | 200 | List jobs (?project_id= filter) |
| GET | `/api/v1/jobs/{id}` | 200 | Get job by ID |
| POST | `/api/v1/characters/generate` | 202 | Generate character profiles via LLM |
| GET | `/api/v1/characters?project_id=` | 200 | List characters (paginated, with role/locked filters) |
| GET | `/api/v1/characters/{id}` | 200 | Get character with full profile |
| GET | `/api/v1/characters/{id}/versions` | 200 | Get character version history |
| PATCH | `/api/v1/characters/{id}` | 200 | Edit character (lock check 409) |
| POST | `/api/v1/characters/{id}/rollback` | 200 | Rollback to version N |
| POST | `/api/v1/assets/generate` | 202 | Generate images via ComfyUI (char_ref/char_scene/bg/prop/cover) |
| POST | `/api/v1/assets/select` | 200 | Approve/select generated assets |
| POST | `/api/v1/assets/favorite` | 200 | Favorite/unfavorite assets |
| GET | `/api/v1/assets?project_id=&character_id=&scene_id=&asset_type=` | 200 | List assets (paginated, with filters) |
| GET | `/api/v1/assets/{id}` | 200 | Get asset with generation metadata |
| PATCH | `/api/v1/assets/{id}` | 200 | Edit asset (lock/unlock, feedback, regenerate) |
| DELETE | `/api/v1/assets/{id}` | 204 | Delete asset (409 if locked) |
| POST | `/api/v1/voices/generate` | 202 | Generate voices via CosyVoice (clone + synthesize + preview) |
| GET | `/api/v1/voices?project_id=&character_id=&scene_id=` | 200 | List voices (paginated, with filters) |
| GET | `/api/v1/voices/{id}` | 200 | Get voice with full metadata |
| GET | `/api/v1/voices/{id}/preview` | 200 | Voice preview audio clip (audio/wav) |
| DELETE | `/api/v1/voices/{id}` | 204 | Delete voice (409 if selected) |
| POST | `/api/v1/videos/generate` | 202 | Generate videos via Wan2.1/CogVideoX (init+submit+poll+composite+save) |
| GET | `/api/v1/videos?project_id=&scene_id=&selected=` | 200 | List videos (paginated, with filters) |
| GET | `/api/v1/videos/{id}` | 200 | Get video metadata (20 fields) |
| GET | `/api/v1/videos/{id}/stream` | 200 | Stream MP4 video file |
| GET | `/api/v1/videos/{id}/thumbnail` | 200 | Keyframe thumbnail image (image/jpeg) |
| GET | `/api/v1/videos/{id}/preview` | 200 | 3s preview clip (video/mp4) |
| POST | `/api/v1/videos/select` | 200 | Mark videos as selected/unselected |
| DELETE | `/api/v1/videos/{id}` | 204 | Delete video (409 if locked) |

Error format: `{"code":"ERROR_CODE","message":"Human message","data":{}}`

## Provider Stack

| Capability | Provider | Adapter |
|------------|----------|---------|
| LLM Primary | DeepSeek (deepseek-chat) | OpenAI-compatible |
| LLM Fallback | OpenAI → Anthropic → Gemini → OpenRouter → Local | Multi-adapter |
| Embedding | sentence-transformers (all-MiniLM-L6-v2, 384-dim) | Local |
| Novel Parsing | Unstructured | NovelParser |
| Long Context | LlamaIndex + SentenceTransformer | ContextStore |
| Vector Storage | Qdrant | VectorStore |
| Image Generation | ComfyUI (SDXL + InstantID) | ComfyUIAdapter |
| Voice Synthesis | CosyVoice / GPT-SoVITS | CosyVoiceAdapter / GPTSoVITSAdapter |
| Video Generation | Wan2.1 / CogVideoX | Wan21Adapter / CogVideoXAdapter |
| Workflow | LangGraph | Built-in |

## Phase Progress

| Phase | Task | Description | Status |
|-------|------|-------------|--------|
| 1 | TASK_001 | Infrastructure | ✅ |
| 2 | TASK_002 | Data Layer | ✅ |
| 3 | TASK_003 | Novel Parsing | ✅ |
| 3A | TASK_003A | Model Gateway | ✅ |
| 4 | TASK_004 | Story Generation | ✅ |
| 5 | TASK_005 | Scene Generation / Storyboard | ✅ |
| 6 | TASK_006 | Character | ✅ |
| 7 | TASK_007 | Image | ✅ |
| 8 | TASK_008 | Voice | ✅ |
| 9 | TASK_009 | Video | ✅ |
| 10 | TASK_010 | Editing | 🔲 |
| 11 | TASK_011 | Production | 🔲 |

## Development

### Backend

```bash
cd backend
pip install -r requirements.txt
alembic upgrade head
uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Tests

```bash
pytest tests/ -v
```

## Documentation

| Document | Description |
|----------|-------------|
| [docs/MASTER_PROMPT.md](docs/MASTER_PROMPT.md) | Vision, architecture, product flow |
| [docs/RULES.md](docs/RULES.md) | Engineering rules (mandatory) |
| [docs/MODEL_POLICY.md](docs/MODEL_POLICY.md) | Model routing, timeout, retry, cache, cost policies |
| [docs/INTEGRATION_POLICY.md](docs/INTEGRATION_POLICY.md) | OSS integration policy |
| [docs/OSS_REGISTRY.md](docs/OSS_REGISTRY.md) | Approved provider registry |
| [docs/PROMPTS.md](docs/PROMPTS.md) | Prompt design (story + scene + character + image) |
| [docs/ASSET_GUIDE.md](docs/ASSET_GUIDE.md) | Asset generation pipeline guide |
| [docs/VOICE_GUIDE.md](docs/VOICE_GUIDE.md) | Voice generation pipeline guide |
| [docs/VIDEO_GUIDE.md](docs/VIDEO_GUIDE.md) | Video generation pipeline guide |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture |
| [docs/STARTUP.md](docs/STARTUP.md) | Startup guide |
| [docs/ER_DIAGRAM.md](docs/ER_DIAGRAM.md) | Entity-relationship diagram |
| [docs/MIGRATION.md](docs/MIGRATION.md) | Database migration guide |
| [backend/DATA_LAYER.md](backend/DATA_LAYER.md) | Data layer internals |
| [CHANGELOG.md](CHANGELOG.md) | Release history |

## License

MIT
