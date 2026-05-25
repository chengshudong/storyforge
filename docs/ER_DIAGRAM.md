# ER Diagram — Novel2Drama Data Layer

```
┌──────────────────────────────────────────────────────────────────────────┐
│                          ENUM TYPES                                       │
│                                                                           │
│  project_status:  PENDING | PARSING | SUMMARIZING | EPISODES | SCENES   │
│                   CHARACTERS | ASSETS | VOICE | VIDEO | EDITING          │
│                   COMPLETED | FAILED | CANCELLED                         │
│                                                                           │
│  job_status:      PENDING | RUNNING | COMPLETED | FAILED | CANCELLED    │
│                                                                           │
│  asset_type:      IMAGE | CHARACTER_IMAGE | STORYBOARD | OTHER           │
└──────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                             TABLES                                       │
└─────────────────────────────────────────────────────────────────────────┘

 projects
 ┌────────────────────────────┬──────────────────────┐
 │ id            UUID         │ PK                   │
 │ name          VARCHAR(255) │ NOT NULL             │
 │ description   TEXT         │                      │
 │ source_file   VARCHAR(500) │                      │
 │ source_format VARCHAR(10)  │                      │
 │ status        project_status│ NOT NULL DEFAULT PENDING│
 │ meta          JSON         │                      │
 │ created_at    TIMESTAMPTZ  │ NOT NULL DEFAULT now()│
 │ updated_at    TIMESTAMPTZ  │ NOT NULL DEFAULT now()│
 └────────────────────────────┴──────────────────────┘
     │
     │ 1:N
     ├──────────────────────────────────────────────────┐
     │                                                  │
     ▼                                                  ▼
 episodes                                       characters
 ┌───────────────────────────┬────────────────┐  ┌──────────────────────────┬────────────────┐
 │ id           UUID         │ PK             │  │ id          UUID          │ PK             │
 │ project_id   UUID         │ FK→projects    │  │ project_id  UUID          │ FK→projects    │
 │ episode_number INTEGER    │ NOT NULL       │  │ name        VARCHAR(255)  │ NOT NULL       │
 │ title        VARCHAR(255) │ NOT NULL       │  │ description TEXT          │                │
 │ summary      TEXT         │                │  │ role        VARCHAR(50)   │                │
 │ status       project_status│ NOT NULL      │  │ traits      JSON          │                │
 │ created_at   TIMESTAMPTZ  │ NOT NULL       │  │ status      project_status│ NOT NULL       │
 │ updated_at   TIMESTAMPTZ  │ NOT NULL       │  │ created_at  TIMESTAMPTZ   │ NOT NULL       │
 └───────────────────────────┴────────────────┘  │ updated_at  TIMESTAMPTZ   │ NOT NULL       │
     │                                            └──────────────────────────┴────────────────┘
     │ 1:N                                            │ 1:N          │ 1:N
     ▼                                                ▼              ▼
 scenes                                       voices          assets (FK)
 ┌──────────────────────────┬────────────────┐  ┌──────────────────────────┬────────────────┐
 │ id           UUID         │ PK             │  │ id          UUID         │ PK             │
 │ episode_id   UUID         │ FK→episodes    │  │ project_id  UUID         │ FK→projects    │
 │ scene_number INTEGER      │ NOT NULL       │  │ character_id UUID         │ FK→characters  │
 │ title        VARCHAR(255) │                │  │ file_path   VARCHAR(500) │ NOT NULL       │
 │ description  TEXT         │                │  │ file_size   INTEGER      │                │
 │ dialogue     JSON         │                │  │ duration    FLOAT        │                │
 │ status       project_status│ NOT NULL      │  │ status      project_status│ NOT NULL      │
 │ created_at   TIMESTAMPTZ  │ NOT NULL       │  │ created_at  TIMESTAMPTZ  │ NOT NULL       │
 │ updated_at   TIMESTAMPTZ  │ NOT NULL       │  │ updated_at  TIMESTAMPTZ  │ NOT NULL       │
 └───────────────────────────┴────────────────┘  └──────────────────────────┴────────────────┘
     │ 1:N
     ▼
 videos
 ┌──────────────────────────┬────────────────┐
 │ id           UUID         │ PK             │
 │ scene_id     UUID         │ FK→scenes      │
 │ file_path    VARCHAR(500) │ NOT NULL       │
 │ duration     FLOAT        │                │
 │ resolution   VARCHAR(20)  │                │
 │ status       project_status│ NOT NULL      │
 │ created_at   TIMESTAMPTZ  │ NOT NULL       │
 │ updated_at   TIMESTAMPTZ  │ NOT NULL       │
 └──────────────────────────┴────────────────┘

 assets (direct to project)
 ┌──────────────────────────┬────────────────┐
 │ id           UUID         │ PK             │
 │ project_id   UUID         │ FK→projects    │
 │ character_id UUID         │ FK→characters  │ NULLABLE
 │ scene_id     UUID         │ FK→scenes      │ NULLABLE
 │ asset_type   asset_type   │ NOT NULL       │
 │ file_path    VARCHAR(500) │ NOT NULL       │
 │ file_size    INTEGER      │                │
 │ status       project_status│ NOT NULL      │
 │ created_at   TIMESTAMPTZ  │ NOT NULL       │
 │ updated_at   TIMESTAMPTZ  │ NOT NULL       │
 └──────────────────────────┴────────────────┘

 props
 ┌──────────────────────────┬────────────────┐
 │ id           UUID         │ PK             │
 │ project_id   UUID         │ FK→projects    │
 │ scene_id     UUID         │ FK→scenes      │ NULLABLE
 │ name         VARCHAR(255) │ NOT NULL       │
 │ description  TEXT         │                │
 │ prop_type    VARCHAR(50)  │                │
 │ created_at   TIMESTAMPTZ  │ NOT NULL       │
 │ updated_at   TIMESTAMPTZ  │ NOT NULL       │
 └──────────────────────────┴────────────────┘

 jobs
 ┌──────────────────────────┬────────────────┐
 │ id            UUID        │ PK             │
 │ project_id    UUID        │ FK→projects    │
 │ job_type      VARCHAR(50) │ NOT NULL       │
 │ status        job_status  │ NOT NULL       │
 │ progress      INTEGER     │ NOT NULL DEFAULT 0│
 │ result        JSON        │                │
 │ error         TEXT        │                │
 │ celery_task_id VARCHAR(255)│               │
 │ created_at    TIMESTAMPTZ │ NOT NULL       │
 │ updated_at    TIMESTAMPTZ │ NOT NULL       │
 └──────────────────────────┴────────────────┘
     │
     │ 1:N
     ▼
 logs
 ┌──────────────────────────┬────────────────┐
 │ id           UUID         │ PK             │
 │ job_id       UUID         │ FK→jobs        │
 │ level        VARCHAR(20)  │ NOT NULL DEFAULT INFO│
 │ message      TEXT         │ NOT NULL       │
 │ timestamp    TIMESTAMPTZ  │ NOT NULL       │
 └──────────────────────────┴────────────────┘
```

