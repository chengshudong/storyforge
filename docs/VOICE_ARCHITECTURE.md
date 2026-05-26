# TASK_008 — Voice Generation Architecture Plan

Version 1.0 — Read-only plan. No code modifications.

---

## 1. Overview

TASK_008 adds voice cloning and dialogue synthesis to Novel2Drama. Every character gets a cloned voice. Every scene dialogue line gets synthesized audio with emotion control. The system orchestrates CosyVoice (primary) with optional GPT-SoVITS fallback — it does not implement TTS internals.

**Inputs**: Character voice_profile, Scene dialogue JSON, storyboard emotion
**Outputs**: Voice asset (WAV), preview clip, voice library entries

**Must reuse**: CharacterMemory (Qdrant), CharacterLocker, SceneRepository, ModelRouter, CacheService
**Must NOT modify**: Any existing agent (NovelAgent, StoryAgent, EpisodeAgent, SceneAgent, CharacterAgent, ImageAgent)

---

## 2. Directory Changes

```
backend/
  interfaces/
    voice.py              ← NEW  VoiceProvider ABC
  providers/voice/
    __init__.py            ← NEW
    cosyvoice_adapter.py   ← NEW  CosyVoice REST client
    gptsovits_adapter.py   ← NEW  GPT-SoVITS REST client (optional)
  agents/
    voice_agent.py         ← NEW  VoiceAgent (orchestration)
  prompts/
    voice.py               ← NEW  Deterministic voice prompts + emotion mapping
  services/
    voice_library.py       ← NEW  VoiceLibrary (voice ID cache, audio cache)
  workflows/
    voice_generation.py    ← NEW  LangGraph DAG
  api/v1/
    voices.py              ← NEW  5 REST endpoints
  repository/
    voice_repository.py    ← MODIFY  Add new query methods (no behavioral changes to existing)
  domain/
    models.py              ← MODIFY  Extend Voice model columns (migration, not in-place)

tests/
  test_voice_prompts.py    ← NEW  15 tests
  test_voice_agent.py      ← NEW  12 tests
  test_voice_adapter.py    ← NEW  10 tests
  test_voice_workflow.py   ← NEW   6 tests
```

---

## 3. VoiceProvider Interface

`backend/interfaces/voice.py`

Follows `ImageProvider` ABC pattern exactly.

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum


class VoiceStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


@dataclass
class VoiceResult:
    voice_id: str
    status: VoiceStatus
    audio: bytes | None = None
    duration_ms: float | None = None
    error: str | None = None


@dataclass
class SynthesisRequest:
    """A single dialogue line to synthesize."""
    text: str
    emotion: str = "neutral"           # happy|sad|angry|soothing|mysterious|determined|neutral
    emotion_vector: dict | None = None  # {pitch, rhythm, timbre} override
    speed: float = 1.0
    pitch: int = 0                     # semitones, -12 to +12
    speaker: str | None = None         # provider-side speaker ID


class VoiceProvider(ABC):
    """Interface for TTS/voice cloning backends (CosyVoice, GPT-SoVITS).

    Per OSS_REGISTRY: Provider → Adapter → Interface → Agent → Workflow → API.
    """

    @abstractmethod
    async def clone_voice(self, character_name: str, reference_audio: bytes,
                          reference_text: str | None = None) -> str:
        """Upload reference audio, create voice clone. Returns provider-side speaker ID."""

    @abstractmethod
    async def synthesize(self, request: SynthesisRequest) -> VoiceResult:
        """Generate TTS audio from text with emotion control."""

    @abstractmethod
    async def synthesize_batch(self, requests: list[SynthesisRequest]) -> list[VoiceResult]:
        """Generate TTS for multiple lines. Provider may batch-optimize."""

    @abstractmethod
    async def preview(self, speaker: str, text: str) -> VoiceResult:
        """Quick preview synthesis — shorter timeout, lower quality acceptable."""

    @abstractmethod
    async def health(self) -> bool:
        """Check provider is reachable and ready."""

    @abstractmethod
    async def list_speakers(self) -> list[str]:
        """List available speaker IDs on the provider."""

    @abstractmethod
    async def delete_speaker(self, speaker: str) -> bool:
        """Remove a cloned voice from the provider."""
