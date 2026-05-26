# TASK 003A

Goal

Build AI Model Gateway.

This task must be completed before TASK_004.

Do not modify business logic.

Do not change completed tasks.

Only introduce model infrastructure.

---

Read

MASTER_PROMPT.md

RULES.md

INTEGRATION_POLICY.md

OSS_REGISTRY.md

MODEL_POLICY.md

---

Objective

Centralize model access.

No direct SDK usage.

No direct API key usage.

All model calls must pass gateway.

---

Architecture

Agent

↓

ModelRouter

↓

ProviderAdapter

↓

SDK

---

Create

backend/

providers/

llm/

openai/

gemini/

deepseek/

anthropic/

openrouter/

local/

services/

model_router/

config/

secrets/

---

Interfaces

LLMProvider

Methods

generate()

stream()

embedding()

health()

---

Router

ModelRouter

Methods

select()

fallback()

retry()

---

Config

backend/config/models.yaml

---

Secrets

.env

.env.example

---

Supported Keys

OPENAI_API_KEY

OPENAI_BASE_URL

DEEPSEEK_API_KEY

DEEPSEEK_BASE_URL

GEMINI_API_KEY

ANTHROPIC_API_KEY

OPENROUTER_API_KEY

---

Create

SecretLoader

Methods

load()

validate()

mask()

---

Generate

provider adapters

health endpoint

cost logging

timeout

retry

cache

---

API

GET /models

GET /models/health

POST /models/test

---

Requirements

No hardcoded model.

No direct sdk.

No business changes.

Support replacement.

---

Tests

missing key

timeout

retry

switch provider

---

Acceptance

set key

call provider

change provider

restart

still works

Stop.
