# Video Generation Guide

TASK_009 — I2V video generation pipeline for Novel2Drama scene rendering using Wan2.1 (primary) and CogVideoX (fallback).

## Architecture

```
                       ┌─────────────────────────────────┐
                       │   POST /api/v1/videos/generate   │
                       │   (phases, variant_count, ...)    │
                       └──────────────┬──────────────────┘
                                      │
                               ┌──────▼──────┐
                               │  Celery Job  │
                               │  (retry×2)   │
                               └──────┬──────┘
                                      │
         ┌────────────────────────────▼────────────────────────────┐
         │              LangGraph Workflow DAG                     │
         │                                                         │
         │  init ──→ submit ──→ poll ──→ composite ──→ save ──→ END│
         │    │        │         │          │            │         │
         │    └────────┴─────────┴──────────┴────────────┘         │
         │              (on failure / no scenes)                   │
         └─────────────────────────────────────────────────────────┘
                                      │
         ┌────────────────────────────▼────────────────────────────┐
         │                    SceneRenderer                        │
         │  ┌──────────────────────┐   ┌──────────────────────┐   │
         │  │  SceneVideoPrompt    │   │  Movement → Motion    │   │
         │  │  (cinematic prompt)  │   │  (6-level mapping)    │   │
         │  └──────────┬───────────┘   └──────────┬───────────┘   │
         │             │                          │               │
         │             └──────────┬───────────────┘               │
         │                        ▼                               │
         │              VideoSubmitRequest                        │
         │     (prompt + negative + seed + keyframe image         │
         │      + motion_bucket_id + num_frames + ...)            │
         └────────────────────────┬───────────────────────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │      VideoProvider         │
                    │  ┌───────────────────────┐ │
                    │  │  Wan2.1Adapter        │ │  primary
                    │  │  (multipart form-data) │ │
                    │  └───────────────────────┘ │
                    │  ┌───────────────────────┐ │
                    │  │  CogVideoXAdapter      │ │  fallback
                    │  │  (JSON + base64 image) │ │
                    │  └───────────────────────┘ │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │    ffmpeg Post-Processing  │
                    │  - composite audio (AAC)   │
                    │  - extract thumbnail (JPG) │
                    │  - extract preview (MP4)   │
                    └─────────────┬─────────────┘
                                  │
                    ┌─────────────▼─────────────┐
                    │      MinIO Storage         │
                    │  4 files per video:        │
                    │  - main MP4                │
                    │  - composited audio MP4    │
                    │  - thumbnail JPG           │
                    │  - preview MP4             │
                    └────────────────────────────┘
```

## Pipeline Phases

### Phase 1: Init
Validates input data. Filters scenes to those with storyboard data. Extracts character assets and voice assets for downstream phases.

**Inputs:**
- `scenes[]` — Scene dicts with `storyboard` containing camera, emotion, location, duration_estimate, characters_present, character_actions
- `character_assets{}` — `{character_name: {profile: {...}, image_data: bytes}}`
- `voice_assets{}` — `{scene_id: [{character_name, audio_data}]}`

**Outputs:** Validated scenes list, status: `init_done` | `no_scenes` | `failed`

### Phase 2: Submit
Builds I2V payloads via SceneRenderer and submits to video provider. One submission per character per scene.

**Submission per scene+character:**
```python
SceneRenderer.build_payload(
    scene, storyboard,
    character_image=image_data,
    character_name=name,
    character_profile=profile,
    seed=hash(f"{project_id}:{scene_id}:{character_name}"),
    cfg=7.5, width=768, height=1152,
)
```

**Outputs:** `submissions[]` with prompt_id, scene_id, character_name

### Phase 3: Poll
Polls all submissions for completion. Wan2.1: 150 iterations × 2s = 5min max. Downloads MP4 on completion. Matches voice audio by scene_id + character_name.

**Retry:** If all polls fail and retry_count < max_retries (1), routes back to submit for fallback provider retry.

**Outputs:** `generated_videos[]` with video_data, audio_data, duration_s

