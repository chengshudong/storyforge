# TASK 005

Goal

Generate storyboard.

Convert episodes into scenes.

Integrate only.

---

Provider

LangGraph

Optional:

MovieAgent

---

Create

SceneAgent

StoryboardEngine

SceneRepository

---

Input

episode

summary

character list

---

Generate

scene list

camera

dialogue

emotion

duration

location

props

transition

---

Scene Format

scene_no

camera

duration

dialogue

character

emotion

asset_refs

---

Workflow

episode

↓

split

↓

storyboard

↓

validate

↓

save

---

Storage

scene json

scene metadata

---

Features

regenerate scene

edit scene

lock scene

resume

---

API

POST /episodes/{id}/scenes

GET /scenes

PATCH /scenes/{id}

---

Output

scene json

preview json

---

Tests

multi scenes

long story

retry

---

Acceptance

generate storyboard

edit storyboard

persist

Stop.
