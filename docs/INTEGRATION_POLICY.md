# Integration Policy

Version 1.0

---

Goal

Reuse existing OSS.

Do not recreate.

Integrate only.

---

Pattern

Provider

↓

Adapter

↓

Interface

↓

Agent

---

Rules

Providers isolated.

Replaceable.

Containerized.

Versioned.

---

Novel Parsing

Provider:

Unstructured

Adapter:

NovelParser

Methods:

parse()

split()

extract()

---

Long Context

Provider:

LlamaIndex

Adapter:

ContextStore

Methods:

embed()

search()

---

Story

Provider:

LangGraph

Adapter:

StoryEngine

Methods:

generate()

resume()

---

Character Memory

Provider:

GraphRAG

Adapter:

CharacterMemory

Methods:

save()

query()

---

Image

Provider:

ComfyUI

Adapter:

ImageProvider

Methods:

generate()

regenerate()

upscale()

---

Character Consistency

Provider:

InstantID

Adapter:

CharacterRenderer

Methods:

lock()

render()

---

Voice

Provider:

CosyVoice

Adapter:

VoiceProvider

Methods:

tts()

clone()

---

Video

Provider:

Wan2.1

Adapter:

VideoProvider

Methods:

generate()

---

Editing

Provider:

FFmpeg

Adapter:

VideoComposer

Methods:

compose()

export()

---

Requirements

No provider modification.

No provider fork.

No training.

Only orchestration.

---

Output Requirements

Docker

README

Tests

Health Check

Metrics

OpenAPI
