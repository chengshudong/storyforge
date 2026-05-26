# Voice Generation Guide

TASK_008 — Voice cloning + dialogue synthesis pipeline for Novel2Drama characters using CosyVoice (primary) and GPT-SoVITS (fallback).

## Architecture

```
                      ┌─────────────────────────────────┐
                      │   POST /api/v1/voices/generate  │
                      │   (phases, regenerate, ...)      │
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
              │  clone ──→ synthesize ──→ preview ──→ save │
              │    │           │             │         │    │
              │    └───────────┴─────────────┘         │    │
              │           (on failure)                  │    │
              │                                         │    │
              │               ┌─────────────────────────┘    │
              │               ▼                              │
              │              END                             │
              └─────────────────────────────────────────────┘
                                     │
                          ┌──────────▼──────────┐
                          │    VoiceAgent        │
                          │  ┌────────────────┐  │
                          │  │ Prompt/Mappers │  │
                          │  │ (deterministic)│  │
                          │  └───────┬────────┘  │
                          │          │           │
                          │  ┌───────▼────────┐  │
                          │  │ CosyVoiceAdapter│  │
                          │  │  (REST client) │  │
                          │  └───────┬────────┘  │
                          └──────────┼──────────┘
                                     │
                          ┌──────────▼──────────┐
                          │      CosyVoice      │
                          │   (TTS engine)      │
                          └──────────┬──────────┘
                                     │
                          ┌──────────▼──────────┐
                          │       Redis         │
                          │  Speaker + Synth    │
                          │  Cache              │
                          └──────────┬──────────┘
                                     │
                          ┌──────────▼──────────┐
                          │       MinIO         │
                          │  (permanent audio   │
                          │   storage)           │
                          └─────────────────────┘
```

## Phases

| Phase | Key | Description | Default |
|-------|-----|-------------|---------|
| Clone | `clone` | Clone character voice from profile | ✅ |
| Synthesize | `synthesize` | Synthesize all dialogue lines | ✅ |
| Preview | `preview` | Generate "Hello, my name is X" clips | ✅ |

### Phase Dependencies

```
clone ────→ synthesize ────→ preview
  │              │              │
  └──────────────┴──────────────┘
         (fail-fast to save)
```

Each phase can fail independently — conditional edges route to save node on failure, persisting all completed work.

## Voice Cloning Flow

```
Step 1: Build Reference Text (deterministic)
  ┌──────────────────────────────────────────┐
  │ ReferenceTextPrompt.render(name, profile) │
  │                                          │
  │ "My name is Captain Alistair.            │
  │  I speak with a medium-pitched, clear    │
  │  voice, carrying a neutral accent."      │
  └──────────────┬───────────────────────────┘
                 │
Step 2: Synthesize Reference Audio
  ┌──────────────────────────────────────────┐
  │ Try ModelRouter TTS → EdgeTTS fallback   │
  │ → Silence WAV (3s 16kHz mono PCM)        │
  └──────────────┬───────────────────────────┘
                 │ reference_audio (bytes)
                 ▼
Step 3: Clone via TTS Provider
  ┌──────────────────────────────────────────┐
  │ POST /upload                             │
  │ {audio: ref.wav, name: "Captain Alistair"}│
  │ → {"voice_id": "spk_captain_alistair"}   │
  └──────────────┬───────────────────────────┘
                 │ speaker ID
                 ▼
Step 4: Preview + Save
  ┌──────────────────────────────────────────┐
  │ Preview: "Hello, my name is..."          │
  │ Upload ref + preview audio to MinIO      │
  │ Save Voice row (selected=True)           │
  │ Cache speaker in Redis (7d TTL)          │
  └──────────────────────────────────────────┘
```

## Emotion System

### Deterministic Mapping (Hot Path — No LLM)

`EmotionResolver.map()` is a pure lookup table with 33 entries mapping to 7 canonical tags:

| Input Examples | Canonical Tag | Pitch | Rhythm | Timbre |
|---------------|---------------|-------|--------|--------|
| happy, joyful, surprised, shocked, sarcastic, mocking | `happy` | 1.15–1.20 | 1.05–1.20 | 0.55–0.60 |
| sad, sorrowful, afraid, terrified, desperate, pleading | `sad` | 0.80–0.90 | 0.90–1.15 | 0.30–0.45 |
| angry, furious, enraged, cold, icy, menacing | `angry` | 0.90–1.10 | 0.85–1.10 | 0.70–0.75 |
| calm, peaceful, gentle, warm, affectionate, loving | `soothing` | 0.95–1.05 | 0.90–0.95 | 0.45–0.50 |
| mysterious, eerie, suspenseful | `mysterious` | 0.90 | 0.85 | 0.35 |
| determined, resolute, firm | `determined` | 1.05 | 1.00 | 0.65 |
| neutral, stoic, emotionless | `neutral` | 0.95–1.00 | 0.90–1.00 | 0.50–0.55 |