### Phase 4: Composite
Post-processing for each generated video:
- `extract_thumbnail(video_data, at_seconds=1.5)` → JPEG
- `extract_preview(video_data, duration_s=3.0)` → 3s MP4 clip

**Outputs:** Videos augmented with thumbnail_data, preview_data

### Phase 5: Save
Persists all generated videos:
1. Upload main MP4 to MinIO
2. Composite audio via ffmpeg → upload composited MP4
3. Upload thumbnail JPG
4. Upload preview MP4
5. Create Video DB record with full metadata

**Outputs:** `saved_video_ids[]`, status: `done`

## Camera Movement → Motion Bucket Mapping

Wan2.1 uses `motion_bucket_id` to control motion intensity. The SceneRenderer maps camera movement keywords:

| Movement Keywords | Motion ID | Description |
|-------------------|-----------|-------------|
| static, still, none | 20 | No camera movement |
| slow_pan, subtle, gentle, slow zoom, creep | 80 | Subtle movement |
| pan, tilt, dolly, zoom, track | 127 | Normal movement (default) |
| fast_pan, tracking, dynamic, whip | 180 | Dynamic movement |
| action, shake, handheld, chaotic | 220 | Intense action |
| (unknown) | 127 | Fallback to normal |

Mapping is case-insensitive via `movement.strip().lower()`.

## Video Model (20 Columns)

| Column | Type | Description |
|--------|------|-------------|
| id | UUID | Primary key |
| project_id | UUID FK→projects | Owning project |
| scene_id | UUID FK→scenes | Source scene |
| file_path | String(500) | MinIO path to main MP4 |
| duration | Float | Video duration in seconds |
| resolution | String(20) | e.g. "768x1152" |
| prompt | Text | Full positive prompt |
| negative_prompt | Text | Negative prompt used |
| seed | Integer | Generation seed |
| fps | Integer, default 24 | Frames per second |
| generation_params | JSONB | Full model config (steps, cfg, motion_bucket_id) |
| provider | String(50) | "wan21" or "cogvideox" |
| preview_path | String(500) | MinIO path to 3s preview |
| thumbnail_path | String(500) | MinIO path to keyframe JPG |
| batch_id | UUID | Generation batch grouping |
| selected | Boolean, default false | User-approved for final edit |
| version | Integer, default 1 | Regeneration tracking |
| audio_path | String(500) | MinIO path to audio-composited MP4 |
| audio_duration | Float | Source dialogue duration (ms) |
| file_size | Integer | Byte size for UI display |
| status | Enum | PENDING / COMPLETED / FAILED |
| created_at | DateTime | Record creation |
| updated_at | DateTime | Last modification |

## Cache Strategy

| Cache | Key Pattern | TTL | Content |
|-------|------------|-----|---------|
| Prompt | `video:prompt:{project}:{scene}:{hash}` | 7 days | LLM-enhanced prompt (optional) |
| Result | `video:result:{MD5(content)}` | 30 days | Generation metadata |
| Active provider | `video:active_provider` | 60s | Health-checked provider name |

Video bytes are NOT cached in Redis — MinIO serves as permanent storage.

## API Reference

| Method | Endpoint | Status | Description |
|--------|----------|--------|-------------|
| POST | `/api/v1/videos/generate` | 202 | Start async video generation |
| GET | `/api/v1/videos?project_id=&scene_id=&selected=` | 200 | List videos (paginated) |
| GET | `/api/v1/videos/{id}` | 200 | Video metadata |
| GET | `/api/v1/videos/{id}/stream` | 200 | Stream MP4 (video/mp4) |
| GET | `/api/v1/videos/{id}/thumbnail` | 200 | Keyframe thumbnail (image/jpeg) |
| GET | `/api/v1/videos/{id}/preview` | 200 | 3s preview clip (video/mp4) |
| POST | `/api/v1/videos/select` | 200 | Mark videos selected/unselected |
| DELETE | `/api/v1/videos/{id}` | 204 | Delete video (409 if locked) |

## Provider Stack

