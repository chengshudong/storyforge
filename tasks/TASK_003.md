# TASK 003

Goal

Novel Parsing.

Integrate.

Do not recreate.

---

Provider

Unstructured

LlamaIndex

Qdrant

---

Create

NovelAgent

NovelParser

ContextStore

---

Input

TXT

DOCX

EPUB

---

Flow

upload

↓

parse

↓

split

↓

embedding

↓

store

---

Output

chapters

summary_stub

entities_stub

---

Storage

raw

parsed

vector

---

API

POST /novels/upload

GET /novels

GET /novels/{id}

---

Generate

progress

retry

resume

---

Tests

large file

resume

---

Acceptance

upload novel

parse

store vectors

query vectors

Stop.
