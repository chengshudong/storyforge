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
  agents/           AI agents (NovelAgent, StoryAgent, EpisodeAgent, SceneAgent)
  alembic/          Database migrations
  api/v1/           REST endpoints (health, projects, parse, models, generate, jobs, scenes)
  config/           Model registry (models.yaml)
  domain/           ORM models + shared mixins
  infra/            Infrastructure (DB, Redis, MinIO, Celery)
  interfaces/       Provider interfaces (LLM, parser, context, vector, storyboard)
  middleware/       Request ID, exception handlers
  prompts/          LLM prompt templates (summary, extraction, episode, scene)
  providers/        Provider adapters (llm, novel, context, vector)
  repository/       Data access layer (9 model repos + base)
  service/          Business logic
  services/         Shared services (model_router, cache, cost_logger)
  workflows/        LangGraph workflows (novel_processing, story_generation, scene_generation)
frontend/           Next.js application
  src/
    app/            Routes (home, dashboard, upload)
    components/     Shared UI (header, providers, shadcn)
    i18n/           Internationalization (zh/en)
    lib/            API client, zustand store, utilities
infra/              Docker compose, nginx, init scripts
tests/              pytest suite (84+ tests)
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
| 6 | TASK_006 | Character | 🔲 |
| 7 | TASK_007 | Image | 🔲 |
| 8 | TASK_008 | Voice | 🔲 |
| 9 | TASK_009 | Video | 🔲 |
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
| [docs/PROMPTS.md](docs/PROMPTS.md) | Prompt design (story + scene generation) |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture |
| [docs/STARTUP.md](docs/STARTUP.md) | Startup guide |
| [docs/ER_DIAGRAM.md](docs/ER_DIAGRAM.md) | Entity-relationship diagram |
| [docs/MIGRATION.md](docs/MIGRATION.md) | Database migration guide |
| [backend/DATA_LAYER.md](backend/DATA_LAYER.md) | Data layer internals |
| [CHANGELOG.md](CHANGELOG.md) | Release history |

## License

MIT
