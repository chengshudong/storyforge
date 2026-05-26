# Asset Generation Guide

TASK_007 — Image/Asset generation pipeline for Novel2Drama characters, scenes, backgrounds, props, and covers.

## Architecture

```
                      ┌─────────────────────────────────┐
                      │   POST /api/v1/assets/generate  │
                      │   (phases, variant_count, ...)   │
                      └──────────────┬──────────────────┘
                                     │
                              ┌──────▼──────┐
                              │  Celery Job  │
                              │  (retry×2)   │
                              └──────┬──────┘
                                     │
              ┌──────────────────────▼──────────────────────┐
              │         LangGraph Workflow DAG              │
              │                                            │
              │  char_ref ──→ upload_refs ──→ char_scene   │
              │       │                        │           │
              │       ▼                        ▼           │
              │    [fail?]                  [fail?]        │
              │       │                        │           │
              │       └────────┬───────────────┘           │
              │                ▼                           │
              │  bg ──→ prop ──→ cover ──→ save ──→ END   │
              │   │       │        │        │              │
              │   └───────┴────────┴───────→ save           │
              │           (on failure)                     │
              └───────────────────────────────────────────┘
                                     │
                          ┌──────────▼──────────┐
                          │    ImageAgent        │
                          │  ┌────────────────┐  │
                          │  │ Prompt Builders│  │
                          │  │ (deterministic)│  │
                          │  └───────┬────────┘  │
                          │          │           │
                          │  ┌───────▼────────┐  │
                          │  │ ComfyUIAdapter │  │
                          │  │  (REST client) │  │
                          │  └───────┬────────┘  │
                          └──────────┼──────────┘
                                     │
                              ┌──────▼──────┐
                              │   ComfyUI    │
                              │  SDXL +      │
                              │  InstantID   │
                              └──────┬──────┘
                                     │
                              ┌──────▼──────┐
                              │    MinIO     │
                              │  (storage)   │
                              └─────────────┘
```

## Phases

| Phase | Key | Description | Uses InstantID | Default |
|-------|-----|-------------|----------------|---------|
| Character Reference | `char_ref` | Portrait with fresh face generation | No | ✅ |
| Upload References | `upload_refs` | Upload char_ref portrait to ComfyUI | — | auto* |
| Character Scene | `char_scene` | Character in storyboard-described scene | Yes | ✅ |
| Background | `bg` | Environment-only scene setting | No | ✅ |
| Prop | `prop` | Isolated object/product shot | No | ✅ |
| Cover | `cover` | Poster-style key art | No | ❌ |

\* `upload_refs` runs automatically when `char_scene` is in the phase list.

### Phase Dependencies

```
char_ref ────→ upload_refs ────→ char_scene
                                    │
bg ─────────────────────────────────┤ (independent, runs after char_scene)
prop ───────────────────────────────┤ (independent, runs after bg)
cover ──────────────────────────────┘ (independent, runs after prop)
```

## Prompt Construction

All image prompts are **deterministic** — constructed from structured data without any LLM calls.

### Character Reference Prompt

Source: `CharacterRefPrompt` in `backend/prompts/image.py`

```python
# Input
profile = {
    "appearance": {
        "age_estimate": "late 20s",
        "height": "tall",
        "build": "athletic",
        "hair": "black, shoulder-length",
        "eyes": "deep brown",
        "typical_expression": "stoic, guarded",
        "distinguishing_features": "small scar on left cheek",
    },
    "costume_style": {
        "era": "Victorian",
        "style": "military greatcoat",
        "color_palette": ["navy", "brass"],
        "signature_items": ["ornamental sword"],
        "notes": "high collar, epaulettes",
    },
}

# Output (SDXL CLIP prompt)
positive = (
    "masterpiece, best quality, highly detailed, "
    "professional portrait photograph of Captain Alistair, "
    "late 20s, tall stature, athletic build, "
    "black, shoulder-length hair, deep brown eyes, "
    "small scar on left cheek, "
    "Victorian military greatcoat, "
    "navy, brass color palette, wearing ornamental sword, "
    "high collar, epaulettes, "
    "stoic, guarded, "
    "looking at camera, chest-up portrait, "
    "professional studio lighting, soft diffused light, "
    "plain gray background, "
    "8k, high resolution, sharp focus, skin texture"
)

negative = (
    "low quality, blurry, distorted face, bad anatomy, "
    "extra limbs, missing limbs, mutation, "
    "poorly drawn face, cloned face, bad hands, "
    "signature, watermark, text, nsfw, nude, naked"
)
```

### Character Scene Prompt

Source: `CharacterScenePrompt` in `backend/prompts/image.py`

Same profile data + storyboard fields (camera, emotion, location) + character action. Uses `InstantID` IP-Adapter for face consistency — the face comes from the reference image, not from the text prompt.

### Background / Prop / Cover

`BackgroundPrompt`, `PropPrompt`, `CoverPrompt` — each assembles structured data into SDXL-optimized tag strings with phase-specific negative prompts.

## Face Consistency (InstantID)

The novel's key requirement: **the same character must look the same across all scenes.**