## Relationships

| Parent | Child | Type | Foreign Key |
|--------|-------|------|-------------|
| projects | episodes | 1:N | episodes.project_id |
| projects | characters | 1:N | characters.project_id |
| projects | assets | 1:N | assets.project_id |
| projects | voices | 1:N | voices.project_id |
| projects | props | 1:N | props.project_id |
| projects | jobs | 1:N | jobs.project_id |
| episodes | scenes | 1:N | scenes.episode_id |
| scenes | videos | 1:N | videos.scene_id |
| scenes | assets | 1:N | assets.scene_id (nullable) |
| scenes | props | 1:N | props.scene_id (nullable) |
| characters | assets | 1:N | assets.character_id (nullable) |
| characters | voices | 1:N | voices.character_id |
| jobs | logs | 1:N | logs.job_id |

## Enum Usage

| Enum Type | Values | Used By |
|-----------|--------|---------|
| project_status | PENDING, PARSING, SUMMARIZING, EPISODES, SCENES, CHARACTERS, ASSETS, VOICE, VIDEO, EDITING, COMPLETED, FAILED, CANCELLED | projects, episodes, scenes, characters, assets, voices, videos |
| job_status | PENDING, RUNNING, COMPLETED, FAILED, CANCELLED | jobs |
| asset_type | IMAGE, CHARACTER_IMAGE, STORYBOARD, OTHER | assets |
