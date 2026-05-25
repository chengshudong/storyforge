import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from domain.models import (
    Project,
    Episode,
    Scene,
    Character,
    Asset,
    Voice,
    Video,
    Job,
    ProjectStatus,
    JobStatus,
    AssetType,
)
from infra.database import Base
from repository.project_repository import ProjectRepository
from repository.episode_repository import EpisodeRepository
from repository.scene_repository import SceneRepository
from repository.character_repository import CharacterRepository
from repository.asset_repository import AssetRepository
from repository.voice_repository import VoiceRepository
from repository.video_repository import VideoRepository
from repository.job_repository import JobRepository


@pytest.fixture
async def session():
    engine = create_async_engine("sqlite+aiosqlite://", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with factory() as s:
        yield s
    await engine.dispose()


async def test_project_repository_crud(session: AsyncSession):
    repo = ProjectRepository(session)
    project = Project(name="Test Project", status=ProjectStatus.PENDING)
    created = await repo.create(project)
    assert created.id is not None
    assert created.name == "Test Project"

    fetched = await repo.get(created.id)
    assert fetched is not None
    assert fetched.name == "Test Project"

    fetched.name = "Updated"
    await repo.update(fetched)
    updated = await repo.get(created.id)
    assert updated.name == "Updated"

    deleted = await repo.delete(created.id)
    assert deleted is True
    assert await repo.get(created.id) is None


async def test_project_repository_list(session: AsyncSession):
    repo = ProjectRepository(session)
    for i in range(3):
        p = Project(name=f"Project {i}", status=ProjectStatus.PENDING)
        await repo.create(p)

    result = await repo.list(offset=0, limit=10)
    assert len(result) == 3

    result = await repo.list(offset=0, limit=2)
    assert len(result) == 2

    total = await repo.count()
    assert total == 3


async def test_project_repository_by_status(session: AsyncSession):
    repo = ProjectRepository(session)
    await repo.create(Project(name="P1", status=ProjectStatus.PENDING))
    await repo.create(Project(name="P2", status=ProjectStatus.COMPLETED))

    pending = await repo.list_by_status(ProjectStatus.PENDING)
    assert len(pending) == 1
    assert pending[0].name == "P1"


async def test_episode_repository(session: AsyncSession):
    project = Project(name="P", status=ProjectStatus.PENDING)
    session.add(project)
    await session.flush()

    repo = EpisodeRepository(session)
    ep = Episode(project_id=project.id, episode_number=1, title="Episode 1")
    await repo.create(ep)

    episodes = await repo.list_by_project(project.id)
    assert len(episodes) == 1

    by_num = await repo.get_by_number(project.id, 1)
    assert by_num is not None


async def test_scene_repository(session: AsyncSession):
    project = Project(name="P", status=ProjectStatus.PENDING)
    session.add(project)
    await session.flush()
    episode = Episode(project_id=project.id, episode_number=1, title="E1")
    session.add(episode)
    await session.flush()

    repo = SceneRepository(session)
    scene = Scene(episode_id=episode.id, scene_number=1, title="Scene 1")
    await repo.create(scene)

    scenes = await repo.list_by_episode(episode.id)
    assert len(scenes) == 1


async def test_character_repository(session: AsyncSession):
    project = Project(name="P", status=ProjectStatus.PENDING)
    session.add(project)
    await session.flush()

    repo = CharacterRepository(session)
    char = Character(project_id=project.id, name="Hero", role="protagonist")
    await repo.create(char)

    chars = await repo.list_by_project(project.id)
    assert len(chars) == 1

    by_name = await repo.get_by_name(project.id, "Hero")
    assert by_name is not None


async def test_asset_repository(session: AsyncSession):
    project = Project(name="P", status=ProjectStatus.PENDING)
    session.add(project)
    await session.flush()

    repo = AssetRepository(session)
    asset = Asset(
        project_id=project.id,
        asset_type=AssetType.IMAGE,
        file_path="s3://test/image.png",
    )
    await repo.create(asset)

    assets = await repo.list_by_project(project.id)
    assert len(assets) == 1

    by_type = await repo.list_by_type(project.id, AssetType.IMAGE)
    assert len(by_type) == 1


async def test_voice_repository(session: AsyncSession):
    project = Project(name="P", status=ProjectStatus.PENDING)
    session.add(project)
    await session.flush()
    character = Character(project_id=project.id, name="Hero")
    session.add(character)
    await session.flush()

    repo = VoiceRepository(session)
    voice = Voice(
        project_id=project.id,
        character_id=character.id,
        file_path="s3://voices/test.wav",
    )
    await repo.create(voice)

    voices = await repo.list_by_project(project.id)
    assert len(voices) == 1


async def test_video_repository(session: AsyncSession):
    project = Project(name="P", status=ProjectStatus.PENDING)
    session.add(project)
    await session.flush()
    episode = Episode(project_id=project.id, episode_number=1, title="E1")
    session.add(episode)
    await session.flush()
    scene = Scene(episode_id=episode.id, scene_number=1, title="S1")
    session.add(scene)
    await session.flush()

    repo = VideoRepository(session)
    video = Video(scene_id=scene.id, file_path="s3://videos/test.mp4")
    await repo.create(video)

    videos = await repo.list_by_scene(scene.id)
    assert len(videos) == 1


async def test_job_repository(session: AsyncSession):
    project = Project(name="P", status=ProjectStatus.PENDING)
    session.add(project)
    await session.flush()

    repo = JobRepository(session)
    job = Job(project_id=project.id, job_type="test", status=JobStatus.PENDING)
    await repo.create(job)

    jobs = await repo.list_by_project(project.id)
    assert len(jobs) == 1

    await repo.update_status(job.id, JobStatus.RUNNING)
    updated = await repo.get(job.id)
    assert updated.status == JobStatus.RUNNING

    await repo.update_progress(job.id, 50)
    updated = await repo.get(job.id)
    assert updated.progress == 50

    log = await repo.add_log(job.id, "INFO", "test message")
    assert log.message == "test message"

    logs = await repo.get_logs(job.id)
    assert len(logs) == 1