| Provider | Port | Payload | motion_bucket_id | guidance_scale | Timeout |
|----------|------|---------|------------------|----------------|---------|
| Wan2.1 (primary) | 7860 | multipart form-data | ✅ | 7.5 | 5min poll |
| CogVideoX (fallback) | 7861 | JSON + base64 image | ❌ (uses num_inference_steps) | 6.0 | 5min poll |

### Wan2.1 Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/video/submit` | Submit I2V job (multipart) |
| GET | `/api/v1/video/status/{id}` | Poll status |
| GET | `/api/v1/video/download/{id}` | Download MP4 |
| POST | `/api/v1/video/cancel/{id}` | Cancel job |
| GET | `/api/health` | Health check |

### CogVideoX Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/generate` | Submit I2V job (JSON) |
| GET | `/status/{id}` | Poll status |
| GET | `/download/{id}` | Download MP4 |
| POST | `/cancel/{id}` | Cancel job |
| GET | `/health` | Health check |

## Audio-Video Sync

Voice audio is composited as post-processing via ffmpeg:

```bash
ffmpeg -y \
  -i video.mp4 \
  -i audio.wav \
  -c:v copy \
  -c:a aac \
  -shortest \
  output.mp4
```

- Video stream is copied (no re-encode)
- Audio is re-encoded to AAC
- `-shortest`: output duration = min(video, audio) — prevents silence padding
- audio_duration stored on Video record for sync validation

## Docker Services

```yaml
wan21:          # Wan2.1 I2V API (GPU, port 7860)
cogvideox:      # CogVideoX fallback (GPU, port 7861)
celery-video:   # Dedicated worker: -Q video_generation --concurrency=1
```

Both GPU services use profiles for selective startup. celery-video uses concurrency=1 to prevent GPU contention.

## Generation Performance

| Phase | Duration | Notes |
|-------|----------|-------|
| Init | <1ms | In-memory filtering |
| Submit | ~500ms/character | HTTP multipart POST |
| Poll | 30s–5min | GPU-bound, 2s polling interval |
| Composite | ~500ms/video | ffmpeg thumbnail + preview |
| Save | ~1s/video | 4 MinIO uploads |
| **Per scene+character** | **~2–5 min** | |
| **5 scenes × 2 characters** | **~20–50 min** | Sequential |

## Recovery & Retry

- **Workflow retry**: Poll node retries failed submissions once (max_retries=1)
- **Provider fallback**: Wan2.1 primary → CogVideoX on retry (at task level)
- **Phase skipping**: Any phase can be skipped via `phases` parameter for targeted reruns
- **Save-accumulated**: Failed phases still persist completed work from prior phases
- **MemorySaver**: In-memory checkpoint for resumability within process lifetime
- **Version tracking**: `regenerate=True` creates version N+1 for any scene

## Configuration

```env
# Wan2.1 I2V
WAN21_BASE_URL=http://localhost:7860

# CogVideoX fallback
COGVIDEOX_BASE_URL=http://localhost:7861
```

## Tests

92 tests across 7 test files:

| File | Count | Focus |
|------|-------|-------|
| test_wan21_adapter.py | 11 | Init, health, submit, poll (completed/failed/timeout), cancel |
| test_cogvideox_adapter.py | 6 | Init, health, submit (base64), poll (completed/failed) |
| test_video_prompts.py | 9 | SceneVideoPrompt (8) + SceneContextPrompt (1) |
| test_video_renderer.py | 12 | Build payload (5) + Movement mapping (7) |
| test_video_agent.py | 14 | Submit, poll, generate, composite, thumbnail, preview, save, cache keys, provider |
| test_video_workflow.py | 23 | State defaults, 5 node tests, conditional edges, retry, graph compilation |
| test_video_api.py | 17 | Generate 202/404, list filters, get 200/404, stream, thumbnail, preview, select, delete |

Run: `pytest tests/test_wan21_adapter.py tests/test_cogvideox_adapter.py tests/test_video_prompts.py tests/test_video_renderer.py tests/test_video_agent.py tests/test_video_workflow.py tests/test_video_api.py -v`
