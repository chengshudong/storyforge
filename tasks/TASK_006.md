# TASK 006

Goal

Build Character System.

Character consistency.

Integrate only.

---

Provider

GraphRAG

spaCy

Optional:

Mem0

---

Create

CharacterAgent

CharacterMemory

CharacterProfile

CharacterLocker

---

Input

chapters

episodes

scenes

---

Generate

appearance

voice

personality

emotion

age

costume

relationship

---

Storage

character table

memory store

vector store

---

Workflow

extract

↓

merge

↓

normalize

↓

approve

↓

lock

---

Features

approve

version

rollback

reuse

---

API

POST /characters/generate

POST /characters/select

GET /characters

PATCH /characters/{id}

---

Output

character profile

character json

---

Tests

duplicate merge

consistency

long novel

---

Acceptance

consistent profile

editable

persist

Stop.
