# CHANGELOG

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
- **PostgreSQL enum values**: Uses UPPERCASE (Python enum `.name`) for consistency across model/migration/database

### Fixed
- `timezone` not imported in models.py (used in Log.timestamp default)
- Enum name mismatch: model `projectstatus` vs migration `project_status` → aligned via explicit `name=` parameter
- Enum value mismatch: lowercase vs UPPERCASE → recreated PostgreSQL enums with UPPERCASE labels
- Nested transaction pattern: `async with db.begin()` removed from endpoint handlers
- Migration `server_default` values: updated to UPPERCASE (`"PENDING"`)

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