```

---

## 4. Voice Schema (Migration 005)

### 4.1 Voice Data Structure

Core voice record — flat columns for frequently-accessed fields, JSONB for bulk metadata only.

```json
{
  "voice_id": "uuid (PK)",
  "character_id": "uuid FK → characters",
  "provider": "cosyvoice | gptsovits",
  "speaker": "provider-side speaker ID string",
  "speed": 1.0,
  "pitch": 0,
  "emotion": "neutral",
  "version": 1,
  "selected": true
}
```

### 4.2 Extended Voice Model

Current Voice model (3 data columns: `file_path`, `file_size`, `duration`) is extended:

| Column | Type | Description |
|--------|------|-------------|
| `id` | UUID | (existing) — voice_id in application layer |
| `project_id` | UUID FK | (existing) |
| `character_id` | UUID FK | (existing) |
| `scene_id` | UUID FK | **NEW** — Scene context (nullable: clone voices have no scene) |
| `dialogue_index` | Integer | **NEW** — Index into scene.dialogue JSON array (nullable) |
| `provider` | String(50) | **NEW** — "cosyvoice" or "gptsovits" |
| `speaker` | String(255) | **NEW** — Provider-side speaker ID (CosyVoice voice_id from /upload) |
| `speed` | Float | **NEW** — Playback speed multiplier (default 1.0) |
| `pitch` | Integer | **NEW** — Pitch shift in semitones (default 0, range -12 to +12) |
| `emotion` | String(50) | **NEW** — Primary emotion tag: neutral/happy/sad/angry/soothing/mysterious/determined |
| `version` | Integer | **NEW** — Character version number this voice was cloned from |
| `selected` | Boolean | **NEW** — User-approved as active voice for this character (default true for first clone) |
| `voice_params` | JSONB | **NEW** — Full synthesis snapshot: {emotion_vector, reference_audio_hash, sample_rate, channels, accent, tone_quality, speech_patterns, ...} |
| `file_path` | String(500) | (existing) — MinIO object path for synthesis audio |
| `file_size` | Integer | (existing) |
| `duration_ms` | Float | **NEW** — Duration in milliseconds (renamed from `duration`) |
| `preview_path` | String(500) | **NEW** — MinIO path for short preview clip |
| `reference_audio_path` | String(500) | **NEW** — MinIO path for uploaded reference audio used in cloning |
| `status` | Enum | (existing) |
| `created_at` | DateTime | (existing) |
| `updated_at` | DateTime | (existing) |

### 4.3 Design Rationale

- **`speaker` vs `voice_id`**: `voice_id` is the application-level UUID (the `id` column). `speaker` is the provider-side identifier (CosyVoice returns a speaker_id after `/upload`). Clean separation.
- **Flat `speed`/`pitch`/`emotion`**: These are queried on every synthesis call for parameter overrides. Storing them in JSONB would require deserialization on every read. Flat columns allow direct SQL filtering: `SELECT * FROM voices WHERE character_id = ? AND selected = true ORDER BY version DESC`.
- **`selected`**: Mirrors Asset model's `selected` field. When a character has multiple voice clones (different versions), exactly one is `selected=true`. First clone auto-selected. User can switch via PATCH.
- **`voice_params` JSONB**: Only for rarely-queried bulk metadata (emotion_vector, accent, tone_quality, speech_patterns, reference_audio_hash). These are written once and read only during debugging or regeneration.

### 4.4 Migration File

`backend/alembic/versions/005_extend_voices.py`

- Add 11 new columns (all nullable for backward compat)
- Rename `duration` → `duration_ms`
- Add index on `(character_id, selected)` for active voice lookup
- Add index on `(character_id, version)` for version history
- Add index on `(scene_id, dialogue_index)` for dialogue-to-audio mapping

---

## 5. Voice Profile

### 5.1 Source (from CharacterAgent)

Voice profiles are already generated by `CharacterProfilePrompt` → `voice_profile` JSONB field:

```json
{
  "voice_profile": {
    "pitch": "medium-low",
    "tempo": "deliberate",
    "accent": "Victorian English, upper-class",
    "tone_quality": "authoritative, smooth",
    "speech_patterns": ["pauses before responding", "clipped consonants"]
  },
  "emotion_range": {
    "dominant": "stoic determination",
    "secondary": ["cold anger", "rare warmth"],
    "rarely_shows": ["fear", "joy", "surprise"],
    "trigger_situations": [
      "threat to allies → cold anger",
      "mention of past betrayal → stoic silence"
    ]
  }
}
```

### 5.2 CosyVoice Protocol Mapping

Character profile → CosyVoice synthesis parameters via `VoiceProfileMapper`:

| Profile Field | CosyVoice Parameter | Mapping |
|--------------|-------------------|---------|
| `pitch` | `speed` | high=1.2, medium-high=1.1, medium=1.0, medium-low=0.9, low=0.8 |
| `tempo` | `speed` modifier | fast=×1.15, measured=×1.0, slow=×0.9, deliberate=×0.85 |
| `tone_quality` | `emotion_vector.timbre` | warm=0.7, cool=0.3, rough=0.8, smooth=0.5, authoritative=0.6 |
| `speech_patterns` | Injected into text | Pauses → `\n` tokens, clipped → shorter segments |

### 5.3 Voice Cloning Flow

```
Character voice_profile (JSONB)
        │
        ▼
┌──────────────────────────────┐
│ 1. Generate reference text   │  ← Deterministic, from CharacterProfilePrompt data
│    (2-3 sentences, contains  │
│     varied phonemes)         │
└────────────┬─────────────────┘
             │
             ▼
┌──────────────────────────────┐
│ 2. Synthesize reference      │  ← ModelRouter → DeepSeek/OAI TTS (text → neutral audio)
│    via LLM TTS or default    │     or system default TTS engine
│    TTS engine                │
└────────────┬─────────────────┘
             │ reference_audio (WAV bytes)
             ▼
┌──────────────────────────────┐
│ 3. POST /upload to CosyVoice │  ← VoiceProvider.clone_voice()
│    → speaker ID              │
└────────────┬─────────────────┘
             │ speaker stored in Voice.speaker
             ▼
┌──────────────────────────────┐
│ 4. Synthesize preview        │  ← VoiceProvider.preview()
│    "Hello, I am [Name]"      │
└────────────┬─────────────────┘
             │ preview_audio → MinIO → Voice.preview_path
             ▼
┌──────────────────────────────┐
│ 5. Store Voice row           │  ← provider="cosyvoice", selected=true
│    (clone entry)             │
└──────────────────────────────┘
```

**Key design decision**: Step 2 uses the LLM gateway (DeepSeek TTS or OpenAI TTS) to generate the reference audio for voice cloning. This avoids requiring a human-supplied reference clip. The reference text is deterministic from the character's name, role, and voice_profile description — no LLM prompt needed.

### 5.4 Reference Text Template

`backend/prompts/voice.py` — `ReferenceTextPrompt` (deterministic):

```python
class ReferenceTextPrompt:
    """Build reference text for voice cloning from character profile.
    Deterministic — no LLM call."""

    def render(self, name: str, voice_profile: dict) -> str:
        pitch = voice_profile.get("pitch", "medium")
        accent = voice_profile.get("accent", "neutral")
        tone = voice_profile.get("tone_quality", "clear")
        patterns = voice_profile.get("speech_patterns", [])

        sentences = [
            f"My name is {name}.",
            f"I speak with a {pitch}-pitched, {tone} voice, carrying a {accent} accent.",
        ]
        if patterns:
            sentences.append(f"People say I tend to {patterns[0]}.")
        else:
            sentences.append("It is a pleasure to make your acquaintance.")

        return " ".join(sentences)
