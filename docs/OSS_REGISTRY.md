# OSS Registry

Version: 2.0

This file defines all approved external providers.

Only integrate listed providers.

Never recreate capabilities.

Never train models.

Never fork providers.

System responsibility:

orchestration only.

Provider responsibility:

generation only.

---

Architecture

Provider

↓

Adapter

↓

Interface

↓

Agent

↓

Workflow

↓

API

---

Provider Rules

Every provider must support:

health check

docker

config

logging

versioning

integration test

replacement

---

Directory

backend/

providers/

interfaces/

agents/

services/

---

Provider Template

Provider

Repository

Version

Deploy

Runtime

GPU

Health

Adapter

Replaceable

Priority

---

Novel Parsing

Provider

Unstructured

Repository

https://github.com/Unstructured-IO/unstructured

Version

latest stable

Deploy

pip

Runtime

python

GPU

no

Health

/health

Install

pip install unstructured

Location

providers/novel/

Adapter

NovelParserAdapter

Interface

NovelParser

Methods

parse()

split()

extract()

Replaceable

yes

Priority

required

---

Long Context

Provider

LlamaIndex

Repository

https://github.com/run-llama/llama_index

Version

latest stable

Deploy

pip

Runtime

python

GPU

optional

Install

pip install llama-index

Location

providers/context/

Adapter

ContextAdapter

Interface

ContextStore

Methods

embed()

search()

delete()

Replaceable

yes

Priority

required

---

Vector Storage

Provider

Qdrant

Repository

https://github.com/qdrant/qdrant

Version

stable

Deploy

docker

Runtime

container

GPU

no

Install

docker compose

Location

providers/vector/

Adapter

VectorAdapter

Interface

VectorStore

Methods

upsert()

query()

delete()

Replaceable

yes

Priority

required

---

Workflow

Provider

LangGraph

Repository

https://github.com/langchain-ai/langgraph

Version

stable

Deploy

pip

Runtime

python

GPU

no

Install

pip install langgraph

Location

providers/workflow/

Adapter

WorkflowAdapter

Interface

StoryEngine

Methods

run()

resume()

checkpoint()

Replaceable

yes

Priority

required

---

Character Memory

Provider

GraphRAG

Repository

https://github.com/microsoft/graphrag

Version

stable

Deploy

pip

Runtime

python

GPU

optional

Install

pip install graphrag

Location

providers/character/

Adapter

CharacterMemoryAdapter

Interface

CharacterMemory

Methods

save()

query()

merge()

Replaceable

yes

Priority

required

---

Entity Extraction

Provider

spaCy

Repository

https://github.com/explosion/spaCy

Version

stable

Deploy

pip

Runtime

python

GPU

optional

Install

pip install spacy

Location

providers/entity/

Adapter

EntityAdapter

Interface

EntityService

Methods

extract()

normalize()

Replaceable

yes

Priority

recommended

---

Image Generation

Provider

ComfyUI

Repository

https://github.com/comfyanonymous/ComfyUI

Version

stable

Deploy

docker

Runtime

python

GPU

required

Install

git clone

Location

providers/image/

Adapter

ImageAdapter

Interface

ImageProvider

Methods

generate()

regenerate()

upscale()

Replaceable

yes

Priority

required

---

Character Consistency

Provider

InstantID

Repository

https://github.com/InstantID/InstantID

Version

stable

Deploy

docker

Runtime

python

GPU

required

Install

git clone

Location

providers/image/

Adapter

CharacterAdapter

Interface

CharacterRenderer

Methods

lock()

render()

Replaceable

yes

Priority

required

---

Optional Story Visual

Provider

StoryDiffusion

Repository

https://github.com/HVision-NKU/StoryDiffusion

Version

latest

Deploy

docker

Runtime

python

GPU

required

Location

providers/image/

Adapter

StoryAdapter

Interface

StoryRenderer

Methods

render_story()

Replaceable

yes

Priority

optional

---

Voice

Provider

CosyVoice

Repository

https://github.com/FunAudioLLM/CosyVoice

Version

stable

Deploy

docker

Runtime

python

GPU

optional

Install

git clone

Location

providers/voice/

Adapter

VoiceAdapter

Interface

VoiceProvider

Methods

tts()

clone()

Replaceable

yes

Priority

required

---

Voice Clone

Provider

GPT-SoVITS

Repository

https://github.com/RVC-Boss/GPT-SoVITS

Version

stable

Deploy

docker

Runtime

python

GPU

recommended

Install

git clone

Location

providers/voice/

Adapter

CloneAdapter

Interface

VoiceClone

Methods

clone()

Replaceable

yes

Priority

optional

---

Video

Provider

Wan2.1

Repository

https://github.com/Wan-Video/Wan2.1

Version

stable

Deploy

docker

Runtime

python

GPU

required

Install

git clone

Location

providers/video/

Adapter

VideoAdapter

Interface

VideoProvider

Methods

generate()

status()

Replaceable

yes

Priority

required

---

Alternative Video

Provider

CogVideoX

Repository

https://github.com/THUDM/CogVideo

Version

latest

Deploy

docker

Runtime

python

GPU

required

Location

providers/video/

Adapter

CogVideoAdapter

Interface

VideoProvider

Methods

generate()

Replaceable

yes

Priority

optional

---

Editing

Provider

FFmpeg

Repository

https://ffmpeg.org

Version

stable

Deploy

apt

Runtime

binary

GPU

no

Install

apt install ffmpeg

Location

providers/export/

Adapter

ExportAdapter

Interface

VideoComposer

Methods

compose()

subtitle()

export()

Replaceable

yes

Priority

required

---

Monitoring

Provider

Prometheus

Provider

Grafana

Location

infra/

Priority

recommended

---

Provider Requirements

Generate:

Dockerfile

health endpoint

README

integration tests

metrics

OpenAPI

---

Strict Rules

Never implement provider internals.

Never rewrite generation.

Only wrap.

Only orchestrate.

Only integrate.

Stop after current TASK.