### LLM Fallback (Cold Path — Cached 24h)

When `EmotionResolver.map()` returns `(None, None)` (unmappable emotion), `EmotionLLMPrompt` constructs a system + user prompt that:
1. Maps the complex description to one of 7 canonical tags
2. Provides pitch (0.7–1.3), rhythm (0.7–1.3), timbre (0.2–0.8) values
3. Result cached per `MD5(character|dominant_emotion|target_emotion)` for 24h

### Per-Character Baseline Offset

`VoiceProfileMapper.apply_character_baseline()` modifies the emotion vector based on the character's `emotion_range.dominant`:

```python
# Stoic characters: slightly slower rhythm
if "stoic" in dominant_emotion:
    vector["rhythm"] = max(0.7, vector["rhythm"] - 0.05)

# Cheerful characters: slightly higher pitch
if "bright" in dominant_emotion or "cheerful" in dominant_emotion:
    vector["pitch"] = min(1.3, vector["pitch"] + 0.05)
```

## Voice Profile Mapping

`VoiceProfileMapper` converts structured voice profiles to synthesis parameters:

| Profile Field | Effect | Mapping |
|--------------|--------|---------|
| `pitch` (high/medium/low) | Speed multiplier | high=1.2, medium=1.0, low=0.8 |
| `tempo` (fast/measured/slow) | Speed modifier | fast×1.15, measured×1.0, slow×0.9 |
| `tone_quality` (warm/cool/rough/smooth) | Timbre offset | warm=0.7, smooth=0.5, rough=0.8 |
| `speech_patterns` | Reference text enrichment | Appended to cloning reference text |
| `accent` | Reference text enrichment | Embedded in cloning reference text |

Pitch offset is clamped to [-5, +5] for CosyVoice compatibility.

## Voice Model

Each generated voice produces a `Voice` row with full provenance:

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | Primary key (application voice_id) |
| `project_id` | UUID FK | Owning project |
| `character_id` | UUID FK | Character this voice belongs to |
| `scene_id` | UUID FK | Scene context (nullable) |
| `dialogue_index` | Integer | Position in scene dialogue (nullable) |
| `provider` | String | TTS engine used ("cosyvoice", "gptsovits") |
| `speaker` | String | Provider-side speaker ID |
| `speed` | Float | Synthesis speed (0.8–1.2) |
| `pitch` | Integer | Pitch offset (-5 to +5) |
| `emotion` | String | Emotion tag used |
| `version` | Integer | Character version this voice was cloned for |
| `selected` | Boolean | True for the active voice of each character |
| `voice_params` | JSONB | Cloning parameters (accent, tone_quality, speech_patterns, emotion_range) |
| `file_path` | String | MinIO audio file path |
| `file_size` | Integer | Bytes |
| `duration_ms` | Float | Audio duration in milliseconds |
| `preview_path` | String | MinIO preview clip path |
| `reference_audio_path` | String | MinIO reference audio path |
| `reference_audio_hash` | String | MD5 hash of voice_profile for dedup |
| `status` | Enum | Pipeline status |

**Key design**: `voice_id` (UUID) is the application identifier. `speaker` is the provider-side ID. They are separate — one application voice may map to different provider speakers across re-clones.

## Caching Strategy

### Three-Layer Cache

| Layer | Storage | Key Pattern | TTL | Content |
|-------|---------|-------------|-----|---------|
| Speaker | Redis | `voice:speaker:{character_id}` | 7d | {speaker, provider, version} |
| Synthesis | Redis | `voice:synth:{MD5[:16]}` | 30d | {audio_b64, speaker, text, emotion} |
| Emotion LLM | Redis | `voice_emotion:system:{hash}` | 24h | {emotion, vector: {pitch, rhythm, timbre}} |
| Provider | Redis | `voice:active_provider` | 60s | {provider} |

### Content-Addressed Synthesis Keys

```
synthesis_key = MD5(speaker | text | emotion | speed | pitch)[:16]
```

Identical text + speaker + emotion → always hits cache, regardless of project/character/scene context.

### Cache Invalidation

- `invalidate_speaker(character_id)` — called on character profile update, forces re-clone
- `invalidate_character_audio(character_id)` — invalidates speaker cache only; synthesis cache naturally expires as speaker ID changes on re-clone

## API Reference

### Generate Voices

```http
POST /api/v1/voices/generate
Content-Type: application/json

{
  "project_id": "550e8400-e29b-41d4-a716-446655440000",
  "regenerate": false,
  "phases": ["clone", "synthesize", "preview"]
}
```

Response (202):
```json
{
  "job_id": "660e8400-...",
  "status": "pending",
  "message": "Voice generation started for phases: ['clone', 'synthesize', 'preview']"
}
```

Monitor progress via `GET /api/v1/jobs/{job_id}`.

Progress milestones: clone_done=35%, synthesize_done=80%, preview_done=95%, done=100%.

### List Voices