```

Output example: `"My name is Captain Alistair. I speak with a medium-low-pitched, authoritative voice, carrying a Victorian English, upper-class accent. People say I tend to pause before responding."`

---

## 6. Emotion Strategy

### 6.1 Emotion Pipeline

```
Scene storyboard (emotion field)
        +
Character emotion_range (JSONB)
        │
        ▼
┌──────────────────────────────┐
│ EmotionResolver              │  ← backend/prompts/voice.py
│ (deterministic mapping)      │
│                              │
│ Maps storyboard emotion      │
│ → CosyVoice emotion tag      │
└────────────┬─────────────────┘
             │ primary_emotion, emotion_vector
             ▼
┌──────────────────────────────┐
│ LLM Fallback                 │  ← ModelRouter (only if EmotionResolver
│ (for unsupported emotions)   │     can't map)
│                              │
│ Maps complex emotion desc    │
│ → closest supported tag      │
└────────────┬─────────────────┘
             │
             ▼
┌──────────────────────────────┐
│ CosyVoice /tts               │
│ emotion: "happy"             │
│ emotion_vector: {            │
│   pitch: 1.15,               │
│   rhythm: 1.05,              │
│   timbre: 0.6                │
│ }                            │
└──────────────────────────────┘
```

### 6.2 Emotion Mapping Table

`backend/prompts/voice.py` — `EmotionResolver`:

| Storyboard Emotion | CosyVoice Tag | emotion_vector {pitch, rhythm, timbre} |
|-------------------|---------------|----------------------------------------|
| happy / joyful | `happy` | {1.15, 1.05, 0.55} |
| sad / sorrowful | `sad` | {0.85, 0.90, 0.40} |
| angry / furious / enraged | `angry` | {1.10, 1.10, 0.75} |
| calm / peaceful / gentle | `soothing` | {0.95, 0.90, 0.45} |
| mysterious / eerie / suspenseful | `mysterious` | {0.90, 0.85, 0.35} |
| determined / resolute / firm | `determined` | {1.05, 1.00, 0.65} |
| afraid / terrified | `sad` | {0.80, 1.15, 0.30} |
| surprised / shocked | `happy` | {1.20, 1.20, 0.55} |
| neutral / default | `neutral` | {1.00, 1.00, 0.50} |
| cold / icy / menacing | `angry` | {0.90, 0.85, 0.70} |
| warm / affectionate / loving | `soothing` | {1.05, 0.95, 0.50} |
| sarcastic / mocking | `happy` | {1.10, 1.15, 0.60} |
| desperate / pleading | `sad` | {0.90, 1.10, 0.45} |
| stoic / emotionless | `neutral` | {0.95, 0.90, 0.55} |

### 6.3 LLM Fallback

Only invoked when:
- Storyboard emotion text is a complex description (not a single word), e.g. "trying to appear calm but seething inside"
- EmotionResolver finds no direct mapping

LLM call: task=`dialogue`, provider=DeepSeek, model=`deepseek-chat`

```python
class EmotionLLMPrompt:
    system: str = (
        "Map a complex emotional description to ONE of: "
        "happy, sad, angry, soothing, mysterious, determined, neutral. "
        "Return JSON: {\"emotion\": \"...\", \"vector\": {\"pitch\": 0.0, \"rhythm\": 0.0, \"timbre\": 0.0}, "
        "\"reasoning\": \"...\"}"
    )
    # Cached: 24h TTL per (emotion_description + character_id)
```

### 6.4 Per-Character Emotion Baseline

Each character's `emotion_range.dominant` sets a persistent offset. Example:

- Captain Alistair: dominant = "stoic determination" → base rhythm -0.05 on all emotions
- Lady Evelyne: dominant = "bright optimism" → base pitch +0.05 on all emotions

This ensures the same "angry" tag sounds different for different characters.

---

## 7. VoiceAgent

`backend/agents/voice_agent.py`

Follows `ImageAgent` pattern (deterministic prompts, no LLM in hot path). Uses ModelRouter only for emotion fallback.

```python
class VoiceAgent:
    """Voice cloning and dialogue synthesis orchestration.

    Reuses:
    - CharacterMemory (Qdrant) → retrieve voice_profile embeddings
    - CharacterLocker → lock character during voice clone
    - SceneRepository → load dialogue JSON arrays
    - ModelRouter → emotion LLM fallback only
    - CacheService → audio + voice_id caching
    """

    def __init__(
        self,
        voice_provider: VoiceProvider,     # CosyVoiceAdapter or GPTSoVITSAdapter
        voice_repo: VoiceRepository,
        cache: CacheService,
        router: ModelRouter,              # Only for emotion fallback
    ) -> None:
        ...

    # ── Voice Cloning ─────────────────────────────────────────────────

    async def clone_character_voice(
        self,
        project_id: str,
        character_id: str,
        voice_profile: dict,
        character_name: str,
    ) -> str:
        """Clone a character's voice. Returns Voice.id (UUID).
        1. Build reference text (deterministic)
        2. Synthesize reference audio (ModelRouter → TTS task or default TTS)
        3. Upload to CosyVoice → speaker ID
        4. Synthesize preview clip
        5. Save Voice row (provider, speaker, speed, pitch, emotion, version, selected=true)
        6. Push to VoiceLibrary
        Cached: speaker per (character_id, voice_profile_hash) — 30-day TTL
        """

    async def get_or_clone_voice(
        self,
        project_id: str,
        character_id: str,
        voice_profile: dict,
        character_version: int,
    ) -> Voice:
        """Return existing selected Voice or clone new one.
        1. Query DB: Voice where character_id, selected=true, version matches
        2. If found → return it
        3. If not → clone, set previous selected=false, set new selected=true
        Uses CharacterLocker to prevent concurrent clones of same character."""

    # ── Dialogue Synthesis ────────────────────────────────────────────

    async def synthesize_dialogue(
        self,
        speaker: str,
        text: str,
        emotion: str = "neutral",
        character_emotion_range: dict | None = None,
        speed: float = 1.0,
        pitch: int = 0,
    ) -> VoiceResult:
        """Synthesize one dialogue line. Deterministic hot path.
        1. EmotionResolver.map(emotion, character_emotion_range)
        2. If unmappable → LLM fallback (cached 24h)
        3. voice_provider.synthesize(SynthesisRequest(speaker, text, emotion, speed, pitch))
        4. Returns VoiceResult with audio bytes
        Cached: audio per (speaker, text, emotion, speed, pitch) — 30-day TTL
        """

    async def synthesize_scene(
        self,
        project_id: str,
        scene_id: str,
        speaker_map: dict[str, str],  # character_name → speaker
    ) -> list[Voice]:
        """Synthesize all dialogue lines for a scene.
        1. SceneRepository.get(scene_id) → dialogue JSON array
        2. For each line: resolve character → speaker, emotion → synthesize
        3. Upload each to MinIO, create Voice rows
        4. Concurrent with asyncio.Semaphore(3)
        """

    # ── Preview ───────────────────────────────────────────────────────

    async def preview_voice(
        self,
        speaker: str,
        sample_text: str | None = None,
    ) -> bytes:
        """Generate a short preview clip (first 8 seconds).
        Uses VoiceProvider.preview() for faster turnaround."""

    # ── Helpers ───────────────────────────────────────────────────────

    async def save_voice_asset(
        self,
        project_id: str,
        character_id: str,
        audio_data: bytes,
        provider: str,
        speaker: str,
        emotion: str,
        speed: float,
        pitch: int,
        version: int,
        scene_id: str | None = None,
        dialogue_index: int | None = None,
    ) -> Voice:
        """Upload audio to MinIO, create Voice DB record. Same pattern as ImageAgent.save_asset()."""

    async def _synthesize_reference_audio(
        self,
        text: str,
        voice_profile: dict,
    ) -> bytes:
        """Generate reference audio for cloning.
        Tries: 1) ModelRouter TTS task 2) System default TTS (edge-tts / pyttsx3 fallback)."""
```

### 7.1 Concurrency

```python
SYNTHESIS_CONCURRENCY = 3      # Per-scene parallel synthesis (CosyVoice GPU limit)
CLONE_CONCURRENCY = 1           # Serial cloning (one character at a time)
```

Contrast with ImageAgent (serial-only) — VoiceAgent uses semaphore(3) for dialogue synthesis because CosyVoice supports concurrent `/tts` requests against a single GPU.

---

## 8. VoiceLibrary Service

`backend/services/voice_library.py`

Central registry of cloned voice IDs. Keeps the mapping of character → voice_id → provider in Redis rather than hitting the DB for every synthesis call.

```python
class VoiceLibrary:
    """Voice speaker cache and audio cache.

    Two-layer cache:
    L1 (Redis): speaker mappings, synthesis results
    L2 (MinIO): audio files (permanent storage)
    """

    # Speaker cache: 7-day TTL
    SPEAKER_TTL = 604800   # 7 days

    # Synthesis cache: 30-day TTL
    SYNTHESIS_TTL = 2592000  # 30 days

    async def get_speaker(self, character_id: str) -> str | None:
        """Look up provider speaker ID for a character. Redis key: voice:speaker:{character_id}"""

    async def set_speaker(self, character_id: str, speaker: str,
                          provider: str, version: int) -> None:
        """Cache speaker. Invalidate on character version bump."""

    async def get_synthesis(self, cache_key: str) -> bytes | None:
        """Retrieve cached synthesis audio. Redis key: voice:synth:{md5}"""

    async def set_synthesis(self, cache_key: str, audio: bytes) -> None:
        """Cache synthesis result."""

    async def invalidate_character(self, character_id: str) -> None:
        """Clear all cached audio for a character (on profile update)."""

    @staticmethod
    def synthesis_cache_key(speaker: str, text: str, emotion: str, speed: float, pitch: int) -> str:
        """Content-addressed key: MD5(speaker + text + emotion + speed + pitch)[:16]"""
```

---

## 9. Provider Adapters

### 9.1 CosyVoiceAdapter

`backend/providers/voice/cosyvoice_adapter.py`

REST client for CosyVoice HTTP API. Async httpx. Same pattern as `ComfyUIAdapter`.

```python
class CosyVoiceAdapter(VoiceProvider):
    """CosyVoice HTTP API adapter.

    CosyVoice exposes:
    - POST /upload          — upload reference audio, returns voice_id
    - POST /tts             — synthesize with emotion control, returns WAV
    - GET  /voices          — list cloned voices
    - DELETE /voices/{id}   — remove cloned voice
    - GET  /health          — health check
    """

    def __init__(self, base_url: str = "http://localhost:5001") -> None:
        self._base_url = base_url
        self._timeout = httpx.Timeout(connect=10.0, read=60.0, write=30.0, pool=10.0)

    # clone_voice(): POST /upload → speaker, timeout 30s
    # synthesize(): POST /tts → WAV bytes, timeout 60s
    # synthesize_batch(): N × POST /tts asyncio.gather (semaphore 3)
    # preview(): POST /tts with max_length=8s, timeout 30s
    # health(): GET /health, timeout 5s
    # list_speakers(): GET /voices
    # delete_speaker(): DELETE /voices/{id}
```

**Configuration** (`.env`):
```bash
COSYVOICE_BASE_URL=http://localhost:5001
COSYVOICE_TIMEOUT=60
```

### 9.2 GPTSoVITSAdapter (Optional)

`backend/providers/voice/gptsovits_adapter.py`

Fallback provider. Same `VoiceProvider` interface, different REST endpoints.

```python
class GPTSoVITSAdapter(VoiceProvider):
    """GPT-SoVITS API adapter (optional fallback).

    GPT-SoVITS exposes:
    - POST /set_reference      — upload reference audio
    - POST /tts               — synthesize
    - GET  /health            — health check
    """

    # clone_voice(): POST /set_reference → speaker ID
    # synthesize(): POST /tts → WAV bytes
    # preview(): POST /tts with short text
    # health(): GET /health
```

**Configuration** (`.env`):
```bash
GPTSOVITS_BASE_URL=http://localhost:5002
GPTSOVITS_ENABLED=false
```

### 9.3 Provider Selection

```python
# In VoiceAgent.__init__ or workflow config:
# Primary: CosyVoiceAdapter
# Fallback: GPTSoVITSAdapter (if GPTSOVITS_ENABLED=true)
# No ModelRouter — VoiceProvider has its own interface, separate from LLM routing.

# If cosyvoice.health() fails and GPTSOVITS_ENABLED:
#   switch to GPTSoVITS, log WARNING, flag voice.voice_provider = "gptsovits"
```

---

## 10. LangGraph Workflow

`backend/workflows/voice_generation.py`

5-node DAG following `image_generation.py` pattern exactly.

```python
@dataclass
class VoiceGenerationState:
    project_id: str
    # Input
    characters: list[dict]       # profiles with id, name, voice_profile, emotion_range
    scenes: list[dict]           # scene id + dialogue JSON array
    scene_storyboards: list[dict]  # scene id → storyboard (for emotion)

    # Config
    phases: list[str]            # ["clone", "synthesize", "preview"]
    regenerate: bool = False

    # Outputs
    speaker_map: dict[str, str]  # character_id → speaker
    selected_voice_ids: dict[str, str]  # character_id → Voice.id (UUID)
    clone_voice_assets: list[dict]
    synthesis_voice_assets: list[dict]
    preview_voice_assets: list[dict]

    # Tracking
    batch_id: str
    job_id: str
    progress: int = 0
    errors: list[str]
    status: str = "running"
```

### 10.1 Node Graph

```
┌─────────┐     ┌──────────────┐     ┌──────────────┐     ┌─────────┐     ┌──────┐
│  clone  │────→│  synthesize  │────→│   preview    │────→│  save   │────→│ END  │
└────┬────┘     └──────┬───────┘     └──────┬───────┘     └────┬────┘     └──────┘
     │                 │                     │                  │
     └─────────────────┴─────────────────────┴──────────────────┤ (on failure)
                                                               │
                                                            ┌──▼──┐
                                                            │ END │
                                                            └─────┘
```

| Node | Description | Phase Key | Skippable |
|------|-------------|-----------|-----------|
| `_clone_node` | Clone voice for each character. Serial (CLONE_CONCURRENCY=1). Skips characters with cached voice_id unless `regenerate=True`. | `clone` | Yes |
| `_synthesize_node` | Synthesize all dialogue lines across all scenes. Concurrent semaphore(3). Load dialogue from SceneRepository. Resolve emotion per line. | `synthesize` | Yes |
| `_preview_node` | Generate 8s preview clip for each character. | `preview` | Yes |
| `_save_node` | Save all accumulated Voice assets. Route here on any phase failure to persist completed work. | — | No |

### 10.2 Phase Progress Map

```python
PROGRESS_MAP = {
    "clone_start": 5,
    "clone_done": 35,
    "synthesize_start": 40,
    "synthesize_done": 85,
    "preview_start": 88,
    "preview_done": 95,
    "save_done": 100,
}
```

### 10.3 Celery Task

`backend/workflows/tasks.py` — Append `run_voice_generation`:

```python
@celery_app.task(name="workflows.voice_generation.run", bind=True,
                 max_retries=2, default_retry_delay=120)
def run_voice_generation(self, project_id: str, job_id: str,
                         phases: list[str] | None = None,
                         regenerate: bool = False):
    """Load characters/scenes from DB, initialize VoiceProvider + VoiceAgent,
    run workflow with progress updates at each phase transition."""
```

---

## 11. API Endpoints

`backend/api/v1/voices.py` — 5 endpoints following `assets.py` pattern:

| Method | Endpoint | Status | Description |
|--------|----------|--------|-------------|
| POST | `/api/v1/voices/generate` | 202 | Trigger voice generation (clone + synthesize) via Celery |
| GET | `/api/v1/voices` | 200 | List voices (?project_id=, ?character_id=, ?voice_type=, paginated) |
| GET | `/api/v1/voices/{id}` | 200 | Get voice with full metadata |
| GET | `/api/v1/voices/{id}/preview` | 200 | Stream preview audio (audio/wav) |
| DELETE | `/api/v1/voices/{id}` | 204 | Delete voice asset (409 if locked) |

### 11.1 Request Schemas

```python
class VoiceGenerateRequest(BaseModel):
    project_id: UUID
    regenerate: bool = False
    phases: list[str] = ["clone", "synthesize", "preview"]

class VoiceGenerateResponse(BaseModel):
    job_id: UUID
    batch_id: UUID
    status: str
    message: str

class VoiceResponse(BaseModel):
    # ── Core identity ──
    voice_id: UUID                  # id column (PK)
    character_id: UUID
    provider: str                   # "cosyvoice" | "gptsovits"
    speaker: str                    # provider-side speaker ID
    # ── Synthesis params ──
    speed: float = 1.0
    pitch: int = 0                  # semitones, -12 to +12
    emotion: str = "neutral"
    # ── Version & selection ──
    version: int                    # character version this voice was cloned from
    selected: bool = True           # user-approved as active voice
    # ── Audio assets ──
    file_path: str                  # MinIO path for synthesis audio
    file_size: int | None
    duration_ms: float | None
    preview_path: str | None        # MinIO path for preview clip
    reference_audio_path: str | None  # MinIO path for uploaded reference audio
    # ── Context ──
    scene_id: UUID | None
    dialogue_index: int | None
    voice_params: dict | None       # JSONB: {emotion_vector, reference_audio_hash, accent, tone_quality, ...}
    # ── Metadata ──
    status: str
    created_at: datetime
    updated_at: datetime

class VoiceListResponse(BaseModel):
    items: list[VoiceResponse]
    total: int
    offset: int
    limit: int
```

---

## 12. Cache Strategy

Three-layer caching following MODEL_POLICY §5 and CharacterAgent patterns:

| Layer | Store | Entity | TTL | Key Pattern |
|-------|-------|--------|-----|-------------|
| L1 | Redis DB 2 | speaker → character mapping | 7 days | `voice:speaker:{character_id}` |
| L1 | Redis DB 2 | synthesis audio (small <100KB) | 30 days | `voice:synth:{md5_hash}` |
| L1 | Redis DB 2 | emotion LLM resolution | 24h | `voice:emotion:{md5_hash}` |
| L2 | MinIO | All audio files (WAV) | Permanent | `projects/{id}/voices/{filename}` |
| L3 | Re-synthesis | On cache miss | — | Same (speaker, text, emotion, speed, pitch) → same audio |

### 12.1 Cache Key Format

```python
# Speaker cache
CacheService.build_key("voice_speaker", character_id, voice_profile_hash)
# → "cache:model:voice_speaker:{project_id}:{hash}"

# Synthesis cache
VoiceLibrary.synthesis_cache_key(speaker, text, emotion, speed, pitch)
# → MD5(f"{speaker}|{text}|{emotion}|{speed}|{pitch}")[:16]

# Emotion LLM cache
CacheService.build_key("voice_emotion", project_id, emotion_desc_hash)
# → "cache:model:voice_emotion:{project_id}:{hash}"
```

### 12.2 Invalidation Triggers

| Trigger | Action |
|---------|--------|
| Character profile updated (version bump) | Invalidate voice_id cache → re-clone on next generate |
| Character locked_by → new lock | Block voice generation (409 Conflict) |
| Scene dialogue changed | No automatic invalidation — user triggers regenerate |
| Regenerate flag set | Skip all caches (X-Bypass-Cache pattern) |

---

## 13. Version Strategy

### 13.1 Voice-Version Binding

Each Voice row records which character version it was cloned from (`version`). This mirrors `CharacterVersion` table pattern.

```
Character.version = 3
    │
    ├── Voice (provider="cosyvoice", version=3, selected=true)   ← current, active
    │
    └── Voice (provider="cosyvoice", version=2, selected=false)  ← stale, preserved for rollback
```

### 13.2 Regeneration Rules

| Scenario | Action |
|----------|--------|
| Character version unchanged, selected Voice exists | Use cached speaker (no re-clone) |
| Character version incremented | Re-clone → new Voice row (version=N, selected=true), old Voice set selected=false |
| `regenerate=True` in request | Force re-clone even if version unchanged |
| Character.voice_profile unchanged but other fields changed | Skip re-clone (voice_profile hash unchanged) |

### 13.3 Rollback

`POST /api/v1/characters/{id}/rollback` (existing endpoint) restores an old character version. When the character version is rolled back:
1. Existing Voice with matching `character_id` and `version` is looked up
2. If found → set `selected=true` on that Voice, set `selected=false` on all other Voices for this character
3. If not found (never cloned for that version) → trigger re-clone

### 13.4 Selection Pattern (mirrors Asset.selected)

```
character_id = "uuid-alistair"

Voice #1: version=1, selected=false  (historical)
Voice #2: version=2, selected=false  (historical)
Voice #3: version=3, selected=true   ← current active voice
```

User can switch via `PATCH /voices/{id}` with `{"selected": true}` — sets all other Voices for that character to `selected=false`.

### 13.4 Voice Profile Hash

```python
# Detect whether voice_profile actually changed between versions:
voice_profile_hash = CacheService.hash_content(
    json.dumps(character.profile.get("voice_profile", {}), sort_keys=True)
)
# Only re-clone if hash differs from last clone's voice_params.reference_audio_hash
```

---

## 14. Prompt Templates

`backend/prompts/voice.py` — 3 modules, all deterministic except EmotionLLMPrompt:

| Class | Type | Purpose |
|-------|------|---------|
| `ReferenceTextPrompt` | Deterministic | Build reference text for voice cloning |
| `EmotionResolver` | Deterministic | Map storyboard emotion → CosyVoice tag + vector |
| `EmotionLLMPrompt` | LLM (cached) | Fallback: complex emotion → supported tag |
| `VoiceProfileMapper` | Deterministic | Character voice_profile → synthesis parameters |

---

## 15. Integration Points (Reuse)

| Existing Component | How VoiceAgent Reuses It |
|-------------------|------------------------|
| `CharacterMemory` (Qdrant) | Retrieve voice_profile embeddings for similarity search across character voices |
| `CharacterLocker` | Lock character during voice cloning to prevent concurrent modification |
| `SceneRepository` | Load dialogue JSON array + storyboard emotion for synthesis |
| `ModelRouter` | Only for emotion LLM fallback (task=`dialogue`); NOT used for TTS hot path |
| `CacheService` | Voice ID + synthesis + emotion LLM caching |
| `CostLogger` | Log emotion LLM calls (TTS provider cost logged separately by VoiceProvider) |
| `infra.minio.upload_file` | Store audio WAV files |
| `infra.queue.create_job` | Celery job creation for async workflows |

**Not used**: CharacterAgent (not modified), ImageAgent (not modified), StoryAgent, EpisodeAgent, SceneAgent, NovelAgent.

---

## 16. Test Plan

### 16.1 Unit Tests (Mock)

`tests/test_voice_prompts.py` — 15 tests:
- `TestReferenceTextPrompt` (3): standard profile, minimal profile (missing fields), empty patterns list
- `TestEmotionResolver` (8): happy, sad, angry, neutral, unknown→LLM-fallback, character baseline offset, edge case: empty emotion, edge case: None emotion
- `TestVoiceProfileMapper` (4): pitch mapping (high/medium/low), tempo mapping, tone_quality→timbre, full profile→params

`tests/test_voice_agent.py` — 12 tests:
- `TestCloneCharacterVoice` (2): successful clone, clone with cached voice_id
- `TestGetOrCloneVoice` (2): cache hit, cache miss → clone
- `TestSynthesizeDialogue` (3): standard synthesis, cached synthesis, emotion fallback to LLM
- `TestSynthesizeScene` (2): full scene (3 dialogue lines), empty dialogue array
- `TestPreviewVoice` (1): preview returns truncated audio
- `TestSaveVoiceAsset` (2): clone type, synthesis type

`tests/test_voice_adapter.py` — 10 tests:
- `TestCosyVoiceClone` (2): successful clone returns voice_id, upload failure
- `TestCosyVoiceSynthesize` (3): standard synthesis, emotion control, batch synthesis
- `TestCosyVoiceHealth` (2): healthy, unhealthy (connection refused)
- `TestCosyVoiceListDelete` (2): list voices, delete voice
- `TestGPTSoVITSFallback` (1): fallback when CosyVoice unhealthy

### 16.2 Workflow Tests

`tests/test_voice_workflow.py` — 6 tests:
- `TestVoiceGenerationState` (2): default state, phase filtering
- `TestBuildWorkflow` (4): workflow construction, clone node, synthesize node, save node on failure

### 16.3 Integration Tests (Real Provider)

Requires CosyVoice running locally:
- `test_clone_real`: Real voice cloning produces valid voice_id
- `test_synthesize_real`: Real synthesis produces non-empty WAV
- `test_preview_real`: Preview returns < 10-second audio
- `test_emotion_real`: Different emotions produce audibly different audio (RMS energy comparison)

**Total**: 43 new tests. Combined with existing 165 = **208 total**.

---

## 17. Acceptance Criteria

### 17.1 Voice Cloning
- [ ] `POST /voices/generate` with `phases=["clone"]` produces one Voice row per character
- [ ] Voice row contains valid `speaker` (CosyVoice provider-side ID)
- [ ] Voice row records `version` matching character's current version
- [ ] First clone for a character has `selected=true`
- [ ] Reference audio is stored in MinIO at `reference_audio_path`
- [ ] Preview clip is stored in MinIO at `preview_path`
- [ ] Subsequent generate with unchanged character version uses cached speaker (no re-clone)

### 17.2 Voice Consistency
- [ ] Same character + same voice_profile → same speaker (deterministic, via cache)
- [ ] Character version bump → new Voice row created, old Voice set `selected=false`, new Voice `selected=true`
- [ ] Character rollback → old `selected` Voice restored if version matches
- [ ] PATCH voice `selected=true` → all other Voices for that character set `selected=false`

### 17.3 Dialogue Synthesis
- [ ] `POST /voices/generate` with `phases=["synthesize"]` produces Voice rows per dialogue line
- [ ] Each synthesis Voice row linked to correct `scene_id` and `dialogue_index`
- [ ] `speed`, `pitch`, `emotion` set from EmotionResolver + per-character baseline
- [ ] Complex emotions fall back to LLM resolution (logged via CostLogger)

### 17.4 Emotion Accuracy
- [ ] All 14 emotion mappings produce valid CosyVoice tags
- [ ] Character baseline emotion offsets applied to synthesis parameters
- [ ] LLM fallback cached — same complex emotion → no repeated LLM calls

### 17.5 Caching
- [ ] Voice ID cache hit → 0 provider calls
- [ ] Synthesis cache hit → 0 provider calls
- [ ] Emotion LLM cache hit → 0 ModelRouter calls
- [ ] Regenerate flag → all caches bypassed

### 17.6 Resilience
- [ ] CosyVoice health check fails → automatic fallback to GPT-SoVITS (if enabled)
- [ ] All providers unhealthy → job status FAILED with clear error, completed phases saved
- [ ] Celery task retry (max 2, delay 120s) on transient failures
- [ ] Celery task cancellation via `POST /jobs/{id}/cancel`

### 17.7 API Coverage
- [ ] `POST /voices/generate` returns 202 with job_id + batch_id
- [ ] `GET /voices?project_id=&character_id=&voice_type=` returns paginated list
- [ ] `GET /voices/{id}` returns full VoiceResponse with all metadata
- [ ] `GET /voices/{id}/preview` streams audio/wav
- [ ] `DELETE /voices/{id}` returns 204 (409 if locked via CharacterLocker)

### 17.8 Non-Regression
- [ ] All 165 existing tests pass unchanged
- [ ] No existing agent modified (NovelAgent, StoryAgent, EpisodeAgent, SceneAgent, CharacterAgent, ImageAgent)
- [ ] No existing API endpoints modified
- [ ] No existing prompt templates modified

---

## 18. Performance Estimates

| Operation | Expected Duration | Scaling |
|-----------|------------------|---------|
| Clone one voice | ~15s (reference TTS 5s + upload 5s + clone 5s) | N characters × 15s (serial) |
| Synthesize one line | ~3s (emotion resolve + TTS) | M lines / 3 concurrent ≈ M × 1s |
| Full scene (10 lines) | ~10s (with semaphore(3)) | — |
| Full project (5 chars × 50 lines) | ~3 min | 75s clone + 150s synthesis |
| Cache hit (any operation) | <50ms | Redis round-trip |

**Comparison**: Voice pipeline ~3 min for full project vs Image pipeline ~17 min for full project. Voice is faster because:
- No GPU diffusion sampling (CosyVoice is encoder-decoder, not diffusion)
- Concurrent synthesis (semaphore(3) vs ImageAgent's serial-only)
- Smaller output files (WAV ~200KB vs PNG ~2MB)

---

## 19. Docker Compose Changes

Add to `docker-compose.yml`:

```yaml
  cosyvoice:
    image: cosyvoice/cosyvoice:latest
    ports:
      - "5001:5001"
    volumes:
      - cosyvoice_models:/app/models
      - cosyvoice_output:/app/output
    environment:
      - CUDA_VISIBLE_DEVICES=0
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]

  gptsovits:  # optional
    image: gptsovits/gptsovits:latest
    ports:
      - "5002:5002"
    volumes:
      - gptsovits_models:/app/models
    environment:
      - CUDA_VISIBLE_DEVICES=0
    profiles:
      - gptsovits  # Only started with --profile gptsovits
