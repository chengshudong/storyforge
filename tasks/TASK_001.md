# TASK 001

Goal

Initialize project.

Build infrastructure only.

No business logic.

---

Generate

backend/

frontend/

infra/

tests/

docs/

---

Backend

FastAPI

Create:

health endpoint

config

logging

exception handler

middleware

swagger

---

Frontend

Next.js

Create:

home

dashboard

upload

routing

tailwind

---

Database

Postgres

Create:

connection

migration

health

---

Cache

Redis

Create:

client

health

---

Storage

MinIO

Create:

upload

download

health

---

Queue

Celery

single worker

---

Docker

docker compose

multi service

---

Output

README

startup guide

env example

architecture diagram

---

Acceptance

docker compose up

open:

localhost:3000

localhost:8000/docs

GET /health

return:

{
 "status":"ok"
}

Stop.
