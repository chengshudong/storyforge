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
  alembic/          Database migrations
  api/v1/           REST endpoints (health, projects, jobs)
  domain/           ORM models + shared mixins
  infra/            Infrastructure (DB, Redis, MinIO, Celery)
  middleware/       Request ID, exception handlers
  prompts/          LLM prompt templates
  repository/       Data access layer (8 model repos + base)
  service/          Business logic
  workflows/        Workflow state (ProjectState)
frontend/           Next.js application
  src/
    app/            Routes (home, dashboard, upload)
    components/     Shared UI (header, providers, shadcn)
    i18n/           Internationalization (zh/en)
    lib/            API client, zustand store, utilities
infra/              Docker compose, nginx, init scripts
tests/              pytest suite (27 tests)
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
| GET | `/api/v1/jobs` | 200 | List jobs (?project_id= filter) |
| GET | `/api/v1/jobs/{id}` | 200 | Get job by ID |

Error format: `{"code":"ERROR_CODE","message":"Human message","data":{}}`

## Data Layer

10 PostgreSQL tables with native enum types. See [docs/ER_DIAGRAM.md](docs/ER_DIAGRAM.md) for the ER diagram and [docs/MIGRATION.md](docs/MIGRATION.md) for migration guide.

Models: Project → Episode → Scene → Video; Project → Character → Voice; Project → Asset; Project → Job → Log

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
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | System architecture |
| [docs/STARTUP.md](docs/STARTUP.md) | Startup guide |
| [docs/ER_DIAGRAM.md](docs/ER_DIAGRAM.md) | Entity-relationship diagram |
| [docs/MIGRATION.md](docs/MIGRATION.md) | Database migration guide |
| [docs/INTEGRATION_POLICY.md](docs/INTEGRATION_POLICY.md) | OSS integration policy |
| [docs/OSS_REGISTRY.md](docs/OSS_REGISTRY.md) | Approved provider registry |
| [backend/DATA_LAYER.md](backend/DATA_LAYER.md) | Data layer internals |
| [CHANGELOG.md](CHANGELOG.md) | Release history |

## License

MIT