```

---

## 20. ENV Changes

Add to `.env.example`:

```bash
# Voice Generation
COSYVOICE_BASE_URL=http://localhost:5001
COSYVOICE_TIMEOUT=60
GPTSOVITS_BASE_URL=http://localhost:5002
GPTSOVITS_ENABLED=false
```

---

## 21. Known Limitations (Proactive)

1. **Reference audio quality**: Step 2 generates reference audio via LLM TTS (DeepSeek/OAI). This is a synthetic voice cloning another synthetic voice — quality degradation is expected compared to human-supplied reference audio. Mitigation: `POST /voices/generate` could accept optional `reference_audio` upload in the future.

2. **No per-line retry**: Like ImageAgent, `VoiceAgent.synthesize_dialogue()` has no retry on individual line failure. One failed synthesis abandons that dialogue slot. Mitigation: Celery task-level retry (2×) catches most transient failures.

3. **MemorySaver only**: Workflow checkpoints are in-memory (same as image workflow). Lost on process restart.

4. **No multi-speaker scene synthesis**: Each dialogue line is synthesized independently. CosyVoice supports multi-speaker conversation mode but this plan uses single-speaker `/tts` for simplicity.

5. **Emotion granularity**: CosyVoice supports 7 emotion tags. The 14-point mapping is a best-effort approximation. "Sarcastic" → "happy" is technically incorrect but the closest available tag.

6. **No streaming**: `GET /voices/{id}/preview` downloads the full WAV file. True audio streaming (chunked transfer) requires additional implementation.

7. **Voice file accumulation**: Unlike ImageAgent (which has select/favorite to prune), VoiceAgent has no pruning mechanism. All synthesis audio is kept permanently. Storage cost grows linearly with dialogue count.

---

## 22. Files Summary

| File | Lines (est.) | New/Modify |
|------|-------------|------------|
| `backend/interfaces/voice.py` | ~80 | NEW |
| `backend/providers/voice/__init__.py` | ~3 | NEW |
| `backend/providers/voice/cosyvoice_adapter.py` | ~180 | NEW |
| `backend/providers/voice/gptsovits_adapter.py` | ~120 | NEW |
| `backend/agents/voice_agent.py` | ~260 | NEW |
| `backend/prompts/voice.py` | ~160 | NEW |
| `backend/services/voice_library.py` | ~90 | NEW |
| `backend/workflows/voice_generation.py` | ~380 | NEW |
| `backend/api/v1/voices.py` | ~170 | NEW |
| `backend/api/v1/schemas.py` | +~60 | MODIFY |
| `backend/domain/models.py` | +~15 | MODIFY |
| `backend/repository/voice_repository.py` | +~20 | MODIFY |
| `backend/workflows/tasks.py` | +~90 | MODIFY |
| `backend/main.py` | +~2 | MODIFY |
| `backend/alembic/versions/005_extend_voices.py` | ~40 | NEW |
| `docker-compose.yml` | +~20 | MODIFY |
| `.env.example` | +~4 | MODIFY |
| `tests/test_voice_prompts.py` | ~120 | NEW |
| `tests/test_voice_agent.py` | ~130 | NEW |
| `tests/test_voice_adapter.py` | ~110 | NEW |
| `tests/test_voice_workflow.py` | ~80 | NEW |

**Total**: ~2,100 new lines, ~200 modified lines. 43 new tests. All under <500 lines/file per RULES.
