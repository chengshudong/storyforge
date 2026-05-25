# Engineering Rules

Version 1.0

Mandatory.

---

## Architecture

Clean Architecture.

Layers:

api

service

repository

domain

infra

No circular imports.

---

## Backend

Framework:

FastAPI

Validation:

Pydantic

ORM:

SQLAlchemy

Migration:

Alembic

---

## Frontend

Framework:

Next.js

Language:

TypeScript

State:

zustand

Fetch:

react-query

UI:

shadcn

---

## Agent Rules

Every agent isolated.

No shared mutable state.

No direct provider calls.

Providers only through interfaces.

---

## Repository Rules

No SQL in services.

Repositories only.

Transactions mandatory.

---

## File Rules

Single file:

<500 lines

Single function:

<60 lines

---

## Config

.env only

No hardcoded credentials.

---

## Logging

JSON

Include:

request_id

project_id

job_id

---

## Queue

Celery only.

Support:

retry

cancel

timeout

---

## API

REST

/api/v1

Error format:

{
 "code":"",
 "message":"",
 "data":{}
}

---

## Prompt Rules

All prompts:

backend/prompts/

No inline prompt.

---

## Testing

pytest

Coverage:

80+

Integration tests required.

---

## Docker

Single command:

docker compose up

---

## Git

feature/*

bugfix/*

---

## AI Rules

Never generate duplicate code.

Never recreate models.

Always generate README.

Always generate migration.

Always explain architecture.
