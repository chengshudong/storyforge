# TASK 002

Goal

Build data layer.

No AI.

No provider.

---

Database

Use:

SQLAlchemy

Alembic

---

Create Tables

projects

episodes

scenes

characters

props

assets

voices

videos

jobs

logs

---

Repositories

Create:

ProjectRepository

EpisodeRepository

SceneRepository

CharacterRepository

AssetRepository

VoiceRepository

VideoRepository

JobRepository

Rules:

CRUD only

---

Create Models

Project

Episode

Scene

Character

Asset

Voice

Video

Job

---

Workflow State

backend/workflows/state.py

Create:

ProjectState

Fields:

project

episodes

scenes

characters

assets

videos

---

Queue

Create:

create_job()

cancel()

retry()

progress()

---

API

POST /projects

GET /projects

GET /jobs

---

Output

ER diagram

migration

README

OpenAPI

---

Acceptance

project saved

job works

state persisted

Stop.