```http
GET /api/v1/voices?project_id=<uuid>&character_id=<uuid>&scene_id=<uuid>&offset=0&limit=50
```

### Get Voice Detail

```http
GET /api/v1/voices/{voice_id}
```

### Preview Audio

```http
GET /api/v1/voices/{voice_id}/preview
Response: audio/wav
```

### Delete Voice

```http
DELETE /api/v1/voices/{voice_id}   → 204 No Content
DELETE /api/v1/voices/{voice_id}   → 409 Conflict (if selected=true)
```

Deselect via PATCH before deleting: set `selected=false`.

## Provider Stack

### CosyVoice (Primary)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/upload` | POST | Clone voice → voice_id |
| `/tts` | POST | Synthesize → WAV bytes |
| `/voices` | GET | List available speakers |
| `/voices/{id}` | DELETE | Remove speaker |
| `/health` | GET | Health check |

### GPT-SoVITS (Fallback)

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/set_reference` | POST | Clone voice → speaker_id |
| `/tts` | POST | Synthesize → WAV bytes |
| `/health` | GET | Health check |

### Fallback Chain

```
CosyVoice.health() → GPTSoVITS.health() → CosyVoice (degraded)
```

If CosyVoice is unhealthy and GPT-SoVITS is healthy → switch to GPT-SoVITS. If both unhealthy → use CosyVoice anyway (fail on first API call).

## Audio Format

All audio is **16-bit mono PCM at 16kHz sample rate**.

- Sample rate: 16000 Hz
- Bit depth: 16 bits per sample
- Channels: 1 (mono)
- Byte rate: 32000 bytes/second
- Duration formula: `duration_ms = len(bytes) / 32000.0 * 1000`

WAV header: 44 bytes (standard RIFF/WAVE/PCM format).

## Emotion Emoji → Tag Quick Reference

| Emoji | Emotion Tag |
|-------|-------------|
| 😊 😄 🤣 😏 | happy |
| 😢 😨 😰 😭 🙏 | sad |
| 😠 😡 😤 😐 ❄️ | angry |
| 😌 ☮️ 🥰 💕 | soothing |
| 🫣 😶‍🌫️ 🔮 | mysterious |
| 💪 😤 ✊ | determined |
| 😐 🗿 | neutral |

## Recovery & Retry

### Workflow Fail-Fast

Each node catches exceptions internally and returns `{"status": "failed"}` rather than raising. Conditional edges route failed → save to persist completed work:

```
clone fail → save (persists 0 assets, but safe exit)
synthesize fail → save (persists clone assets)
preview fail → save (persists clone + synthesis assets)
```

### Celery Retry

```
max_retries = 2
default_retry_delay = 120s
```

Maximum 3 execution attempts (1 initial + 2 retries) with 2-minute intervals.

### Checkpointing

`MemorySaver` checkpoints allow resuming from intermediate states within a single process lifetime. For production persistence, replace with a database-backed checkpointer.

## Configuration

Environment variables (`.env`):

```bash
# CosyVoice
COSYVOICE_BASE_URL=http://localhost:5001
COSYVOICE_TIMEOUT=60

# GPT-SoVITS (optional fallback)
GPTSOVITS_BASE_URL=http://localhost:5002
GPTSOVITS_ENABLED=true
```

Docker Compose (GPU profile):

```yaml
services:
  cosyvoice:
    profiles: [gpu]
    image: cosyvoice:latest
    ports: ["5001:5000"]
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  gptsovits:
    profiles: [gpu]
    image: gptsovits:latest
    ports: ["5002:5000"]
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
```

## Performance

| Operation | Latency | Notes |
|-----------|---------|-------|
| Voice clone (CosyVoice) | 2–5s | Upload + model inference |
| Single synthesis (cold) | 50–200ms | TTS API call, no LLM |
| Single synthesis (cached) | <5ms | Redis hit |
| Emotion LLM fallback (cold) | 500ms–2s | Only for unmappable emotions |
| Emotion LLM (cached) | <5ms | 24h TTL |
| Full project (5 chars, 150 lines) | ~10–15s | Concurrent synthesis with Semaphore(3) |

**Hot path guarantee**: `synthesize_dialogue()` has zero LLM calls. All emotion resolution is deterministic lookup or cached LLM result.

## Tests

```bash
pytest tests/test_voice_prompts.py tests/test_voice_agent.py tests/test_voice_adapter.py tests/test_voice_workflow.py -v
# 56 tests: 25 prompts/mappers, 12 agent, 10 adapter, 6 workflow integration, 1 WAV header, 2 voice library
```

## CosyVoice Setup

Required for production use:

1. **CosyVoice** running with HTTP API enabled
2. **GPU**: NVIDIA GPU with CUDA support recommended
3. **Models**: CosyVoice base model for voice cloning + TTS
4. **Network**: CosyVoice HTTP API accessible from backend (default: `http://localhost:5001`)

Optional fallback: **GPT-SoVITS** on port 5002 with compatible `/set_reference` + `/tts` endpoints.
