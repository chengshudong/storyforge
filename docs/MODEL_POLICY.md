# Model Policy

Version 1.0

---

## Purpose

Define how the system accesses AI models.

Centralize all model access through the Model Gateway.

No direct SDK calls.

No hardcoded models.

No hardcoded API keys.

---

## 1. Provider Strategy

### Supported Providers

| Provider | Priority | Protocol | Auth | Health Check |
|----------|----------|----------|------|-------------|
| DeepSeek | 1 (primary) | OpenAI-compatible REST | `DEEPSEEK_API_KEY` | `GET /v1/models` |
| OpenAI | 2 (fallback) | OpenAI REST | `OPENAI_API_KEY` | `GET /v1/models` |
| Anthropic | 3 | Anthropic REST | `ANTHROPIC_API_KEY` | `GET /v1/messages` |
| Gemini | 4 | Gemini REST | `GEMINI_API_KEY` | `GET /v1/models` |
| OpenRouter | 5 (routing) | OpenAI-compatible REST | `OPENROUTER_API_KEY` | `GET /v1/models` |
| Local | 6 (offline) | Local HTTP / gRPC | None | Configurable |

### Fallback Chain

```
DeepSeek
  ↓ (fail / timeout / rate-limit)
OpenAI
  ↓ (fail)
Anthropic
  ↓ (fail)
Gemini
  ↓ (fail)
OpenRouter
  ↓ (fail)
Local
  ↓ (fail)
Error → return to caller
```

### Provider Health

Every provider adapter must implement `health()`.

Health check interval: 30 seconds.

Unhealthy provider: skip in fallback chain for 60 seconds, then retry.

---

## 2. Model Registry

### Registry File

`backend/config/models.yaml`

### Task → Default Model Mapping

| Task | Default Provider | Default Model | Purpose |
|------|-----------------|---------------|---------|
| summary | DeepSeek | `deepseek-chat` | Novel summary generation |
| episode | DeepSeek | `deepseek-chat` | Episode breakdown |
| scene | DeepSeek | `deepseek-chat` | Scene script generation |
| character | DeepSeek | `deepseek-chat` | Character profile extraction |
| dialogue | DeepSeek | `deepseek-chat` | Dialogue generation |
| narration | DeepSeek | `deepseek-chat` | Narration text |
| embedding | (local) | `all-MiniLM-L6-v2` | Text embedding (384-dim) |
| rerank | (local) | `bge-reranker-base` | Result reranking |

### Model Registry Format

```yaml
providers:
  deepseek:
    api_key_env: DEEPSEEK_API_KEY
    base_url_env: DEEPSEEK_BASE_URL
    default_base_url: https://api.deepseek.com
    models:
      - deepseek-chat
      - deepseek-reasoner
  openai:
    api_key_env: OPENAI_API_KEY
    base_url_env: OPENAI_BASE_URL
    default_base_url: https://api.openai.com
    models:
      - gpt-4o
      - gpt-4o-mini
  # ... (per provider)

tasks:
  summary:
    provider: deepseek
    model: deepseek-chat
  episode:
    provider: deepseek
    model: deepseek-chat
  scene:
    provider: deepseek
    model: deepseek-chat
  character:
    provider: deepseek
    model: deepseek-chat
  embedding:
    provider: local
    model: all-MiniLM-L6-v2
```

---

## 3. Timeout Policy

### Defaults

| Parameter | Default | Max |
|-----------|---------|-----|
| `connect_timeout` | 10s | 30s |
| `read_timeout` | 60s | 300s |
| `total_timeout` | 120s | 600s |

### Per-Task Overrides

| Task | `read_timeout` | Reason |
|------|---------------|--------|
| summary | 120s | Long context input |
| episode | 90s | Multi-chapter processing |
| scene | 60s | Medium output |
| character | 60s | Entity extraction |
| embedding | 30s | Small input chunks |

### Behavior

Timeout triggers fallback to next provider.

No timeout reaches caller — always fallback first.

---

## 4. Retry Policy

### Defaults

| Parameter | Value |
|-----------|-------|
| `max_retries` | 3 |
| `backoff_initial` | 1s |
| `backoff_multiplier` | 2x |
| `backoff_max` | 30s |

### Backoff Formula