```
Step 1: char_ref phase
  ┌──────────────────┐
  │ Generate portrait │ → SDXL fresh face (no InstantID)
  │ of Captain Alistair│
  └────────┬─────────┘
           │ char_assets[0] (first variant)
           ▼
Step 2: upload_refs phase
  ┌──────────────────┐
  │ Upload to ComfyUI │ → POST /api/upload/image
  │ as "Alistair_face_ref.png"
  └────────┬─────────┘
           │ comfyui filename
           ▼
Step 3: char_scene phase
  ┌──────────────────────────────────────┐
  │ For each scene where Alistair appears:│
  │                                      │
  │ IPAdapterInstantID (                 │
  │   image="Alistair_face_ref.png",     │
  │   weight=0.8                         │
  │ )                                    │
  │ +                                    │
  │ CLIPTextEncode(                      │
  │   "medium shot of Captain Alistair,  │
  │    [physique], [costume],            │
  │    angry expression, drawing sword,  │
  │    in castle hall..."                │
  │ )                                    │
  │ → SDXL with face conditioning        │
  └──────────────────────────────────────┘
```

**Limitation**: The first variant is always used as the face reference. No quality scoring or human selection occurs during the automated pipeline. Use `POST /assets/select` to manually choose the best reference portrait before triggering char_scene.

## API Reference

### Generate Assets

```http
POST /api/v1/assets/generate
Content-Type: application/json

{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "regenerate": false,
  "variant_count": 4,
  "phases": ["char_ref", "char_scene", "bg", "prop"]
}
```

Response (202):
```json
{
  "job_id": "660e8400-...",
  "batch_id": "770e8400-...",
  "status": "pending",
  "message": "Image generation started for phases: ['char_ref', 'char_scene', 'bg', 'prop']"
}
```

Monitor progress via `GET /api/v1/jobs/{job_id}`.

### Select / Favorite Assets

```http
POST /api/v1/assets/select
{"asset_ids": ["uuid1", "uuid2"], "selected": true}

POST /api/v1/assets/favorite
{"asset_ids": ["uuid1"], "favorite": true}
```

### List Assets with Filters

```http
GET /api/v1/assets?project_id=<uuid>&character_id=<uuid>&asset_type=character_image&offset=0&limit=50
```

### Edit / Regenerate

```http
PATCH /api/v1/assets/{id}
{"locked": true}                           # Lock asset from deletion

PATCH /api/v1/assets/{id}
{"feedback": "too dark, make it brighter"} # Store feedback

PATCH /api/v1/assets/{id}
{"regenerate": true}                       # Trigger re-generation
```

### Delete

```http
DELETE /api/v1/assets/{id}   → 204 No Content
DELETE /api/v1/assets/{id}   → 409 Conflict (if locked)
```

## Asset Model

Each generated image produces an `Asset` row with full provenance:

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key |
| `project_id` | UUID FK | Owning project |
| `character_id` | UUID FK | Character in image (nullable for bg/prop/cover) |
| `scene_id` | UUID FK | Scene context (nullable) |
| `asset_type` | Enum | `character_image`, `storyboard`, `cover`, `image`, `other` |
| `file_path` | String | MinIO object path |
| `file_size` | Integer | Bytes |
| `prompt` | Text | SDXL positive prompt used |
| `negative_prompt` | Text | SDXL negative prompt used |
| `seed` | Integer | SDXL seed (for reproducibility) |
| `generation_params` | JSONB | Full params snapshot (checkpoint, steps, cfg, sampler, width, height) |
| `variation_of` | UUID FK→assets | Parent asset (for re-generation lineage) |
| `batch_id` | UUID | Generation batch grouping |
| `selected` | Boolean | User-approved |
| `favorite` | Boolean | User-favorited |
| `locked` | Boolean | Protected from deletion |
| `locked_at` | DateTime | When locked |
| `asset_ref` | String | Storyboard asset_ref identifier |
| `status` | Enum | Pipeline status |

## Configuration

Environment variables (`.env`):

```bash
# ComfyUI connection
comfyui_base_url=http://localhost:8188
```

Asset generation parameters (API request body or defaults):

```python
class AssetGenerationParams(BaseModel):
    checkpoint: str | None = None       # "sd_xl_base_1.0.safetensors"
    steps: int = 25
    cfg: float = 7.5
    sampler: str = "dpmpp_2m"
    width: int = 768
    height: int = 1152
```

## Performance

| Phase | Per-image time | Scaling |
|-------|---------------|---------|
| char_ref | ~30s | N characters × V variants (serial) |
| char_scene | ~30s | M scenes × C characters × V/2 variants (serial) |
| bg | ~30s | M scenes × V variants (serial) |
| prop | ~30s | P props × V variants (serial) |

**Known bottleneck**: All generations within a phase are serial (submit → poll → next). Wall-clock time grows linearly with (characters × scenes × variants). Concurrent generation is a planned optimization.

## Tests

```bash
pytest tests/test_image_prompts.py tests/test_image_agent.py tests/test_image_workflow.py -v
# 40 tests: 20 prompt builders, 14 agent methods, 6 workflow integration
```

## ComfyUI Setup

Required for production use:

1. **ComfyUI** running with SDXL checkpoint
2. **Custom nodes**: IPAdapter-InstantID (for face consistency)
3. **Checkpoint**: `sd_xl_base_1.0.safetensors` (or override via `AssetGenerationParams.checkpoint`)
4. **CLIP Vision**: SDXL checkpoint must output CLIP Vision at index 3 for InstantID

The `comfyui_base_url` setting points to your ComfyUI HTTP API (default: `http://localhost:8188`).
