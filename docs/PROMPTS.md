# Prompt Design — Full Pipeline

## Design Principles

Per RULES.md: "All prompts: backend/prompts/. No inline prompt."

Every LLM call follows this pattern:

```python
prompt = SomePrompt().render(arg1=..., arg2=...)
text, meta = await router.generate(
    task="scene",
    prompt=prompt["system"] + "\n\n" + prompt["user"],
    project_id=project_id,
)
```

---

# Story Generation Layer (TASK_004)

## Design Principles

Per RULES.md: "All prompts: backend/prompts/. No inline prompt."

Every LLM call follows this pattern:

```python
prompt = SomePrompt().render(arg1=..., arg2=...)
text, meta = await router.generate(
    task="summary",
    prompt=prompt["system"] + "\n\n" + prompt["user"],
    project_id=project_id,
)
```

## Prompt Inventory

### 1. StorySummarizePrompt (`prompts/summary.py`)

**Purpose:** Produce structured narrative summary from merged chapter summaries.

**System prompt:** Positions the model as a senior story analyst. Requires structured JSON output with four fields:
- `narrative_summary` — 3-5 cohesive paragraphs
- `protagonist_arc` — main character's journey
- `central_conflict` — primary narrative tension
- `turning_points` — 3-7 key moments

**User template:** Chapter summaries + entity metadata → structured JSON.

**Used by:** `StoryAgent.summarize()` — final polish step after hierarchical merge.

---

### 2. ChapterSummaryPrompt (`prompts/summary.py`)

**Purpose:** Summarize a single chapter into structured data.

**System prompt:** 200-400 word summary format. Output: chapter_summary, key_events (3-8), characters_appearing, primary location.

**User template:** Chapter index + text (truncated to 12K chars) → structured JSON.

**Used by:** `StoryAgent._summarize_chapter()` — MAP phase of map-reduce.

---

### 3. MergeSummaryPrompt (`prompts/summary.py`)

**Purpose:** Merge multiple chapter summaries into one coherent summary.

**Output:** merged_summary, key_themes, narrative_throughline.

**Used by:** `StoryAgent._merge_summaries()` — REDUCE phase, called hierarchically with batch_size=6.

---

### 4. ExtractionPrompt (`prompts/extraction.py`)

**Purpose:** Extract structured narrative data from story summary.

**Output (JSON):**
- `timeline` — chronological events with chapter_ref and characters
- `conflicts` — typed conflicts (person_vs_person, person_vs_self, person_vs_society, person_vs_nature, person_vs_technology)
- `relationships` — character pairs with relation_type, evolution, significance
- `world_setting` — time_period, primary_locations, social_rules, atmosphere, notable_systems

**Used by:** `StoryAgent.extract()` — single LLM call after summarization.

---

### 5. EpisodePlanPrompt (`prompts/episode.py`)

**Purpose:** Convert story summary + timeline → serialized episode breakdown.

**System prompt rules:**
- Every episode is a self-contained narrative unit.
- End with cliffhanger (except final episode → narrative closure).
- Distribute turning points evenly for pacing.
- Episode count heuristic: <20 chapters → 5-8, 20-50 → 8-15, >50 → 12-20.
- Every chapter assigned exactly once (no gaps, no overlaps).
- Each episode: 3-5 key_scenes.

**Output:** Ordered episode list with episode_number, title, summary, chapter_range, cliffhanger, key_scenes.

**Used by:** `EpisodeAgent.plan()`.

---

### 6. EpisodeRegeneratePrompt (`prompts/episode.py`)

**Purpose:** Regenerate a single episode with human feedback.

**Context provided:**
- Original episode (title, summary, key_scenes, cliffhanger)
- Adjacent episodes (for consistency)
- User feedback

**Used by:** `EpisodeAgent.regenerate_episode()`.

---

## Token Strategy

### Map-Reduce Pipeline

```
Chapters (N) → MAP: ChapterSummaries (N calls, ~8K in / 500 out each)
                    ↓
              REDUCE: MergeSummaries (log₂(N) calls, ~4K in / 800 out each)
                    ↓
              StorySummarizePrompt (1 call, ~4K in / 1500 out)
                    ↓
              ExtractionPrompt (1 call, ~3.5K in / 2K out)
                    ↓
              EpisodePlanPrompt (1 call, ~3K in / 3K out)
```

### Budget (40-chapter novel)

| Phase | Calls | Est. Input | Est. Output |
|-------|-------|-----------|-------------|
| Chapter summaries | 40 | 320K | 20K |
| Hierarchical merge | ~3 | 12K | 2.4K |
| Story summary | 1 | 4K | 1.5K |
| Extraction | 1 | 3.5K | 2K |
| Episode plan | 1 | 3K | 3K |
| **Total** | **46** | **342.5K** | **28.9K** |

Estimated cost (DeepSeek): ~$0.025

## JSON Parsing

All prompts request structured JSON. The `_parse_json_response` method handles three cases:

1. Direct JSON parse (best case).
2. Extraction from markdown code fences (```json ... ```).
3. Regex extraction of first `{...}` block in text.

Fallback: returns the provided default dict. Parsing failures are logged at WARNING level but do not crash the workflow.

## Cache Integration

Per MODEL_POLICY §5:
- Chapter summaries: permanent cache (TTL=0, content-addressed).
- Story summary: 24h TTL.
- Extraction results: 24h TTL.
- Episode plan: 24h TTL.

`X-Bypass-Cache: true` header skips all cache layers for regeneration requests.

---

# Scene Generation Layer (TASK_005)

### 1. SceneSplitPrompt (`prompts/scene.py`)

**Purpose:** Split episode summary into numbered scene beat boundaries.

**System prompt rules:**
- Each key_scene beat → 1-2 actual scenes
- Scene duration: 20-60 seconds (short-form video format)
- characters_present: only characters who appear on screen or speak
- scene_beat: 2-4 sentence description of what happens
- Number scenes sequentially from 1

**Output:** `scenes[]` — each with scene_number, scene_title, scene_beat, characters_present, estimated_duration.

**Used by:** `SceneAgent._split_episode()`.

---

### 2. SceneStoryboardPrompt (`prompts/scene.py`)

**Purpose:** Generate full cinematography for a single scene beat.

**Controlled vocabularies:**
- **Camera** (10 terms): wide, medium, close-up, POV, tracking, pan, dutch angle, over-the-shoulder, two-shot, establishing
- **Emotion** (12 tones): tense, joyful, melancholic, suspenseful, romantic, ominous, peaceful, chaotic, tender, angry, fearful, hopeful
- **Transition** (5 types): cut, fade, dissolve, match_cut, wipe (default: cut)

**Output:** scene_title, description (3-5 sentences), camera, emotion, location (visual detail), dialogue[{character, line}], props[], transition, character_actions{}, asset_refs[] (SCREAMING_SNAKE_CASE identifiers for future asset generation).

**Context provided:** episode summary, world setting, scene beat, characters_present, previous scene summary, next scene beat.

**Used by:** `SceneAgent._storyboard_scene()` — called per scene with asyncio.Semaphore(3) concurrency.

---

### 3. SceneValidatePrompt (`prompts/scene.py`)

**Purpose:** Continuity checker — validate scene sequence for logical consistency.

**Checks (5 dimensions):**
1. Character continuity — no character appears without entrance or exit
2. Location consistency — scene changes are motivated by narrative
3. Time progression — timeline flows forward logically
4. Emotional arc — emotions shift naturally between scenes
5. Prop continuity — props don't vanish without reason

**Output:** `valid: bool`, `issues[{scene_pair, problem, suggestion}]`. If valid=true, issues must be empty array.

**Used by:** `SceneAgent._validate_continuity()` — non-blocking on failure (returns `validation_passed=True` even if valid=false, issues logged as WARNING).

---

### 4. SceneEditPrompt (`prompts/scene.py`)

**Purpose:** Regenerate a single scene incorporating director feedback while maintaining continuity with adjacent scenes.

**Rules:**
- Preserve scene_number and characters_present from original
- Fully incorporate feedback
- Maintain continuity with adjacent scenes
- Keep original values for fields not mentioned in feedback

**Context provided:** current scene (full JSON), adjacent scenes (before/after), director feedback.

**Used by:** `SceneAgent.regenerate_scene()` — triggered by PATCH /scenes/{id} with `feedback` field.

---

## Scene Token Strategy

### Per-Episode Budget (5-scene episode)

| Phase | Calls | Est. Input | Est. Output |
|-------|-------|-----------|-------------|
| Scene split | 1 | ~500 | ~350 |
| Storyboard (×5) | 5 | ~2,125 | ~1,500 |
| Continuity validate | 1 | ~650 | ~250 |
| **Total** | **7** | **~3,275** | **~2,100** |

Estimated cost (DeepSeek): ~$0.0010 per episode.

### Cache Strategy

| Entity | TTL | Content Hash Input |
|--------|-----|--------------------|
| Scene split | 24h | episode title + summary |
| Scene storyboard | 1h | episode summary + scene beat + scene number |
| Scene validate | 24h | full serialized scenes JSON |

Cold start: N+2 LLM calls. Full cache hit: 0 calls.

## JSON Parsing (Scene Layer)

All scene prompts share the same 3-fallback parsing as the story layer (`SceneAgent._parse_json()`):

1. Direct `json.loads()` (best case — LLM outputs clean JSON)
2. Code fence extraction: regex ```` ```json ... ``` ```` or ```` ``` ... ````
3. Regex `{...}` extraction — greedy first JSON object in the text
4. Fallback: returns the default dict provided by the caller (WARNING log)

Scene storyboard default: medium shot, neutral emotion, empty dialogue/props, cut transition — a usable but generic scene that won't block the pipeline.