```
delay = min(backoff_initial * (multiplier ^ attempt), backoff_max)
       + random_jitter(0, delay * 0.1)

attempt 0: 0s
attempt 1: 1s + jitter
attempt 2: 2s + jitter
attempt 3: 4s + jitter
```

### Non-Retryable Errors

Do NOT retry on:

- `401` — Invalid API key
- `403` — Access denied / billing
- `404` — Model not found
- `413` — Request too large (permanent)
- `422` — Invalid request format

Only retry on:

- `429` — Rate limit
- `500`, `502`, `503`, `504` — Server errors
- Network timeout / connection reset

### Per-Provider Overrides

| Provider | `max_retries` | `backoff_max` |
|----------|--------------|---------------|
| DeepSeek | 3 | 30s |
| OpenAI | 3 | 30s |
| Anthropic | 2 | 20s |
| Gemini | 3 | 30s |
| OpenRouter | 2 | 20s |
| Local | 1 | 5s |

---

## 5. Cache Policy

### Default TTL

| Entity | TTL | Reason |
|--------|-----|--------|
| embedding | permanent | Deterministic per model |
| summary | 24h | Project-scoped, expensive |
| episode plan | 24h | Derived from summary |
| character profile | 24h | Extracted once |
| scene script | 1h | May be regenerated |
| model list | 1h | Infrequent changes |
| health status | 30s | Transient |

### Cache Key Format

```
cache:model:{task}:{project_id}:{content_hash}

Example:
cache:model:summary:proj-abc123:md5(input_text)
cache:model:embedding:md5(chunk_text)
```

### Cache Backend

Redis (same instance as Celery broker).

DB index: `2` (dedicated, separate from Celery).

### Cache Bypass

Set header `X-Bypass-Cache: true` to skip cache.

Used for:
- Regeneration requests
- Debugging
- Provider testing

---

## 6. Cost Policy

### Log Format (JSON)

```json
{
  "request_id": "uuid",
  "project_id": "uuid",
  "provider": "deepseek",
  "model": "deepseek-chat",
  "task": "summary",
  "tokens_input": 4500,
  "tokens_output": 800,
  "cost_usd": 0.0023,
  "duration_ms": 3200,
  "cached": false,
  "retry_count": 0,
  "status": "success"
}
```

### Log Destination

`logs/cost/{YYYY-MM-DD}.jsonl`

Rotated daily.

### Rate Tracking

Per-provider per-minute token counter in Redis.

Alert threshold: 80% of tier limit.

### Required Fields

Every model call MUST log:

- `request_id`
- `project_id` (if available)
- `provider`
- `model`
- `task`
- `tokens_input`
- `tokens_output`
- `duration_ms`
- `status`

---

## 7. Secret Policy

### Storage

Secrets ONLY in `.env` file.

`.env` is `.gitignore`d.

`.env.example` contains placeholder values only — never real keys.

### Environment Variable Names

| Secret | Variable |
|--------|----------|
| OpenAI API Key | `OPENAI_API_KEY` |
| OpenAI Base URL | `OPENAI_BASE_URL` |
| DeepSeek API Key | `DEEPSEEK_API_KEY` |
| DeepSeek Base URL | `DEEPSEEK_BASE_URL` |
| Gemini API Key | `GEMINI_API_KEY` |
| Anthropic API Key | `ANTHROPIC_API_KEY` |
| OpenRouter API Key | `OPENROUTER_API_KEY` |

### Rules

**Forbidden:**

- Hardcoded keys in source code
- Keys in config files (yaml, json, toml)
- Keys in migration files
- Full keys in logs
- Keys in error messages
- Keys in API responses

**Required:**

- `SecretLoader.load()` reads from `.env` only
- `SecretLoader.validate()` checks non-empty on startup
- `SecretLoader.mask()` masks all but last 4 characters for logging
  - Example: `sk-...xyz1234` → `sk-****234`

### Startup Validation

On app startup, validate:

1. At least ONE provider has a valid API key
2. Key format matches expected pattern (e.g., `sk-` prefix for OpenAI)
3. No placeholder values (block `change-me`, `your-key-here`)

Fail fast on invalid config — do not start with bad secrets.

---

## 8. Router Policy

### `ModelRouter.select(task, provider_override?)`

