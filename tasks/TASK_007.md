# TASK 007

Goal

Generate Assets.

Integrate image providers.

No diffusion implementation.

---

Provider

ComfyUI

InstantID

Optional:

StoryDiffusion

---

Create

ImageAgent

ImageProvider

CharacterRenderer

AssetSelector

---

Input

scene

character

props

---

Generate

character image

prop image

scene image

cover image

---

Workflow

prompt

↓

generate

↓

review

↓

select

↓

lock

---

Storage

MinIO

metadata

---

Features

batch generate

regenerate

compare

favorite

---

API

POST /generate/images

GET /assets

POST /assets/select

---

Output

images

asset refs

---

Tests

batch

retry

storage

---

Acceptance

generate images

manual selection

reuse assets

Stop.
