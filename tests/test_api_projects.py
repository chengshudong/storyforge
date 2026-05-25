import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from main import create_app
from infra.database import Base, get_db


@pytest.fixture
def app():
    return create_app()


@pytest.fixture
async def db_session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


@pytest.fixture
def client(app, db_session):
    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


def test_create_project(client):
    response = client.post("/api/v1/projects", json={
        "name": "Test Project",
        "description": "A test project",
        "source_file": "test.txt",
        "source_format": "txt",
    })
    assert response.status_code == 201
    data = response.json()
    assert data["name"] == "Test Project"
    assert data["status"] == "pending"
    assert "id" in data


def test_get_projects(client):
    # Create first
    client.post("/api/v1/projects", json={"name": "Project A"})
    client.post("/api/v1/projects", json={"name": "Project B"})

    response = client.get("/api/v1/projects")
    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_get_project_not_found(client):
    response = client.get(f"/api/v1/projects/{uuid.uuid4()}")
    assert response.status_code == 404
    data = response.json()
    assert "message" in data


def test_get_jobs(client):
    response = client.get("/api/v1/jobs")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_root_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