1. Look up task in model registry → get default provider + model
2. If `provider_override` is set, use that provider instead
3. Filter out unhealthy providers (last health check failed)
4. Return `(provider, model)` tuple

### `ModelRouter.fallback(task, failed_provider)`

1. Get fallback chain for task
2. Skip `failed_provider` and any unhealthy providers
3. Return next `(provider, model)` or raise `AllProvidersExhausted`

### `ModelRouter.degrade(task)`

When all cloud providers fail, degrade to:

| Task | Degraded Model |
|------|---------------|
| summary | Local model |
| episode | Skip (manual) |
| scene | Local model |
| character | Regex extraction |
| embedding | Local sentence-transformers |

Degradation is logged at WARNING level with project_id.

### Routing State

Per-request routing state stored in call context (not global):

```python
@dataclass
class RouteState:
    task: str
    attempts: list[dict]  # [{provider, model, error, duration_ms}]
    current_provider: str
    current_model: str
    degraded: bool
```

---

## 9. Health Policy

### Endpoint

`GET /api/v1/models/health`

### Response

```json
{
  "status": "ok",
  "providers": {
    "deepseek": {"status": "healthy", "latency_ms": 120},
    "openai": {"status": "healthy", "latency_ms": 340},
    "anthropic": {"status": "unconfigured"},
    "gemini": {"status": "unhealthy", "error": "timeout"},
    "openrouter": {"status": "unconfigured"},
    "local": {"status": "healthy", "latency_ms": 5}
  },
  "degraded": false
}
```

### Health States

| State | Meaning | Action |
|-------|---------|--------|
| `healthy` | Provider responding | Can route |
| `unhealthy` | Last check failed | Skip in fallback, retry in 60s |
| `unconfigured` | No API key set | Skip always |
| `rate_limited` | 429 received | Skip for 30s |

### Health Check Implementation

Each adapter's `health()` method:

1. Send minimal request (e.g., list models with limit=1)
2. Timeout: 5s
3. Success: mark healthy, record latency
4. Failure: mark unhealthy, record error

Background health checker runs every 30 seconds.

### Failure Handling

When a provider is unhealthy:

1. Log at WARNING level
2. Route to next fallback
3. Do NOT return error to caller unless ALL providers unhealthy
4. If all providers unhealthy → return 503 with `{"code": "ALL_PROVIDERS_DOWN"}`

---

## 10. Testing Policy

### Unit Tests (Mock)

Test with mock HTTP transport — no real API calls.

| Test | What it verifies |
|------|-----------------|
| `test_missing_key` | Adapter raises clear error when env var empty |
| `test_timeout` | Adapter respects timeout, triggers fallback |
| `test_retry_count` | Retry fires correct number of times |
| `test_non_retryable_error` | 401/403/404 do not retry |
| `test_retryable_error` | 429/500/502 do retry |
| `test_fallback_chain` | Router walks fallback order correctly |
| `test_degrade` | Router degrades when all providers down |
| `test_cache_hit` | Cached response returns without API call |
| `test_cache_bypass` | Header bypasses cache |
| `test_secret_mask` | Masked key only shows last 4 chars |
| `test_secret_validation` | Startup fails on placeholder key |
| `test_health_check` | health() returns correct status |
| `test_cost_logging` | Cost log contains all required fields |

### Integration Tests (Real API)

Requires valid API keys in `.env`.

| Test | What it verifies |
|------|-----------------|
| `test_generate_real` | Real generation returns text |
| `test_stream_real` | Streaming returns chunks |
| `test_embedding_real` | Embedding returns correct dimensions |
| `test_provider_switch` | Change `LLM_PROVIDER` → restart → still works |

### Provider Switch Test

```bash
# Set DeepSeek
LLM_PROVIDER=deepseek DEEPSEEK_API_KEY=sk-xxx python -m pytest tests/test_provider_switch.py

# Switch to OpenAI
LLM_PROVIDER=openai OPENAI_API_KEY=sk-yyy python -m pytest tests/test_provider_switch.py

# Both must pass with identical test assertions.
```

### Test Requirements

- All mock tests must pass without network access
- Integration tests are skipped when API key is not set (`@pytest.mark.skipif`)
- Provider switch test uses same input, same assertions across providers
- Cost log tests verify JSONL output format
- Cache tests use isolated Redis DB index (15)
