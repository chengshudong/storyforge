# Startup Guide

## Prerequisites

- Docker Engine 24+
- Docker Compose v2+
- 8GB+ RAM available

## Quick Start

### 1. Clone and configure

```bash
cd csdmoble2
cp .env.example .env
```

### 2. Start all services

```bash
docker compose up
```

### 3. Verify

Open in browser:

| Service     | URL                            |
|-------------|--------------------------------|
| Frontend    | http://localhost:3000          |
| API Docs    | http://localhost:8000/docs     |
| Health      | http://localhost:8000/health   |
| MinIO       | http://localhost:9001          |

### 4. Health Check

```bash
curl http://localhost:8000/health
# {"status":"ok"}

curl http://localhost:8000/api/v1/health
# {"status":"ok"}
```

### 5. Stop

```bash
docker compose down
```

To remove all data volumes:

```bash
docker compose down -v
```

## Local Development

### Backend

```bash
cd backend
pip install -r requirements.txt

# Ensure postgres/redis/minio are running (via docker compose up -d postgres redis minio)
uvicorn main:app --reload --port 8000

# Run migrations
alembic upgrade head
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

### Run Tests

```bash
pip install pytest pytest-asyncio httpx
pytest tests/ -v
```

## Troubleshooting

- **Port conflicts**: Ensure ports 3000, 8000, 5432, 6379, 9000, 9001, 6333 are free
- **Postgres connection refused**: Wait for healthcheck to pass (may take ~30s first time)
- **MinIO bucket**: Created automatically on first API call
- **Celery worker**: Ensure Redis is healthy before worker starts
