# Architecture

## Overview

Novel2Drama Agent is an AI orchestration platform that converts novels into serialized short-form drama videos.

```
┌──────────────────────────────────────────────────────┐
│                    Frontend (Next.js)                 │
│                  localhost:3000                       │
└────────────────────────┬─────────────────────────────┘
                         │ HTTP
┌────────────────────────▼─────────────────────────────┐
│                   Backend (FastAPI)                   │
│                  localhost:8000                       │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────────┐  │
│  │  API/v1  │ │ Service  │ │     Repository       │  │
│  └──────────┘ └──────────┘ └──────────────────────┘  │
│  ┌──────────┐ ┌──────────┐ ┌──────────────────────┐  │
│  │  Domain  │ │  Infra   │ │     Middleware        │  │
│  └──────────┘ └──────────┘ └──────────────────────┘  │
└──────┬──────────┬──────────┬──────────┬──────────────┘
       │          │          │          │
┌──────▼──┐ ┌─────▼────┐ ┌──▼───┐ ┌───▼──────┐
│Postgres │ │  Redis   │ │MinIO │ │  Qdrant  │
│  :5432  │ │  :6379   │ │:9000 │ │  :6333   │
└─────────┘ └──────────┘ └──────┘ └──────────┘
                         │
┌────────────────────────▼─────────────────────────────┐
│                   Celery Worker                       │
│              (async task execution)                   │
└──────────────────────────────────────────────────────┘
```

## Clean Architecture Layers

```
api ──→ service ──→ repository ──→ domain
  │                                  │
  └────────── infra ◄────────────────┘
```

1. **api** — HTTP handlers, request/response DTOs
2. **service** — Business logic, orchestration
3. **repository** — Data access, transactions
4. **domain** — Entity models, interfaces
5. **infra** — External systems (DB, Redis, MinIO, Celery)

No circular imports. Each layer depends only inward.

## Agent System (Phase 2+)

```
Agent ──→ Interface ──→ Adapter ──→ Provider
```

- **Agent**: LangGraph workflow node
- **Interface**: Abstract contract
- **Adapter**: Provider-specific implementation
- **Provider**: External OSS (ComfyUI, CosyVoice, etc.)

All providers isolated, replaceable, containerized, versioned.

## Data Flow

```
Novel Upload
  → Parse (NovelAgent)
  → Story Summary (StoryAgent)
  → Episode Plan (EpisodeAgent)
  → Scenes (SceneAgent)
  → Characters (CharacterAgent)
  → Images (ImageAgent)
  → Voice (VoiceAgent)
  → Video (VideoAgent)
  → Editing (ExportAgent)
  → MP4 Export
```

## Services

| Service  | Port  | Purpose                     |
|----------|-------|-----------------------------|
| Frontend | 3000  | Next.js web UI              |
| Backend  | 8000  | FastAPI REST API            |
| Postgres | 5432  | Relational data             |
| Redis    | 6379  | Cache + Celery broker       |
| MinIO    | 9000  | Object storage              |
| MinIO UI | 9001  | MinIO console               |
| Qdrant   | 6333  | Vector database             |
| Celery   | —     | Background task worker      |
