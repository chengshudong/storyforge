# Novel2Drama Agent

Version: 1.0

---

## Vision

Build an AI Agent platform that converts novels into serialized short-form drama videos.

The platform orchestrates existing open-source capabilities.

The system itself does not train models.

The system coordinates generation.

---

## Inputs

Supported:

TXT
DOCX
EPUB

Optional:

PDF

---

## Outputs

Story Summary

Episode Plan

Storyboard

Character Profiles

Character Images

Character Voices

Video Clips

Final MP4

---

## Product Flow

Novel

↓

Parse

↓

Story Summary

↓

Episodes

↓

Scenes

↓

Characters

↓

Assets

↓

Voice

↓

Video

↓

Editing

↓

Export

---

## Architecture

Frontend

Next.js

Backend

FastAPI

Agent

LangGraph

Database

Postgres

Cache

Redis

Vector Database

Qdrant

Object Storage

MinIO

Task Queue

Celery

Deployment

Docker

---

## Principles

Agent Driven

Provider Independent

Async Execution

Human Review

Resumable Workflow

Stateless Services

---

## Agent List

NovelAgent

StoryAgent

EpisodeAgent

SceneAgent

CharacterAgent

ImageAgent

VoiceAgent

VideoAgent

ExportAgent

---

## System Responsibilities

System coordinates.

Providers generate.

---

## Workflow Rules

All workflows:

checkpoint enabled

retry enabled

cancel enabled

resume enabled

---

## Data Ownership

Everything belongs to project.

Projects own:

episodes

scenes

characters

assets

videos

---

## APIs

POST /projects

POST /generate

GET /projects

GET /jobs

POST /export

---

## Deliverables

Code

Docker

Database

Tests

OpenAPI

Deployment Guide

README

Architecture Diagram

---

## Phases

Phase 1

Infrastructure

Phase 2

Data

Phase 3

Novel

Phase 4

Story

Phase 5

Character

Phase 6

Image

Phase 7

Voice

Phase 8

Video

Phase 9

Editing

Phase 10

Production

---

## Success Criteria

Upload novel.

Generate drama.

Export video.

Run locally.

Deploy in cloud.
