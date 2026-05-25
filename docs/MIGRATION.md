# Database Migration Guide

## Current State

```
Revision: 001 (head)
Title: initial schema
Created: 2026-05-25
```

## Migration File

```
backend/alembic/versions/001_initial_schema.py
```

Single baseline migration that creates the complete data layer:

- **3 native PostgreSQL enum types**
- **10 tables** with all constraints

## Enum Types

| Type | Values |
|------|--------|
| `project_status` | PENDING, PARSING, SUMMARIZING, EPISODES, SCENES, CHARACTERS, ASSETS, VOICE, VIDEO, EDITING, COMPLETED, FAILED, CANCELLED |
| `job_status` | PENDING, RUNNING, COMPLETED, FAILED, CANCELLED |
| `asset_type` | IMAGE, CHARACTER_IMAGE, STORYBOARD, OTHER |

All enum values use UPPERCASE, matching SQLAlchemy's Python enum `.name` convention.

## Tables

| # | Table | Rows | Description |
|---|-------|------|-------------|
| 1 | projects | 0+ | Root project entity |
| 2 | episodes | 0+ | Per-project episodes |
| 3 | scenes | 0+ | Per-episode scenes |
| 4 | characters | 0+ | Per-project characters |
| 5 | props | 0+ | Per-project/scene props |
| 6 | assets | 0+ | Generated media files |
| 7 | voices | 0+ | Generated voice audio |
| 8 | videos | 0+ | Generated video clips |
| 9 | jobs | 0+ | Async task tracking |
| 10 | logs | 0+ | Per-job log entries |

## Foreign Key Relationships

```
projects ──1:N──→ episodes ──1:N──→ scenes ──1:N──→ videos
projects ──1:N──→ characters ──1:N──→ voices
projects ──1:N──→ characters ──1:N──→ assets (nullable FK)
projects ──1:N──→ scenes ──1:N──→ assets (nullable FK)
projects ──1:N──→ assets (direct)
projects ──1:N──→ voices (direct)
projects ──1:N──→ props ──FK──→ scenes (nullable)
projects ──1:N──→ jobs ──1:N──→ logs
```

## Commands

```bash
cd backend

# View current state
alembic current

# Apply all pending migrations
alembic upgrade head

# Rollback one version
alembic downgrade -1

# View migration history
alembic history

# Generate a new migration (for TASK_003+)
alembic revision --autogenerate -m "description"
```

## Important: Enum Alignment

SQLAlchemy's `Enum(MyEnum)` generates the type by the Python enum's `.name` (UPPERCASE). The migration must create enum types with matching UPPERCASE labels:

```python
# Migration
sa.Enum("PENDING", "RUNNING", ..., name="job_status", create_type=True)

# Model
status: Mapped[JobStatus] = mapped_column(
    Enum(JobStatus, name="job_status"), ...
)
```

Both the `name=` parameter in the model and the migration enum labels must match. If changing enum values, you must drop and recreate the PostgreSQL enum type.

## Verification

Verify migration state after deployment:

```sql
-- Check version
SELECT * FROM alembic_version;  -- should show: 001

-- Check tables (expect 10 + alembic_version)
SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;

-- Check enum types (expect 3)
SELECT typname, enum_range(NULL::project_status) FROM pg_type
WHERE typname IN ('project_status', 'job_status', 'asset_type');
```
